# syntax=docker/dockerfile:1
FROM python:3.11-slim-bookworm

# Set container environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    RENAME_CONFIG_FILE=/config/config.ini \
    PUID=1000 \
    PGID=1000

# Install system dependencies:
# - ffmpeg / ffprobe: audio/video stream inspection (resolution/quality tags)
# - gosu: clean permission dropping from root to PUID/PGID
# - ca-certificates: TLS verification for TMDB and cloud AI APIs
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    gosu \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Set up working directory and default non-root user
WORKDIR /app
RUN groupadd -r -g 1000 renamer && useradd -r -u 1000 -g renamer -m -d /home/renamer renamer

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application assets, source code, and entrypoint
COPY data/ /app/data/
COPY src/ /app/src/
COPY main.py /app/main.py
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh

# Set entrypoint permissions and create volume mount points
RUN sed -i -e 's/\r$//' /usr/local/bin/docker-entrypoint.sh \
    && chmod +x /usr/local/bin/docker-entrypoint.sh \
    && mkdir -p /config /data/Movies /data/TV_Shows /data/input \
    && chown -R renamer:renamer /config /data /app

COPY docker_sample_config /config/config.ini
COPY docker_sample_config /app/docker_sample_config

RUN printf '#!/bin/sh\nexec python /app/main.py "$@"\n' > /usr/local/bin/organizer \
    && chmod +x /usr/local/bin/organizer

VOLUME ["/config", "/data/Movies", "/data/TV_Shows", "/data/input"]

ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["--help"]
