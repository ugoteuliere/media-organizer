#!/usr/bin/env bash
set -e

# Default PUID and PGID to 1000 if not provided
PUID=${PUID:-1000}
PGID=${PGID:-1000}

if [ -d /config ] && [ ! -f /config/config.ini ]; then
    echo "No config file found in /config, copying sample one..." >&2
    cp /app/docker_sample_config /config/config.ini 2>/dev/null || true
fi

echo "Starting media organizer..." >&2

if [ "$(id -u)" = "0" ]; then
    # Adjust group GID
    CURRENT_GID=$(id -g renamer 2>/dev/null || echo "")
    if [ -n "$CURRENT_GID" ] && [ "$CURRENT_GID" != "$PGID" ]; then
        groupmod -o -g "$PGID" renamer 2>/dev/null || true
    fi

    # Adjust user UID
    CURRENT_UID=$(id -u renamer 2>/dev/null || echo "")
    if [ -n "$CURRENT_UID" ] && [ "$CURRENT_UID" != "$PUID" ]; then
        usermod -o -u "$PUID" -g "$PGID" renamer 2>/dev/null || true
    fi

    # Ensure /config and /app/log directories have proper ownership for renamer
    [ -d /config ] && chown -R renamer:renamer /config 2>/dev/null || true
    [ -d /app/log ] && chown -R renamer:renamer /app/log 2>/dev/null || true

    # If first argument is an existing command in PATH (like bash, sh, ffmpeg, ffprobe) and not a renamer subcommand
    if [ $# -gt 0 ] && command -v "$1" > /dev/null 2>&1 && [ "$1" != "config" ] && [ "$1" != "configure" ]; then
        exec gosu renamer:renamer "$@"
    fi

    exec gosu renamer:renamer organizer "$@"
else
    # Running directly as non-root
    if [ $# -gt 0 ] && command -v "$1" > /dev/null 2>&1 && [ "$1" != "config" ] && [ "$1" != "configure" ]; then
        exec "$@"
    fi

    exec organizer "$@"
fi
