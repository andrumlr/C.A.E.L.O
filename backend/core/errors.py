"""Turn exceptions into API-safe error dicts without leaking internals to the client."""

from __future__ import annotations

# RuntimeError/ValueError (and subclasses) in this codebase are deliberately raised
# with user-facing messages (see providers/claude_provider.py, services/document_service.py).
# Anything else is an unexpected bug — log it, don't echo its details to the caller.
_SAFE_EXCEPTION_TYPES = (RuntimeError, ValueError)


def safe_error_response(e: Exception, *, log_prefix: str) -> dict:
    if isinstance(e, _SAFE_EXCEPTION_TYPES):
        return {"error_type": type(e).__name__, "error_message": str(e)}
    print(f"[{log_prefix}] unexpected error: {type(e).__name__}: {e}")
    return {
        "error_type": "InternalError",
        "error_message": "Something went wrong processing your request.",
    }
