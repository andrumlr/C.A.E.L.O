from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Any

from core.config import Settings

_LEAK_MARKERS = (
    "## end of file",
    "# critical mode",
    "# execution mode",
    "# analysis mode",
    "# advisory mode",
    "# presence mode",
    "### execution",
    "output rules:",
    "threading:",
    "mode policy",
    "mode guidance",
    "long-term memory",
    "live response rules",
    "caelo — behavioral guide",
)

_INTERNAL_LINE = re.compile(
    r"^\s*(output rules:|threading:|mode:|mode policy|mode guidance|long-term memory|"
    r"##\s+|#\s+(analysis|execution|advisory|presence|critical)\s+mode|"
    r"response shape|behavior:|response style:)\b",
    re.IGNORECASE,
)


def looks_like_internal_echo(text: str) -> bool:
    low = text.lower()
    if any(m in low for m in _LEAK_MARKERS):
        return True
    return any(_INTERNAL_LINE.match(line.strip()) for line in text.splitlines())


def _scrub_echoed_prompt_artifacts(text: str) -> str:
    """Remove leaked internal prompt/mode artifacts from model output."""
    low = text.lower()
    cut_at = len(text)
    for m in _LEAK_MARKERS:
        i = low.find(m)
        if i != -1:
            cut_at = min(cut_at, i)
    out = text[:cut_at].rstrip()
    kept: list[str] = []
    for line in out.splitlines():
        s = line.strip()
        if not s:
            kept.append(line)
            continue
        if _INTERNAL_LINE.match(s):
            continue
        if s == "---":
            continue
        kept.append(line)
    cleaned = "\n".join(kept).strip()
    if not cleaned and looks_like_internal_echo(text):
        return "Let's continue from your last line. Give me one concrete detail and I will stay on that thread."
    return cleaned


class OllamaProvider:
    """Calls a local Ollama server (`/api/chat`, non-streaming)."""

    def __init__(self, settings: Settings | None = None) -> None:
        from core.config import get_settings

        self._settings = settings or get_settings()

    def generate_messages(self, messages: list[dict[str, str]], max_tokens: int = 4096) -> str:
        # max_tokens accepted for interface parity with ClaudeProvider (the
        # production provider); not applied to the Ollama call here.
        return _ollama_chat(
            base_url=self._settings.ollama_base_url,
            model=self._settings.ollama_model,
            messages=messages,
            timeout=self._settings.ollama_timeout_s,
        )


def _ollama_chat(
    base_url: str,
    model: str,
    messages: list[dict[str, str]],
    timeout: float,
) -> str:
    url = base_url.rstrip("/") + "/api/chat"
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": False,
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body: dict[str, Any] = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Ollama HTTP {e.code}: {err_body}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(
            "Cannot reach Ollama. Is `ollama serve` running? "
            f"Expected server at {base_url!s}. ({e.reason!s})"
        ) from e

    if err := body.get("error"):
        raise RuntimeError(f"Ollama error: {err}")

    msg = body.get("message") or {}
    content = msg.get("content")
    if not isinstance(content, str):
        raise RuntimeError("Unexpected Ollama response (no assistant text).")

    return _scrub_echoed_prompt_artifacts(content.strip())
