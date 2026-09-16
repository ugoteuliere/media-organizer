"""
Runtime configuration dataclass for media-organizer.

Replaces the 20+ module-level mutable globals that were scattered across
``src/ui.py`` and read via ``global`` statements.  A single typed
:class:`RuntimeConfig` instance is constructed once by
:func:`src.ui.parse_arguments` and then accessible everywhere via the
module-level :data:`runtime` singleton.

Tests create a fresh ``RuntimeConfig()`` instance and replace the singleton
via ``monkeypatch.setattr("src.runtime_config", "runtime", RuntimeConfig())``.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RuntimeConfig:
    """Holds every CLI-derived runtime flag for the current process."""

    # Logging
    log_enabled: bool = False
    log_mode: str = "console"  # "console" | "file" | "both"

    # Email
    mail_enabled: bool = False

    # Processing flags
    ai_fallback_enabled: bool = False
    learn_enabled: bool = False
    bypass_enabled: bool = False
    verbose_enabled: bool = False
    simulate_enabled: bool = False
    resolution_enabled: bool = False
    quality_enabled: bool = False

    # Notification flags
    notify_success_enabled: bool = False
    notify_error_enabled: bool = False
    notify_tag_enabled: bool = False

    # Daemon
    daemon_enabled: bool = False
    polling_interval: int = 15

    def reset(self) -> None:
        """Resets all fields to their defaults (used in tests)."""
        default = RuntimeConfig()
        for f in self.__dataclass_fields__:  # type: ignore[attr-defined]
            setattr(self, f, getattr(default, f))


# ── Module-level singleton ──────────────────────────────────────────────────
# Tests replace this with ``monkeypatch.setattr("src.runtime_config", "runtime", RuntimeConfig())``.
runtime = RuntimeConfig()
