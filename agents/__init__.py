# agents/__init__.py
import importlib.util
import sys
from pathlib import Path

_AGENTS_DIR = Path(__file__).parent  # this is the /agents/ folder

def _load(filename):
    spec = importlib.util.spec_from_file_location(
        filename,
        _AGENTS_DIR / f"{filename}.py"
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[filename] = mod
    spec.loader.exec_module(mod)
    return mod

agent_01_research  = _load("01_research_agent")
agent_02_story     = _load("02_story_agent")
agent_03_scene     = _load("03_scene_agent")
agent_04_prompt    = _load("04_prompt_agent")
agent_05_voice     = _load("05_voice_agent")
agent_06_image     = _load("06_image_agent")
agent_07_video     = _load("07_video_agent")
agent_08_subtitle  = _load("08_subtitle_agent")
agent_09_thumbnail = _load("09_thumbnail_agent")
agent_10_upload    = _load("10_upload_agent")