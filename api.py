"""
FastAPI backend for the AI video generation workflow.

The UI uses a reviewed flow:
1. POST /draft starts research, script, scene, and image-prompt generation.
2. GET /status/{job_id} polls until status is awaiting_confirmation.
3. POST /confirm/{job_id} accepts approved/edited script data and renders video.
"""

from __future__ import annotations

import re
import shutil
import uuid
from pathlib import Path
from typing import Dict

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from core.config import (
    IMAGE_COUNT,
    SCRIPT_LANGUAGE,
    SUBTITLE_FONT_SIZE,
    SUBTITLES_ENABLED,
    TEMP_DIR,
    VIDEO_FPS,
    VIDEO_HEIGHT,
    VIDEO_WIDTH,
    VOICE_NAME,
    VOICE_PROVIDER,
    VOICE_RATE,
    PipelineState,
    Scene,
)
from pipeline import create_state, run_draft_from_state, run_full_from_state, run_render_from_state
from agents import agent_05_voice as voice_agent
from agents import agent_06_image as image_agent

app = FastAPI(title="AI Crime Video Agent API", version="2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

JOBS: Dict[str, PipelineState] = {}
WS_CONNECTIONS: Dict[str, list[WebSocket]] = {}

LANGUAGE_DEFAULT_VOICE = {
    "en": ("edge", "en-IN-PrabhatNeural"),
    "hi": ("edge", "hi-IN-MadhurNeural"),
    "mr": ("edge", "mr-IN-ManoharNeural"),
}


class DraftRequest(BaseModel):
    topic: str = Field(..., min_length=3, max_length=240)
    details: str = Field("", max_length=3000)
    script_language: str = Field(SCRIPT_LANGUAGE, pattern="^(en|hi|mr)$")
    pronunciation_map: str = Field("", max_length=4000)
    video_width: int = Field(VIDEO_WIDTH, ge=320, le=3840)
    video_height: int = Field(VIDEO_HEIGHT, ge=320, le=3840)
    video_fps: int = Field(VIDEO_FPS, ge=12, le=60)
    image_count: int = Field(IMAGE_COUNT, ge=1, le=24)
    image_source: str = Field("ai", pattern="^(ai|upload)$")
    image_fit_mode: str = Field("contain_blur", pattern="^(contain_blur|cover)$")
    voice_provider: str = Field(VOICE_PROVIDER, pattern="^(edge|gtts)$")
    voice_name: str = Field(VOICE_NAME, max_length=120)
    voice_rate: str = Field(VOICE_RATE, max_length=12)
    voice_pitch: str = Field("+0Hz", max_length=12)
    subtitles_enabled: bool = SUBTITLES_ENABLED
    subtitle_font_size: int = Field(SUBTITLE_FONT_SIZE, ge=12, le=48)
    transition_style: str = Field("crossfade", pattern="^(crossfade|fade|none)$")
    transition_duration: float = Field(0.45, ge=0, le=2)
    ken_burns_intensity: float = Field(0.045, ge=0, le=0.12)
    render_quality: str = Field("balanced", pattern="^(preview|balanced|final)$")
    background_music: str = Field("none", pattern="^(none|suspense|ambient|emotional)$")
    background_music_volume: float = Field(0.08, ge=0, le=0.35)
    upload_to_youtube: bool = False


class GenerateRequest(DraftRequest):
    pass


class ScenePayload(BaseModel):
    number: int = Field(..., ge=1)
    duration: float = Field(6, ge=1, le=60)
    narration: str = Field(..., min_length=1, max_length=1200)
    visual_desc: str = Field("", max_length=1600)
    image_prompt: str = Field("", max_length=1600)
    upload_image_index: int | None = Field(None, ge=0)
    image_url: str = ""


class ConfirmRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=120)
    hook: str = Field("", max_length=1200)
    story: str = Field(..., min_length=1, max_length=12000)
    scenes: list[ScenePayload] = Field(default_factory=list)
    script_language: str = Field(SCRIPT_LANGUAGE, pattern="^(en|hi|mr)$")
    pronunciation_map: str = Field("", max_length=4000)
    image_source: str = Field("ai", pattern="^(ai|upload)$")
    image_fit_mode: str = Field("contain_blur", pattern="^(contain_blur|cover)$")
    voice_provider: str = Field(VOICE_PROVIDER, pattern="^(edge|gtts)$")
    voice_name: str = Field(VOICE_NAME, max_length=120)
    voice_rate: str = Field(VOICE_RATE, max_length=12)
    voice_pitch: str = Field("+0Hz", max_length=12)
    subtitles_enabled: bool = SUBTITLES_ENABLED
    subtitle_font_size: int = Field(SUBTITLE_FONT_SIZE, ge=12, le=48)
    transition_style: str = Field("crossfade", pattern="^(crossfade|fade|none)$")
    transition_duration: float = Field(0.45, ge=0, le=2)
    ken_burns_intensity: float = Field(0.045, ge=0, le=0.12)
    render_quality: str = Field("balanced", pattern="^(preview|balanced|final)$")
    background_music: str = Field("none", pattern="^(none|suspense|ambient|emotional)$")
    background_music_volume: float = Field(0.08, ge=0, le=0.35)
    upload_to_youtube: bool = False


class VoicePreviewRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=500)
    voice_provider: str = Field(VOICE_PROVIDER, pattern="^(edge|gtts)$")
    voice_name: str = Field(VOICE_NAME, max_length=120)
    voice_rate: str = Field(VOICE_RATE, max_length=12)
    voice_pitch: str = Field("+0Hz", max_length=12)
    pronunciation_map: str = Field("", max_length=4000)


class ImagePreviewRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=1600)
    fit_mode: str = Field("contain_blur", pattern="^(contain_blur|cover)$")


class UploadedImagePayload(BaseModel):
    index: int
    name: str
    url: str


class ProjectPayload(BaseModel):
    topic: str = ""
    details: str = ""
    script_language: str = SCRIPT_LANGUAGE
    pronunciation_map: str = ""
    title: str = ""
    hook: str = ""
    story: str = ""
    scenes: list[ScenePayload] = Field(default_factory=list)
    settings: dict = Field(default_factory=dict)


class JobStatus(BaseModel):
    job_id: str
    status: str
    progress: int
    topic: str = ""
    details: str = ""
    script_language: str = SCRIPT_LANGUAGE
    pronunciation_map: str = ""
    title: str = ""
    hook: str = ""
    story: str = ""
    scenes: list[ScenePayload] = Field(default_factory=list)
    video_width: int = VIDEO_WIDTH
    video_height: int = VIDEO_HEIGHT
    video_fps: int = VIDEO_FPS
    image_count: int = IMAGE_COUNT
    image_source: str = "ai"
    image_fit_mode: str = "contain_blur"
    uploaded_image_count: int = 0
    voice_provider: str = VOICE_PROVIDER
    voice_name: str = VOICE_NAME
    voice_rate: str = VOICE_RATE
    voice_pitch: str = "+0Hz"
    subtitles_enabled: bool = SUBTITLES_ENABLED
    subtitle_font_size: int = SUBTITLE_FONT_SIZE
    transition_style: str = "crossfade"
    transition_duration: float = 0.45
    ken_burns_intensity: float = 0.045
    render_quality: str = "balanced"
    background_music: str = "none"
    background_music_volume: float = 0.08
    estimated_duration: float = 0
    uploaded_images: list[UploadedImagePayload] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    video_url: str = ""
    thumbnail_url: str = ""
    youtube_url: str = ""


def _scene_payload(state: PipelineState, scene: Scene) -> ScenePayload:
    image_url = ""
    if scene.image_path and Path(scene.image_path).exists():
        image_url = f"/scene-image/{state.job_id}/{scene.number}"
    return ScenePayload(
        number=scene.number,
        duration=scene.duration,
        narration=scene.narration,
        visual_desc=scene.visual_desc,
        image_prompt=scene.image_prompt,
        upload_image_index=scene.upload_image_index,
        image_url=image_url,
    )


def _uploaded_payloads(state: PipelineState) -> list[UploadedImagePayload]:
    return [
        UploadedImagePayload(index=i, name=path.name, url=f"/uploaded/{state.job_id}/{i}")
        for i, path in enumerate(state.uploaded_image_paths)
        if path.exists()
    ]


def _job_status(state: PipelineState) -> JobStatus:
    video_url = ""
    thumbnail_url = ""
    if state.captioned_path and Path(state.captioned_path).exists():
        video_url = f"/download/{state.job_id}"
    if state.thumbnail_path and Path(state.thumbnail_path).exists():
        thumbnail_url = f"/thumbnail/{state.job_id}"

    return JobStatus(
        job_id=state.job_id,
        status=state.status,
        progress=state.progress,
        topic=state.topic,
        details=state.details,
        script_language=state.script_language,
        pronunciation_map=state.pronunciation_map,
        title=state.title,
        hook=state.hook,
        story=state.story,
        scenes=[_scene_payload(state, scene) for scene in state.scenes],
        video_width=state.video_width,
        video_height=state.video_height,
        video_fps=state.video_fps,
        image_count=state.image_count,
        image_source=state.image_source,
        image_fit_mode=state.image_fit_mode,
        uploaded_image_count=len(state.uploaded_image_paths),
        voice_provider=state.voice_provider,
        voice_name=state.voice_name,
        voice_rate=state.voice_rate,
        voice_pitch=state.voice_pitch,
        subtitles_enabled=state.subtitles_enabled,
        subtitle_font_size=state.subtitle_font_size,
        transition_style=state.transition_style,
        transition_duration=state.transition_duration,
        ken_burns_intensity=state.ken_burns_intensity,
        render_quality=state.render_quality,
        background_music=state.background_music,
        background_music_volume=state.background_music_volume,
        estimated_duration=sum(scene.duration for scene in state.scenes),
        uploaded_images=_uploaded_payloads(state),
        errors=state.errors,
        video_url=video_url,
        thumbnail_url=thumbnail_url,
        youtube_url=state.youtube_url,
    )


def _safe_download_name(state: PipelineState) -> str:
    name = state.title or state.topic or state.job_id
    name = re.sub(r"[^a-zA-Z0-9._ -]+", "", name).strip()[:60]
    return f"{name or state.job_id}.mp4"


def _make_state(req: DraftRequest, job_id: str) -> PipelineState:
    provider = req.voice_provider
    voice_name = req.voice_name
    if voice_name == VOICE_NAME and req.script_language in LANGUAGE_DEFAULT_VOICE:
        provider, voice_name = LANGUAGE_DEFAULT_VOICE[req.script_language]

    return create_state(
        topic=req.topic.strip(),
        job_id=job_id,
        details=req.details.strip(),
        script_language=req.script_language,
        pronunciation_map=req.pronunciation_map,
        video_width=req.video_width,
        video_height=req.video_height,
        video_fps=req.video_fps,
        image_count=req.image_count,
        image_source=req.image_source,
        image_fit_mode=req.image_fit_mode,
        voice_provider=provider,
        voice_name=voice_name,
        voice_rate=req.voice_rate,
        voice_pitch=req.voice_pitch,
        subtitles_enabled=req.subtitles_enabled,
        subtitle_font_size=req.subtitle_font_size,
        transition_style=req.transition_style,
        transition_duration=req.transition_duration,
        ken_burns_intensity=req.ken_burns_intensity,
        render_quality=req.render_quality,
        background_music=req.background_music,
        background_music_volume=req.background_music_volume,
        upload_to_youtube=req.upload_to_youtube,
    )


def _apply_render_settings(state: PipelineState, req: ConfirmRequest):
    state.script_language = req.script_language
    state.pronunciation_map = req.pronunciation_map
    state.image_source = req.image_source
    state.image_fit_mode = req.image_fit_mode
    state.voice_provider = req.voice_provider
    state.voice_name = req.voice_name
    state.voice_rate = req.voice_rate
    state.voice_pitch = req.voice_pitch
    state.subtitles_enabled = req.subtitles_enabled
    state.subtitle_font_size = req.subtitle_font_size
    state.transition_style = req.transition_style
    state.transition_duration = req.transition_duration
    state.ken_burns_intensity = req.ken_burns_intensity
    state.render_quality = req.render_quality
    state.background_music = req.background_music
    state.background_music_volume = req.background_music_volume
    state.upload_to_youtube = req.upload_to_youtube


def _mark_error(state: PipelineState, exc: Exception):
    state.status = "error"
    message = str(exc)
    if not state.errors or state.errors[-1] != message:
        state.errors.append(message)


def _run_draft_job(job_id: str):
    state = JOBS[job_id]
    try:
        run_draft_from_state(state)
    except Exception as exc:
        _mark_error(state, exc)


def _run_render_job(job_id: str, upload: bool):
    state = JOBS[job_id]
    state.upload_to_youtube = upload
    try:
        run_render_from_state(state, skip_upload=not upload)
    except Exception as exc:
        _mark_error(state, exc)


def _run_full_job(job_id: str, upload: bool):
    state = JOBS[job_id]
    state.upload_to_youtube = upload
    try:
        run_full_from_state(state, skip_upload=not upload)
    except Exception as exc:
        _mark_error(state, exc)


@app.post("/draft", response_model=JobStatus)
def draft(req: DraftRequest, background_tasks: BackgroundTasks):
    job_id = uuid.uuid4().hex[:8]
    state = _make_state(req, job_id)
    state.status = "queued"
    state.progress = 0
    JOBS[job_id] = state
    background_tasks.add_task(_run_draft_job, job_id)
    return _job_status(state)


@app.post("/uploads/{job_id}", response_model=JobStatus)
def upload_images(job_id: str, files: list[UploadFile] = File(...)):
    state = JOBS.get(job_id)
    if not state:
        raise HTTPException(status_code=404, detail="Job not found")
    if not files:
        raise HTTPException(status_code=400, detail="No image files uploaded")

    upload_dir = TEMP_DIR / job_id / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)

    saved_paths: list[Path] = []
    allowed_suffixes = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
    for index, upload in enumerate(files, start=1):
        suffix = Path(upload.filename or "").suffix.lower() or ".png"
        if suffix not in allowed_suffixes:
            raise HTTPException(status_code=400, detail=f"Unsupported image type: {upload.filename}")
        if upload.content_type and not upload.content_type.startswith("image/"):
            raise HTTPException(status_code=400, detail=f"File is not an image: {upload.filename}")

        target = upload_dir / f"source_{index:02d}{suffix}"
        with target.open("wb") as out_file:
            shutil.copyfileobj(upload.file, out_file)
        saved_paths.append(target)

    state.uploaded_image_paths = saved_paths
    state.image_source = "upload"
    return _job_status(state)


@app.get("/uploaded/{job_id}/{index}")
def uploaded_image(job_id: str, index: int):
    state = JOBS.get(job_id)
    if not state or index < 0 or index >= len(state.uploaded_image_paths):
        raise HTTPException(status_code=404, detail="Uploaded image not found")
    path = state.uploaded_image_paths[index]
    if not path.exists():
        raise HTTPException(status_code=404, detail="Uploaded image not found")
    return FileResponse(path=str(path))


@app.get("/scene-image/{job_id}/{scene_number}")
def scene_image(job_id: str, scene_number: int):
    state = JOBS.get(job_id)
    if not state:
        raise HTTPException(status_code=404, detail="Job not found")
    scene = next((item for item in state.scenes if item.number == scene_number), None)
    if not scene or not scene.image_path or not Path(scene.image_path).exists():
        raise HTTPException(status_code=404, detail="Scene image not found")
    return FileResponse(path=str(scene.image_path), media_type="image/png")


@app.post("/voice-preview")
def voice_preview(req: VoicePreviewRequest):
    preview_id = uuid.uuid4().hex[:10]
    out_dir = TEMP_DIR / "voice_previews"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{preview_id}.mp3"
    voice_agent.generate_preview_audio(
        text=req.text,
        output_path=out_path,
        provider=req.voice_provider,
        voice_name=req.voice_name,
        rate=req.voice_rate,
        pitch=req.voice_pitch,
        pronunciation_map=req.pronunciation_map,
    )
    return {"preview_id": preview_id, "audio_url": f"/voice-preview/{preview_id}"}


@app.get("/voice-preview/{preview_id}")
def voice_preview_file(preview_id: str):
    if not re.fullmatch(r"[a-f0-9]{10}", preview_id):
        raise HTTPException(status_code=400, detail="Invalid preview id")
    path = TEMP_DIR / "voice_previews" / f"{preview_id}.mp3"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Voice preview not found")
    return FileResponse(path=str(path), media_type="audio/mpeg")


@app.post("/preview-image/{job_id}/{scene_number}", response_model=JobStatus)
def preview_image(job_id: str, scene_number: int, req: ImagePreviewRequest):
    state = JOBS.get(job_id)
    if not state:
        raise HTTPException(status_code=404, detail="Job not found")
    scene = next((item for item in state.scenes if item.number == scene_number), None)
    if not scene:
        raise HTTPException(status_code=404, detail="Scene not found")

    job_dir = TEMP_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    prompt = f"{req.prompt.strip()}, variation {uuid.uuid4().hex[:6]}"
    scene.image_prompt = req.prompt.strip()
    scene.image_path = image_agent.fetch_scene_image(
        prompt=prompt,
        scene_num=scene.number,
        job_dir=job_dir,
        width=state.video_width,
        height=state.video_height,
        fit_mode=req.fit_mode,
    )
    return _job_status(state)


@app.get("/project/{job_id}", response_model=ProjectPayload)
def export_project(job_id: str):
    state = JOBS.get(job_id)
    if not state:
        raise HTTPException(status_code=404, detail="Job not found")
    return ProjectPayload(
        topic=state.topic,
        details=state.details,
        script_language=state.script_language,
        pronunciation_map=state.pronunciation_map,
        title=state.title,
        hook=state.hook,
        story=state.story,
        scenes=[_scene_payload(state, scene) for scene in state.scenes],
        settings=_job_status(state).model_dump(mode="json"),
    )


@app.post("/project", response_model=JobStatus)
def import_project(project: ProjectPayload):
    job_id = uuid.uuid4().hex[:8]
    settings = project.settings or {}
    state = create_state(
        topic=project.topic,
        job_id=job_id,
        details=project.details,
        script_language=project.script_language,
        pronunciation_map=project.pronunciation_map,
        video_width=int(settings.get("video_width", VIDEO_WIDTH)),
        video_height=int(settings.get("video_height", VIDEO_HEIGHT)),
        video_fps=int(settings.get("video_fps", VIDEO_FPS)),
        image_count=len(project.scenes) or int(settings.get("image_count", IMAGE_COUNT)),
        image_source=settings.get("image_source", "ai"),
        image_fit_mode=settings.get("image_fit_mode", "contain_blur"),
        voice_provider=settings.get("voice_provider", VOICE_PROVIDER),
        voice_name=settings.get("voice_name", VOICE_NAME),
        voice_rate=settings.get("voice_rate", VOICE_RATE),
        voice_pitch=settings.get("voice_pitch", "+0Hz"),
        subtitles_enabled=bool(settings.get("subtitles_enabled", SUBTITLES_ENABLED)),
        subtitle_font_size=int(settings.get("subtitle_font_size", SUBTITLE_FONT_SIZE)),
        transition_style=settings.get("transition_style", "crossfade"),
        transition_duration=float(settings.get("transition_duration", 0.45)),
        ken_burns_intensity=float(settings.get("ken_burns_intensity", 0.045)),
        render_quality=settings.get("render_quality", "balanced"),
        background_music=settings.get("background_music", "none"),
        background_music_volume=float(settings.get("background_music_volume", 0.08)),
    )
    state.title = project.title
    state.hook = project.hook
    state.story = project.story
    state.scenes = [
        Scene(
            number=i + 1,
            duration=scene.duration,
            narration=scene.narration,
            visual_desc=scene.visual_desc,
            image_prompt=scene.image_prompt,
            upload_image_index=scene.upload_image_index,
        )
        for i, scene in enumerate(project.scenes)
    ]
    state.status = "awaiting_confirmation" if state.scenes else "idle"
    state.progress = 52 if state.scenes else 0
    JOBS[job_id] = state
    return _job_status(state)


@app.post("/confirm/{job_id}", response_model=JobStatus)
def confirm(job_id: str, req: ConfirmRequest, background_tasks: BackgroundTasks):
    state = JOBS.get(job_id)
    if not state:
        raise HTTPException(status_code=404, detail="Job not found")
    if state.status != "awaiting_confirmation":
        raise HTTPException(status_code=409, detail=f"Job is not ready for confirmation: {state.status}")
    if not req.scenes:
        raise HTTPException(status_code=400, detail="At least one scene is required")
    if req.image_source == "upload" and not state.uploaded_image_paths:
        raise HTTPException(status_code=400, detail="Upload images before confirming with upload image mode")

    state.title = req.title.strip()
    state.hook = req.hook.strip()
    state.story = req.story.strip()
    _apply_render_settings(state, req)
    state.scenes = [
        Scene(
            number=i + 1,
            duration=scene.duration,
            narration=scene.narration.strip(),
            visual_desc=scene.visual_desc.strip(),
            image_prompt=(
                scene.image_prompt.strip()
                or f"{scene.visual_desc.strip()}, cinematic documentary photography, realistic, 4K"
            ),
            upload_image_index=scene.upload_image_index,
        )
        for i, scene in enumerate(req.scenes)
    ]
    state.image_count = len(state.scenes)
    state.status = "queued_for_render"
    state.progress = max(state.progress, 55)
    background_tasks.add_task(_run_render_job, job_id, req.upload_to_youtube)
    return _job_status(state)


@app.post("/generate", response_model=JobStatus)
def generate(req: GenerateRequest, background_tasks: BackgroundTasks):
    job_id = uuid.uuid4().hex[:8]
    state = _make_state(req, job_id)
    state.status = "queued"
    state.progress = 0
    JOBS[job_id] = state
    background_tasks.add_task(_run_full_job, job_id, req.upload_to_youtube)
    return _job_status(state)


@app.get("/status/{job_id}", response_model=JobStatus)
def status(job_id: str):
    state = JOBS.get(job_id)
    if not state:
        raise HTTPException(status_code=404, detail="Job not found")
    return _job_status(state)


@app.get("/download/{job_id}")
def download(job_id: str):
    state = JOBS.get(job_id)
    if not state or not state.captioned_path or not Path(state.captioned_path).exists():
        raise HTTPException(status_code=404, detail="Video not ready yet")
    return FileResponse(
        path=str(state.captioned_path),
        media_type="video/mp4",
        filename=_safe_download_name(state),
    )


@app.get("/thumbnail/{job_id}")
def thumbnail(job_id: str):
    state = JOBS.get(job_id)
    if not state or not state.thumbnail_path or not Path(state.thumbnail_path).exists():
        raise HTTPException(status_code=404, detail="Thumbnail not ready yet")
    return FileResponse(path=str(state.thumbnail_path), media_type="image/png")


@app.websocket("/ws/{job_id}")
async def websocket_progress(websocket: WebSocket, job_id: str):
    await websocket.accept()
    WS_CONNECTIONS.setdefault(job_id, []).append(websocket)

    try:
        while True:
            state = JOBS.get(job_id)
            if not state:
                await websocket.send_json({"status": "missing", "progress": 0})
                break
            await websocket.send_json(_job_status(state).model_dump(mode="json"))
            if state.status in ("done", "error", "awaiting_confirmation"):
                break
            import asyncio

            await asyncio.sleep(1.5)
    except WebSocketDisconnect:
        pass
    finally:
        connections = WS_CONNECTIONS.get(job_id, [])
        if websocket in connections:
            connections.remove(websocket)


@app.get("/")
def root():
    return {
        "message": "AI Crime Video Agent API",
        "workflow": ["/draft", "/status/{job_id}", "/confirm/{job_id}", "/download/{job_id}"],
        "docs": "/docs",
    }
