from __future__ import annotations

from core.config import Settings

from anthropic import (
    Anthropic,
    APIConnectionError,
    APIError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    PermissionDeniedError,
    RateLimitError,
)


def _split_system_and_messages(
    messages: list[dict[str, str]],
) -> tuple[str | None, list[dict[str, str]]]:
    system_chunks: list[str] = []
    rest: list[dict[str, str]] = []
    for m in messages:
        role = (m.get("role") or "").strip()
        content = m.get("content")
        text = content if isinstance(content, str) else ""
        if role == "system":
            if text.strip():
                system_chunks.append(text)
            continue
        if role in ("user", "assistant"):
            rest.append({"role": role, "content": text})
    system = "\n\n".join(system_chunks).strip() if system_chunks else None
    return system, rest


def _message_text_content(message: object) -> str:
    parts: list[str] = []
    content = getattr(message, "content", None)
    if not content:
        return ""
    for block in content:
        if getattr(block, "type", None) == "text":
            t = getattr(block, "text", None)
            if isinstance(t, str):
                parts.append(t)
    return "".join(parts).strip()


def _anthropic_messages(
    api_key: str,
    model: str,
    messages: list[dict[str, str]],
    max_tokens: int = 4096,
) -> str:
    if not (api_key or "").strip():
        raise RuntimeError(
            "Anthropic API key is missing. Set ANTHROPIC_API_KEY in the environment."
        )

    system, api_messages = _split_system_and_messages(messages)
    client = Anthropic(api_key=api_key.strip())
    try:
        kwargs: dict[str, object] = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": api_messages,
        }
        if system:
            kwargs["system"] = system
        response = client.messages.create(**kwargs)
    except AuthenticationError as e:
        raise RuntimeError(
            "Anthropic authentication failed. Check ANTHROPIC_API_KEY is set and valid."
        ) from e
    except PermissionDeniedError as e:
        raise RuntimeError(
            "Anthropic access was denied. Check your API key and organization permissions."
        ) from e
    except (APIConnectionError, APITimeoutError) as e:
        raise RuntimeError(
            "Cannot connect to the Anthropic API. Check your network, firewall, and that "
            f"api.anthropic.com is reachable. ({e})"
        ) from e
    except RateLimitError as e:
        raise RuntimeError(
            f"Anthropic rate limit reached. Back off and retry, or check your plan. ({e})"
        ) from e
    except APIStatusError as e:
        raise RuntimeError(
            f"Anthropic API request failed: HTTP {e.status_code} — {e.message}"
        ) from e
    except APIError as e:
        raise RuntimeError(f"Anthropic request failed: {e}") from e

    text = _message_text_content(response)
    if not text:
        raise RuntimeError("Anthropic returned an empty assistant message.")
    return text


class ClaudeProvider:
    """Calls Anthropic Messages API (non-streaming) via the official `anthropic` package."""

    def __init__(self, settings: Settings | None = None) -> None:
        from core.config import get_settings

        self._settings = settings or get_settings()

    def generate_messages(self, messages: list[dict[str, str]], max_tokens: int = 4096) -> str:
        return _anthropic_messages(
            api_key=self._settings.anthropic_api_key,
            model=self._settings.claude_model,
            messages=messages,
            max_tokens=max_tokens,
        )
