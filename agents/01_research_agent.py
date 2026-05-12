"""
agents/01_research_agent.py
────────────────────────────
Research Agent
  Role  : Collects structured details about the crime case/topic.
  Input : Raw topic string  (e.g. "The Muskan murder case 2023")
  Output: Structured research dict stored in PipelineState.research
  Tools : Groq LLaMA 3 (knowledge base) + optional web search
  Cost  : FREE
"""

from __future__ import annotations
import json
from core.config import PipelineState
from core import llm

SYSTEM_PROMPT = """
You are a senior investigative journalist and documentary researcher.
Your job is to collect ALL known facts about a crime case and return them
as structured JSON. Be accurate. If you don't know something, use "unknown".

Return ONLY valid JSON — no markdown, no preamble — in this exact shape:
{
  "case_name":       "Official or common name of the case",
  "year":            "Year(s) the events took place",
  "location":        "City, State/Country",
  "victim":          { "name": "", "age": "", "background": "" },
  "suspect":         { "name": "", "age": "", "relationship_to_victim": "" },
  "crime_type":      "murder | kidnapping | fraud | etc.",
  "timeline": [
    { "date": "...", "event": "..." }
  ],
  "key_evidence":    ["evidence 1", "evidence 2"],
  "investigation":   "How the case was investigated (2-3 sentences)",
  "verdict":         "Final court verdict or current status",
  "motive":          "Known or suspected motive",
  "public_reaction": "How the public/media reacted",
  "documentary_angle": "The most emotionally compelling angle for a documentary"
}
"""


def run(state: PipelineState) -> PipelineState:
    print("\n[Agent 1/9] Research Agent - collecting case details...")
    state.status = "researching"
    state.progress = 5

    extra_details = (
        f"\n\nAdditional user-provided context and direction:\n{state.details}"
        if state.details
        else ""
    )

    research = llm.chat_json(
        system=SYSTEM_PROMPT,
        user=f"Research this crime case in depth: {state.topic}{extra_details}",
        temperature=0.3,  # Low temp for factual accuracy
        max_tokens=2000,
    )

    state.research = research

    print(f"    Case     : {research.get('case_name', state.topic)}")
    print(f"    Location : {research.get('location', 'unknown')}")
    print(f"    Crime    : {research.get('crime_type', 'unknown')}")
    print(f"    Timeline : {len(research.get('timeline', []))} events collected")
    state.progress = 15
    return state
