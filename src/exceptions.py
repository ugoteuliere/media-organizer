"""
Custom exception hierarchy for media-organizer.

Replaces bare ``RuntimeError`` and ``sys.exit()`` calls inside library
functions so that callers (including ``main()``) can handle failures
gracefully through typed exceptions instead of process termination.
"""

from __future__ import annotations


class MediaOrganizerError(Exception):
    """Base class for all media-organizer runtime errors."""


class ConfigurationError(MediaOrganizerError, ValueError):
    """Raised when required configuration is missing or invalid."""


class APIError(MediaOrganizerError, ValueError, RuntimeError):
    """Raised when an external API call fails unrecoverably."""


class FileOperationError(MediaOrganizerError, OSError, RuntimeError):
    """Raised when a filesystem operation (rename/move/delete) fails."""


class FolderNotFoundError(FileOperationError, FileNotFoundError):
    """Raised when a required media folder is absent on disk."""


class PermissionError_(FileOperationError, PermissionError):  # noqa: N818 – not shadowing builtin directly
    """Raised when the process lacks read/write permission on a folder."""
