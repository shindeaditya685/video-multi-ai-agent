"""
agents/04_prompt_agent.py
──────────────────────────
Prompt Engineering Agent
  Role  : Converts each scene's visual description into an optimised
          AI image generation prompt.
  Input : PipelineState.scenes (visual_desc per scene)
  Output: PipelineState.scenes[*].image_prompt populated
  Cost  : FREE (Groq)
"""

from __future__ import annotations
from core.config import PipelineState
from core import llm

SYSTEM_PROMPT = """
You are an expert at writing AI image generation prompts for true-crime
documentary videos. You convert scene descriptions into highly detailed,
cinematic prompts that produce realistic, atmospheric, moody images.

Prompt style rules:
- Always start with the subject and setting
- Include: lighting, mood, camera angle, time of day
- Style suffix: "cinematic documentary photography, realistic, 4K, moody lighting"
- Avoid: faces of real people, names, text in image, graphic violence
- Vary shot type across scenes: establishing wide, over-the-shoulder,
  evidence macro, empty corridor, silhouette, newspaper archive, courtroom detail
- Favor authentic Indian locations and textures when the case is India-specific
- Keep each prompt under 75 words
- Make it visual, not narrative

Return ONLY a JSON array of prompt strings (one per scene, in order):
["prompt for scene 1", "prompt for scene 2", ...]
"""


def run(state: PipelineState) -> PipelineState:
    print("\n[Agent 4/9] Prompt Engineering Agent - crafting image prompts...")
    state.status = "generating_prompts"
    state.progress = 44

    # Build list of scene visuals for the LLM
    scene_descs = "\n".join(
        f"Scene {s.number}: {s.visual_desc}"
        for s in state.scenes
    )

    prompts: list[str] = llm.chat_json(
        system=SYSTEM_PROMPT,
        user=f"""
Convert these {len(state.scenes)} documentary scene descriptions into
AI image generation prompts. Return exactly {len(state.scenes)} prompts
in a JSON array.

Documentary topic: {state.topic}
User direction: {state.details or "No extra direction provided."}
Tone: dark, moody, realistic, true-crime documentary

SCENES:
{scene_descs}
""",
        temperature=0.7,
        max_tokens=3000,
    )

    # Assign prompts back to scenes
    for i, scene in enumerate(state.scenes):
        if i < len(prompts):
            scene.image_prompt = prompts[i]
        else:
            # Fallback if LLM returns fewer prompts than scenes
            scene.image_prompt = (
                f"{scene.visual_desc}, cinematic documentary photography, "
                "realistic, 4K, moody lighting, dark atmosphere"
            )

    print(f"    Prompts  : {len(prompts)} prompts generated")
    print(f"    Sample   : {state.scenes[0].image_prompt[:80]}...")
    state.progress = 50
    return state
