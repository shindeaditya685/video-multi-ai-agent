"""
Image Generation Agent

Downloads one generated image per approved scene and fits each image to the
per-job video dimensions.
"""

from __future__ import annotations

import time
from pathlib import Path
from urllib.parse import quote

import requests
from PIL import Image, ImageDraw, ImageFilter, ImageOps

from core.config import (
    IMAGE_PROVIDER,
    STABILITY_API_KEY,
    TEMP_DIR,
    VIDEO_HEIGHT,
    VIDEO_WIDTH,
    PipelineState,
)


def _fetch_pollinations(
    prompt: str,
    scene_num: int,
    width: int,
    height: int,
    seed: int = 0,
) -> bytes | None:
    encoded = quote(prompt)
    url = (
        f"https://image.pollinations.ai/prompt/{encoded}"
        f"?width={width}&height={height}"
        f"&nologo=true&seed={seed}"
        f"&model=flux"
    )
    try:
        resp = requests.get(url, timeout=90)
        if resp.status_code == 200 and "image" in resp.headers.get("Content-Type", ""):
            return resp.content
    except requests.RequestException:
        pass
    return None


def _fetch_stability(prompt: str, width: int, height: int) -> bytes | None:
    if not STABILITY_API_KEY:
        return None
    try:
        resp = requests.post(
            "https://api.stability.ai/v1/generation/stable-diffusion-xl-1024-v1-0/text-to-image",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {STABILITY_API_KEY}",
            },
            json={
                "text_prompts": [{"text": prompt, "weight": 1}],
                "cfg_scale": 7,
                "height": height,
                "width": width,
                "samples": 1,
                "steps": 30,
            },
            timeout=60,
        )
        if resp.status_code == 200:
            import base64

            return base64.b64decode(resp.json()["artifacts"][0]["base64"])
    except Exception:
        pass
    return None


def _make_placeholder(scene_num: int, prompt: str, width: int, height: int) -> Image.Image:
    import textwrap as tw

    palette = ["#15191e", "#243230", "#3d2b2b", "#1f3440", "#352b3d", "#2c3324"]
    img = Image.new("RGB", (width, height), palette[scene_num % len(palette)])
    draw = ImageDraw.Draw(img)
    lines = tw.wrap(f"Scene {scene_num}: {prompt}", width=max(28, width // 24))
    y = height // 2 - len(lines) * 22
    for line in lines:
        bbox = draw.textbbox((0, 0), line)
        text_width = bbox[2] - bbox[0]
        draw.text(((width - text_width) // 2, y), line, fill=(220, 220, 220))
        y += 44
    return img


def _fit_image(img: Image.Image, width: int, height: int, fit_mode: str = "contain_blur") -> Image.Image:
    img = img.convert("RGB")
    if fit_mode == "cover":
        return ImageOps.fit(img, (width, height), method=Image.LANCZOS, centering=(0.5, 0.5))

    target_ratio = width / height
    src_ratio = img.width / img.height

    if src_ratio > target_ratio:
        new_w = width
        new_h = int(width / src_ratio)
    else:
        new_h = height
        new_w = int(height * src_ratio)

    img = img.resize((new_w, new_h), Image.LANCZOS)
    bg = img.resize((width, height), Image.LANCZOS).filter(ImageFilter.GaussianBlur(radius=20))
    x = (width - new_w) // 2
    y = (height - new_h) // 2
    bg.paste(img, (x, y))
    return bg


def fetch_scene_image(
    prompt: str,
    scene_num: int,
    job_dir: Path,
    width: int,
    height: int,
    fit_mode: str = "contain_blur",
) -> Path:
    out_path = job_dir / f"image_{scene_num:02d}.png"
    img_bytes = None

    for attempt in range(3):
        if IMAGE_PROVIDER == "stability":
            img_bytes = _fetch_stability(prompt, width, height)
        if not img_bytes:
            img_bytes = _fetch_pollinations(
                prompt,
                scene_num,
                width,
                height,
                seed=scene_num * 77 + attempt,
            )
        if img_bytes:
            break
        print(f"    Scene {scene_num}: attempt {attempt + 1} failed, retrying...")
        time.sleep(4)

    if img_bytes:
        from io import BytesIO

        img = Image.open(BytesIO(img_bytes))
    else:
        print(f"    Scene {scene_num}: using placeholder image.")
        img = _make_placeholder(scene_num, prompt, width, height)

    final = _fit_image(img, width, height, fit_mode)
    final.save(out_path, "PNG")
    return out_path


def fit_uploaded_image(source_path: Path, scene_num: int, job_dir: Path, width: int, height: int, fit_mode: str) -> Path:
    out_path = job_dir / f"image_{scene_num:02d}.png"
    img = Image.open(source_path)
    final = _fit_image(img, width, height, fit_mode)
    final.save(out_path, "PNG")
    return out_path


def run(state: PipelineState) -> PipelineState:
    width = int(state.video_width or VIDEO_WIDTH)
    height = int(state.video_height or VIDEO_HEIGHT)
    fit_mode = state.image_fit_mode or "contain_blur"

    image_source = (state.image_source or "ai").lower()
    verb = "fitting uploaded" if image_source == "upload" else "generating"
    print(f"\n[Agent 6/9] Image Agent - {verb} {len(state.scenes)} images...")
    state.status = "generating_images"
    state.progress = 64

    job_dir = TEMP_DIR / state.job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    if image_source == "upload":
        if not state.uploaded_image_paths:
            raise RuntimeError("Image source is upload, but no uploaded images were provided")
        if len(state.uploaded_image_paths) < len(state.scenes):
            state.errors.append(
                f"Only {len(state.uploaded_image_paths)} uploaded images for {len(state.scenes)} scenes; reusing images."
            )
        for i, scene in enumerate(state.scenes):
            selected = scene.upload_image_index if scene.upload_image_index is not None else i
            source = state.uploaded_image_paths[selected % len(state.uploaded_image_paths)]
            print(f"    Scene {scene.number:02d}/{len(state.scenes):02d}: fitting {source.name}")
            scene.image_path = fit_uploaded_image(source, scene.number, job_dir, width, height, fit_mode)
            state.progress = 64 + int((i + 1) / len(state.scenes) * 12)
        print(f"    Done: uploaded images fitted to {width}x{height}")
        state.progress = 76
        return state

    for i, scene in enumerate(state.scenes):
        print(f"    Scene {scene.number:02d}/{len(state.scenes):02d}: {scene.image_prompt[:55]}...")
        scene.image_path = fetch_scene_image(scene.image_prompt, scene.number, job_dir, width, height, fit_mode)
        time.sleep(1)
        state.progress = 64 + int((i + 1) / len(state.scenes) * 12)

    print(f"    Done: {len(state.scenes)} images saved to {job_dir}")
    state.progress = 76
    return state
