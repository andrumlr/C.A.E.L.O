from __future__ import annotations

from core.config import Settings
from providers.ollama_provider import _scrub_echoed_prompt_artifacts

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    OpenAI,
    OpenAIError,
    PermissionDeniedError,
    RateLimitError,
)


def _openai_chat(
    api_key: str,
    model: str,
    messages: list[dict[str, str]],
) -> str:
    if not (api_key or "").strip():
        raise RuntimeError(
            "OpenAI API key is missing. Set OPENAI_API_KEY in the environment."
        )

    client = OpenAI(api_key=api_key.strip())
    try:
        completion = client.chat.completions.create(
            model=model,
            messages=messages,
        )
    except AuthenticationError as e:
        raise RuntimeError(
            "OpenAI authentication failed. Check OPENAI_API_KEY is set and valid."
        ) from e
    except PermissionDeniedError as e:
        raise RuntimeError(
            "OpenAI access was denied. Check your API key and organization permissions."
        ) from e
    except (APIConnectionError, APITimeoutError) as e:
        raise RuntimeError(
            "Cannot connect to the OpenAI API. Check your network, firewall, and that "
            f"api.openai.com is reachable. ({e})"
        ) from e
    except RateLimitError as e:
        raise RuntimeError(
            f"OpenAI rate limit reached. Back off and retry, or check your plan. ({e})"
        ) from e
    except APIStatusError as e:
        raise RuntimeError(
            f"OpenAI API request failed: HTTP {e.status_code} — {e.message}"
        ) from e
    except OpenAIError as e:
        raise RuntimeError(f"OpenAI request failed: {e}") from e

    if not completion.choices:
        raise RuntimeError("OpenAI returned no completion choices.")
    msg = completion.choices[0].message
    if not msg or msg.content is None:
        raise RuntimeError("OpenAI returned an empty assistant message.")
    content = (msg.content or "").strip()
    if not content:
        raise RuntimeError("OpenAI returned an empty assistant message.")
    return _scrub_echoed_prompt_artifacts(content)


class OpenAIProvider:
    """Calls OpenAI chat completions (non-streaming) via the official `openai` package."""

    def __init__(self, settings: Settings | None = None) -> None:
        from core.config import get_settings

        self._settings = settings or get_settings()

    def generate_messages(self, messages: list[dict[str, str]], max_tokens: int = 4096) -> str:
        # max_tokens accepted for interface parity with ClaudeProvider (the
        # production provider); not applied to the OpenAI call here.
        return _openai_chat(
            api_key=self._settings.openai_api_key,
            model=self._settings.openai_model,
            messages=messages,
        )
