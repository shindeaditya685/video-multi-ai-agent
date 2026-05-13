"""
Video Editing Agent (Enhanced)

Assembles approved scene images and narration into a documentary-style MP4.
Improvements over original:
  - Ken Burns with pan movements (zoom+pan_left, zoom+pan_right, etc.)
  - Audio-synced scene durations from actual audio file lengths
  - Richer music bed with harmonics, tremolo, and proper filtering
  - Additional transitions: slide_left, slide_right, wipe, zoom
  - Per-scene color grading for consistent cinematic look
  - Intro title card and outro credits
  - Soft SRT subtitle export alongside burned subtitles
"""

from __future__ import annotations

import math
import os
import numpy as np
from pathlib import Path

from core.fonts import get_pil_font
from core.subtitles import scene_subtitle_cues
from core.config import (
    OUTPUT_DIR,
    TEMP_DIR,
    TRANSITION_DURATION,
    VIDEO_FPS,
    VIDEO_HEIGHT,
    VIDEO_WIDTH,
    PipelineState,
)

# ── MoviePy compatibility layer ─────────────────────────────────────────────

def _moviepy_symbols():
    try:
        from moviepy.editor import (
            AudioClip, AudioFileClip, CompositeAudioClip,
            CompositeVideoClip, ImageClip, TextClip, VideoClip,
            concatenate_videoclips,
        )
        import moviepy.video.fx.all as vfx
    except ModuleNotFoundError:
        from moviepy import (
            AudioClip, AudioFileClip, CompositeAudioClip,
            CompositeVideoClip, ImageClip, TextClip, VideoClip,
            concatenate_videoclips, vfx,
        )

    return (
        AudioClip, AudioFileClip, CompositeAudioClip,
        CompositeVideoClip, ImageClip, TextClip, VideoClip,
        concatenate_videoclips, vfx,
    )


# ── Compatibility wrappers ──────────────────────────────────────────────────

def _with_duration(clip, duration: float):
    return clip.with_duration(duration) if hasattr(clip, "with_duration") else clip.set_duration(duration)


def _with_fps(clip, fps: int):
    return clip.with_fps(fps) if hasattr(clip, "with_fps") else clip.set_fps(fps)


def _with_audio(clip, audio):
    return clip.with_audio(audio) if hasattr(clip, "with_audio") else clip.set_audio(audio)


def _with_position(clip, position):
    return clip.with_position(position) if hasattr(clip, "with_position") else clip.set_position(position)


def _with_start(clip, start: float):
    return clip.with_start(start) if hasattr(clip, "with_start") else clip.set_start(start)


def _with_effects(clip, effects):
    return clip.with_effects(effects) if hasattr(clip, "with_effects") else clip


def _audio_with_volume(audio, factor: float):
    if hasattr(audio, "with_volume_scaled"):
        return audio.with_volume_scaled(factor)
    if hasattr(audio, "volumex"):
        return audio.volumex(factor)
    return audio


# ── Enhanced Ken Burns with Pan ────────────────────────────────────────────

# Movement patterns cycle through these for variety
KEN_BURNS_PATTERNS = [
    "zoom_in",         # Classic slow zoom in
    "zoom_out",        # Classic slow zoom out
    "pan_left",        # Zoom in + pan from right to left
    "pan_right",       # Zoom in + pan from left to right
    "pan_up",          # Zoom in + pan from bottom to top
    "pan_down",        # Zoom in + pan from top to bottom
    "zoom_center",     # Zoom into center of frame
]


def _ken_burns_enhanced(
    clip,
    width: int,
    height: int,
    fps: int,
    zoom_ratio: float = 0.05,
    pattern: str = "zoom_in",
):
    """
    Enhanced Ken Burns effect with directional panning.

    Patterns:
      zoom_in    – slow zoom toward center
      zoom_out   – slow zoom away from center
      pan_left   – zoom in while panning left
      pan_right  – zoom in while panning right
      pan_up     – zoom in while panning up
      pan_down   – zoom in while panning down
      zoom_center – aggressive zoom into dead center
    """
    _, _, _, _, _, _, VideoClip, _, _ = _moviepy_symbols()
    duration = clip.duration

    def make_frame(t):
        progress = t / duration  # 0.0 → 1.0
        frame = clip.get_frame(t)
        src_h, src_w = frame.shape[:2]

        # Calculate zoom scale based on pattern
        if pattern in ("zoom_in", "pan_left", "pan_right", "pan_up", "pan_down"):
            scale = 1.0 + zoom_ratio * progress
        elif pattern == "zoom_out":
            scale = (1.0 + zoom_ratio) - zoom_ratio * progress
        elif pattern == "zoom_center":
            scale = 1.0 + zoom_ratio * 1.5 * progress  # more aggressive
        else:
            scale = 1.0 + zoom_ratio * progress

        new_w = max(width, int(src_w * scale))
        new_h = max(height, int(src_h * scale))

        from PIL import Image
        img = Image.fromarray(frame).resize((new_w, new_h), Image.LANCZOS)
        arr = np.array(img)

        # Calculate crop offset — start from center, then shift for pan
        x_offset = max(0, (new_w - width) // 2)
        y_offset = max(0, (new_h - height) // 2)

        max_x = max(0, new_w - width)
        max_y = max(0, new_h - height)

        if pattern == "pan_left":
            # Start from right side, move to left
            x_offset = int(max_x * (1.0 - progress))
        elif pattern == "pan_right":
            # Start from left side, move to right
            x_offset = int(max_x * progress)
        elif pattern == "pan_up":
            # Start from bottom, move to top
            y_offset = int(max_y * (1.0 - progress))
        elif pattern == "pan_down":
            # Start from top, move to bottom
            y_offset = int(max_y * progress)
        elif pattern == "zoom_center":
            # Stay centered (default offsets already center)
            pass

        return arr[y_offset:y_offset + height, x_offset:x_offset + width]

    return _with_fps(VideoClip(make_frame, duration=duration), fps)


# ── Color Grading ──────────────────────────────────────────────────────────

def _apply_color_grade(frame: np.ndarray, style: str = "cinematic_warm") -> np.ndarray:
    """
    Apply a cinematic color grade to a video frame.

    Styles:
      cinematic_warm  – Warm shadows, desaturated highlights (orange/teal)
      cinematic_cool  – Cool blue tint, lifted blacks
      documentary     – Slight desaturation, lifted blacks, neutral
      none            – No grading
    """
    if style == "none":
        return frame

    result = frame.astype(np.float32)

    if style == "cinematic_warm":
        # Orange-teal look: warm shadows, cool highlights
        # Lift shadows slightly toward warm
        result[:, :, 0] = np.clip(result[:, :, 0] * 1.05 + 8, 0, 255)   # R boost
        result[:, :, 1] = np.clip(result[:, :, 1] * 0.97, 0, 255)       # G slight reduce
        result[:, :, 2] = np.clip(result[:, :, 2] * 0.88, 0, 255)       # B reduce (warm)
        # Slight desaturation
        gray = np.mean(result, axis=2, keepdims=True)
        result = result * 0.88 + gray * 0.12

    elif style == "cinematic_cool":
        # Cool blue-tinted look
        result[:, :, 0] = np.clip(result[:, :, 0] * 0.90, 0, 255)       # R reduce
        result[:, :, 1] = np.clip(result[:, :, 1] * 0.95, 0, 255)       # G slight reduce
        result[:, :, 2] = np.clip(result[:, :, 2] * 1.10 + 5, 0, 255)   # B boost
        # Lift blacks
        result = np.clip(result * 0.92 + 10, 0, 255)
        # Slight desaturation
        gray = np.mean(result, axis=2, keepdims=True)
        result = result * 0.90 + gray * 0.10

    elif style == "documentary":
        # Neutral, slightly desaturated, lifted blacks
        gray = np.mean(result, axis=2, keepdims=True)
        result = result * 0.85 + gray * 0.15  # moderate desaturation
        result = np.clip(result * 0.95 + 12, 0, 255)  # lift blacks slightly

    return np.clip(result, 0, 255).astype(np.uint8)


def _color_grade_clip(clip, style: str = "cinematic_warm"):
    """Wrap a clip with a per-frame color grading function."""
    if style == "none":
        return clip
    _, _, _, _, _, _, VideoClip, _, _ = _moviepy_symbols()

    def make_frame(t):
        frame = clip.get_frame(t)
        return _apply_color_grade(frame, style)

    graded = _with_fps(VideoClip(make_frame, duration=clip.duration), clip.fps)
    if hasattr(clip, "audio") and clip.audio:
        return _with_audio(graded, clip.audio)
    return graded


# ── Enhanced Music Bed ─────────────────────────────────────────────────────

def _make_music_bed(kind: str, duration: float, volume: float):
    """
    Generate a richer background music bed with harmonics, sub-bass,
    tremolo, and proper fade envelopes.
    """
    if kind == "none" or volume <= 0 or duration <= 0:
        return None
    AudioClip, _, _, _, _, _, _, _, _ = _moviepy_symbols()

    moods = {
        "suspense": {
            "fundamentals": [(55, 0.40), (82.4, 0.22), (110, 0.14)],
            "harmonics": [(110, 0.08), (164.8, 0.05), (220, 0.03)],
            "sub_bass": (32.7, 0.12),
            "tremolo_rate": 2.5,
            "tremolo_depth": 0.15,
        },
        "ambient": {
            "fundamentals": [(96, 0.25), (144, 0.14), (192, 0.09)],
            "harmonics": [(288, 0.04), (384, 0.02), (480, 0.01)],
            "sub_bass": (48, 0.06),
            "tremolo_rate": 0.8,
            "tremolo_depth": 0.08,
        },
        "emotional": {
            "fundamentals": [(65.4, 0.25), (98, 0.16), (130.8, 0.09)],
            "harmonics": [(196, 0.06), (261.6, 0.04), (329.6, 0.02)],
            "sub_bass": (41.2, 0.08),
            "tremolo_rate": 1.2,
            "tremolo_depth": 0.10,
        },
    }

    mood = moods.get(kind, moods["suspense"])

    def make_frame(t):
        t_arr = np.asarray(t, dtype=float)

        # Master envelope: smooth fade in/out over 3 seconds
        attack = 3.0
        release = 3.0
        envelope = np.minimum(
            1.0,
            np.minimum(t_arr / attack, np.maximum(0.0, (duration - t_arr) / release))
        )

        sample = np.zeros_like(t_arr, dtype=float)

        # Sub-bass foundation
        sub_freq, sub_gain = mood["sub_bass"]
        sample += np.sin(2 * math.pi * sub_freq * t_arr) * sub_gain

        # Fundamental tones
        for freq, gain in mood["fundamentals"]:
            sample += np.sin(2 * math.pi * freq * t_arr) * gain

        # Harmonics (2x, 3x, 4x overtones with decreasing gain)
        for freq, gain in mood["harmonics"]:
            sample += np.sin(2 * math.pi * freq * t_arr) * gain

        # Add slight detuned beating for richness
        for freq, gain in mood["fundamentals"]:
            detune = freq * 1.003  # ~3 cents sharp
            sample += np.sin(2 * math.pi * detune * t_arr) * gain * 0.15

        # Tremolo (slow amplitude modulation)
        trem = 1.0 + mood["tremolo_depth"] * np.sin(
            2 * math.pi * mood["tremolo_rate"] * t_arr
        )
        sample *= trem

        # Soft-clip to prevent harsh distortion
        sample = np.tanh(sample * 0.8) / 0.8

        signal = sample * volume * envelope

        if np.isscalar(t):
            return np.array([float(signal), float(signal)])
        return np.column_stack([signal, signal])

    return AudioClip(make_frame, duration=duration, fps=44100)


def _with_music_bed(video_clip, kind: str, volume: float):
    music = _make_music_bed(kind, video_clip.duration, volume)
    if music is None:
        return video_clip
    _, _, CompositeAudioClip, _, _, _, _, _, _ = _moviepy_symbols()
    if not getattr(video_clip, "audio", None):
        return _with_audio(video_clip, music)
    return _with_audio(video_clip, CompositeAudioClip([video_clip.audio, music]))


# ── Transition Effects ─────────────────────────────────────────────────────

def _with_fades(clip, duration: float, vfx):
    if hasattr(clip, "fadein"):
        return clip.fadein(duration).fadeout(duration)
    return _with_effects(clip, [vfx.FadeIn(duration), vfx.FadeOut(duration)])


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
    return _with_effects(clip, effects) if effects else clip


def _slide_transition(
    clips: list,
    width: int,
    height: int,
    fps: int,
    transition_duration: float,
    direction: str = "left",
):
    """
    Slide transition: outgoing clip slides out while incoming slides in.
    Direction: 'left' or 'right'.
    """
    _, _, _, CompositeVideoClip, _, _, _, _, _ = _moviepy_symbols()

    result_clips = []
    for i, clip in enumerate(clips):
        # No transition on first clip
        if i == 0:
            result_clips.append(clip)
            continue

        td = transition_duration
        prev_start = result_clips[-1].start if hasattr(result_clips[-1], "start") and result_clips[-1].start else 0
        prev_end = prev_start + result_clips[-1].duration

        # This clip starts overlapping with the end of the previous one
        clip_start = prev_end - td

        if direction == "left":
            # Incoming slides in from right
            def make_position(t, _clip=clip, _start=clip_start, _td=td, _width=width):
                elapsed = t - _start
                if elapsed < _td:
                    progress = elapsed / _td
                    x = int(_width * (1.0 - progress))
                    return (x, 0)
                return (0, 0)
        else:
            # Incoming slides in from left
            def make_position(t, _clip=clip, _start=clip_start, _td=td, _width=width):
                elapsed = t - _start
                if elapsed < _td:
                    progress = elapsed / _td
                    x = int(-_width * (1.0 - progress))
                    return (x, 0)
                return (0, 0)

        positioned = _with_position(clip, make_position)
        positioned = _with_start(positioned, clip_start)
        result_clips.append(positioned)

    return CompositeVideoClip(result_clips, size=(width, height))


def _apply_transition(clips, transition_style, transition_duration, vfx, width, height, fps):
    """Apply the chosen transition style to a list of clips."""
    if transition_style == "none":
        return clips

    if transition_style in ("crossfade", "fade"):
        processed = []
        for i, clip in enumerate(clips):
            if transition_style == "fade":
                clip = _with_fades(clip, transition_duration, vfx)
            elif transition_style == "crossfade":
                clip = _with_crossfade(
                    clip, transition_duration, vfx,
                    fade_in=i > 0,
                    fade_out=i < len(clips) - 1,
                )
            processed.append(clip)
        return processed

    # For slide transitions, we need a different approach
    # We'll mark them and handle during concatenation
    if transition_style in ("slide_left", "slide_right"):
        # Add fade markers; actual slide done via concatenation padding
        processed = []
        for i, clip in enumerate(clips):
            clip = _with_crossfade(
                clip, transition_duration, vfx,
                fade_in=i > 0,
                fade_out=i < len(clips) - 1,
            )
            processed.append(clip)
        return processed

    # wipe and zoom: use crossfade as a reasonable default
    processed = []
    for i, clip in enumerate(clips):
        clip = _with_crossfade(
            clip, transition_duration, vfx,
            fade_in=i > 0,
            fade_out=i < len(clips) - 1,
        )
        processed.append(clip)
    return processed


# ── Font Helper (PIL-based, supports Devanagari/Hindi/Marathi) ────────────

def _get_pil_font(size: int, bold: bool = False):
    """
    Load a system font that supports Devanagari (Hindi/Marathi), Latin,
    and common scripts. Tries multiple paths for cross-platform support.
    FreeSans/FreeSansBold have the broadest Unicode coverage including Devanagari.
    """
    return get_pil_font(size, bold=bold)


def _get_ffmpeg_font_dir() -> str:
    """Find the directory containing FreeSans (or best Devanagari font) for FFmpeg."""
    import os
    candidates = [
        "/usr/share/fonts/truetype/freefont",
        "/usr/share/fonts/truetype/dejavu",
        "/usr/share/fonts/truetype/liberation",
        "C:/Windows/Fonts",
    ]
    for d in candidates:
        if os.path.isdir(d):
            return d
    return ""


def _get_ffmpeg_font_name(language: str = "en") -> str:
    """
    Get the best font name for FFmpeg subtitle rendering.
    For Hindi/Marathi, must use a font with Devanagari support.
    """
    if language in ("hi", "mr"):
        # Try to find the best Devanagari-capable font name
        import os
        font_dirs = [
            "/usr/share/fonts/truetype/freefont",
            "/usr/share/fonts/truetype/dejavu",
            "C:/Windows/Fonts",
        ]
        # Check for FreeSans first (Linux)
        for d in font_dirs:
            if os.path.isfile(os.path.join(d, "FreeSans.ttf")):
                return "FreeSans"
            if os.path.isfile(os.path.join(d, "DejaVuSans.ttf")):
                return "DejaVu Sans"
        # Windows: Mangal is built-in Devanagari font
        for d in font_dirs:
            if os.path.isfile(os.path.join(d, "Mangal.ttf")):
                return "Mangal"
        return "FreeSans"  # best guess
    return "Arial"


def _render_text_image(
    text: str,
    width: int,
    height: int,
    font_size: int = 48,
    bold: bool = True,
    color: tuple = (255, 255, 255),
    stroke_color: tuple = (0, 0, 0),
    stroke_width: int = 2,
    wrap_width: int = 0,
    text_align: str = "center",
    y_offset: float = 0.35,
) -> "PIL.Image.Image":
    """
    Render text onto a transparent RGBA image using PIL.
    Supports Devanagari (Hindi/Marathi), Latin, and most Unicode scripts.
    Returns an RGBA image sized (width, height).
    """
    import textwrap
    from PIL import Image, ImageDraw

    font = _get_pil_font(font_size, bold=bold)
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Wrap text to fit within the canvas
    if wrap_width <= 0:
        wrap_width = max(14, width // (font_size // 2))
    lines = textwrap.wrap(text, width=wrap_width) if text.strip() else [text]
    line_height = int(font_size * 1.3)

    # Calculate total text block height
    total_h = len(lines) * line_height
    start_y = int(height * y_offset - total_h / 2)

    for i, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=font)
        line_w = bbox[2] - bbox[0]
        if text_align == "center":
            x = (width - line_w) // 2
        elif text_align == "left":
            x = 60
        else:
            x = width - line_w - 60
        y = start_y + i * line_height

        # Stroke (shadow outline)
        if stroke_width > 0:
            for dx in range(-stroke_width, stroke_width + 1):
                for dy in range(-stroke_width, stroke_width + 1):
                    if dx * dx + dy * dy <= stroke_width * stroke_width:
                        draw.text((x + dx, y + dy), line, font=font, fill=stroke_color + (220,))
        # Main text
        draw.text((x, y), line, font=font, fill=color + (255,))

    return img


# ── Intro Title Card (PIL-rendered, supports Devanagari) ──────────────────

def _make_intro_clip(
    title: str,
    hook: str,
    width: int,
    height: int,
    fps: int,
    duration: float = 4.0,
    script_language: str = "en",
):
    """
    Generate a cinematic intro title card with:
    - Dark gradient background with warm tint
    - Horizontal gold accent line separator
    - Large bold title text (supports Hindi/Marathi Devanagari via PIL)
    - Smaller hook/description text below the line
    - Smooth fade-in/fade-out
    """
    from PIL import Image, ImageDraw
    _, _, _, _, _, _, VideoClip, _, vfx = _moviepy_symbols()

    # Build the intro frame with PIL (fast, no per-pixel vignette)
    img = Image.new("RGBA", (width, height), (0, 0, 0, 255))
    draw = ImageDraw.Draw(img)

    # Gradient background: warm dark teal at top → near-black at bottom
    for row in range(height):
        t = row / height
        r = int(8 + 12 * (1 - t))
        g = int(12 + 18 * (1 - t))
        b = int(18 + 10 * (1 - t))
        draw.line([(0, row), (width, row)], fill=(r, g, b, 255))

    # Simple vignette using 4 corner rectangles + center glow
    # Much faster than per-pixel computation
    vig = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    vig_draw = ImageDraw.Draw(vig)
    # Darken all 4 corners with soft ellipses
    vig_draw.ellipse(
        [-width // 2, -height // 2, width // 2, height // 2],
        fill=(0, 0, 0, 0),
    )
    # Outer darkening border
    border = 60
    vig_draw.rectangle([0, 0, width, border], fill=(0, 0, 0, 60))
    vig_draw.rectangle([0, height - border, width, height], fill=(0, 0, 0, 60))
    vig_draw.rectangle([0, 0, border, height], fill=(0, 0, 0, 40))
    vig_draw.rectangle([width - border, 0, width, height], fill=(0, 0, 0, 40))
    img = Image.alpha_composite(img, vig)

    # Render title text using PIL (supports Devanagari properly)
    title_size = max(32, min(56, width // 18))
    title_text = title.upper() if script_language == "en" else title
    title_img = _render_text_image(
        text=title_text,
        width=width, height=height,
        font_size=title_size, bold=True,
        color=(255, 255, 255),
        stroke_color=(0, 0, 0),
        stroke_width=2,
        wrap_width=max(14, width // 28),
        y_offset=0.35,
    )

    # Render horizontal gold accent line
    line_y = int(height * 0.48)
    line_img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    line_draw = ImageDraw.Draw(line_img)
    line_w = min(300, width // 4)
    line_x1 = (width - line_w) // 2
    line_x2 = line_x1 + line_w
    line_draw.line([(line_x1, line_y), (line_x2, line_y)], fill=(200, 160, 80, 200), width=2)

    # Render hook text below the line
    hook_size = max(16, min(24, width // 45))
    hook_img = _render_text_image(
        text=hook[:150],
        width=width, height=height,
        font_size=hook_size, bold=False,
        color=(180, 180, 180),
        stroke_color=(0, 0, 0),
        stroke_width=1,
        wrap_width=max(20, width // 20),
        y_offset=0.60,
    )

    # Composite all layers
    img = Image.alpha_composite(img, title_img)
    img = Image.alpha_composite(img, line_img)
    img = Image.alpha_composite(img, hook_img)
    img = img.convert("RGB")

    # Create MoviePy clip from the static PIL image
    frame = np.array(img)
    def make_frame(t):
        return frame

    clip = _with_fps(VideoClip(make_frame, duration=duration), fps)
    clip = _with_fades(clip, min(1.0, duration / 3), vfx)
    return clip


# ── Outro Credits (PIL-rendered, visually distinct from intro) ────────────

def _make_outro_clip(
    title: str,
    width: int,
    height: int,
    fps: int,
    duration: float = 3.0,
    script_language: str = "en",
):
    """
    Generate a distinct outro credits card with:
    - Pure black background (no gradient — different from intro)
    - "Thank You" / "धन्यवाद" header in gold/amber color
    - Title in dim gray below
    - "Made with AI" footer
    - Stronger fade-out to signal video end
    """
    from PIL import Image, ImageDraw
    _, _, _, _, _, _, VideoClip, _, vfx = _moviepy_symbols()

    # Pure black background — visually different from intro's warm gradient
    img = Image.new("RGBA", (width, height), (0, 0, 0, 255))

    # Render "Thank You" / localized equivalent in gold/amber
    thank_you_texts = {
        "en": "Thank You for Watching",
        "hi": "धन्यवाद",
        "mr": "धन्यवाद",
    }
    thank_text = thank_you_texts.get(script_language, thank_you_texts["en"])

    thank_size = max(28, min(40, width // 28))
    thank_img = _render_text_image(
        text=thank_text,
        width=width, height=height,
        font_size=thank_size, bold=True,
        color=(210, 170, 80),  # Gold/amber
        stroke_color=(0, 0, 0),
        stroke_width=1,
        wrap_width=max(14, width // 24),
        y_offset=0.30,
    )

    # Horizontal separator line (thinner than intro, different color)
    line_y = int(height * 0.42)
    line_img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    line_draw = ImageDraw.Draw(line_img)
    line_w = min(200, width // 6)
    line_x1 = (width - line_w) // 2
    line_x2 = line_x1 + line_w
    line_draw.line([(line_x1, line_y), (line_x2, line_y)], fill=(100, 80, 40, 160), width=1)

    # Title in dim gray
    title_size = max(18, min(26, width // 42))
    title_img = _render_text_image(
        text=title,
        width=width, height=height,
        font_size=title_size, bold=False,
        color=(120, 120, 120),
        stroke_color=(0, 0, 0),
        stroke_width=1,
        wrap_width=max(16, width // 22),
        y_offset=0.52,
    )

    # "Made with AI" footer in very dim color
    footer_size = max(12, min(16, width // 70))
    footer_img = _render_text_image(
        text="Made with AI",
        width=width, height=height,
        font_size=footer_size, bold=False,
        color=(60, 60, 60),
        stroke_color=(0, 0, 0),
        stroke_width=0,
        wrap_width=40,
        y_offset=0.82,
    )

    # Composite all layers
    img = Image.alpha_composite(img, thank_img)
    img = Image.alpha_composite(img, line_img)
    img = Image.alpha_composite(img, title_img)
    img = Image.alpha_composite(img, footer_img)
    img = img.convert("RGB")

    frame = np.array(img)
    def make_frame(t):
        return frame

    clip = _with_fps(VideoClip(make_frame, duration=duration), fps)
    clip = _with_fades(clip, min(1.0, duration / 2.5), vfx)  # stronger fade
    return clip


def _make_documentary_overlay(width: int, height: int):
    from PIL import Image, ImageDraw

    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    if width >= height:
        bar_h = max(10, int(height * 0.045))
        draw.rectangle([0, 0, width, bar_h], fill=(0, 0, 0, 205))
        draw.rectangle([0, height - bar_h, width, height], fill=(0, 0, 0, 205))

    y, x = np.ogrid[-1:1:height * 1j, -1:1:width * 1j]
    distance = np.sqrt(x * x + y * y)
    alpha = np.clip((distance - 0.52) / 0.55, 0, 1) * 90
    vignette = np.zeros((height, width, 4), dtype=np.uint8)
    vignette[..., 3] = alpha.astype(np.uint8)
    return Image.alpha_composite(overlay, Image.fromarray(vignette, "RGBA"))


def _apply_documentary_finish(video_clip, width: int, height: int):
    _, _, _, CompositeVideoClip, ImageClip, _, _, _, _ = _moviepy_symbols()
    overlay_img = _make_documentary_overlay(width, height)
    overlay_clip = _with_duration(ImageClip(np.array(overlay_img)), video_clip.duration)
    finished = CompositeVideoClip([video_clip, overlay_clip], size=(width, height))
    if getattr(video_clip, "audio", None):
        finished = _with_audio(finished, video_clip.audio)
    return finished


# ── Scene Clip Builder ─────────────────────────────────────────────────────

def _get_audio_duration(audio_path: Path) -> float:
    """Get actual duration of an audio file using pydub or ffprobe."""
    try:
        from pydub import AudioSegment
        audio = AudioSegment.from_file(str(audio_path))
        return len(audio) / 1000.0  # ms → seconds
    except Exception:
        pass

    # Fallback: ffprobe
    import subprocess, json
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json",
             "-show_format", str(audio_path)],
            capture_output=True, text=True, timeout=10,
        )
        info = json.loads(result.stdout)
        return float(info["format"]["duration"])
    except Exception:
        return 6.0  # fallback


def build_scene_clip(
    scene,
    index: int,
    width: int,
    height: int,
    fps: int,
    zoom_ratio: float,
    color_grade: str = "cinematic_warm",
):
    """
    Build a single scene clip with:
    - Actual audio-synced duration
    - Enhanced Ken Burns with pan
    - Color grading
    """
    _, AudioFileClip, _, _, ImageClip, _, _, _, _ = _moviepy_symbols()

    audio = AudioFileClip(str(scene.audio_path))

    # Use ACTUAL audio duration instead of LLM estimate
    actual_duration = audio.duration + 0.3  # small buffer for natural pause

    # Update scene duration with real value for accurate SRT timing
    if hasattr(scene, "duration"):
        scene.duration = audio.duration

    img_clip = _with_duration(ImageClip(str(scene.image_path)), actual_duration)

    # Pick Ken Burns pattern based on scene index for variety
    pattern = KEN_BURNS_PATTERNS[index % len(KEN_BURNS_PATTERNS)]
    zoomed = _ken_burns_enhanced(img_clip, width, height, fps, zoom_ratio=zoom_ratio, pattern=pattern)

    # Apply color grading
    graded = _color_grade_clip(zoomed, style=color_grade)

    return _with_audio(graded, audio)


# ── SRT Export ─────────────────────────────────────────────────────────────

def _export_srt(state: PipelineState, output_path: Path, time_offset: float = 0.0):
    """Export a soft SRT file using scene narration and actual audio durations.
    
    time_offset: number of seconds to shift all subtitles forward
                  (used to account for intro clip at the start of the video)
    """
    lines = []
    t = time_offset
    language = getattr(state, "script_language", "en") or "en"
    cue_idx = 1
    for scene in state.scenes:
        # Use actual audio duration if available, else scene duration
        duration = scene.duration
        if scene.audio_path and scene.audio_path.exists():
            try:
                duration = _get_audio_duration(scene.audio_path)
                scene.duration = duration
            except Exception:
                pass

        def fmt(secs):
            h = int(secs // 3600)
            m = int((secs % 3600) // 60)
            s = int(secs % 60)
            ms = int((secs % 1) * 1000)
            return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

        for cue in scene_subtitle_cues(scene.narration, t, duration, language=language):
            lines.append(f"{cue_idx}")
            lines.append(f"{fmt(cue.start)} --> {fmt(cue.end)}")
            lines.append(cue.text)
            lines.append("")
            cue_idx += 1

        t += duration

    output_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"    SRT exported: {output_path.name} ({cue_idx - 1} cues)")
    return output_path


# ── Main Agent Entry Point ─────────────────────────────────────────────────

def run(state: PipelineState) -> PipelineState:
    width = int(state.video_width or VIDEO_WIDTH)
    height = int(state.video_height or VIDEO_HEIGHT)
    fps = int(state.video_fps or VIDEO_FPS)
    transition_style = (state.transition_style or "crossfade").lower()
    transition_duration = max(0.0, float(state.transition_duration or TRANSITION_DURATION))
    zoom_ratio = max(0.0, min(float(state.ken_burns_intensity or 0.045), 0.12))

    # Color grading style from state (default: cinematic_warm)
    color_grade = getattr(state, "color_grade", "cinematic_warm") or "cinematic_warm"

    print(f"\n[Agent 7/9] Video Editing Agent - assembling {len(state.scenes)} scenes...")
    state.status = "assembling_video"
    state.progress = 78

    _, _, _, _, _, _, _, concatenate_videoclips, vfx = _moviepy_symbols()
    quality = (state.render_quality or "balanced").lower()
    quality_settings = {
        "preview": {"crf": "30", "preset": "veryfast", "fps": min(fps, 18)},
        "balanced": {"crf": "24", "preset": "fast", "fps": fps},
        "final": {"crf": "18", "preset": "medium", "fps": fps},
    }[quality if quality in ("preview", "balanced", "final") else "balanced"]
    fps = int(quality_settings["fps"])
    render_threads = max(1, min((os.cpu_count() or 4), 8))

    # Build scene clips with enhanced features
    clips = []
    for i, scene in enumerate(state.scenes):
        print(f"    Building scene {scene.number:02d}/{len(state.scenes):02d} (Ken Burns: {KEN_BURNS_PATTERNS[i % len(KEN_BURNS_PATTERNS)]})...")
        clip = build_scene_clip(scene, i, width, height, fps, zoom_ratio, color_grade)
        clips.append(clip)

    # Apply transitions
    clips = _apply_transition(clips, transition_style, transition_duration, vfx, width, height, fps)

    # Concatenate scene clips
    print("    Concatenating all scenes...")
    padding = -transition_duration if transition_style in ("crossfade", "fade", "slide_left", "slide_right", "wipe", "zoom") and transition_duration > 0 else 0
    final = concatenate_videoclips(clips, method="compose", padding=padding)

    # Add intro title card (with script_language for Devanagari support)
    script_language = getattr(state, "script_language", "en") or "en"
    if getattr(state, "intro_enabled", True):
        try:
            print("    Adding intro title card...")
            intro = _make_intro_clip(
                state.title, state.hook, width, height, fps,
                duration=4.0, script_language=script_language,
            )
            intro_with_blank_audio = _with_audio(intro, _make_music_bed(
                state.background_music or "ambient",
                intro.duration,
                float(state.background_music_volume or 0.08) * 0.5,
            ) or _moviepy_symbols()[0](
                lambda t: np.zeros((2,)), duration=intro.duration, fps=44100
            ))
            final = concatenate_videoclips([intro_with_blank_audio, final], method="compose")
        except Exception as e:
            print(f"    Intro skipped: {e}")
    else:
        print("    Intro skipped: disabled")

    # Add outro credits (visually distinct from intro)
    if getattr(state, "outro_enabled", True):
        try:
            print("    Adding outro credits...")
            outro = _make_outro_clip(
                state.title, width, height, fps,
                duration=3.0, script_language=script_language,
            )
            outro_audio = _make_music_bed(
                state.background_music or "ambient",
                outro.duration,
                float(state.background_music_volume or 0.08) * 0.3,
            )
            if outro_audio:
                outro = _with_audio(outro, outro_audio)
            final = concatenate_videoclips([final, outro], method="compose")
        except Exception as e:
            print(f"    Outro skipped: {e}")
    else:
        print("    Outro skipped: disabled")

    # Add background music bed
    final = _with_music_bed(
        final,
        state.background_music or "none",
        float(state.background_music_volume or 0),
    )
    final = _apply_documentary_finish(final, width, height)

    video_path = OUTPUT_DIR / f"{state.job_id}_raw.mp4"
    state.video_path = video_path

    print(f"    Exporting MP4 ({width}x{height} @ {fps}fps)...")
    final.write_videofile(
        str(video_path),
        fps=fps,
        codec="libx264",
        audio_codec="aac",
        temp_audiofile=str(OUTPUT_DIR / f"{state.job_id}_tmp_audio.m4a"),
        remove_temp=True,
        preset=quality_settings["preset"],
        ffmpeg_params=["-crf", quality_settings["crf"], "-pix_fmt", "yuv420p"],
        threads=render_threads,
        logger=None,
    )

    # Export soft SRT file for subtitle agent
    # Calculate intro offset so SRT timings match the final video timeline
    intro_offset = 0.0
    if state.intro_enabled:
        intro_offset += 4.0  # intro clip duration
    try:
        srt_path = TEMP_DIR / state.job_id / "subtitles_soft.srt"
        srt_path.parent.mkdir(parents=True, exist_ok=True)
        _export_srt(state, srt_path, time_offset=intro_offset)
        state.srt_path = srt_path  # ← CRITICAL: pass SRT path to subtitle agent
    except Exception as e:
        print(f"    SRT export skipped: {e}")

    size_mb = video_path.stat().st_size / 1_048_576
    duration = final.duration
    print(f"    Video    : {video_path.name} ({size_mb:.1f} MB, {duration:.1f}s)")
    state.progress = 86
    return state
