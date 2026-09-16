# media-organizer

[![CI](https://github.com/ugoteuliere/media-organizer/actions/workflows/github-ci.yml/badge.svg)](https://github.com/ugoteuliere/media-organizer/actions/workflows/github-ci.yml)
[![Release](https://img.shields.io/github/v/release/ugoteuliere/media-organizer?color=blue)](https://github.com/ugoteuliere/media-organizer/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A CLI tool that parses video filenames, retrieves official titles via **The Movie Database (TMDB)**, and organizes files into Movie and TV Show directories according to **Plex naming conventions**.

When standard regex and parsing algorithms fail to identify heavily obfuscated filenames, the tool optionally falls back to Cloud AI providers (**Google Gemini**, **Groq Cloud**, **OpenRouter**, or **Cloudflare Workers AI**).

## Quick Start

### 1. Configuration

Configure storage folders, API keys, and options using either the graphical interface or the terminal wizard:

```bash
# Launch Graphical Configuration Tool (GUI)
media-organizer --gui

# Launch Terminal Wizard
media-organizer configure
```

### 2. Run

```bash
# Rename and sort media files
media-organizer
```

### 3. Docker (Container)

Run as an automated background daemon using the official GHCR container:

```bash
docker run -d \
  --name media-organizer \
  -e PUID=1000 -e PGID=1000 \
  -e TMDB_API_KEY="<your_tmdb_api_key>" \
  -v /path/to/downloads:/data/input \
  -v /path/to/movies:/data/Movies \
  -v /path/to/series:/data/TV_Shows \
  ghcr.io/ugoteuliere/media-organizer:latest
```

## Features

| Mode | Description |
| :--- | :--- |
| **Rename & Move** | Scans download folder, renames and moves items to Movies/TV Shows. |
| **Rename Only** | Renames files in a specific folder. |
| **Simulation** | Dry-run preview: prints proposed renames without modifying files on disk. |
| **Daemon** | Continuous background daemon polling download folder every X minutes. |
| **Docker Container** | Headless container deployment via GitHub Container Registry (`ghcr.io`). |
| **Cloud AI Fallback** | Uses Cloud AI models to resolve obfuscated filenames when local parsing fails. |
| **Keyword Learning** | Discovers missing release tags via AI and saves them. |

## Documentation

See the [Full Documentation](docs/documentation.md).

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.