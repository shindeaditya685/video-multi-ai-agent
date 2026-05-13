"""
Voice Agent

Generates narration with either Microsoft Edge neural voices or gTTS.
Edge remains the best free no-key option here; Indian Edge voices greatly
improve pronunciation for Indian names compared with the old US default.
"""

from __future__ import annotations

import asyncio
import os
import re
import subprocess
from pathlib import Path

from core.config import PipelineState, TEMP_DIR, VOICE_NAME, VOICE_PITCH, VOICE_PROVIDER, VOICE_RATE

FFMPEG_BIN = r"C:\ffmpeg\bin\ffmpeg.exe" if Path(r"C:\ffmpeg\bin\ffmpeg.exe").exists() else "ffmpeg"
FFPROBE_BIN = r"C:\ffmpeg\bin\ffprobe.exe" if Path(r"C:\ffmpeg\bin\ffprobe.exe").exists() else "ffprobe"

if FFMPEG_BIN != "ffmpeg":
    os.environ["IMAGEIO_FFMPEG_EXE"] = FFMPEG_BIN
    os.environ["PATH"] = str(Path(FFMPEG_BIN).parent) + os.pathsep + os.environ["PATH"]

from pydub import AudioSegment

AudioSegment.converter = FFMPEG_BIN
AudioSegment.ffmpeg = FFMPEG_BIN
AudioSegment.ffprobe = FFPROBE_BIN

GTTS_VOICES = {
    "gtts-en-in": ("en", "co.in"),
    "gtts-hi-in": ("hi", "co.in"),
    "gtts-mr-in": ("mr", "co.in"),
    "gtts-en-us": ("en", "com"),
    "gtts-en-uk": ("en", "co.uk"),
}

VOICE_EMOTION_ENABLED = os.getenv("VOICE_EMOTION_ENABLED", "true").lower() not in ("0", "false", "no")

MOOD_PROFILES = {
    "suspense": {"rate": -7, "pitch": -6, "pause_ms": 420},
    "somber": {"rate": -10, "pitch": -8, "pause_ms": 520},
    "urgent": {"rate": 7, "pitch": 4, "pause_ms": 220},
    "investigative": {"rate": 1, "pitch": -2, "pause_ms": 300},
    "reflective": {"rate": -5, "pitch": -4, "pause_ms": 380},
    "neutral": {"rate": 0, "pitch": 0, "pause_ms": 280},
}

MOOD_KEYWORDS = {
    "urgent": [
        "suddenly", "rush", "panic", "breaking", "attack", "escape", "urgent",
        "अचानक", "घाई", "हल्ला", "भाग", "तत्काळ",
    ],
    "somber": [
        "grief", "mourning", "loss", "funeral", "tears", "silence", "family",
        "दुख", "आंसू", "कुटुंब", "शोक", "मृत्यू", "वेदना",
    ],
    "suspense": [
        "mystery", "unknown", "question", "dark", "shadow", "secret", "night",
        "रहस्य", "सवाल", "प्रश्न", "अंधार", "गुपित", "रात्री",
    ],
    "investigative": [
        "police", "court", "evidence", "investigation", "timeline", "witness",
        "पोलिस", "न्यायालय", "पुरावा", "तपास", "साक्षीदार",
    ],
}


def apply_pronunciation_map(text: str, pronunciation_map: str = "") -> str:
    result = text
    for raw_line in (pronunciation_map or "").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, value = line.split("=", 1)
        elif ":" in line:
            key, value = line.split(":", 1)
        else:
            continue
        key = key.strip()
        value = value.strip()
        if key and value:
            result = result.replace(key, value)
    return result


def _parse_percent(value: str) -> int:
    match = re.search(r"([+-]?\d+)", value or "0")
    return int(match.group(1)) if match else 0


def _parse_hz(value: str) -> int:
    match = re.search(r"([+-]?\d+)", value or "0")
    return int(match.group(1)) if match else 0


def _format_percent(value: int) -> str:
    value = max(-35, min(35, int(value)))
    return f"{value:+d}%"


def _format_hz(value: int) -> str:
    value = max(-40, min(40, int(value)))
    return f"{value:+d}Hz"


def _infer_mood(text: str, visual_desc: str = "") -> str:
    combined = f"{text} {visual_desc}".lower()
    scores = {mood: 0 for mood in MOOD_PROFILES}
    for mood, keywords in MOOD_KEYWORDS.items():
        scores[mood] += sum(1 for keyword in keywords if keyword.lower() in combined)

    if "?" in text or "?" in visual_desc:
        scores["suspense"] += 1
    if any(mark in text for mark in ("!", "।")) and len(text.split()) <= 12:
        scores["urgent"] += 1
    if not any(scores.values()):
        return "reflective" if len(text.split()) > 20 else "neutral"
    return max(scores, key=scores.get)


def _scene_voice_settings(scene, base_rate: str, base_pitch: str) -> tuple[str, str, str, int]:
    mood = _infer_mood(scene.narration, getattr(scene, "visual_desc", ""))
    if not VOICE_EMOTION_ENABLED:
        return mood, base_rate, base_pitch, MOOD_PROFILES["neutral"]["pause_ms"]

    profile = MOOD_PROFILES.get(mood, MOOD_PROFILES["neutral"])
    rate = _format_percent(_parse_percent(base_rate) + int(profile["rate"]))
    pitch = _format_hz(_parse_hz(base_pitch) + int(profile["pitch"]))
    return mood, rate, pitch, int(profile["pause_ms"])


def _prepare_spoken_text(text: str) -> str:
    spoken = re.sub(r"\s+", " ", text or "").strip()
    if spoken and spoken[-1] not in ".?!।":
        spoken += "."
    return spoken


def _polish_scene_audio(audio_path: Path, pause_ms: int):
    audio = AudioSegment.from_file(str(audio_path))
    audio = audio.fade_in(25).fade_out(min(120, max(40, pause_ms // 3)))
    if pause_ms > 0:
        audio += AudioSegment.silent(duration=pause_ms)
    audio.export(str(audio_path), format="mp3", bitrate="128k")


async def _edge_tts_scene(text: str, out_path: Path, voice: str, rate: str, pitch: str):
    import edge_tts

    communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
    await communicate.save(str(out_path))


def _gtts_scene(text: str, out_path: Path, voice_name: str):
    from gtts import gTTS

    lang, tld = GTTS_VOICES.get(voice_name, ("en", "co.in"))
    gTTS(text=text, lang=lang, tld=tld, slow=False).save(str(out_path))


def generate_preview_audio(
    text: str,
    output_path: Path,
    provider: str,
    voice_name: str,
    rate: str,
    pitch: str,
    pronunciation_map: str = "",
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    spoken_text = _prepare_spoken_text(apply_pronunciation_map(text, pronunciation_map))
    if provider == "gtts":
        _gtts_scene(spoken_text, output_path, voice_name)
    else:
        mood = _infer_mood(spoken_text)
        profile = MOOD_PROFILES.get(mood, MOOD_PROFILES["neutral"])
        preview_rate = _format_percent(_parse_percent(rate) + int(profile["rate"]))
        preview_pitch = _format_hz(_parse_hz(pitch) + int(profile["pitch"]))
        asyncio.run(_edge_tts_scene(spoken_text, output_path, voice_name, preview_rate, preview_pitch))
        _polish_scene_audio(output_path, int(profile["pause_ms"]))
    return output_path


async def _generate_all(state: PipelineState, job_dir: Path):
    provider = (state.voice_provider or VOICE_PROVIDER).lower()
    voice = state.voice_name or VOICE_NAME
    rate = state.voice_rate or VOICE_RATE
    pitch = state.voice_pitch or VOICE_PITCH

    tasks = []
    polish_jobs: list[tuple[Path, int, str]] = []
    for scene in state.scenes:
        audio_path = job_dir / f"voice_{scene.number:02d}.mp3"
        scene.audio_path = audio_path
        narration = _prepare_spoken_text(apply_pronunciation_map(scene.narration, state.pronunciation_map))
        mood, scene_rate, scene_pitch, pause_ms = _scene_voice_settings(scene, rate, pitch)
        polish_jobs.append((audio_path, pause_ms, mood))
        if provider == "gtts":
            tasks.append(asyncio.to_thread(_gtts_scene, narration, audio_path, voice))
        else:
            tasks.append(_edge_tts_scene(narration, audio_path, voice, scene_rate, scene_pitch))

    await asyncio.gather(*tasks)

    await asyncio.gather(
        *(asyncio.to_thread(_polish_scene_audio, path, pause_ms) for path, pause_ms, _ in polish_jobs)
    )
    mood_counts: dict[str, int] = {}
    for _, _, mood in polish_jobs:
        mood_counts[mood] = mood_counts.get(mood, 0) + 1
    if mood_counts:
        print("    Voice mood mix: " + ", ".join(f"{mood}={count}" for mood, count in sorted(mood_counts.items())))


def merge_audio(scene_paths: list[Path], output_path: Path) -> Path:
    list_file = output_path.parent / "concat_list.txt"
    with open(list_file, "w", encoding="utf-8") as f:
        for path in scene_paths:
            safe = str(path).replace("\\", "/")
            f.write(f"file '{safe}'\n")

    cmd = [
        FFMPEG_BIN,
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(list_file),
        "-c",
        "copy",
        str(output_path),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    list_file.unlink(missing_ok=True)

    if result.returncode != 0:
        print(f"    Fast audio concat failed, falling back to pydub merge: {result.stderr[-220:]}")
        combined = AudioSegment.empty()
        for path in scene_paths:
            combined += AudioSegment.from_file(str(path))
        combined.export(str(output_path), format="mp3", bitrate="128k")

    return output_path


def run(state: PipelineState) -> PipelineState:
    provider = (state.voice_provider or VOICE_PROVIDER).lower()
    voice = state.voice_name or VOICE_NAME
    print(f"\n[Agent 5/9] Voice Agent - generating narration ({provider}: {voice})...")
    state.status = "generating_voice"
    state.progress = 54

    job_dir = TEMP_DIR / state.job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    try:
        asyncio.run(_generate_all(state, job_dir))
    except RuntimeError:
        import nest_asyncio

        nest_asyncio.apply()
        loop = asyncio.get_event_loop()
        loop.run_until_complete(_generate_all(state, job_dir))

    for scene in state.scenes:
        if not scene.audio_path or not scene.audio_path.exists():
            raise RuntimeError(f"Voice generation failed for scene {scene.number}")

    merged_path = job_dir / "narration_full.mp3"
    merge_audio([s.audio_path for s in state.scenes], merged_path)
    state.voice_path = merged_path

    total_secs = sum(s.duration for s in state.scenes)
    print(f"    Voice    : {len(state.scenes)} clips generated")
    print(f"    Merged   : {merged_path.name} (~{total_secs:.0f}s total)")
    state.progress = 62
    return state
