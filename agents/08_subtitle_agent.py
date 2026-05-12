"""
agents/08_subtitle_agent.py
────────────────────────────
Subtitle Agent
  Role  : Generates accurate SRT captions using OpenAI Whisper (local, free).
           Burns subtitles into the video using FFmpeg.
  Input : PipelineState.video_path  (raw MP4 from Video Agent)
  Output: PipelineState.captioned_path  (final MP4 with burned captions)
  Tools : Whisper (open source, free, runs locally)
           FFmpeg (free)
  Cost  : FREE
"""

from __future__ import annotations
import subprocess
import shutil
from pathlib import Path
from core.config import PipelineState, OUTPUT_DIR, TEMP_DIR, VIDEO_FPS, WHISPER_MODEL

FFMPEG_BIN = str(Path("C:/ffmpeg/bin/ffmpeg.exe")) if Path("C:/ffmpeg/bin/ffmpeg.exe").exists() else "ffmpeg"


# ── Whisper transcription → SRT ───────────────────────────────────────────────

def _seconds_to_srt_time(seconds: float) -> str:
    """Convert float seconds to SRT timestamp format: HH:MM:SS,mmm"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def transcribe_to_srt(video_path: Path, job_dir: Path) -> Path:
    """Run Whisper on the video audio and return an SRT subtitle file."""
    import whisper

    print("    Loading Whisper model...")
    model = whisper.load_model(WHISPER_MODEL)

    print("    Transcribing audio...")
    result = model.transcribe(
        str(video_path),
        language="en",
        word_timestamps=True,
        verbose=False,
    )

    srt_path = job_dir / "subtitles.srt"
    srt_lines = []
    idx = 1

    for segment in result["segments"]:
        start = _seconds_to_srt_time(segment["start"])
        end   = _seconds_to_srt_time(segment["end"])
        text  = segment["text"].strip()
        srt_lines.append(f"{idx}\n{start} --> {end}\n{text}\n")
        idx += 1

    srt_path.write_text("\n".join(srt_lines), encoding="utf-8")
    print(f"    SRT: {len(result['segments'])} subtitle segments generated")
    return srt_path


# ── Burn subtitles with FFmpeg ─────────────────────────────────────────────────

def burn_subtitles(video_path: Path, srt_path: Path, output_path: Path, font_size: int = 18) -> Path:
    """
    Use FFmpeg to burn subtitles directly into the video.
    Style: white text, dark semi-transparent background, bottom-centered.
    """
    # Escape Windows path backslashes for FFmpeg filter
    srt_str = str(srt_path).replace("\\", "/").replace(":", "\\:")

    subtitle_filter = (
        f"subtitles='{srt_str}':"
        "force_style='"
        "Fontname=Arial,"
        f"Fontsize={font_size},"
        "PrimaryColour=&H00FFFFFF,"    # White text
        "OutlineColour=&H00000000,"    # Black outline
        "BackColour=&H80000000,"       # Semi-transparent black bg
        "BorderStyle=4,"               # Box background
        "Outline=1,"
        "Shadow=0,"
        "MarginV=25,"                  # Vertical margin from bottom
        "Alignment=2'"                 # Bottom-center
    )

    cmd = [
        FFMPEG_BIN, "-y",
        "-i", str(video_path),
        "-vf", subtitle_filter,
        "-c:v", "libx264",
        "-crf", "26",
        "-preset", "fast",
        "-c:a", "copy",
        str(output_path),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"    FFmpeg warning: {result.stderr[-300:]}")
        # Fallback: copy video without burning subtitles
        shutil.copy(video_path, output_path)
        print("    Subtitle burn failed - copied raw video as fallback.")

    return output_path


# ── Fallback: subtitle via MoviePy (no Whisper) ───────────────────────────────

def add_subtitles_moviepy(state: PipelineState, output_path: Path) -> Path:
    """
    If Whisper is not available, use the narration text directly from scenes
    and overlay it with MoviePy (no transcription needed).
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

    # Place each scene's narration as a timed text overlay
    text_clips = []
    t = 0.0
    for scene in state.scenes:
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


# ── Agent entry point ─────────────────────────────────────────────────────────

def run(state: PipelineState) -> PipelineState:
    print("\n[Agent 8/9] Subtitle Agent - adding captions...")
    state.status = "adding_subtitles"
    state.progress = 88

    job_dir  = TEMP_DIR / state.job_id
    out_path = OUTPUT_DIR / f"{state.job_id}_final.mp4"

    if not state.subtitles_enabled:
        shutil.copy(state.video_path, out_path)
        state.captioned_path = out_path
        print("    Subtitles disabled - copied raw video as final output")
        state.progress = 92
        return state

    try:
        import whisper
        srt_path = transcribe_to_srt(state.video_path, job_dir)
        burn_subtitles(state.video_path, srt_path, out_path, font_size=state.subtitle_font_size)
        print("    Subtitles burned via Whisper + FFmpeg")
    except ImportError:
        print("    Whisper not installed - using MoviePy subtitle fallback")
        add_subtitles_moviepy(state, out_path)

    state.captioned_path = out_path
    size_mb = out_path.stat().st_size / 1_048_576
    print(f"    Final    : {out_path.name} ({size_mb:.1f} MB)")
    state.progress = 92
    return state
