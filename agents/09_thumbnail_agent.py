"""
agents/09_thumbnail_agent.py
─────────────────────────────
Thumbnail Agent
  Role  : Creates a cinematic YouTube thumbnail with title text overlay.
  Input : PipelineState (title + first/middle scene image)
  Output: PipelineState.thumbnail_path  (1280×720 PNG)
  Tools : Pillow (open source, free)
  Cost  : FREE
"""

from __future__ import annotations
import textwrap
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageEnhance
from core.config import PipelineState, OUTPUT_DIR, VIDEO_WIDTH, VIDEO_HEIGHT


def _get_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Try to load a system font; fall back to PIL default."""
    font_candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "C:/Windows/Fonts/arialbd.ttf",
        "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
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

    # ── Pick a dramatic mid-video scene as background ──────────────────────
    mid = len(state.scenes) // 3
    bg_scene = state.scenes[mid]
    bg_path = bg_scene.image_path or state.scenes[0].image_path

    img = Image.open(bg_path).convert("RGB").resize((width, height), Image.LANCZOS)

    # ── Dramatic processing ────────────────────────────────────────────────
    # Slightly darken
    img = ImageEnhance.Brightness(img).enhance(0.55)
    # Slight vignette via blur on edges (composited)
    blurred = img.filter(ImageFilter.GaussianBlur(radius=6))
    mask = Image.new("L", (width, height), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.ellipse(
        [width * 0.1, height * 0.1, width * 0.9, height * 0.9],
        fill=255
    )
    mask = mask.filter(ImageFilter.GaussianBlur(80))
    img = Image.composite(img, blurred, mask)

    draw = ImageDraw.Draw(img)

    # ── Red "TRUE CRIME" badge top-left ───────────────────────────────────
    badge_font = _get_font(22)
    badge_text = "◆ TRUE CRIME DOCUMENTARY"
    draw.rectangle([30, 30, min(width - 30, 380), 62], fill=(180, 20, 20))
    draw.text((42, 36), badge_text, font=badge_font, fill="white")

    # ── Main title (large, white, wrapped) ───────────────────────────────
    title = state.title.upper()
    title_font = _get_font(72, bold=True)
    small_font = _get_font(38)

    lines = textwrap.wrap(title, width=22)
    y = height // 2 - len(lines) * 45

    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=title_font)
        w = bbox[2] - bbox[0]
        x = (width - w) // 2

        # Shadow
        draw.text((x + 3, y + 3), line, font=title_font, fill=(0, 0, 0, 180))
        # Main
        draw.text((x, y), line, font=title_font, fill=(255, 255, 255))
        y += 82

    # ── Bottom bar with hook text ─────────────────────────────────────────
    bar_height = max(90, int(height * 0.14))
    bar_top = height - bar_height
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(overlay).rectangle(
        [(0, bar_top), (width, height)],
        fill=(0, 0, 0, 180)
    )
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(img)

    hook = state.hook[:90] + "..." if len(state.hook) > 90 else state.hook
    hook_font = _get_font(28)
    hook_bbox = draw.textbbox((0, 0), hook, font=hook_font)
    hook_w = hook_bbox[2] - hook_bbox[0]
    draw.text(
        ((width - hook_w) // 2, bar_top + 28),
        hook, font=hook_font, fill=(220, 220, 220)
    )

    # ── Save ──────────────────────────────────────────────────────────────
    out_path = OUTPUT_DIR / f"{state.job_id}_thumbnail.png"
    img.save(out_path, "PNG")
    return out_path


def run(state: PipelineState) -> PipelineState:
    print("\n[Agent 9/9] Thumbnail Agent - creating thumbnail...")
    state.status = "creating_thumbnail"
    state.progress = 94

    state.thumbnail_path = create_thumbnail(state)
    print(f"    Saved    : {state.thumbnail_path.name}")
    state.progress = 97
    return state
