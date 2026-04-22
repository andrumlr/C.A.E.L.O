from __future__ import annotations

import re
from typing import Final

MODE_ANALYSIS: Final = "analysis"
MODE_EXECUTION: Final = "execution"
MODE_ADVISORY: Final = "advisory"
MODE_PRESENCE: Final = "presence"
MODE_CRITICAL: Final = "critical"

_MODES: Final[tuple[str, ...]] = (
    MODE_ANALYSIS,
    MODE_EXECUTION,
    MODE_ADVISORY,
    MODE_PRESENCE,
    MODE_CRITICAL,
)


def normalize_mode(name: str | None) -> str | None:
    if not name:
        return None
    key = name.strip().lower()
    return key if key in _MODES else None


def select_mode(user_message: str, explicit_mode: str | None = None) -> str:
    """
    Choose a behavior mode. explicit_mode wins when it is a known mode name;
    otherwise heuristics on user_message apply. Default is presence.
    """
    if explicit := normalize_mode(explicit_mode):
        return explicit
    text = user_message.strip().lower()
    if not text:
        return MODE_PRESENCE

    if _matches_critical(text):
        return MODE_CRITICAL
    # Before execution: phrases like "don't fix this" still contain the word "fix".
    if _matches_presence_intent(text):
        return MODE_PRESENCE
    if _matches_execution(text):
        return MODE_EXECUTION
    if _matches_advisory(text):
        return MODE_ADVISORY
    if _matches_analysis(text):
        return MODE_ANALYSIS
    return MODE_PRESENCE


def _just_stay_presence(text: str) -> bool:
    """Treat 'just stay' as presence, not e.g. 'just stay focused'."""
    m = re.search(r"\bjust stay\b", text)
    if not m:
        return False
    tail = text[m.end() :].lstrip()
    if not tail:
        return True
    if tail[0] in ".,;:!?…":
        return True
    low = tail.lower()
    return low.startswith("with me") or low.startswith("here")


def _matches_presence_intent(text: str) -> bool:
    """
    Explicit steadiness / no-fix — wins over execution heuristics that match 'fix'.
    """
    if re.search(r"\b(?:don'?t|do not) fix (?:this|it|that|anything)\b", text):
        return True
    if re.search(r"\bjust sit with me\b", text):
        return True
    if re.search(r"\bsit with me\b", text):
        return True
    if re.search(r"\bjust be here\b", text):
        return True
    if re.search(r"\bjust want you here\b", text) or re.search(
        r"\bonly want you (?:here|there)\b", text
    ):
        return True
    if re.search(r"\bdon'?t want to explain\b", text):
        return True
    if re.search(r"\bno advice\b", text) or re.search(r"\bdon'?t want advice\b", text):
        return True
    return _just_stay_presence(text)


def _matches_critical(text: str) -> bool:
    patterns = (
        r"\b(wrong|incorrect|dangerous|unsafe|risky|critical|urgent)\b",
        r"\b(must not|do not|never do|serious risk|legal liability)\b",
        r"\b(data loss|security breach|exploit|vulnerability)\b",
    )
    return any(re.search(p, text) for p in patterns)


def _matches_execution(text: str) -> bool:
    patterns = (
        r"\b(run|execute|deploy|implement|build|fix|install|configure)\b",
        r"\b(step by step|commands? to|how do i (do|run|fix))\b",
        r"\b(give me the (code|snippet|script|command))\b",
        r"\b(first move only|give me the first move|first move)\b",
        r"\b(too much to do|no time|not enough time)\b",
        r"\bdeadline\b",
        r"\b(i need a|give me a|what('?s| is) the) plan\b",
        r"\b(help me decide|decide fast)\b",
        r"\bwhat matters (right now|now)\b",
        r"\btriage\b",
    )
    return any(re.search(p, text) for p in patterns)


def _matches_advisory(text: str) -> bool:
    patterns = (
        r"\b(should i|would you recommend|which (option|one)|vs\.? |versus)\b",
        r"\b(trade-?offs?|pros and cons|better choice)\b",
        r"\b(what would you (pick|choose))\b",
    )
    return any(re.search(p, text) for p in patterns)


def _matches_analysis(text: str) -> bool:
    patterns = (
        r"\b(analyze|analyse|break down|architecture|design|why does)\b",
        r"\b(explain how|root cause|deep dive|compare in detail)\b",
        r"\b(how does .{3,40} work)\b",
    )
    return any(re.search(p, text) for p in patterns)
