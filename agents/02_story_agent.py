"""
agents/02_story_agent.py
─────────────────────────
Story Writer Agent
  Role  : Transforms raw research into a gripping documentary narration script.
  Input : PipelineState.research (from Research Agent)
  Output: PipelineState.title, .hook, .story
  Style : True-crime documentary (think Netflix / HBO style)
  Cost  : FREE (Groq)
"""

from __future__ import annotations
import json
from core.config import PipelineState
from core import llm

LANGUAGE_NAMES = {
    "en": "English",
    "hi": "Hindi written in Devanagari script",
    "mr": "Marathi written in Devanagari script",
}

SYSTEM_PROMPT = """
You are an award-winning true-crime documentary scriptwriter.
You write in the style of Netflix true-crime documentaries — gripping,
cinematic, emotionally resonant, with suspense and moral weight.

Writing rules:
- Open with a chilling hook that drops the viewer into the scene
- Use present tense for immediacy ("The door opens. She doesn't know...")
- Build suspense through unanswered questions
- Humanize victims — give them dignity and depth
- Never sensationalize violence; suggest it, don't describe it graphically
- Each sentence should make the viewer lean forward
- Total length: 400-600 words
- Tone: serious, contemplative, documentary
- The JSON field names must stay in English.
- Write JSON values in the user-requested language.

Return ONLY valid JSON:
{
  "title": "Clickable YouTube title (max 60 chars, no clickbait caps)",
  "hook":  "Opening 1-2 sentences that drop viewers into the scene",
  "story": "Full documentary narration script (400-600 words)"
}
"""


def run(state: PipelineState) -> PipelineState:
    print("\n[Agent 2/9] Story Writer Agent - crafting documentary script...")
    state.status = "writing_story"
    state.progress = 20

    research_str = json.dumps(state.research, indent=2)
    language = LANGUAGE_NAMES.get(state.script_language, "English")

    result = llm.chat_json(
        system=SYSTEM_PROMPT,
        user=f"""
Using this research, write a compelling true-crime documentary script.

SCRIPT LANGUAGE:
{language}

Language rules:
- If Hindi or Marathi is selected, write natural Devanagari, not Romanized text.
- Keep names, places, and legal terms pronounced naturally for Indian audiences.
- Preserve factual accuracy while making narration sound locally fluent.
- Respect this pronunciation dictionary when writing names or aliases:
{state.pronunciation_map or "No pronunciation dictionary provided."}

RESEARCH:
{research_str}

TOPIC: {state.topic}

USER DIRECTION:
{state.details or "No extra direction provided."}
""",
        temperature=0.8,  # Higher temp for creative writing
        max_tokens=3000,
    )

    state.title = result.get("title", state.topic)
    state.hook  = result.get("hook", "")
    state.story = result.get("story", "")

    print(f"    Title    : {state.title}")
    print(f"    Hook     : {state.hook[:80]}...")
    print(f"    Story    : {len(state.story.split())} words generated")
    state.progress = 28
    return state
