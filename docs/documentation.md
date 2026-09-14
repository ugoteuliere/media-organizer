# Documentation

Technical guide and reference for the Media Organizer & Renamer.

## Table of Contents

1. [Folder Structure & Plex Standards](#1-folder-structure--plex-standards)
2. [Configuration](#2-configuration)
   - [Configuration Tool](#configuration-tool)
   - [Configuration File](#configuration-file)
   - [Obtaining API Keys](#obtaining-api-keys)
   - [Setup Email Notifications](#setup-email-notifications)
   - [Command-Line Configuration (Inspect & Update)](#command-line-configuration-inspect--update)
3. [Modes](#3-modes)
   - [Default: Rename & Move](#default-rename--move)
   - [Rename Only](#rename-only)
   - [Simulation Mode](#simulation-mode)
   - [Daemon Background Watcher](#daemon-background-watcher)
4. [Options & CLI Flags](#4-options--cli-flags)
5. [Matching & Multi-Cloud AI Architecture](#5-matching--multi-cloud-ai-architecture)
   - [Metadata Extraction Pipeline](#metadata-extraction-pipeline)
   - [TMDB Match Probability Scorer](#tmdb-match-probability-scorer)
6. [Keyword Management](#6-keyword-management)
7. [Docker Deployment](#7-docker-deployment)
   - [Volumes & Permissions](#volumes--permissions)
   - [Docker Run (CLI)](#docker-run-cli)
   - [Docker Compose](#docker-compose)



## 1. Folder Structure & Plex Standards

The application operates on three directories:
* **Downloads folder** (`paths.not_sorted_media_files_folder`): incoming, unsorted media files.
* **Movies folder** (`paths.movies_folder`): destination directory for processed movies.
* **TV Shows folder** (`paths.tv_shows_folder`): destination directory for processed series.

These folders are independent and can be located anywhere on local storage, external drives, or SMB/NFS network shares.

### Plex Standard Formatting
Processed files follow official Plex naming conventions:
* **Movies**: `Title (Year).ext` or `Title (Year) [Resolution Quality].ext`
* **TV Shows**: `Show Name/Season XX/Show Name - SXXEXX.ext`

## 2. Configuration

### Configuration Tool
Launch the graphical settings window:
```bash
media-organizer --gui
```

For headless environments or SSH sessions, run the terminal wizard:
```bash
media-organizer configure
```

### Configuration File

Default file location:
* **Windows**: `%APPDATA%\rename\config.ini`
* **Linux / macOS**: `~/.config/rename/config.ini`

```ini
[paths]
movies_folder = /media/storage/Movies
tv_shows_folder = /media/storage/TV_Shows
not_sorted_media_files_folder = /media/storage/.downloads

[api]
tmdb_api_key = your_tmdb_api_key
gemini_api_key = your_gemini_api_key
groq_api_key = your_groq_api_key
openrouter_api_key = your_openrouter_api_key
cloudflare_api_token = your_cloudflare_api_token
cloudflare_account_id = your_cloudflare_account_id

[options]
ai_provider = auto
tmdb_min_confidence = 0.75
ai_min_confidence = 0.70
resolution = false
quality = false
bypass = false
daemon = false
polling_interval = 15
ai = false
learn = false
log = false
verbose = false
notify_on_success = false
notify_on_error = true
notify_on_tag = false

[mail]
mail = your_email@gmail.com
mail_pswd = your_16_char_app_password
```

### Obtaining API Keys

* **TMDB** (`api.tmdb_api_key`): Create a free account at [themoviedb.org](https://www.themoviedb.org/) > **Settings** > **API** > generate an **API Key (v3 auth)**.
* **Google Gemini** (`api.gemini_api_key`): Visit [Google AI Studio](https://aistudio.google.com/app/apikey) and click **Create API Key**.
* **Groq** (`api.groq_api_key`): Sign up at [Groq Console](https://console.groq.com/keys) and click **Create API Key** (`gsk_...`).
* **OpenRouter** (`api.openrouter_api_key`): Register at [OpenRouter](https://openrouter.ai/settings/keys) and create a key (set a $0.00 credit limit to only use free models).
* **Cloudflare Workers AI**: In the [Cloudflare Dashboard](https://dash.cloudflare.com/):
  - **Account ID** (`api.cloudflare_account_id`): Found on the right sidebar of the dashboard overview.
  - **API Token** (`api.cloudflare_api_token`): Go to **My Profile** > **API Tokens** > create a token with **Workers AI** permissions (`cfut_...`).

### Setup Email Notifications
1. Enable **2-Step Verification** on your [Google Account](https://myaccount.google.com/security).
2. Generate a 16-character **App Password** under Account Security > App Passwords.

### Command-Line Configuration (Inspect & Update)

```bash
# List all settings
media-organizer config --list

# Print active config file path
media-organizer config --path

# Get a specific value
media-organizer config --get paths.movies_folder

# Set a specific value
media-organizer config --set paths.movies_folder "D:/Media/Movies"

# Unset / delete a configuration key
media-organizer config --unset api.gemini_api_key
```

## 3. Modes

### Default: Rename & Move
Scans incoming downloads, queries TMDB, prompts for user confirmation, renames files, and moves them to destination folders.
```bash
media-organizer
```

### Rename Only
Renames files in-place without moving them to destination directories.
```bash
media-organizer --only-rename
```

### Simulation Mode
Previews proposed renames and destination paths without writing to disk or sending emails.
```bash
media-organizer --simulate
```

### Daemon Background Watcher
The daemon polls the download folder periodically.
```bash
media-organizer --daemon --interval 15
```

## 4. Options & CLI Flags

| Flag | Long Option | Config Key | Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `-s` | `--simulate` | — | `false` | Dry-run simulation preview. |
| `-r` | `--only-rename` | — | `false` | Renames files in-place without moving them. |
| `-d` | `--daemon` | `options.daemon` | `false` | Runs background watcher daemon. |
| — | `--once`, `--no-daemon` | — | `false` | Runs once and exits immediately, overriding `daemon = true`. |
| — | `--interval <min>` | `options.polling_interval` | `15` | Polling interval for daemon mode (minutes). |
| `-b` | `--bypass` | `options.bypass` | `false` | Bypasses interactive confirmation prompts. |
| `-a` | `--ai` | `options.ai` | `false` | Enables Cloud AI fallback for unrecognizable filenames. |
| `-L` | `--learn` | `options.learn` | `false` | Enables keyword learning to save newly discovered tags. |
| — | `--provider <p>` | `options.ai_provider` | `auto` | Selects AI provider (`auto`, `gemini`, `groq`, `openrouter`, `cloudflare`). |
| `-R` | `--resolution` | `options.resolution` | `false` | Appends video resolution tags (`[1080p]`, `[4K]`). Requires `ffprobe`. |
| `-q` | `--quality` | `options.quality` | `false` | Appends video quality tags (`[BluRay]`, `[WEB-DL]`). Requires `ffprobe`. |
| `-l` | `--log` | `options.log` | `false` | Writes console output to `log/YYYY-MM-DD.txt` (auto-pruned after 14 days). |
| `-v` | `--verbose` | `options.verbose` | `false` | Displays full error stack traces on failure. |
| — | `--notify-success` | `options.notify_on_success` | `false` | Sends email notification on successful processing. |
| — | `--notify-error` | `options.notify_on_error` | `true` | Sends email notification when an error occurs. |
| `-t` | `--notify-tag` | `options.notify_on_tag` | `false` | Sends email notification when a new keyword tag is learned. |
| — | `--path="<dir>"` | — | Incoming dir | Targets a specific folder. |

## 5. Matching & Multi-Cloud AI Architecture

```
Raw Filename 
    │
    ▼
[Regex & PTN Sanitization] ──► [TMDB Metadata Query]
                                         │
                                         ▼
                             [Match Probability Scorer]
                                         │
                        ┌────────────────┴────────────────┐
                        │ Probability >= 0.75             │ Probability < 0.75
                        ▼                                 ▼
                 [Accept Match]                 [Queue for AI Batch]
                                                           │
                                                           ▼
                                             [Multi-Cloud AI Orchestrator]
                                             (Gemini / Groq / OpenRouter / Cloudflare)
                                                           │
                                                           ▼
                                             [Pydantic Validation & Sanitization]
```

### Metadata Extraction Pipeline
1. **Local Cleaning**: Strips known release tags (from `data/tags.json`, `custom_tags.json`, `gemini_tags.json`), URLs, and technical markers.
2. **Local Parsing**: Uses PTN to isolate candidate title, release year, season, and episode.
3. **TMDB Query**: Queries The Movie Database in `en-US` (and `fr-FR` for French productions).
4. **Probability Scoring**: Evaluates candidate validity using token overlap and release year proximity.
5. **AI Batch Fallback**: Items with low confidence or failed lookups are bundled into batches of up to 25 items per request.

### TMDB Match Probability Scorer
Computes a match probability $P \in [0.0, 1.0]$:
$$P = 0.50 \cdot \text{SequenceSimilarity} + 0.35 \cdot \text{TokenOverlap} + 0.15 \cdot \text{YearProximity}$$
* If $P \ge 0.75$, the match is accepted directly.
* If $P < 0.75$ and AI fallback is enabled (`-a`), the item is queued for cloud AI verification.

## 6. Keyword Management

The cleaning engine uses a dictionary to strip filenames:
1. **Default Keywords (`data/tags.json`)**: Default keywords shipped with the application.
2. **User Custom Keywords (`custom_tags.json`)**: User's personal keywords stored in the configuration folder alongside `config.ini`.
3. **AI Learned Keywords (`gemini_tags.json`)**: When keyword learning is enabled (`-L` or `options.learn = true`), missing keywords discovered by AI are validated and appended to `gemini_tags.json`.

## 7. Docker Deployment

A multi-architecture Docker image (`linux/amd64`, `linux/arm64`) with pre-bundled `ffmpeg`, `ffprobe`, and `gosu` is published on GitHub Container Registry: `ghcr.io/ugoteuliere/rename`.

The container is designed to run **out-of-the-box** with zero manual configuration required other than mounting your 3 media folders.

---

### Quick Start (Zero-Config Minimal Compose)

By default, the container starts in **daemon mode** with automatic prompt bypass (`bypass = true`), polling every 15 minutes and streaming logs directly to `stdout` (`docker logs`).

```yaml
services:
  media-organizer:
    image: ghcr.io/ugoteuliere/rename:latest
    container_name: media-organizer
    restart: unless-stopped
    environment:
      - PUID=1000
      - PGID=1000
    volumes:
      - /mnt/storage/downloads:/data/input
      - /mnt/storage/movies:/data/Movies
      - /mnt/storage/series:/data/TV_Shows
```

---

### Volume Mount Points

| Volume Mount | Type | Purpose | Description |
| :--- | :--- | :--- | :--- |
| `/data/input` | **Required** | Source | Incoming / unsorted media directory to scan and organize. |
| `/data/Movies` | **Required** | Destination | Destination folder for recognized and sorted movies. |
| `/data/TV_Shows` | **Required** | Destination | Destination folder for recognized and sorted TV series. |
| `/config` | *Optional* | Configuration | Persistent storage for custom `config.ini`, `custom_tags.json`, `gemini_tags.json`. |
| `/app/log` | *Optional* | Logs | Persistent storage for daily rotated log files (`YYYY-MM-DD.txt`). |

> [!TIP]
> If your downloads, movies, and TV shows reside on the same drive, you can also mount a single root volume `-v /path/to/media:/data` containing `input`, `Movies`, and `TV_Shows` subfolders.

---

### Configuration Hierarchy & Priority

Settings are resolved using a **3-tier priority hierarchy**:
1. **Tier 1 (Highest): Environment Variables** (`TMDB_API_KEY`, `DAEMON`, `LOG`, etc.).
2. **Tier 2 (Middle): Mounted Volume Config** (`/config/config.ini`).
3. **Tier 3 (Baseline): Internal Docker Defaults** (generated inside container with `/data/input`, `/data/Movies`, `/data/TV_Shows`, `daemon=true`, `bypass=true`, `verbose=true`, `polling_interval=15`).

---

### Environment Variables

All variables accept clean names (without prefix) or legacy `RENAME_*` aliases:

| Variable | Clean Alias | Config Key | Default in Docker | Description |
| :--- | :--- | :--- | :--- | :--- |
| `PUID` | — | — | `1000` | Host user ID for permission matching. |
| `PGID` | — | — | `1000` | Host group ID for permission matching. |
| `RUN_AS_ROOT` | — | — | `false` | Set to `true` to bypass `gosu` privilege drop on strict root systems. |
| `INPUT_FOLDER` | `DOWNLOADS_FOLDER` | `paths.not_sorted_media_files_folder` | `/data/input` | Path to incoming media folder. |
| `MOVIES_FOLDER` | — | `paths.movies_folder` | `/data/Movies` | Path to destination movies folder. |
| `TV_SHOWS_FOLDER` | — | `paths.tv_shows_folder` | `/data/TV_Shows` | Path to destination TV shows folder. |
| `DAEMON` | — | `options.daemon` | `true` | Enables continuous polling background daemon. |
| `POLLING_INTERVAL` | `INTERVAL` | `options.polling_interval` | `15` | Polling interval in minutes. |
| `BYPASS` | — | `options.bypass` | `true` | Automatically bypasses confirmation prompts. |
| `VERBOSE` | — | `options.verbose` | `true` | Displays detailed error tracebacks on failure. |
| `LOG` | — | `options.log` | `false` | Enables file logging to `/app/log/` in addition to console. |
| `TMDB_API_KEY` | — | `api.tmdb_api_key` | — | TheMovieDatabase v3 API key for online matching. |
| `AI` | — | `options.ai` | `false` | Enables cloud AI fallback for unrecognizable titles. |
| `AI_PROVIDER` | — | `options.ai_provider` | `auto` | AI provider (`auto`, `gemini`, `groq`, `openrouter`, `cloudflare`). |
| `GEMINI_API_KEY` | — | `api.gemini_api_key` | — | Google Gemini API key. |
| `GROQ_API_KEY` | — | `api.groq_api_key` | — | Groq API key. |
| `OPENROUTER_API_KEY`| — | `api.openrouter_api_key` | — | OpenRouter API key. |
| `CLOUDFLARE_API_TOKEN`| — | `api.cloudflare_api_token` | — | Cloudflare AI API token. |
| `CLOUDFLARE_ACCOUNT_ID`| — | `api.cloudflare_account_id`| — | Cloudflare Account ID. |
| `MAIL` | — | `mail.mail` | — | Gmail address for email alerts. |
| `MAIL_PSWD` | — | `mail.mail_pswd` | — | 16-character Gmail App Password. |
| `NOTIFY_ON_SUCCESS`| — | `options.notify_on_success`| `false` | Send email notification on successful processing. |
| `NOTIFY_ON_ERROR` | — | `options.notify_on_error` | `false` | Send email notification on processing errors. |

---

### Logging Behavior in Docker (Dual Logging)

1. **Console Logging (Default)**:
   All events stream live to `stdout`/`stderr` viewable with `docker logs -f media-organizer`.
2. **Dual Logging (Console + File)**:
   When `LOG=true` (or `options.log = true`), the container writes daily log files to `/app/log/YYYY-MM-DD.txt` (auto-pruned after 14 days) **WITHOUT silencing console output**.
3. **Permission Safeguards**:
   If `/app/log` does not exist or lacks write permissions for `PUID`/`PGID`, the container outputs a clear warning to `stderr` and automatically falls back to console-only logging without crashing.

---

### Advanced Docker Compose Example

Full setup with TMDB, cloud AI, custom config mount, persistent logs, and dual logging:

```yaml
version: "3.8"

services:
  media-organizer:
    image: ghcr.io/ugoteuliere/rename:latest
    container_name: media-organizer
    restart: unless-stopped
    environment:
      - PUID=1000
      - PGID=1000
      - POLLING_INTERVAL=10
      - TMDB_API_KEY=your_tmdb_api_key
      # AI Fallback
      - AI=true
      - AI_PROVIDER=groq
      - GROQ_API_KEY=gsk_your_groq_key
      # Enable Dual Logging (stdout + /app/log)
      - LOG=true
    volumes:
      - /mnt/storage/downloads:/data/input
      - /mnt/storage/movies:/data/Movies
      - /mnt/storage/series:/data/TV_Shows
      - /mnt/storage/appdata/rename/config:/config
      - /mnt/storage/appdata/rename/logs:/app/log
```
