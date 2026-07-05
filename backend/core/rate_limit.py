"""Simple in-memory per-IP rate limiting for expensive/public endpoints.

Single-process, in-memory window — adequate for a low-traffic single-instance
deployment. Not a substitute for real auth if this ever serves multiple users.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from threading import Lock

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

_WINDOW_SECONDS = 60
# Keyed by (method, path) — only the expensive write endpoints are limited;
# read-only listing endpoints (GET /documents/, /conversations/) are unrestricted.
_LIMITS: dict[tuple[str, str], int] = {
    ("POST", "/chat/"): 20,
    ("POST", "/documents/"): 6,
}

_lock = Lock()
_hits: dict[tuple[str, str], deque] = defaultdict(deque)


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        limit = _LIMITS.get((request.method, request.url.path))
        if limit is not None:
            key = (request.url.path, _client_ip(request))
            now = time.monotonic()
            with _lock:
                bucket = _hits[key]
                while bucket and now - bucket[0] > _WINDOW_SECONDS:
                    bucket.popleft()
                if len(bucket) >= limit:
                    return JSONResponse(
                        status_code=429,
                        content={
                            "error_type": "RateLimitExceeded",
                            "error_message": "Too many requests. Please slow down and try again shortly.",
                        },
                    )
                bucket.append(now)
        return await call_next(request)
