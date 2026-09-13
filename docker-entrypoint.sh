#!/usr/bin/env bash
set -e

# Default PUID and PGID to 1000 if not provided
PUID=${PUID:-1000}
PGID=${PGID:-1000}

if [ ! -f /config/config.ini ]; then
    echo "No config file found, copying sample one..."
    cp /app/docker_sample_config /config/config.ini
fi

echo "Starting media organizer..."

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

    # Ensure /config directory has proper ownership for renamer
    [ -d /config ] && chown -R renamer:renamer /config 2>/dev/null || true

    if [ "${RUN_AS_ROOT:-false}" = "true" ]; then
        echo "WARNING: Running as root because RUN_AS_ROOT=true"
        exec organizer "$@"
    fi

    # If first argument is an existing command in PATH (like bash, sh, ffmpeg, ffprobe) and not a renamer subcommand
    if command -v "$1" > /dev/null 2>&1 && [ "$1" != "config" ] && [ "$1" != "configure" ]; then
        exec gosu renamer:renamer "$@"
    fi

    exec gosu renamer:renamer organizer "$@"
else
    # Running directly as non-root
    if command -v "$1" > /dev/null 2>&1 && [ "$1" != "config" ] && [ "$1" != "configure" ]; then
        exec "$@"
    fi

    exec organizer "$@"
fi
