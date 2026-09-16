"""
Public API façade for media-organizer.

This module re-exports the public symbols from the two specialist modules
created by the A3 refactor:
- :mod:`src.tmdb_api` — TMDB REST API client
- :mod:`src.ai_api`   — Multi-cloud AI batch inference

Import from here for backward-compatible access; the underlying
implementations live in the sub-modules.
"""

from __future__ import annotations

import sys
import types

import requests
from google import genai
from data.data import TAGS

from src.config import config
from src.ui import print_error, print_log
from src.tags import tag_manager

# ── Re-exports from tmdb_api ─────────────────────────────────────────────────
from src.tmdb_api import api_call

# ── Re-exports from ai_api ───────────────────────────────────────────────────
from src.ai_api import (
    ParsedMediaItem,
    BatchMediaResponse,
    is_quota_or_rate_limit_error,
    get_available_providers,
    get_prioritized_providers,
    build_batch_user_prompt,
    call_gemini_batch,
    call_groq_batch,
    call_openrouter_batch,
    call_cloudflare_batch,
    execute_ai_batch_with_failover,
    gemini_api_call,
)

__all__ = [
    "api_call",
    "ParsedMediaItem",
    "BatchMediaResponse",
    "is_quota_or_rate_limit_error",
    "get_available_providers",
    "get_prioritized_providers",
    "build_batch_user_prompt",
    "call_gemini_batch",
    "call_groq_batch",
    "call_openrouter_batch",
    "call_cloudflare_batch",
    "execute_ai_batch_with_failover",
    "gemini_api_call",
    "tag_manager",
    "config",
    "print_error",
    "print_log",
    "requests",
    "genai",
    "TAGS",
]

_AI_FUNCS = {
    "get_available_providers",
    "get_prioritized_providers",
    "build_batch_user_prompt",
    "call_gemini_batch",
    "call_groq_batch",
    "call_openrouter_batch",
    "call_cloudflare_batch",
    "execute_ai_batch_with_failover",
    "gemini_api_call",
}

_CONFIG_KEYS = {
    "TMDB_API_KEY",
    "GEMINI_API_KEY",
    "GROQ_API_KEY",
    "OPENROUTER_API_KEY",
    "CLOUDFLARE_API_TOKEN",
    "CLOUDFLARE_ACCOUNT_ID",
}


class _ApiModule(types.ModuleType):
    def __getattr__(self, name: str):
        if name in _CONFIG_KEYS:
            from src.config import config

            return getattr(config, name, None)
        if name == "config":
            from src.config import config

            return config
        from src import ai_api, tmdb_api

        if hasattr(ai_api, name):
            return getattr(ai_api, name)
        if hasattr(tmdb_api, name):
            return getattr(tmdb_api, name)
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    def __setattr__(self, name: str, value):
        if name in _CONFIG_KEYS:
            from src.config import config

            setattr(config, name, value)
        elif name in _AI_FUNCS:
            from src import ai_api

            setattr(ai_api, name, value)
        super().__setattr__(name, value)


sys.modules[__name__].__class__ = _ApiModule
