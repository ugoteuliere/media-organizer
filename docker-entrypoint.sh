#!/usr/bin/env bash
set -e

# Default PUID and PGID to 1000 if not provided
PUID=${PUID:-1000}
PGID=${PGID:-1000}

# Apply UMASK (default: 002 = group-writable)
umask "${UMASK:-002}"

if [ -d /config ] && [ ! -f /config/config.ini ]; then
    echo "No config file found in /config, copying sample one..." >&2
    cp /app/docker_sample_config /config/config.ini 2>/dev/null || true
fi

echo "Starting media-organizer..." >&2

if [ "$(id -u)" = "0" ]; then
    # Adjust group GID
    CURRENT_GID=$(id -g organizer 2>/dev/null || echo "")
    if [ -n "$CURRENT_GID" ] && [ "$CURRENT_GID" != "$PGID" ]; then
        groupmod -o -g "$PGID" organizer 2>/dev/null || true
    fi

    # Adjust user UID
    CURRENT_UID=$(id -u organizer 2>/dev/null || echo "")
    if [ -n "$CURRENT_UID" ] && [ "$CURRENT_UID" != "$PUID" ]; then
        usermod -o -u "$PUID" -g "$PGID" organizer 2>/dev/null || true
    fi

    # Ensure /config and /app/log directories have proper ownership for organizer
    [ -d /config ] && chown -R organizer:organizer /config 2>/dev/null || true
    [ -d /app/log ] && chown -R organizer:organizer /app/log 2>/dev/null || true

    
    # Dynamic volume path resolution (ConfigManager precedence: env vars -> config.ini -> defaults)
    DIAG_PATHS=$(python3 -c '
import configparser, os
cfg = configparser.ConfigParser()
if os.path.isfile("/config/config.ini"):
    try:
        cfg.read("/config/config.ini", encoding="utf-8")
    except Exception:
        pass
inp = os.environ.get("INPUT_FOLDER") or cfg.get("paths", "not_sorted_media_files_folder", fallback="/data/Downloads")
mov = os.environ.get("MOVIES_FOLDER") or cfg.get("paths", "movies_folder", fallback="/data/Movies")
tv = os.environ.get("TV_SHOWS_FOLDER") or cfg.get("paths", "tv_shows_folder", fallback="/data/TV_Shows")
print(inp)
print(mov)
print(tv)
' 2>/dev/null || printf "%s\n%s\n%s\n" "${INPUT_FOLDER:-/data/Downloads}" "${MOVIES_FOLDER:-/data/Movies}" "${TV_SHOWS_FOLDER:-/data/TV_Shows}")

    # T12: Startup Diagnostics
    echo "-------------------------------------"
    echo "media-organizer"
    echo "-------------------------------------"
    echo "UID: $PUID  GID: $PGID  UMASK: ${UMASK:-002}"
    if [ -f /config/config.ini ]; then echo "Config: /config/config.ini [found]"; else echo "Config: /config/config.ini [missing]"; fi
    echo "Volumes:"
    while IFS= read -r v; do
        [ -z "$v" ] && continue
        if [ -d "$v" ]; then
            if [ -w "$v" ]; then echo "  $v .. [OK: rw]"; else echo "  $v .. [ERROR: read-only]"; fi
        else
            echo "  $v .. [Missing]"
        fi
    done << EOF
$DIAG_PATHS
/config
/app/log
EOF
    echo "-------------------------------------"

    # If first argument is an existing command in PATH (like bash, sh, ffmpeg, ffprobe) and not a media-organizer subcommand
    if [ $# -gt 0 ] && command -v "$1" > /dev/null 2>&1 && [ "$1" != "config" ] && [ "$1" != "configure" ] && [ "$1" != "media-organizer" ]; then
        exec gosu organizer:organizer "$@"
    fi

    RUN_CMD="gosu organizer:organizer media-organizer"
else
    # Running directly as non-root
    if [ $# -gt 0 ] && command -v "$1" > /dev/null 2>&1 && [ "$1" != "config" ] && [ "$1" != "configure" ] && [ "$1" != "media-organizer" ]; then
        exec "$@"
    fi

    RUN_CMD="media-organizer"
fi

START_TIME=$(date +%s)
$RUN_CMD "$@" &
CHILD_PID=$!
trap 'kill -TERM "$CHILD_PID" 2>/dev/null' TERM INT
wait "$CHILD_PID" 2>/dev/null || true
EXIT_CODE=$?
END_TIME=$(date +%s)

if [ "$EXIT_CODE" -ne 0 ] && [ $((END_TIME - START_TIME)) -lt 5 ]; then
    printf "\033[31mmedia-organizer terminated unexpectedly with code %s within 5s. Waiting 30s cooldown before container termination to prevent rapid restart loops...\033[0m\n" "$EXIT_CODE" >&2
    sleep 30
fi
exit "$EXIT_CODE"
