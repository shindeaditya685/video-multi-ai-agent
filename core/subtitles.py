"""Subtitle text formatting shared by video and subtitle agents."""

from __future__ import annotations

from dataclasses import dataclass
import re


@dataclass(frozen=True)
class SubtitleCue:
    start: float
    end: float
    text: str


_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?।])\s+")
_CLAUSE_SPLIT_RE = re.compile(r"(?<=[,;:])\s+")


def normalize_subtitle_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def _wrap_words(text: str, max_chars: int) -> list[str]:
    words = text.split()
    if not words:
        return []

    lines: list[str] = []
    current = ""
    for word in words:
        if not current:
            current = word
            continue
        candidate = f"{current} {word}"
        if len(candidate) <= max_chars:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def split_subtitle_text(text: str, language: str = "en", max_chars: int | None = None) -> list[str]:
    """Split narration into readable one- or two-line subtitle cue texts."""
    normalized = normalize_subtitle_text(text)
    if not normalized:
        return []

    limit = max_chars or (36 if language in ("hi", "mr") else 48)
    sentences: list[str] = []
    for sentence in _SENTENCE_SPLIT_RE.split(normalized):
        sentence = sentence.strip()
        if not sentence:
            continue
        if len(sentence) <= limit * 2:
            sentences.append(sentence)
            continue
        sentences.extend(part.strip() for part in _CLAUSE_SPLIT_RE.split(sentence) if part.strip())

    lines: list[str] = []
    for sentence in sentences:
        if len(sentence) <= limit:
            lines.append(sentence)
        else:
            lines.extend(_wrap_words(sentence, limit))

    cues: list[str] = []
    for idx in range(0, len(lines), 2):
        cues.append("\n".join(lines[idx:idx + 2]))
    return cues


def scene_subtitle_cues(
    text: str,
    start: float,
    duration: float,
    language: str = "en",
    max_chars: int | None = None,
) -> list[SubtitleCue]:
    parts = split_subtitle_text(text, language=language, max_chars=max_chars)
    if not parts:
        return []

    duration = max(0.5, float(duration or 0.5))
    total_weight = sum(max(1, len(part.replace("\n", " "))) for part in parts)
    cursor = float(start)
    end_limit = cursor + duration
    cues: list[SubtitleCue] = []

    for idx, part in enumerate(parts):
        if idx == len(parts) - 1:
            end = end_limit
        else:
            weight = max(1, len(part.replace("\n", " ")))
            cue_duration = duration * (weight / total_weight)
            end = min(end_limit, cursor + max(0.45, cue_duration))
        if end > cursor:
            cues.append(SubtitleCue(start=cursor, end=end, text=part))
        cursor = end
    return cues
