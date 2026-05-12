"""
Main pipeline orchestrator.

The project supports two modes:
- full automation: topic -> final video
- reviewed workflow: draft script/scenes -> user confirms -> render video
"""

from __future__ import annotations

import argparse
import sys
import time
import traceback
import uuid

from colorama import Fore, Style, init

init(autoreset=True)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except AttributeError:
    pass

from agents import (
    agent_01_research as research_agent,
    agent_02_story as story_agent,
    agent_03_scene as scene_agent,
    agent_04_prompt as prompt_agent,
    agent_05_voice as voice_agent,
    agent_06_image as image_agent,
    agent_07_video as video_agent,
    agent_08_subtitle as subtitle_agent,
    agent_09_thumbnail as thumbnail_agent,
    agent_10_upload as upload_agent,
)
from core.config import (
    COLOR_GRADE,
    IMAGE_COUNT,
    IMAGE_FIT_MODE,
    IMAGE_SOURCE,
    INTRO_ENABLED,
    KEN_BURNS_INTENSITY,
    OUTRO_ENABLED,
    OUTPUT_DIR,
    THUMBNAIL_BADGE,
    BACKGROUND_MUSIC,
    BACKGROUND_MUSIC_VOLUME,
    RENDER_QUALITY,
    SCRIPT_LANGUAGE,
    SUBTITLE_FONT_SIZE,
    SUBTITLES_ENABLED,
    TRANSITION_DURATION,
    TRANSITION_STYLE,
    VIDEO_FPS,
    VIDEO_HEIGHT,
    VIDEO_WIDTH,
    VOICE_NAME,
    VOICE_PITCH,
    VOICE_PROVIDER,
    VOICE_RATE,
    PipelineState,
)


PIPELINE = [
    ("Research", research_agent),
    ("Story", story_agent),
    ("Scenes", scene_agent),
    ("Prompts", prompt_agent),
    ("Voice", voice_agent),
    ("Images", image_agent),
    ("Video", video_agent),
    ("Subtitles", subtitle_agent),
    ("Thumbnail", thumbnail_agent),
    ("Upload", upload_agent),
]

DRAFT_PIPELINE = PIPELINE[:4]
RENDER_PIPELINE = PIPELINE[4:]
CRITICAL_STAGES = {"Research", "Story", "Scenes", "Prompts", "Voice", "Images", "Video"}


def _print_banner(topic: str):
    print(Fore.CYAN + "=" * 62)
    print(Fore.CYAN + "  FREE AI CRIME VIDEO AGENT")
    print(Fore.CYAN + "=" * 62)
    print(f"  Topic  : {Fore.YELLOW}{topic}")
    print(f"  Output : {Fore.YELLOW}{OUTPUT_DIR}")
    print(Fore.CYAN + "=" * 62 + Style.RESET_ALL)


def _print_summary(state: PipelineState, elapsed: float):
    print(Fore.GREEN + "\n" + "=" * 62)
    print(Fore.GREEN + "  PIPELINE COMPLETE")
    print(Fore.GREEN + "=" * 62)
    print(f"  Title     : {state.title}")
    print(f"  Scenes    : {len(state.scenes)}")
    print(f"  Video     : {state.captioned_path}")
    print(f"  Thumbnail : {state.thumbnail_path}")
    if state.srt_path:
        print(f"  SRT       : {state.srt_path}")
    if state.youtube_url:
        print(f"  YouTube   : {Fore.CYAN}{state.youtube_url}")
    if state.errors:
        print(Fore.YELLOW + f"  Warnings  : {len(state.errors)} non-fatal errors")
        for error in state.errors:
            print(Fore.YELLOW + f"    - {error}")
    print(f"  Time      : {elapsed:.1f} seconds")
    print(Fore.GREEN + "=" * 62 + Style.RESET_ALL)


def create_state(
    topic: str,
    job_id: str | None = None,
    details: str = "",
    script_language: str = SCRIPT_LANGUAGE,
    pronunciation_map: str = "",
    video_width: int = VIDEO_WIDTH,
    video_height: int = VIDEO_HEIGHT,
    video_fps: int = VIDEO_FPS,
    image_count: int = IMAGE_COUNT,
    upload_to_youtube: bool = False,
    image_source: str = IMAGE_SOURCE,
    image_fit_mode: str = IMAGE_FIT_MODE,
    voice_provider: str = VOICE_PROVIDER,
    voice_name: str = VOICE_NAME,
    voice_rate: str = VOICE_RATE,
    voice_pitch: str = VOICE_PITCH,
    subtitles_enabled: bool = SUBTITLES_ENABLED,
    subtitle_font_size: int = SUBTITLE_FONT_SIZE,
    transition_style: str = TRANSITION_STYLE,
    transition_duration: float = TRANSITION_DURATION,
    ken_burns_intensity: float = KEN_BURNS_INTENSITY,
    render_quality: str = RENDER_QUALITY,
    background_music: str = BACKGROUND_MUSIC,
    background_music_volume: float = BACKGROUND_MUSIC_VOLUME,
    color_grade: str = COLOR_GRADE,
    thumbnail_badge: str = THUMBNAIL_BADGE,
    intro_enabled: bool = INTRO_ENABLED,
    outro_enabled: bool = OUTRO_ENABLED,
) -> PipelineState:
    return PipelineState(
        topic=topic,
        job_id=job_id or uuid.uuid4().hex[:8],
        details=details,
        script_language=script_language,
        pronunciation_map=pronunciation_map,
        video_width=video_width,
        video_height=video_height,
        video_fps=video_fps,
        image_count=image_count,
        upload_to_youtube=upload_to_youtube,
        image_source=image_source,
        image_fit_mode=image_fit_mode,
        voice_provider=voice_provider,
        voice_name=voice_name,
        voice_rate=voice_rate,
        voice_pitch=voice_pitch,
        subtitles_enabled=subtitles_enabled,
        subtitle_font_size=subtitle_font_size,
        transition_style=transition_style,
        transition_duration=transition_duration,
        ken_burns_intensity=ken_burns_intensity,
        render_quality=render_quality,
        background_music=background_music,
        background_music_volume=background_music_volume,
        color_grade=color_grade,
        thumbnail_badge=thumbnail_badge,
        intro_enabled=intro_enabled,
        outro_enabled=outro_enabled,
    )


def _run_steps(
    state: PipelineState,
    steps: list[tuple[str, object]],
    skip_upload: bool = True,
) -> PipelineState:
    for name, agent in steps:
        try:
            if agent is upload_agent:
                state = agent.run(state, skip_upload=skip_upload)
            else:
                state = agent.run(state)

            print(Fore.GREEN + f"    OK {name} agent done [{state.progress}%]")

        except Exception as exc:
            state.errors.append(f"{name}: {exc}")
            state.status = "error"
            print(Fore.RED + f"\n  ERROR {name} agent failed: {exc}")
            traceback.print_exc()

            if name in CRITICAL_STAGES:
                raise RuntimeError(f"{name} agent failed: {exc}") from exc

            print(Fore.YELLOW + f"  Continuing despite {name} failure...")

    return state


def run_draft_from_state(state: PipelineState) -> PipelineState:
    state.status = "drafting"
    state = _run_steps(state, DRAFT_PIPELINE, skip_upload=True)
    state.status = "awaiting_confirmation"
    state.progress = max(state.progress, 52)
    return state


def run_render_from_state(state: PipelineState, skip_upload: bool = True) -> PipelineState:
    state.status = "rendering"
    state = _run_steps(state, RENDER_PIPELINE, skip_upload=skip_upload)
    state.status = "done"
    state.progress = 100
    return state


def run_full_from_state(state: PipelineState, skip_upload: bool = True) -> PipelineState:
    state = run_draft_from_state(state)
    state = run_render_from_state(state, skip_upload=skip_upload)
    return state


def run_pipeline(
    topic: str,
    job_id: str | None = None,
    skip_upload: bool = True,
    details: str = "",
    script_language: str = SCRIPT_LANGUAGE,
    pronunciation_map: str = "",
    video_width: int = VIDEO_WIDTH,
    video_height: int = VIDEO_HEIGHT,
    video_fps: int = VIDEO_FPS,
    image_count: int = IMAGE_COUNT,
    image_source: str = IMAGE_SOURCE,
    image_fit_mode: str = IMAGE_FIT_MODE,
    voice_provider: str = VOICE_PROVIDER,
    voice_name: str = VOICE_NAME,
    voice_rate: str = VOICE_RATE,
    voice_pitch: str = VOICE_PITCH,
    subtitles_enabled: bool = SUBTITLES_ENABLED,
    subtitle_font_size: int = SUBTITLE_FONT_SIZE,
    transition_style: str = TRANSITION_STYLE,
    transition_duration: float = TRANSITION_DURATION,
    ken_burns_intensity: float = KEN_BURNS_INTENSITY,
    render_quality: str = RENDER_QUALITY,
    background_music: str = BACKGROUND_MUSIC,
    background_music_volume: float = BACKGROUND_MUSIC_VOLUME,
) -> PipelineState:
    _print_banner(topic)
    start = time.time()
    state = create_state(
        topic=topic,
        job_id=job_id,
        details=details,
        script_language=script_language,
        pronunciation_map=pronunciation_map,
        video_width=video_width,
        video_height=video_height,
        video_fps=video_fps,
        image_count=image_count,
        upload_to_youtube=not skip_upload,
        image_source=image_source,
        image_fit_mode=image_fit_mode,
        voice_provider=voice_provider,
        voice_name=voice_name,
        voice_rate=voice_rate,
        voice_pitch=voice_pitch,
        subtitles_enabled=subtitles_enabled,
        subtitle_font_size=subtitle_font_size,
        transition_style=transition_style,
        transition_duration=transition_duration,
        ken_burns_intensity=ken_burns_intensity,
        render_quality=render_quality,
        background_music=background_music,
        background_music_volume=background_music_volume,
    )
    state = run_full_from_state(state, skip_upload=skip_upload)
    _print_summary(state, time.time() - start)
    return state


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Free AI Crime Video Agent - generates YouTube-ready videos from a topic."
    )
    parser.add_argument(
        "topic",
        nargs="?",
        default="The Nirbhaya case 2012 - India's landmark rape and murder case",
        help="Crime case topic (quoted string)",
    )
    parser.add_argument(
        "--details",
        default="",
        help="Extra direction for research, script, tone, or angle",
    )
    parser.add_argument("--language", choices=["en", "hi", "mr"], default=SCRIPT_LANGUAGE)
    parser.add_argument(
        "--upload",
        action="store_true",
        help="Upload to YouTube after generation (requires client_secrets.json)",
    )
    parser.add_argument("--job-id", default=None, help="Custom job ID")
    parser.add_argument("--width", type=int, default=VIDEO_WIDTH, help="Video width")
    parser.add_argument("--height", type=int, default=VIDEO_HEIGHT, help="Video height")
    parser.add_argument("--fps", type=int, default=VIDEO_FPS, help="Video frame rate")
    parser.add_argument("--images", type=int, default=IMAGE_COUNT, help="Number of scenes/images")
    parser.add_argument("--image-source", choices=["ai", "upload"], default=IMAGE_SOURCE)
    parser.add_argument("--voice-provider", choices=["edge", "gtts"], default=VOICE_PROVIDER)
    parser.add_argument("--voice-name", default=VOICE_NAME)
    parser.add_argument("--no-subtitles", action="store_true", help="Skip burned subtitles")
    parser.add_argument("--subtitle-size", type=int, default=SUBTITLE_FONT_SIZE)
    parser.add_argument("--transition", choices=["crossfade", "fade", "none", "slide_left", "slide_right", "wipe", "zoom"], default=TRANSITION_STYLE)
    parser.add_argument("--quality", choices=["preview", "balanced", "final"], default=RENDER_QUALITY)
    parser.add_argument("--music", choices=["none", "suspense", "ambient", "emotional"], default=BACKGROUND_MUSIC)
    parser.add_argument("--color-grade", choices=["cinematic_warm", "cinematic_cool", "documentary", "none"], default=COLOR_GRADE)
    parser.add_argument("--thumbnail-badge", default=THUMBNAIL_BADGE)
    parser.add_argument("--no-intro", action="store_true", help="Skip intro title card")
    parser.add_argument("--no-outro", action="store_true", help="Skip outro credits")

    args = parser.parse_args()

    try:
        run_pipeline(
            topic=args.topic,
            job_id=args.job_id,
            skip_upload=not args.upload,
            details=args.details,
            script_language=args.language,
            video_width=args.width,
            video_height=args.height,
            video_fps=args.fps,
            image_count=args.images,
            image_source=args.image_source,
            voice_provider=args.voice_provider,
            voice_name=args.voice_name,
            subtitles_enabled=not args.no_subtitles,
            subtitle_font_size=args.subtitle_size,
            transition_style=args.transition,
            render_quality=args.quality,
            background_music=args.music,
            color_grade=args.color_grade,
            thumbnail_badge=args.thumbnail_badge,
            intro_enabled=not args.no_intro,
            outro_enabled=not args.no_outro,
        )
    except Exception as exc:
        print(Fore.RED + f"Pipeline failed: {exc}")
        sys.exit(1)