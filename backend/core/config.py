"""
Runtime configuration from environment variables.

Ollama defaults match a local install: http://127.0.0.1:11434
"""

from __future__ import annotations

import os
from dataclasses import dataclass


def _env_str(name: str, default: str) -> str:
    v = os.environ.get(name)
    return v.strip() if v and v.strip() else default


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return float(raw)
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    ollama_base_url: str
    ollama_model: str
    ollama_timeout_s: float


def get_settings() -> Settings:
    return Settings(
        ollama_base_url=_env_str("OLLAMA_BASE_URL", "http://127.0.0.1:11434"),
        ollama_model=_env_str("OLLAMA_MODEL", "llama3.1:8b"),
        ollama_timeout_s=_env_float("OLLAMA_TIMEOUT_S", 120.0),
    )
