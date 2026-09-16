"""
Filename parsing and cleaning utilities for media-organizer.

This module was extracted from the monolithic ``src/utils.py`` (A4 refactor).
It owns all string-level filename operations:

- URL removal
- Season/episode normalisation
- PTN-based parsing
- Tag stripping (via TagManager)
- Title sanitisation
- Resolution/quality string translation
- New filename generation
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

import PTN

from data.data import TLDS, QUALITY_PATTERNS, RESOLUTION_PATTERNS
from src.tags import tag_manager

if TYPE_CHECKING:
    pass


# ── Season / Episode patterns ────────────────────────────────────────────────

SEASON_EPISODE_PATTERNS: list[re.Pattern[str]] = [
    # 1. Saison/Season XX (Episode/Ep/E) XX
    re.compile(r"\b(?:saison|season)[.\s_-]*(\d{1,2})[.\s_-]*(?:episode|ep|e)[.\s_-]*(\d{1,3})\b", re.IGNORECASE),
    # 2. SXX (Episode/Ep) XX
    re.compile(r"\bs(\d{1,2})[.\s_-]*(?:episode|ep)[.\s_-]*(\d{1,3})\b", re.IGNORECASE),
    # 3. SXX séparé de EXX
    re.compile(r"\bs(\d{1,2})[.\s_-]+e(\d{1,3})\b", re.IGNORECASE),
]


def normalize_season_episode(filename: str) -> str:
    """Normalises all season/episode formats to ``SxxExx``."""
    if not filename:
        return filename
    for pattern in SEASON_EPISODE_PATTERNS:

        def repl(match: re.Match[str]) -> str:  # noqa: ANN001
            s = int(match.group(1))
            e = int(match.group(2))
            return f"S{s:02d}E{e:02d}"

        new_filename, count = pattern.subn(repl, filename)
        if count > 0:
            return new_filename
    return filename


def parse_season_episode(season: str | None, episode: str | None, filename: str) -> tuple[int, int]:
    """Parses raw season/episode tokens into integers.

    Falls back to scanning *filename* when ``season``/``episode`` are missing.
    """
    try:
        s = int(season)  # type: ignore[arg-type]
        e = int(episode)  # type: ignore[arg-type]
    except (ValueError, TypeError):
        norm_filename = normalize_season_episode(filename)
        season_regex = r"(?:saison|season|s)[.\s-]*(\d+)"
        episode_regex = r"(?:episode|ep|e)[.\s-]*(\d+)"
        s_match = re.search(season_regex, norm_filename, re.IGNORECASE)
        e_match = re.search(episode_regex, norm_filename, re.IGNORECASE)
        if s_match and e_match:
            s = int(s_match.group(1))
            e = int(e_match.group(1))
        else:
            raise ValueError(f"Could not extract season/episode from filename: {filename}")
    return s, e


def format_season_and_episode(season: int | str, episode: int | str) -> tuple[str, str]:
    """Returns zero-padded season and episode strings."""
    try:
        s = int(season)
        e = int(episode)
    except (ValueError, TypeError):
        raise ValueError("Failed parsing season or episode")
    return str(s).zfill(2), str(e).zfill(2)


# ── URL removal ──────────────────────────────────────────────────────────────


def remove_url(filename: str) -> str:
    """Strips URL-like patterns from a filename."""
    tlds_pattern = "|".join(TLDS)
    url_pattern = rf"""
        (?:
            # CASE 1: Starts with 'www.' (Safe to greedily capture multiple subdomains)
            (?:\b|(?<=_))www\.(?:[a-zA-Z0-9-]+\.)+(?:{tlds_pattern})(?:\b|(?=_))

            | # OR

            # CASE 2: No 'www.' (Strictly ONE word before the TLD chain)
            # This captures "site.com" or "amazon.co.uk" but stops before "My.Movie."
            (?:\b|(?<=_))[a-zA-Z0-9-]+\.(?:(?:{tlds_pattern})\.)*(?:{tlds_pattern})(?:\b|(?=_))
        )
    """
    clean_filename = re.sub(url_pattern, "", filename, flags=re.IGNORECASE | re.VERBOSE)
    clean_filename = re.sub(r"\[\s*\]|\(\s*\)", "", clean_filename)
    clean_filename = re.sub(r"\.{2,}", ".", clean_filename)
    clean_filename = clean_filename.strip(".-_ ")
    return clean_filename


# ── Filename sanitisation ────────────────────────────────────────────────────


def sanitize_filename(name: str) -> str:
    """Sanitises a title or filename component against directory traversal and forbidden characters."""
    if not name or not isinstance(name, str):
        return ""

    # Replace colons with standard title separator " -"
    sanitized = name.replace(":", " -")

    # Remove directory traversal segments
    sanitized = re.sub(r"(?:\.\.[\\/]+)+", "", sanitized)
    sanitized = re.sub(r"\.{2,}", "", sanitized)

    # Replace illegal filesystem characters with hyphen
    sanitized = re.sub(r'[\x00\\/*?"<>|]', "-", sanitized)

    # Collapse multiple consecutive hyphens or spaces
    sanitized = re.sub(r"-{2,}", "-", sanitized)
    sanitized = re.sub(r"\s+", " ", sanitized)

    # Strip leading/trailing dots, hyphens, and whitespace
    sanitized = sanitized.strip(". -")

    return sanitized


# ── Resolution / Quality translation ────────────────────────────────────────


def translate_resolution_to_name(resolution_str: str | None) -> str | None:
    """Maps raw resolution strings (``1080p``, ``2160p`` …) to friendly names."""
    if not resolution_str:
        return None
    mapping = {"2160p": "4K", "1440p": "2K", "1080p": "FullHD", "720p": "HD", "480p": "SD", "576p": "SD"}
    clean_res = str(resolution_str).strip().lower()
    return mapping.get(clean_res, resolution_str)


# ── PTN-based filename parsing ───────────────────────────────────────────────


def parse_filename(filename: str) -> tuple[list[str], str]:
    """Parses a raw filename into a structured token list and media type.

    Returns ``(parse, media)`` where *parse* is a list whose layout is:
    - Movie:  ``[title, year, resolution, quality]``
    - TV:     ``[title, year, season, episode, resolution, quality]``
    """
    filename = normalize_season_episode(filename)
    filename_without_url = remove_url(filename)
    filename_without_url = re.sub(r"\d{5,}", "", filename_without_url)
    filename_parsed = PTN.parse(filename_without_url)
    media = "tv" if (filename_parsed.get("season") or filename_parsed.get("episode")) else "movie"
    title = str(filename_parsed.get("title")) if filename_parsed.get("title") else ""
    year = str(filename_parsed.get("year")) if filename_parsed.get("year") else ""
    resolution = str(filename_parsed.get("resolution")) if filename_parsed.get("resolution") else ""
    quality = str(filename_parsed.get("quality")) if filename_parsed.get("quality") else ""
    if media == "movie":
        parse: list[str] = [title, year, resolution, quality]
    else:
        season = str(filename_parsed.get("season")) if filename_parsed.get("season") else ""
        episode = str(filename_parsed.get("episode")) if filename_parsed.get("episode") else ""
        parse = [title, year, season, episode, resolution, quality]
    return parse, media


def clean_filename(filename: str) -> tuple[str, str, str, str]:
    """Cleans a raw filename into ``(clean_title, year, resolution, quality)``."""
    filename = normalize_season_episode(filename)
    raw_name = filename.rsplit(".", 1)[0]
    raw_name = raw_name.replace("_", ".")

    # Remove URLs
    filename_without_urls = remove_url(raw_name)

    # Year
    year_match = re.search(r"\(?((?:19|20)\d{2})\)?", raw_name)
    year = year_match.group(1) if year_match else ""

    # Resolution
    resolution = ""
    for pattern in RESOLUTION_PATTERNS:
        res_match = re.search(pattern, raw_name, flags=re.IGNORECASE)
        if res_match:
            resolution = res_match.group(0)
            break

    # Quality
    quality = ""
    for pattern in QUALITY_PATTERNS:
        qual_match = re.search(pattern, raw_name, flags=re.IGNORECASE)
        if qual_match:
            quality = qual_match.group(0)
            break

    # Regex filters
    clean_title = re.sub(r"S\d+E\d+", "", filename_without_urls, flags=re.IGNORECASE)
    clean_title = re.sub(r"\d{5,}", "", clean_title)
    clean_title = re.sub(r"\(?(?:19|20)\d{2}\)?", "", clean_title)
    clean_title = re.sub(r"\s+", " ", clean_title).strip()

    # Remove torrent tags
    from src import tags, utils

    tm = getattr(utils, "tag_manager", getattr(tags, "tag_manager", tag_manager))
    clean_title = tm.clean_text(clean_title)

    # Clean separators
    clean_title = clean_title.replace(".", " ").replace("_", " ").replace("-", " ")
    clean_title = " ".join(clean_title.split()).strip()

    return clean_title, year, resolution, quality


# ── New filename generators ──────────────────────────────────────────────────


def generate_new_movie_filename(
    success: bool,
    title: str | None,
    year: str | None,
    resolution: str | None,
    quality: str | None,
    *,
    resolution_enabled: bool | None = None,
    quality_enabled: bool | None = None,
) -> str:
    """Generates a standardised movie filename stem.

    Parameters ``resolution_enabled`` / ``quality_enabled`` replace the old
    module-level ``RESOLUTION`` / ``QUALITY`` globals (B8 fix).
    """
    if resolution_enabled is None:
        from src.runtime_config import runtime
        from src.config import config

        resolution_enabled = bool(runtime.resolution_enabled or config.RESOLUTION)
    if quality_enabled is None:
        from src.runtime_config import runtime
        from src.config import config

        quality_enabled = bool(runtime.quality_enabled or config.QUALITY)

    is_title_valid = title and str(title).strip()
    if not success or not is_title_valid:
        raise LookupError("API calls failed or essential metadata (Title) is missing/empty.")

    safe_title = sanitize_filename(title)  # type: ignore[arg-type]
    if not safe_title:
        raise LookupError("Title contains only invalid characters.")

    new_name = safe_title
    if year and str(year).strip():
        safe_year = re.sub(r"[^0-9]", "", str(year).strip())
        if safe_year:
            new_name += f" ({safe_year})"

    metadata_parts: list[str] = []
    if quality_enabled and quality and str(quality).strip():
        metadata_parts.append(str(quality))
    if resolution_enabled and resolution and str(resolution).strip():
        metadata_parts.append(str(resolution))
    if metadata_parts:
        new_name += f" [{' '.join(metadata_parts)}]"

    return new_name


def generate_new_tvshow_filename(
    success: bool,
    title: str | None,
    season: str | int | None,
    episode: str | int | None,
    resolution: str | None = None,
    quality: str | None = None,
    *,
    resolution_enabled: bool | None = None,
    quality_enabled: bool | None = None,
) -> str:
    """Generates a standardised TV show filename stem."""
    if resolution_enabled is None:
        from src.runtime_config import runtime
        from src.config import config

        resolution_enabled = bool(runtime.resolution_enabled or config.RESOLUTION)
    if quality_enabled is None:
        from src.runtime_config import runtime
        from src.config import config

        quality_enabled = bool(runtime.quality_enabled or config.QUALITY)

    is_title_valid = title and str(title).strip()
    is_season_valid = season is not None and str(season).strip() != ""
    is_episode_valid = episode is not None and str(episode).strip() != ""

    if not success or not is_title_valid or not is_season_valid or not is_episode_valid:
        raise LookupError("API calls failed or essential metadata (Title, Season, or Episode) is missing/empty.")

    safe_title = sanitize_filename(title)  # type: ignore[arg-type]
    if not safe_title:
        raise LookupError("Title contains only invalid characters.")

    s_padded = str(season).zfill(2)
    e_padded = str(episode).zfill(2)
    new_name = f"{safe_title} - S{s_padded}E{e_padded}"

    metadata_parts: list[str] = []
    if quality_enabled and quality and str(quality).strip():
        metadata_parts.append(str(quality))
    if resolution_enabled and resolution and str(resolution).strip():
        metadata_parts.append(str(resolution))
    if metadata_parts:
        new_name += f" [{' '.join(metadata_parts)}]"

    return new_name
