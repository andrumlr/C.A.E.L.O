"""Shared-secret gate for the public API. Not per-user auth — just a door key."""

from __future__ import annotations

from fastapi import Header, HTTPException, status

from core.config import get_settings


async def require_api_key(x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> None:
    expected = get_settings().api_key
    if not expected:
        # No key configured (e.g. local dev) — leave the endpoint open.
        return
    if not x_api_key or x_api_key != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid API key.",
        )
