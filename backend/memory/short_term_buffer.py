"""
In-memory rolling window of recent user/assistant turns per conversation_id.

Server restart clears history. For production, swap this backend for Redis/DB later.
"""

from __future__ import annotations

import threading
from collections import deque
from typing import Final

_LOCK = threading.Lock()
# conversation_id -> deque of {"role": "user"|"assistant", "content": str}
_STORE: dict[str, deque[dict[str, str]]] = {}
_LAST_MODE: dict[str, str] = {}

_MAX_MESSAGES: Final[int] = 24  # up to 12 back-and-forth turns
_MAX_ID_LEN: Final[int] = 256


def _normalize_id(conversation_id: str | None) -> str | None:
    if conversation_id is None:
        return None
    cid = conversation_id.strip()
    if not cid:
        return None
    return cid[:_MAX_ID_LEN]


def get_recent_messages(conversation_id: str | None) -> list[dict[str, str]]:
    """Return a shallow copy of stored messages (oldest first)."""
    cid = _normalize_id(conversation_id)
    if not cid:
        return []
    with _LOCK:
        dq = _STORE.get(cid)
        if not dq:
            return []
        return list(dq)


def get_last_mode(conversation_id: str | None) -> str | None:
    cid = _normalize_id(conversation_id)
    if not cid:
        return None
    with _LOCK:
        return _LAST_MODE.get(cid)


def set_last_mode(conversation_id: str | None, mode: str) -> None:
    cid = _normalize_id(conversation_id)
    if not cid:
        return
    with _LOCK:
        _LAST_MODE[cid] = mode


def append_exchange(
    conversation_id: str | None,
    user_content: str,
    assistant_content: str,
) -> None:
    """Append one user turn and one assistant turn after a successful reply."""
    cid = _normalize_id(conversation_id)
    if not cid:
        return
    with _LOCK:
        dq = _STORE.setdefault(cid, deque(maxlen=_MAX_MESSAGES))
        dq.append({"role": "user", "content": user_content})
        dq.append({"role": "assistant", "content": assistant_content})
