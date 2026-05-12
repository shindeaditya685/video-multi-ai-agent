"""
agents/03_scene_agent.py
─────────────────────────
Scene Breakdown Agent
  Role  : Splits the documentary story into timed, visual scenes.
  Input : PipelineState.story
  Output: PipelineState.scenes  (list of Scene objects)
  Cost  : FREE (Groq)
"""

from __future__ import annotations
import json
from core.config import PipelineState, Scene
from core import llm

LANGUAGE_NAMES = {
    "en": "English",
    "hi": "Hindi in Devanagari",
    "mr": "Marathi in Devanagari",
}

SYSTEM_PROMPT = """
You are a documentary film director and editor.
Your job is to break a narration script into 12-16 cinematic scenes.

Each scene needs:
- A short narration chunk (1-3 sentences, max 30 words) — the exact words spoken
- A vivid visual description of what the viewer sees on screen
- A realistic duration (4-8 seconds based on narration length)

Rules:
- Scenes should flow cinematically — each one leads to the next
- Vary pacing: some short (4s) for impact, some longer (8s) for atmosphere
- Visuals should be CINEMATIC — think documentary B-roll, not literal

Return ONLY a JSON array:
[
  {
    "scene":       1,
    "duration":    6,
    "narration":   "Exact spoken words for this scene.",
    "visual_desc": "What the viewer sees — mood, setting, action, lighting"
  }
]
"""


def run(state: PipelineState) -> PipelineState:
    print("\n[Agent 3/9] Scene Breakdown Agent - splitting story into scenes...")
    state.status = "breaking_scenes"
    state.progress = 32
    scene_count = max(1, min(int(state.image_count or 12), 24))
    language = LANGUAGE_NAMES.get(state.script_language, "English")
    system_prompt = SYSTEM_PROMPT.replace(
        "break a narration script into 12-16 cinematic scenes",
        f"break a narration script into exactly {scene_count} cinematic scenes",
    )

    raw_scenes = llm.chat_json(
        system=system_prompt,
        user=f"""
Break this documentary script into exactly {scene_count} cinematic scenes.
This count controls the number of generated images in the final video.

Narration language: {language}
Keep every scene narration in that language/script.
Write visual_desc in English so image generation prompts remain high quality.

TITLE: {state.title}

SCRIPT:
{state.story}
""",
        temperature=0.6,
        max_tokens=3000,
    )

    raw_scenes = raw_scenes[:scene_count]

    state.scenes = [
        Scene(
            number=i + 1,
            duration=float(s.get("duration", 6)),
            narration=s["narration"],
            visual_desc=s.get("visual_desc", ""),
            image_prompt="",  # Filled by Prompt Agent next
        )
        for i, s in enumerate(raw_scenes)
    ]

    total_duration = sum(s.duration for s in state.scenes)
    print(f"    Scenes   : {len(state.scenes)} scenes created")
    print(f"    Duration : ~{total_duration:.0f} seconds ({total_duration/60:.1f} min)")
    for s in state.scenes[:3]:
        print(f"    Scene {s.number}  : {s.narration[:60]}...")

    state.progress = 40
    return state
