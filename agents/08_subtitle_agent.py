"""
Subtitle Agent (Enhanced v2)

Subtitle generation strategy (in priority order):
  1. Pre-generated SRT from Video Agent (best: has correct Devanagari text
     from scene.narration with accurate audio-synced timings + intro offset)
  2. Scene-based SRT (good: uses scene.narration text, no Whisper needed)
  3. Whisper transcription (fallback: for English or when above not available;
     Hindi/Marathi Whisper often outputs Urdu script → garbled Devanagari)

Key fixes:
  - No longer uses Whisper for Hindi/Marathi (it outputs Urdu script which
    cannot be reliably converted to Devanagari with a character mapping)
  - Uses the original narration text from scenes (which IS in Devanagari)
  - Proper intro offset in SRT timings so subtitles match video timeline
  - Better FFmpeg subtitle burn with multiple fallback methods
  - Windows-safe path escaping for FFmpeg
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from core.config import PipelineState, OUTPUT_DIR, TEMP_DIR, VIDEO_FPS, WHISPER_MODEL

FFMPEG_BIN = str(Path("C:/ffmpeg/bin/ffmpeg.exe")) if Path("C:/ffmpeg/bin/ffmpeg.exe").exists() else "ffmpeg"
FFPROBE_BIN = str(Path("C:/ffmpeg/bin/ffprobe.exe")) if Path("C:/ffmpeg/bin/ffprobe.exe").exists() else "ffprobe"

# Map script_language to Whisper language codes
WHISPER_LANG_MAP = {
    "en": "en",
    "hi": "hi",
    "mr": "mr",
}

# Devanagari-capable font directories (for FFmpeg subtitle burn)
_DEVANAGARI_FONT_DIRS = [
    "/usr/share/fonts/truetype/freefont",     # Linux - FreeSans (best)
    "/usr/share/fonts/truetype/dejavu",       # Linux - DejaVu Sans
    "/usr/share/fonts/truetype/liberation",   # Linux - Liberation
]

# Devanagari-capable font names for Windows
_WINDOWS_DEVANAGARI_FONTS = {
    "Mangal": "C:/Windows/Fonts/Mangal.ttf",       # Built-in Windows Devanagari
    "Nirmala UI": "C:/Windows/Fonts/Nirmala.ttf",   # Built-in Windows Indian
}


# ── SRT helpers ────────────────────────────────────────────────────────────

def _seconds_to_srt_time(seconds: float) -> str:
    """Convert float seconds to SRT timestamp format: HH:MM:SS,mmm"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _get_audio_duration(audio_path: Path) -> float:
    """Get actual duration of an audio file."""
    try:
        from pydub import AudioSegment
        audio = AudioSegment.from_file(str(audio_path))
        return len(audio) / 1000.0
    except Exception:
        pass
    try:
        result = subprocess.run(
            [FFPROBE_BIN, "-v", "quiet", "-print_format", "json",
             "-show_format", str(audio_path)],
            capture_output=True, text=True, timeout=10,
        )
        info = json.loads(result.stdout)
        return float(info["format"]["duration"])
    except Exception:
        return 6.0


# ── Generate scene-based SRT without Whisper ───────────────────────────────

def generate_scene_srt(state: PipelineState, job_dir: Path, time_offset: float = 0.0) -> Path:
    """
    Generate an SRT file from scene narration and actual audio durations.
    
    This produces CORRECT Devanagari text because it uses scene.narration
    (the original Hindi/Marathi text from the story agent), not Whisper's
    broken Urdu-script output.
    
    Args:
        state: Pipeline state with scenes
        job_dir: Directory to write SRT file
        time_offset: Seconds to shift all timestamps forward (for intro clip)
    """
    srt_path = job_dir / "subtitles_scene.srt"
    lines = []
    t = time_offset  # Start after intro if present
    idx = 1

    for scene in state.scenes:
        # Use actual audio duration for accurate timing
        if scene.audio_path and scene.audio_path.exists():
            duration = _get_audio_duration(scene.audio_path)
        else:
            duration = scene.duration

        start = _seconds_to_srt_time(t)
        end = _seconds_to_srt_time(t + duration)
        text = scene.narration.strip()

        if text:
            lines.append(f"{idx}")
            lines.append(f"{start} --> {end}")
            lines.append(text)
            lines.append("")
            idx += 1

        t += duration

    srt_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"    Scene SRT: {idx - 1} segments generated (correct Devanagari text, no Whisper)")
    return srt_path


# ── Whisper transcription → SRT (ENGLISH ONLY or last resort) ─────────────

def transcribe_to_srt_english(video_path: Path, job_dir: Path) -> Path:
    """
    Run Whisper on the video audio for ENGLISH transcription only.
    
    For Hindi/Marathi, Whisper's base model frequently outputs Urdu (Arabic)
    script instead of Devanagari. A character-level Urdu→Devanagari mapping
    is fundamentally broken because:
      - Urdu is an abjad (vowels mostly omitted), Devanagari is an abugida
      - Urdu is RTL, Devanagari is LTR
      - Conjunct consonants, matras, nuktas don't map 1:1
    
    Therefore, we ONLY use Whisper for English. For Hindi/Marathi, we use
    the scene-based SRT which has the original Devanagari narration text.
    """
    import whisper

    print(f"    Loading Whisper model ({WHISPER_MODEL}) for English transcription...")
    model = whisper.load_model(WHISPER_MODEL)

    transcribe_kwargs = {
        "language": "en",
        "task": "transcribe",
        "word_timestamps": True,
        "verbose": False,
    }

    print(f"    Transcribing audio (language=en)...")
    result = model.transcribe(str(video_path), **transcribe_kwargs)

    srt_path = job_dir / "subtitles.srt"
    srt_lines = []
    idx = 1

    for segment in result["segments"]:
        start = _seconds_to_srt_time(segment["start"])
        end = _seconds_to_srt_time(segment["end"])
        text = segment["text"].strip()
        if text:
            srt_lines.append(f"{idx}\n{start} --> {end}\n{text}\n")
            idx += 1

    srt_path.write_text("\n".join(srt_lines), encoding="utf-8")
    print(f"    SRT: {idx - 1} subtitle segments generated (Whisper, lang=en)")
    return srt_path


# ── Burn subtitles with FFmpeg (with multiple fallback methods) ────────────

def _find_devanagari_font() -> tuple[str, str]:
    """
    Find the best Devanagari-capable font for FFmpeg subtitle rendering.
    Returns (font_name, fontsdir_or_empty).
    """
    # Try Linux font directories
    for d in _DEVANAGARI_FONT_DIRS:
        if os.path.isdir(d):
            if os.path.isfile(os.path.join(d, "FreeSans.ttf")):
                return "FreeSans", d
            if os.path.isfile(os.path.join(d, "DejaVuSans.ttf")):
                return "DejaVu Sans", d

    # Windows: try built-in Devanagari fonts
    for fname, fpath in _WINDOWS_DEVANAGARI_FONTS.items():
        if os.path.isfile(fpath):
            print(f"    Subtitle font: {fname} (dir: {os.path.dirname(fpath)})")
            return fname, os.path.dirname(fpath)

    return "FreeSans", ""


def burn_subtitles(video_path: Path, srt_path: Path, output_path: Path,
                   font_size: int = 18, quality_crf: str = "20",
                   language: str = "en") -> Path:
    """
    Burn subtitles into the video using FFmpeg with multiple fallback methods.
    
    Strategy:
    1. Try styled FFmpeg subtitles filter (with proper Devanagari font)
    2. If that fails, try ASS subtitle format (better Unicode support)
    3. If that fails, try simple subtitles filter (no custom styling)
    4. If all fail, copy video without burned subtitles
    """
    # Escape path for FFmpeg subtitle filter (Windows backslashes + colon drive letters)
    srt_str = str(srt_path).replace("\\", "/").replace(":", "\\:")

    if language in ("hi", "mr"):
        font_name, fontsdir = _find_devanagari_font()
    else:
        font_name = "Arial"
        fontsdir = ""

    # ── Method 1: Styled subtitles filter ─────────────────────────────────
    if fontsdir:
        subtitle_filter = (
            f"subtitles='{srt_str}':"
            f"fontsdir={fontsdir}:"
            "force_style='"
            f"Fontname={font_name},"
            f"Fontsize={font_size},"
            "PrimaryColour=&H00FFFFFF,"
            "OutlineColour=&H00000000,"
            "BackColour=&H80000000,"
            "BorderStyle=4,"
            "Outline=1,"
            "Shadow=0,"
            "MarginV=25,"
            "Alignment=2'"
        )
    else:
        subtitle_filter = (
            f"subtitles='{srt_str}':"
            "force_style='"
            f"Fontname={font_name},"
            f"Fontsize={font_size},"
            "PrimaryColour=&H00FFFFFF,"
            "OutlineColour=&H00000000,"
            "BackColour=&H80000000,"
            "BorderStyle=4,"
            "Outline=1,"
            "Shadow=0,"
            "MarginV=25,"
            "Alignment=2'"
        )

    cmd = [
        FFMPEG_BIN, "-y",
        "-i", str(video_path),
        "-vf", subtitle_filter,
        "-c:v", "libx264",
        "-crf", quality_crf,
        "-preset", "fast",
        "-c:a", "copy",
        "-movflags", "+faststart",
        str(output_path),
    ]

    print(f"    Using Devanagari font: {font_name}")
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")

    if result.returncode == 0 and output_path.exists() and output_path.stat().st_size > 1000:
        # Verify audio is present in output
        if _video_has_audio(output_path):
            print(f"    Subtitles burned successfully (styled, audio preserved)")
            return output_path
        else:
            print(f"    WARNING: Audio lost during subtitle burn, attempting recovery...")
            _recover_audio(video_path, output_path, output_path)
            if _video_has_audio(output_path):
                print(f"    Audio recovered successfully")
                return output_path
    else:
        print(f"    Method 1 (styled subtitles) failed: {result.stderr[-200:]}")

    # ── Method 2: Convert SRT to ASS and burn (better Unicode/Devanagari) ──
    try:
        ass_path = _srt_to_ass(srt_path, font_name, font_size, language)
        ass_str = str(ass_path).replace("\\", "/").replace(":", "\\:")
        
        cmd2 = [
            FFMPEG_BIN, "-y",
            "-i", str(video_path),
            "-vf", f"ass='{ass_str}'",
            "-c:v", "libx264",
            "-crf", quality_crf,
            "-preset", "fast",
            "-c:a", "copy",
            "-movflags", "+faststart",
            str(output_path),
        ]
        result2 = subprocess.run(cmd2, capture_output=True, text=True, encoding="utf-8", errors="replace")
        
        if result2.returncode == 0 and output_path.exists() and output_path.stat().st_size > 1000:
            if _video_has_audio(output_path):
                print(f"    Subtitles burned successfully (ASS format, audio preserved)")
                return output_path
            else:
                _recover_audio(video_path, output_path, output_path)
                if _video_has_audio(output_path):
                    print(f"    Subtitles burned (ASS format), audio recovered")
                    return output_path
        else:
            print(f"    Method 2 (ASS subtitles) failed: {result2.stderr[-200:]}")
    except Exception as e:
        print(f"    Method 2 (ASS subtitles) skipped: {e}")

    # ── Method 3: Simple subtitles filter (no custom styling) ──────────────
    simple_filter = f"subtitles='{srt_str}'"
    cmd3 = [
        FFMPEG_BIN, "-y",
        "-i", str(video_path),
        "-vf", simple_filter,
        "-c:v", "libx264",
        "-crf", quality_crf,
        "-preset", "fast",
        "-c:a", "copy",
        "-movflags", "+faststart",
        str(output_path),
    ]
    result3 = subprocess.run(cmd3, capture_output=True, text=True, encoding="utf-8", errors="replace")

    if result3.returncode == 0 and output_path.exists() and output_path.stat().st_size > 1000:
        if _video_has_audio(output_path):
            print(f"    Subtitles burned successfully (simple filter, audio preserved)")
            return output_path
        else:
            _recover_audio(video_path, output_path, output_path)
            if _video_has_audio(output_path):
                print(f"    Subtitles burned (simple filter), audio recovered")
                return output_path
    else:
        print(f"    Method 3 (simple subtitles) failed: {result3.stderr[-200:]}")

    # ── All methods failed: copy video without subtitles ───────────────────
    print(f"    All subtitle burn methods failed - copying raw video as fallback")
    shutil.copy(video_path, output_path)
    return output_path


def _video_has_audio(video_path: Path) -> bool:
    """Check if a video file has an audio stream."""
    try:
        result = subprocess.run(
            [FFPROBE_BIN, "-v", "quiet", "-select_streams", "a",
             "-show_entries", "stream=codec_type",
             "-of", "csv=p=0", str(video_path)],
            capture_output=True, text=True, timeout=10,
        )
        return "audio" in result.stdout.lower()
    except Exception:
        return True  # Assume audio exists if we can't check


def _recover_audio(source_video: Path, video_no_audio: Path, output_path: Path):
    """Recover audio from source video and combine with subtitle video."""
    try:
        cmd = [
            FFMPEG_BIN, "-y",
            "-i", str(video_no_audio),    # subtitled video (no audio)
            "-i", str(source_video),       # original video (has audio)
            "-c:v", "copy",
            "-c:a", "aac",
            "-map", "0:v:0",               # video from subtitled
            "-map", "1:a:0?",              # audio from original
            "-shortest",
            str(output_path),
        ]
        subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except Exception as e:
        print(f"    Audio recovery failed: {e}")


def _srt_to_ass(srt_path: Path, font_name: str, font_size: int, language: str) -> Path:
    """
    Convert SRT subtitle file to ASS (Advanced SubStation Alpha) format.
    ASS format has better Unicode/Devanagari support and more styling options.
    """
    ass_path = srt_path.with_suffix(".ass")
    
    # Read SRT content
    srt_content = srt_path.read_text(encoding="utf-8")
    
    # ASS header with Devanagari-capable font
    ass_header = f"""[Script Info]
Title: Subtitles
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font_name},{int(font_size * 2.5)},&H00FFFFFF,&H000000FF,&H00000000,&H80000000,0,0,0,0,100,100,0,0,4,2,0,2,10,10,30,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    
    # Parse SRT entries
    events = []
    blocks = srt_content.strip().split("\n\n")
    
    for block in blocks:
        lines = block.strip().split("\n")
        if len(lines) < 3:
            continue
        
        # Parse timestamp line (format: HH:MM:SS,mmm --> HH:MM:SS,mmm)
        timestamp_line = lines[1] if "-->" in lines[1] else (lines[0] if "-->" in lines[0] else "")
        if not timestamp_line:
            continue
        
        parts = timestamp_line.split("-->")
        if len(parts) != 2:
            continue
        
        start_time = _srt_time_to_ass(parts[0].strip())
        end_time = _srt_time_to_ass(parts[1].strip())
        
        # Text is everything after the timestamp line
        text_lines = []
        for line in lines:
            if "-->" not in line and not line.strip().isdigit():
                text_lines.append(line.strip())
        text = "\\N".join(text_lines)  # \N is ASS line break
        
        if text:
            events.append(f"Dialogue: 0,{start_time},{end_time},Default,,0,0,0,,{text}")
    
    # Write ASS file
    ass_content = ass_header + "\n".join(events) + "\n"
    ass_path.write_text(ass_content, encoding="utf-8")
    return ass_path


def _srt_time_to_ass(srt_time: str) -> str:
    """Convert SRT timestamp (HH:MM:SS,mmm) to ASS timestamp (H:MM:SS.cc)."""
    # SRT format: 00:00:05,300
    # ASS format: 0:00:05.30
    try:
        parts = srt_time.replace(",", ".").split(":")
        h = int(parts[0])
        m = int(parts[1])
        s_parts = parts[2].split(".")
        s = int(s_parts[0])
        ms = int(s_parts[1]) if len(s_parts) > 1 else 0
        # Convert milliseconds to centiseconds (2 decimal places)
        cs = ms // 10
        return f"{h}:{m:02d}:{s:02d}.{cs:02d}"
    except Exception:
        return "0:00:00.00"


# ── Fallback: subtitle via MoviePy (no Whisper, no FFmpeg) ────────────────

def add_subtitles_moviepy(state: PipelineState, output_path: Path) -> Path:
    """
    Last resort: overlay subtitles using MoviePy.
    Uses scene.narration text (correct Devanagari), not Whisper.
    """
    try:
        from moviepy.editor import VideoFileClip, TextClip, CompositeVideoClip
    except ModuleNotFoundError:
        from moviepy import VideoFileClip, TextClip, CompositeVideoClip

    fps = int(state.video_fps or VIDEO_FPS)
    font_size = int(state.subtitle_font_size or 18)

    def with_position(clip, position):
        return clip.with_position(position) if hasattr(clip, "with_position") else clip.set_position(position)

    def with_start(clip, start):
        return clip.with_start(start) if hasattr(clip, "with_start") else clip.set_start(start)

    def with_duration(clip, duration):
        return clip.with_duration(duration) if hasattr(clip, "with_duration") else clip.set_duration(duration)

    def make_text_clip(text: str, width: int):
        try:
            return TextClip(
                text=text,
                font_size=font_size,
                color="white",
                stroke_color="black",
                stroke_width=1,
                method="caption",
                size=(width, None),
                text_align="center",
            )
        except TypeError:
            return TextClip(
                text,
                fontsize=font_size,
                color="white",
                font="DejaVu-Sans",
                stroke_color="black",
                stroke_width=1,
                method="caption",
                size=(width, None),
                align="center",
            )

    video = VideoFileClip(str(state.video_path))
    total_duration = video.duration

    # Calculate intro offset
    intro_offset = 4.0 if state.intro_enabled else 0.0

    # Place each scene's narration as a timed text overlay
    text_clips = []
    t = intro_offset
    for scene in state.scenes:
        # Use actual audio duration if available
        if scene.audio_path and scene.audio_path.exists():
            duration = _get_audio_duration(scene.audio_path)
        else:
            duration = scene.duration

        txt = make_text_clip(scene.narration, video.w - 80)
        txt = with_position(txt, ("center", "bottom"))
        txt = with_start(txt, t)
        txt = with_duration(txt, min(duration, total_duration - t))
        text_clips.append(txt)
        t += duration
        if t >= total_duration:
            break

    final = CompositeVideoClip([video] + text_clips)
    final.write_videofile(
        str(output_path),
        fps=fps,
        codec="libx264",
        audio_codec="aac",
        logger=None,
    )
    return output_path


# ── Agent entry point ─────────────────────────────────────────────────────

def run(state: PipelineState) -> PipelineState:
    print("\n[Agent 8/9] Subtitle Agent - adding captions...")
    state.status = "adding_subtitles"
    state.progress = 88

    job_dir = TEMP_DIR / state.job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / f"{state.job_id}_final.mp4"

    # Always export soft SRT for download
    srt_export_path = OUTPUT_DIR / f"{state.job_id}_subtitles.srt"

    if not state.subtitles_enabled:
        # Copy raw video as final output (no re-encoding)
        shutil.copy(state.video_path, out_path)
        state.captioned_path = out_path
        print("    Subtitles disabled - copied raw video as final output")

        # Still generate soft SRT for optional download
        try:
            intro_offset = 4.0 if state.intro_enabled else 0.0
            generate_scene_srt(state, job_dir, time_offset=intro_offset)
            srt_src = job_dir / "subtitles_scene.srt"
            if srt_src.exists():
                shutil.copy(srt_src, srt_export_path)
                print(f"    Soft SRT available: {srt_export_path.name}")
        except Exception as e:
            print(f"    Soft SRT generation skipped: {e}")

        state.progress = 92
        return state

    # Get the script language
    language = getattr(state, "script_language", "en") or "en"

    # ═══════════════════════════════════════════════════════════════════════
    # SUBTITLE STRATEGY (priority order):
    #
    # 1. Pre-generated SRT from Video Agent (BEST for all languages)
    #    - Has correct Devanagari text from scene.narration
    #    - Has accurate audio-synced durations
    #    - Has proper intro offset
    #
    # 2. Scene-based SRT (GOOD for all languages)
    #    - Uses scene.narration (correct Devanagari for Hindi/Marathi)
    #    - Needs intro offset calculation
    #
    # 3. Whisper transcription (LAST RESORT, English only)
    #    - For Hindi/Marathi, Whisper outputs Urdu script which is UNUSABLE
    #    - Only use for English where Whisper works correctly
    # ═══════════════════════════════════════════════════════════════════════

    srt_path = None
    used_method = "unknown"

    # ── Priority 1: Pre-generated SRT from Video Agent ────────────────────
    pregenned_srt = getattr(state, "srt_path", None)
    if pregenned_srt and Path(pregenned_srt).exists():
        srt_path = Path(pregenned_srt)
        used_method = "pre-generated (scene narration, correct Devanagari)"
        print(f"    Using pre-generated SRT from Video Agent (correct Devanagari text)")
    else:
        # ── Priority 2: Generate scene-based SRT ──────────────────────────
        try:
            intro_offset = 4.0 if state.intro_enabled else 0.0
            srt_path = generate_scene_srt(state, job_dir, time_offset=intro_offset)
            used_method = "scene-based (narration text, correct Devanagari)"
            print(f"    Generated scene-based SRT (correct Devanagari text, no Whisper)")
        except Exception as e:
            print(f"    Scene-based SRT generation failed: {e}")

    # ── Priority 3: Whisper (English only, last resort) ───────────────────
    if srt_path is None and language == "en":
        try:
            import whisper
            srt_path = transcribe_to_srt_english(state.video_path, job_dir)
            used_method = "Whisper English transcription"
        except ImportError:
            print("    Whisper not installed - skipping transcription")
        except Exception as e:
            print(f"    Whisper transcription failed: {e}")

    # ── If we still don't have an SRT, try MoviePy overlay as last resort ─
    if srt_path is None:
        print("    All SRT methods failed - trying MoviePy text overlay...")
        try:
            add_subtitles_moviepy(state, out_path)
            state.captioned_path = out_path
            size_mb = out_path.stat().st_size / 1_048_576
            print(f"    Final    : {out_path.name} ({size_mb:.1f} MB, MoviePy overlay)")
            state.progress = 92
            return state
        except Exception as e:
            print(f"    MoviePy overlay failed: {e}")
            # Just copy the raw video
            shutil.copy(state.video_path, out_path)
            state.captioned_path = out_path
            state.progress = 92
            return state

    # ── Burn subtitles into video ─────────────────────────────────────────
    print(f"    Burning subtitles into video ({used_method})...")
    burn_subtitles(state.video_path, srt_path, out_path,
                   font_size=state.subtitle_font_size, language=language)

    # Copy soft SRT to output for download
    try:
        shutil.copy(srt_path, srt_export_path)
        print(f"    Soft SRT available: {srt_export_path.name}")
    except Exception:
        pass

    # Final verification
    state.captioned_path = out_path
    size_mb = out_path.stat().st_size / 1_048_576
    
    # Check audio is present
    has_audio = _video_has_audio(out_path)
    audio_status = "with audio" if has_audio else "NO AUDIO - check recovery"
    print(f"    Final    : {out_path.name} ({size_mb:.1f} MB, {audio_status})")
    
    state.progress = 92
    return state