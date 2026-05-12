"""
core/llm.py — Shared LLM caller (Groq / LLaMA 3, free)
Robust JSON parsing that handles truncated or malformed responses.
"""

import json
import re
import textwrap
from groq import Groq
from core.config import GROQ_API_KEY, GROQ_MODEL


_client = None

def get_client():
    global _client
    if _client is None:
        if not GROQ_API_KEY or GROQ_API_KEY == "your_groq_api_key_here":
            raise ValueError(
                "Missing GROQ_API_KEY.\n"
                "Get a free key at https://console.groq.com and set it in .env"
            )
        _client = Groq(api_key=GROQ_API_KEY)
    return _client


def chat(system: str, user: str, temperature: float = 0.7, max_tokens: int = 4000) -> str:
    """Simple chat completion — returns the assistant's text."""
    resp = get_client().chat.completions.create(
        model=GROQ_MODEL,
        messages=[
            {"role": "system", "content": textwrap.dedent(system)},
            {"role": "user",   "content": user},
        ],
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return resp.choices[0].message.content.strip()


def _try_parse(text: str):
    """Try to parse JSON, return None on failure."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _repair_truncated_json(raw: str):
    """
    Attempt to repair truncated JSON arrays/objects by closing open structures.
    Handles the case where the LLM hits max_tokens mid-response.
    """
    raw = raw.strip()

    # Remove markdown fences
    if "```" in raw:
        for part in raw.split("```"):
            part = part.strip()
            if part.startswith("json"):
                part = part[4:].strip()
            result = _try_parse(part)
            if result is not None:
                return result

    # Direct parse first
    result = _try_parse(raw)
    if result is not None:
        return result

    # Find the outermost [ or {
    is_array = raw.lstrip().startswith("[")
    start_char = "[" if is_array else "{"
    end_char   = "]" if is_array else "}"

    start = raw.find(start_char)
    if start == -1:
        return None

    content = raw[start:]

    # Try progressively shorter substrings (remove last incomplete item)
    # Strategy: find last complete item by locating last "},\n" or "}\n"
    for pattern in ["},\n  {", "},\n{", "}\n  ,", "  },", "},"]:
        last_complete = content.rfind(pattern)
        if last_complete != -1:
            # Cut off after the last complete object
            truncated = content[:last_complete + 1]
            if is_array:
                truncated += "\n]"
            else:
                truncated += "\n}"
            result = _try_parse(truncated)
            if result is not None:
                print(f"    ⚠ JSON was truncated — recovered {len(result)} items")
                return result

    # Last resort: extract all complete {...} objects from array
    if is_array:
        objects = re.findall(r'\{[^{}]*\}', content, re.DOTALL)
        if objects:
            joined = "[" + ",".join(objects) + "]"
            result = _try_parse(joined)
            if result is not None:
                print(f"    ⚠ JSON repaired via extraction — got {len(result)} items")
                return result

    return None


def chat_json(system: str, user: str, temperature: float = 0.7, max_tokens: int = 4000):
    """
    Chat completion that expects and parses a JSON response.
    Handles truncation, malformed output, and markdown fences.
    Retries once with a higher max_tokens if first attempt is truncated.
    """
    for attempt in range(2):
        tokens = max_tokens if attempt == 0 else 6000
        raw = chat(system, user, temperature, tokens)

        result = _repair_truncated_json(raw)
        if result is not None:
            return result

        if attempt == 0:
            print(f"    ⚠ JSON parse failed, retrying with more tokens...")

    raise ValueError(
        f"Could not parse JSON from LLM response after 2 attempts.\n"
        f"Raw response (first 300 chars):\n{raw[:300]}"
    )