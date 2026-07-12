"""
Chat orchestration: mode selection → prompt assembly → LLM call.

Memory and voice can plug in here later (e.g. enrich `messages` or swap provider).
"""

from __future__ import annotations

import re

from core.config import get_settings
from core.mode_selector import select_mode
from core.prompt_builder import build_chat_messages
from db.persistence import save_exchange, get_recent_messages_from_db, get_last_message_age_seconds
from memory.core_values import get_active_core_values, propose_core_value
from memory.fact_extractor import maybe_extract_facts
from memory.facts import get_active_facts, format_facts_for_prompt
from memory.summary_generator import maybe_generate_summary, get_current_summary
from memory.short_term_buffer import (
    append_exchange,
    get_last_mode,
    get_recent_messages,
    set_last_mode,
)
from providers.claude_provider import ClaudeProvider
from providers.openai_provider import OpenAIProvider
from providers.ollama_provider import OllamaProvider, looks_like_internal_echo
from services.document_service import save_image


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
    image: dict | None = None,
) -> dict:
    """
    Returns a dict suitable for JSON from `/chat/`:
    { "response": str, "mode": str } on success.

    Pass the same ``conversation_id`` across turns to enable short-term continuity
    (rolling in-memory window). Omit it for stateless requests.

    ``image`` (optional) is a dict with ``media_type``, ``data`` (base64),
    ``bytes`` (decoded), and ``filename``. When present, Caelo reacts to it
    conversationally (no forced fact extraction on this path); the image is
    persisted so it also appears in the Images tab, and history stores a text
    placeholder — never base64.
    """
    if not memory_context.strip():
        memory_context = format_facts_for_prompt(get_active_facts())

    active_core_values = get_active_core_values()

    # An image-only turn still needs a mode; treat the empty text as a light
    # presence turn so mode selection has something to work with.
    mode_input = user_message or "[shared an image]"
    inferred_mode = select_mode(mode_input)
    previous_mode = get_last_mode(conversation_id)
    mode = _resolve_effective_mode(mode_input, inferred_mode, previous_mode)
    db_recent = get_recent_messages_from_db(limit=20)
    if db_recent:
        recent_raw = db_recent
    else:
        recent_raw = get_recent_messages(conversation_id)

    # How long since the previous message — measured before this turn is saved,
    # so Caelo can tell a quick reply from a days-later one.
    last_message_age_seconds = get_last_message_age_seconds()

    # Skip any historical assistant turns that look like leaked internals.
    recent = [
        m
        for m in recent_raw
        if not (
            m.get("role") == "assistant"
            and looks_like_internal_echo((m.get("content") or "").strip())
        )
    ]
    summary_text = get_current_summary()

    # Text the model actually sees for this turn. An image can arrive with no
    # caption, so give the model a light nudge to react in-voice.
    model_text = user_message
    if image is not None and not model_text:
        model_text = "(The user shared an image without a caption.)"

    messages = build_chat_messages(
        model_text,
        mode,
        memory_context=memory_context,
        recent_messages=recent,
        summary_text=summary_text,
        last_message_age_seconds=last_message_age_seconds,
        active_core_values=active_core_values,
    )

    images_arg = None
    if image is not None:
        images_arg = [{"media_type": image["media_type"], "data": image["data"]}]
        # Persist the shared image so it also appears in the Images tab. No fact
        # extraction on this path — this is a conversational reaction, not ingest.
        try:
            save_image(image["filename"], image["bytes"])
        except Exception as e:  # persistence must never break the chat reply
            print(f"[conversation_service] save_image failed: {e}")

    text = _provider.generate_messages(messages, max_tokens=1024, images=images_arg)

    # Caelo may propose a value to his own core by writing a line starting with
    # "Add to core:". Capture it as a pending value, but leave the line untouched
    # in the reply/history — the user still sees it. Never let this break the chat.
    try:
        for line in (text or "").splitlines():
            stripped = line.strip()
            if stripped.lower().startswith("add to core:"):
                proposed = stripped[len("add to core:"):].strip()
                if proposed:
                    propose_core_value(proposed)
    except Exception as e:
        print(f"[conversation_service] core value capture failed: {e}")

    # History stores a text placeholder for shared images — never base64.
    history_user_text = user_message
    if image is not None:
        history_user_text = (f"{user_message}\n[shared an image]").strip() if user_message else "[shared an image]"

    # Never persist leaked/system-looking output into short-term history.
    if text and not looks_like_internal_echo(text):
        append_exchange(conversation_id, history_user_text, text)
        save_exchange(conversation_id, history_user_text, text, mode)
        maybe_generate_summary()
        maybe_extract_facts()
        set_last_mode(conversation_id, mode)
    return {"response": text, "mode": mode}
