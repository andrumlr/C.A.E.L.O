"""
Chat orchestration: mode selection → prompt assembly → LLM call.

Memory and voice can plug in here later (e.g. enrich `messages` or swap provider).
"""

from __future__ import annotations

import re

from core.config import get_settings
from core.mode_selector import select_mode
from core.prompt_builder import build_chat_messages
from db.persistence import save_exchange
from memory.short_term_buffer import (
    append_exchange,
    get_last_mode,
    get_recent_messages,
    set_last_mode,
)
from providers.claude_provider import ClaudeProvider
from providers.openai_provider import OpenAIProvider
from providers.ollama_provider import OllamaProvider, looks_like_internal_echo


def _build_provider() -> OllamaProvider | OpenAIProvider | ClaudeProvider:
    s = get_settings()
    p = s.provider.lower().strip()
    if p == "ollama":
        return OllamaProvider()
    if p == "openai":
        return OpenAIProvider()
    if p == "claude":
        return ClaudeProvider()
    raise ValueError(
        f"Unknown provider {s.provider!r} (CAELO_PROVIDER). "
        "Use 'ollama', 'openai', or 'claude'."
    )


_provider = _build_provider()

_PURE_PRESENCE_PATTERNS = (
    r"\b(?:don'?t|do not) fix (?:this|it|that|anything)\b",
    r"\bjust sit with me\b",
    r"\bsit with me\b",
    r"\bjust stay\b(?:\W|$)",
    r"\bjust be here\b",
    r"\bjust want you here\b",
    r"\bonly want you (?:here|there)\b",
    r"\bdon'?t want (?:advice|to explain)\b",
    r"\bno advice\b",
)

_FOLLOW_UP_HINTS = (
    r"^\s*keep going\.?\s*$",
    r"^\s*go on\.?\s*$",
    r"\bno[, ]+not\b",
    r"\bi mean\b",
    r"\bfirst move only\b",
    r"\bjust the first move\b",
    r"\bthat one\b",
    r"\bcontinue\b",
)


def _is_explicit_presence_request(text: str) -> bool:
    return any(re.search(p, text) for p in _PURE_PRESENCE_PATTERNS)


def _is_short_contextual_follow_up(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    if len(stripped) <= 80 and any(re.search(p, stripped) for p in _FOLLOW_UP_HINTS):
        return True
    return stripped.lower().startswith(("no,", "no ", "i mean "))


def _resolve_effective_mode(
    user_message: str,
    inferred_mode: str,
    previous_mode: str | None,
) -> str:
    """
    Keep execution threads in execution for short clarification/follow-up turns unless
    user explicitly requests presence.
    """
    text = user_message.lower()
    if _is_explicit_presence_request(text):
        return "presence"
    if (
        previous_mode == "execution"
        and inferred_mode == "presence"
        and _is_short_contextual_follow_up(text)
    ):
        return "execution"
    return inferred_mode


def run_chat(
    user_message: str,
    memory_context: str = "",
    *,
    conversation_id: str | None = None,
) -> dict:
    """
    Returns a dict suitable for JSON from `/chat/`:
    { "response": str, "mode": str } on success.

    Pass the same ``conversation_id`` across turns to enable short-term continuity
    (rolling in-memory window). Omit it for stateless requests.
    """
    inferred_mode = select_mode(user_message)
    previous_mode = get_last_mode(conversation_id)
    mode = _resolve_effective_mode(user_message, inferred_mode, previous_mode)
    recent_raw = get_recent_messages(conversation_id)
    # Skip any historical assistant turns that look like leaked internals.
    recent = [
        m
        for m in recent_raw
        if not (
            m.get("role") == "assistant"
            and looks_like_internal_echo((m.get("content") or "").strip())
        )
    ]
    messages = build_chat_messages(
        user_message,
        mode,
        memory_context=memory_context,
        recent_messages=recent,
    )
    text = _provider.generate_messages(messages)
    # Never persist leaked/system-looking output into short-term history.
    if text and not looks_like_internal_echo(text):
        append_exchange(conversation_id, user_message, text)
        save_exchange(conversation_id, user_message, text, mode)
        set_last_mode(conversation_id, mode)
    return {"response": text, "mode": mode}
