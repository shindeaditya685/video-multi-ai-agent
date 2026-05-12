"""
Thumbnail Agent (Enhanced)

Creates a cinematic YouTube thumbnail with title text overlay.

Improvements over original:
  - Configurable badge text (auto-detected from topic or customizable)
  - Genre-aware styling (documentary, mystery, news, etc.)
  - Better text layout with proportional sizing
  - Gradient overlays for readability
  - Support for non-crime topics (no more hardcoded "TRUE CRIME")
"""

from __future__ import annotations

import re
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageEnhance

from core.config import PipelineState, OUTPUT_DIR, VIDEO_WIDTH, VIDEO_HEIGHT

# Badge presets for different genres
GENRE_BADGES = {
    "crime": {
        "text": "TRUE CRIME DOCUMENTARY",
        "bg_color": (180, 20, 20),
        "icon": "\u25C6",  # ◆ diamond
    },
    "mystery": {
        "text": "MYSTERY DOCUMENTARY",
        "bg_color": (30, 30, 140),
        "icon": "\u2753",  # ❓
    },
    "history": {
        "text": "HISTORICAL DOCUMENTARY",
        "bg_color": (120, 80, 20),
        "icon": "\u25B6",  # ▶
    },
    "science": {
        "text": "SCIENCE DOCUMENTARY",
        "bg_color": (20, 100, 120),
        "icon": "\u2609",  # ☉
    },
    "news": {
        "text": "NEWS DOCUMENTARY",
        "bg_color": (140, 30, 30),
        "icon": "\u25B6",  # ▶
    },
    "general": {
        "text": "DOCUMENTARY",
        "bg_color": (100, 60, 20),
        "icon": "\u25C6",  # ◆
    },
}

# Keywords to auto-detect genre from topic
GENRE_KEYWORDS = {
    "crime": ["murder", "kill", "crime", "rape", "assault", "kidnap", "serial killer",
              "court", "verdict", "convict", "prison", "jail", "police", "investigation",
              "nirbhaya", "case", "trial", "justice"],
    "mystery": ["mystery", "disappear", "missing", "unsolved", "haunted", "ghost",
                "paranormal", "strange", "bizarre", "unexplained"],
    "history": ["history", "historical", "war", "battle", "ancient", "empire", "king",
                "queen", "revolution", "colonial", "independence"],
    "science": ["science", "space", "nasa", "quantum", "physics", "biology", "dna",
                "evolution", "climate", "technology", "ai", "robot"],
    "news": ["news", "current", "breaking", "latest", "today", "expose", "report"],
}


def _detect_genre(topic: str, details: str = "") -> str:
    """Auto-detect genre from topic and details text."""
    text = f"{topic} {details}".lower()
    scores = {}
    for genre, keywords in GENRE_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in text)
        if score > 0:
            scores[genre] = score

    if scores:
        return max(scores, key=scores.get)
    return "general"


def _get_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Try to load a system font; fall back to PIL default."""
    font_candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/noto-serif-sc/NotoSerifSC-Bold.ttf" if bold else "/usr/share/fonts/truetype/noto-serif-sc/NotoSerifSC-Regular.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
        "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/TTF/DejaVuSans.ttf",
    ]
    for path in font_candidates:
        try:
            return ImageFont.truetype(path, size)
        except (IOError, OSError):
            continue
    return ImageFont.load_default()


def create_thumbnail(state: PipelineState) -> Path:
    if not state.scenes:
        raise RuntimeError("Cannot create thumbnail without scenes")

    width = int(state.video_width or VIDEO_WIDTH)
    height = int(state.video_height or VIDEO_HEIGHT)

    # ── Detect genre ─────────────────────────────────────────────────────
    custom_badge = getattr(state, "thumbnail_badge", "") or ""
    if custom_badge:
        genre = "custom"
        badge_config = {
            "text": custom_badge.upper(),
            "bg_color": (100, 60, 20),
            "icon": "\u25C6",
        }
    else:
        genre = _detect_genre(state.topic, state.details)
        badge_config = GENRE_BADGES.get(genre, GENRE_BADGES["general"])

    # ── Pick a dramatic mid-video scene as background ──────────────────────
    mid = len(state.scenes) // 3
    bg_scene = state.scenes[mid]
    bg_path = bg_scene.image_path or state.scenes[0].image_path

    img = Image.open(bg_path).convert("RGB").resize((width, height), Image.LANCZOS)

    # ── Dramatic processing ────────────────────────────────────────────────
    # Darken for text readability
    img = ImageEnhance.Brightness(img).enhance(0.45)

    # Contrast boost for punch
    img = ImageEnhance.Contrast(img).enhance(1.15)

    # Vignette via blur on edges (composited)
    blurred = img.filter(ImageFilter.GaussianBlur(radius=6))
    mask = Image.new("L", (width, height), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.ellipse(
        [width * 0.1, height * 0.1, width * 0.9, height * 0.9],
        fill=255
    )
    mask = mask.filter(ImageFilter.GaussianBlur(80))
    img = Image.composite(img, blurred, mask)

    # ── Bottom gradient overlay for text readability ──────────────────────
    gradient = Image.new("RGBA", img.size, (0, 0, 0, 0))
    gradient_draw = ImageDraw.Draw(gradient)
    for row in range(height):
        alpha = int(180 * max(0, (row - height * 0.55) / (height * 0.45)))
        gradient_draw.line([(0, row), (width, row)], fill=(0, 0, 0, alpha))

    draw = ImageDraw.Draw(img)

    # ── Genre badge top-left ──────────────────────────────────────────────
    badge_font = _get_font(22, bold=True)
    badge_text = f"{badge_config['icon']} {badge_config['text']}"
    # Measure badge text to size rectangle properly
    badge_bbox = draw.textbbox((0, 0), badge_text, font=badge_font)
    badge_w = badge_bbox[2] - badge_bbox[0] + 24
    badge_right = min(width - 30, 30 + badge_w)
    draw.rectangle([30, 30, badge_right, 62], fill=badge_config["bg_color"])
    draw.text((42, 36), badge_text, font=badge_font, fill="white")

    # ── Main title (large, white, wrapped) ──────────────────────────────
    title = state.title.upper()
    # Proportional font sizing based on canvas width
    title_font_size = max(32, min(72, width // 16))
    title_font = _get_font(title_font_size, bold=True)

    # Wrap title text at appropriate width for canvas
    chars_per_line = max(14, width // 32)
    lines = textwrap.wrap(title, width=chars_per_line)
    line_height = int(title_font_size * 1.15)

    # Position title in upper-center area
    total_text_height = len(lines) * line_height
    y = max(int(height * 0.15), int(height * 0.38 - total_text_height / 2))

    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=title_font)
        w = bbox[2] - bbox[0]
        x = (width - w) // 2

        # Drop shadow
        draw.text((x + 3, y + 3), line, font=title_font, fill=(0, 0, 0, 200))
        # Main text
        draw.text((x, y), line, font=title_font, fill=(255, 255, 255))
        y += line_height

    # ── Apply gradient overlay ────────────────────────────────────────────
    img = Image.alpha_composite(img.convert("RGBA"), gradient).convert("RGB")
    draw = ImageDraw.Draw(img)

    # ── Bottom bar with hook text ─────────────────────────────────────────
    bar_height = max(80, int(height * 0.13))
    bar_top = height - bar_height
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(overlay).rectangle(
        [(0, bar_top), (width, height)],
        fill=(0, 0, 0, 200)
    )
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(img)

    # Hook text
    hook = state.hook[:100] + "..." if len(state.hook) > 100 else state.hook
    hook_font_size = max(20, min(28, width // 42))
    hook_font = _get_font(hook_font_size)
    hook_bbox = draw.textbbox((0, 0), hook, font=hook_font)
    hook_w = hook_bbox[2] - hook_bbox[0]
    draw.text(
        ((width - hook_w) // 2, bar_top + (bar_height - hook_font_size) // 2),
        hook, font=hook_font, fill=(220, 220, 220)
    )

    # ── Save ──────────────────────────────────────────────────────────────
    out_path = OUTPUT_DIR / f"{state.job_id}_thumbnail.png"
    img.save(out_path, "PNG")

    genre_label = genre.upper() if genre != "custom" else "CUSTOM"
    print(f"    Genre   : {genre_label} (badge: {badge_config['text']})")
    return out_path


def run(state: PipelineState) -> PipelineState:
    print("\n[Agent 9/9] Thumbnail Agent - creating thumbnail...")
    state.status = "creating_thumbnail"
    state.progress = 94

    state.thumbnail_path = create_thumbnail(state)
    print(f"    Saved    : {state.thumbnail_path.name}")
    state.progress = 97
    return state
