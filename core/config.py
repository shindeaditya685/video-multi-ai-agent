"""
core/config.py — Shared configuration and state across all agents
"""

import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR   = Path(__file__).parent.parent
OUTPUT_DIR = BASE_DIR / os.getenv("OUTPUT_DIR", "output")
TEMP_DIR   = BASE_DIR / os.getenv("TEMP_DIR", "temp")
TEMP_DIR.mkdir(exist_ok=True)

try:
    OUTPUT_DIR.mkdir(exist_ok=True)
    _write_test = OUTPUT_DIR / ".write_test"
    _write_test.write_text("", encoding="utf-8")
    _write_test.unlink(missing_ok=True)
except OSError:
    OUTPUT_DIR = TEMP_DIR / "output"
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ── LLM ──────────────────────────────────────────────────────────────────────
GROQ_API_KEY  = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL    = os.getenv("GROQ_MODEL", "llama3-70b-8192")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
SCRIPT_LANGUAGE = os.getenv("SCRIPT_LANGUAGE", "en")

# ── Voice ─────────────────────────────────────────────────────────────────────
VOICE_NAME  = os.getenv("VOICE_NAME", "en-US-GuyNeural")
VOICE_RATE  = os.getenv("VOICE_RATE", "+0%")
VOICE_PITCH = os.getenv("VOICE_PITCH", "+0Hz")
VOICE_PROVIDER = os.getenv("VOICE_PROVIDER", "edge")
GTTS_TLD = os.getenv("GTTS_TLD", "co.in")

# ── Image ─────────────────────────────────────────────────────────────────────
IMAGE_PROVIDER    = os.getenv("IMAGE_PROVIDER", "pollinations")
STABILITY_API_KEY = os.getenv("STABILITY_API_KEY", "")
IMAGE_SOURCE      = os.getenv("IMAGE_SOURCE", "ai")
IMAGE_FIT_MODE    = os.getenv("IMAGE_FIT_MODE", "contain_blur")

# ── Video ─────────────────────────────────────────────────────────────────────
VIDEO_WIDTH           = int(os.getenv("VIDEO_WIDTH", 1280))
VIDEO_HEIGHT          = int(os.getenv("VIDEO_HEIGHT", 720))
VIDEO_FPS             = int(os.getenv("VIDEO_FPS", 24))
IMAGE_COUNT           = int(os.getenv("IMAGE_COUNT", 12))
TRANSITION_DURATION   = float(os.getenv("TRANSITION_DURATION", 0.5))
TRANSITION_STYLE      = os.getenv("TRANSITION_STYLE", "crossfade")
KEN_BURNS_INTENSITY   = float(os.getenv("KEN_BURNS_INTENSITY", 0.045))
RENDER_QUALITY        = os.getenv("RENDER_QUALITY", "balanced")
BACKGROUND_MUSIC      = os.getenv("BACKGROUND_MUSIC", "none")
BACKGROUND_MUSIC_VOLUME = float(os.getenv("BACKGROUND_MUSIC_VOLUME", 0.08))
COLOR_GRADE           = os.getenv("COLOR_GRADE", "cinematic_warm")  # cinematic_warm | cinematic_cool | documentary | none
THUMBNAIL_BADGE       = os.getenv("THUMBNAIL_BADGE", "")  # Auto-detect if empty
INTRO_ENABLED         = os.getenv("INTRO_ENABLED", "true").lower() not in ("0", "false", "no")
OUTRO_ENABLED         = os.getenv("OUTRO_ENABLED", "true").lower() not in ("0", "false", "no")

# ── Whisper ───────────────────────────────────────────────────────────────────
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "base")
SUBTITLES_ENABLED = os.getenv("SUBTITLES_ENABLED", "true").lower() not in ("0", "false", "no")
SUBTITLE_FONT_SIZE = int(os.getenv("SUBTITLE_FONT_SIZE", 18))

# ── YouTube ───────────────────────────────────────────────────────────────────
YOUTUBE_CLIENT_SECRETS = os.getenv("YOUTUBE_CLIENT_SECRETS_FILE", "client_secrets.json")
YOUTUBE_CATEGORY_ID    = os.getenv("YOUTUBE_CATEGORY_ID", "25")
YOUTUBE_PRIVACY        = os.getenv("YOUTUBE_PRIVACY", "private")


# ── Shared pipeline state ─────────────────────────────────────────────────────

@dataclass
class Scene:
    """Represents one scene in the video."""
    number:       int
    duration:     float          # seconds
    narration:    str            # spoken text
    visual_desc:  str            # visual description
    image_prompt: str            # AI image generation prompt
    image_path:   Optional[Path] = None
    audio_path:   Optional[Path] = None
    subtitle_srt: Optional[str]  = None
    upload_image_index: Optional[int] = None


@dataclass
class PipelineState:
    """Shared state passed through all agents in the pipeline."""
    topic:          str = ""
    job_id:         str = ""
    details:        str = ""
    script_language: str = SCRIPT_LANGUAGE  # en | hi | mr
    pronunciation_map: str = ""

    # User-selected render settings
    video_width:    int = VIDEO_WIDTH
    video_height:   int = VIDEO_HEIGHT
    video_fps:      int = VIDEO_FPS
    image_count:    int = IMAGE_COUNT
    upload_to_youtube: bool = False
    image_source:   str = IMAGE_SOURCE       # ai | upload
    image_fit_mode: str = IMAGE_FIT_MODE     # contain_blur | cover
    uploaded_image_paths: list[Path] = field(default_factory=list)
    voice_provider: str = VOICE_PROVIDER     # edge | gtts
    voice_name:     str = VOICE_NAME
    voice_rate:     str = VOICE_RATE
    voice_pitch:    str = VOICE_PITCH
    gtts_tld:       str = GTTS_TLD
    subtitles_enabled: bool = SUBTITLES_ENABLED
    subtitle_font_size: int = SUBTITLE_FONT_SIZE
    transition_style: str = TRANSITION_STYLE  # crossfade | fade | none | slide_left | slide_right | wipe | zoom
    transition_duration: float = TRANSITION_DURATION
    ken_burns_intensity: float = KEN_BURNS_INTENSITY
    render_quality: str = RENDER_QUALITY  # preview | balanced | final
    background_music: str = BACKGROUND_MUSIC  # none | suspense | ambient | emotional
    background_music_volume: float = BACKGROUND_MUSIC_VOLUME
    color_grade:      str = COLOR_GRADE       # cinematic_warm | cinematic_cool | documentary | none
    thumbnail_badge:  str = THUMBNAIL_BADGE    # Auto-detect genre if empty
    intro_enabled:    bool = INTRO_ENABLED
    outro_enabled:    bool = OUTRO_ENABLED

    # Research
    research:       dict = field(default_factory=dict)

    # Story
    title:          str = ""
    hook:           str = ""
    story:          str = ""

    # Scenes
    scenes:         list[Scene] = field(default_factory=list)

    # Outputs
    voice_path:     Optional[Path] = None   # merged narration
    video_path:     Optional[Path] = None   # raw video (no captions)
    captioned_path: Optional[Path] = None   # final with captions
    thumbnail_path: Optional[Path] = None
    srt_path:       Optional[Path] = None   # soft SRT subtitle file

    # Upload results
    youtube_url:    str = ""
    progress:       int = 0   # 0-100
    status:         str = "idle"
    errors:         list[str] = field(default_factory=list)