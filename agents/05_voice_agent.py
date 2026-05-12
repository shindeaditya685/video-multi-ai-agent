"""
Voice Agent

Generates narration with either Microsoft Edge neural voices or gTTS.
Edge remains the best free no-key option here; Indian Edge voices greatly
improve pronunciation for Indian names compared with the old US default.
"""

from __future__ import annotations

import asyncio
import os
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
    spoken_text = apply_pronunciation_map(text, pronunciation_map)
    if provider == "gtts":
        _gtts_scene(spoken_text, output_path, voice_name)
    else:
        asyncio.run(_edge_tts_scene(spoken_text, output_path, voice_name, rate, pitch))
    return output_path


async def _generate_all(state: PipelineState, job_dir: Path):
    provider = (state.voice_provider or VOICE_PROVIDER).lower()
    voice = state.voice_name or VOICE_NAME
    rate = state.voice_rate or VOICE_RATE
    pitch = state.voice_pitch or VOICE_PITCH

    tasks = []
    for scene in state.scenes:
        audio_path = job_dir / f"voice_{scene.number:02d}.mp3"
        scene.audio_path = audio_path
        narration = apply_pronunciation_map(scene.narration, state.pronunciation_map)
        if provider == "gtts":
            tasks.append(asyncio.to_thread(_gtts_scene, narration, audio_path, voice))
        else:
            tasks.append(_edge_tts_scene(narration, audio_path, voice, rate, pitch))

    await asyncio.gather(*tasks)


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
        raise RuntimeError(f"ffmpeg merge failed:\n{result.stderr[-500:]}")

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
