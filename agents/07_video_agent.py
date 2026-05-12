"""
Video Editing Agent

Assembles approved scene images and narration into a documentary-style MP4.
The render dimensions and frame rate come from the current PipelineState.
"""

from __future__ import annotations

import math
import numpy as np

from core.config import (
    OUTPUT_DIR,
    TRANSITION_DURATION,
    VIDEO_FPS,
    VIDEO_HEIGHT,
    VIDEO_WIDTH,
    PipelineState,
)


def _moviepy_symbols():
    try:
        from moviepy.editor import AudioClip, AudioFileClip, CompositeAudioClip, ImageClip, VideoClip, concatenate_videoclips
        import moviepy.video.fx.all as vfx
    except ModuleNotFoundError:
        from moviepy import AudioClip, AudioFileClip, CompositeAudioClip, ImageClip, VideoClip, concatenate_videoclips, vfx

    return AudioClip, AudioFileClip, CompositeAudioClip, ImageClip, VideoClip, concatenate_videoclips, vfx


def _with_duration(clip, duration: float):
    return clip.with_duration(duration) if hasattr(clip, "with_duration") else clip.set_duration(duration)


def _with_fps(clip, fps: int):
    return clip.with_fps(fps) if hasattr(clip, "with_fps") else clip.set_fps(fps)


def _with_audio(clip, audio):
    return clip.with_audio(audio) if hasattr(clip, "with_audio") else clip.set_audio(audio)


def _with_fades(clip, duration: float, vfx):
    if hasattr(clip, "fadein"):
        return clip.fadein(duration).fadeout(duration)
    return clip.with_effects([vfx.FadeIn(duration), vfx.FadeOut(duration)])


def _with_crossfade(clip, duration: float, vfx, fade_in: bool, fade_out: bool):
    if duration <= 0:
        return clip
    if hasattr(clip, "crossfadein"):
        if fade_in:
            clip = clip.crossfadein(duration)
        if fade_out:
            clip = clip.crossfadeout(duration)
        return clip

    effects = []
    if fade_in and hasattr(vfx, "CrossFadeIn"):
        effects.append(vfx.CrossFadeIn(duration))
    if fade_out and hasattr(vfx, "CrossFadeOut"):
        effects.append(vfx.CrossFadeOut(duration))
    return clip.with_effects(effects) if effects and hasattr(clip, "with_effects") else clip


def _audio_with_duration(audio, duration: float):
    return audio.with_duration(duration) if hasattr(audio, "with_duration") else audio.set_duration(duration)


def _audio_with_start(audio, start: float):
    return audio.with_start(start) if hasattr(audio, "with_start") else audio.set_start(start)


def _audio_with_volume(audio, factor: float):
    if hasattr(audio, "with_volume_scaled"):
        return audio.with_volume_scaled(factor)
    if hasattr(audio, "volumex"):
        return audio.volumex(factor)
    return audio


def _make_music_bed(kind: str, duration: float, volume: float):
    if kind == "none" or volume <= 0 or duration <= 0:
        return None
    AudioClip, _, CompositeAudioClip, _, _, _, _ = _moviepy_symbols()
    moods = {
        "suspense": [(55, 0.55), (82, 0.3), (110, 0.18)],
        "ambient": [(96, 0.36), (144, 0.18), (192, 0.12)],
        "emotional": [(65, 0.34), (98, 0.2), (130, 0.12)],
    }
    tones = moods.get(kind, moods["suspense"])

    def make_frame(t):
        t_arr = np.asarray(t)
        sample = np.zeros_like(t_arr, dtype=float)
        envelope = np.minimum(1.0, np.minimum(t_arr / 2.0, np.maximum(0.0, (duration - t_arr) / 2.0)))
        for freq, gain in tones:
            sample += np.sin(2 * math.pi * freq * t_arr) * gain
        signal = sample * volume * envelope
        if np.isscalar(t):
            return np.array([float(signal), float(signal)])
        return np.column_stack([signal, signal])

    return AudioClip(make_frame, duration=duration, fps=44100)


def _with_music_bed(video_clip, kind: str, volume: float):
    music = _make_music_bed(kind, video_clip.duration, volume)
    if music is None:
        return video_clip
    _, _, CompositeAudioClip, _, _, _, _ = _moviepy_symbols()
    if not getattr(video_clip, "audio", None):
        return _with_audio(video_clip, music)
    return _with_audio(video_clip, CompositeAudioClip([video_clip.audio, music]))


def _ken_burns(
    clip,
    width: int,
    height: int,
    fps: int,
    zoom_ratio: float = 0.05,
    direction: str = "in",
):
    _, _, _, _, VideoClip, _, _ = _moviepy_symbols()

    duration = clip.duration

    def make_frame(t):
        progress = t / duration
        if direction == "in":
            scale = 1.0 + zoom_ratio * progress
        else:
            scale = (1.0 + zoom_ratio) - zoom_ratio * progress

        frame = clip.get_frame(t)
        src_h, src_w = frame.shape[:2]
        new_w = max(width, int(src_w * scale))
        new_h = max(height, int(src_h * scale))

        from PIL import Image

        img = Image.fromarray(frame).resize((new_w, new_h), Image.LANCZOS)
        arr = np.array(img)
        x_offset = max(0, (new_w - width) // 2)
        y_offset = max(0, (new_h - height) // 2)
        return arr[y_offset:y_offset + height, x_offset:x_offset + width]

    return _with_fps(VideoClip(make_frame, duration=duration), fps)


def build_scene_clip(scene, index: int, width: int, height: int, fps: int, zoom_ratio: float):
    _, AudioFileClip, _, ImageClip, _, _, _ = _moviepy_symbols()

    audio = AudioFileClip(str(scene.audio_path))
    duration = audio.duration + 0.3
    img_clip = _with_duration(ImageClip(str(scene.image_path)), duration)
    direction = "in" if index % 2 == 0 else "out"
    zoomed = _ken_burns(img_clip, width, height, fps, zoom_ratio=zoom_ratio, direction=direction)
    return _with_audio(zoomed, audio)


def run(state: PipelineState) -> PipelineState:
    width = int(state.video_width or VIDEO_WIDTH)
    height = int(state.video_height or VIDEO_HEIGHT)
    fps = int(state.video_fps or VIDEO_FPS)
    transition_style = (state.transition_style or "crossfade").lower()
    transition_duration = max(0.0, float(state.transition_duration or TRANSITION_DURATION))
    zoom_ratio = max(0.0, min(float(state.ken_burns_intensity or 0.045), 0.12))

    print(f"\n[Agent 7/9] Video Editing Agent - assembling {len(state.scenes)} scenes...")
    state.status = "assembling_video"
    state.progress = 78

    _, _, _, _, _, concatenate_videoclips, vfx = _moviepy_symbols()
    quality = (state.render_quality or "balanced").lower()
    quality_settings = {
        "preview": {"crf": "30", "preset": "veryfast", "fps": min(fps, 18)},
        "balanced": {"crf": "23", "preset": "medium", "fps": fps},
        "final": {"crf": "18", "preset": "slow", "fps": fps},
    }[quality if quality in ("preview", "balanced", "final") else "balanced"]
    fps = int(quality_settings["fps"])

    clips = []
    for i, scene in enumerate(state.scenes):
        print(f"    Building scene {scene.number:02d}/{len(state.scenes):02d}...")
        clip = build_scene_clip(scene, i, width, height, fps, zoom_ratio)
        if transition_style == "fade":
            clip = _with_fades(clip, transition_duration, vfx)
        elif transition_style == "crossfade":
            clip = _with_crossfade(
                clip,
                transition_duration,
                vfx,
                fade_in=i > 0,
                fade_out=i < len(state.scenes) - 1,
            )
        clips.append(clip)

    print("    Concatenating all scenes...")
    padding = -transition_duration if transition_style in ("crossfade", "fade") and transition_duration > 0 else 0
    final = concatenate_videoclips(clips, method="compose", padding=padding)
    final = _with_music_bed(
        final,
        state.background_music or "none",
        float(state.background_music_volume or 0),
    )

    video_path = OUTPUT_DIR / f"{state.job_id}_raw.mp4"
    state.video_path = video_path

    print(f"    Exporting MP4 ({width}x{height} @ {fps}fps)...")
    final.write_videofile(
        str(video_path),
        fps=fps,
        codec="libx264",
        audio_codec="aac",
        temp_audiofile=str(OUTPUT_DIR / "tmp_audio.m4a"),
        remove_temp=True,
        preset=quality_settings["preset"],
        ffmpeg_params=["-crf", quality_settings["crf"], "-pix_fmt", "yuv420p"],
        logger=None,
    )

    size_mb = video_path.stat().st_size / 1_048_576
    duration = final.duration
    print(f"    Video    : {video_path.name} ({size_mb:.1f} MB, {duration:.1f}s)")
    state.progress = 86
    return state
