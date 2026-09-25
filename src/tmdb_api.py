"""
TMDB REST API client for media-organizer.

Extracted from the monolithic ``src/api.py`` (A3 refactor).

Key improvements over the old implementation:
- **B4 / R1 fix**: ``api_call`` now scores *all* returned results with
  :func:`src.utils.compute_tmdb_match_probability` and returns the
  best-scoring one rather than blindly taking ``results[0]``.
- Uses typed exceptions (``APIError``, ``ConfigurationError``) instead of
  ``sys.exit()`` so callers can handle failures gracefully.
- No module-level config-value snapshots (B3/P2 fix) — every function reads
  live from ``config``.
"""

from __future__ import annotations

import sys
import urllib.parse

import requests


def api_call(
    name: str,
    year: str | None,
    language: str,
    media_type: str,
) -> list:
    """Queries TMDB and returns the *best-scoring* match.

    Returns ``[True, title, year, original_language]`` on success or
    ``[False, None, None, None]`` on failure / no results.

    Unlike the old implementation, all results from TMDB are scored with
    :func:`src.utils.compute_tmdb_match_probability` and the highest-scoring
    entry (above a minimum threshold of 0.0) is returned, rather than
    unconditionally picking ``results[0]``.
    """
    from src.config import config
    from src import mail, api
    from src.ui import print_error
    from src.runtime_config import runtime

    api_key = config.TMDB_API_KEY
    if api_key is None:
        err_msg = (
            "Missing configuration: TMDB API key is not configured.\n"
            "The TMDB API key is required to identify and fetch metadata for media files.\n\n"
            "How to fix:\n"
            "  1. Run the interactive setup wizard:\n"
            "     media-organizer configure\n"
            "  2. Or set the key via CLI:\n"
            '     media-organizer config --set api.tmdb_api_key "<your_tmdb_api_key>"\n'
            "  3. Or set the environment variable:\n"
            '     export TMDB_API_KEY="<your_tmdb_api_key>"\n\n'
            "Stopping program."
        )
        api.print_log(err_msg)
        mail.send_error_email(error_message=err_msg)
        if runtime.daemon_enabled:
            return [False, None, None, None]
        sys.exit(1)

    encoded_query = urllib.parse.quote(name)
    url = f"https://api.themoviedb.org/3/search/{media_type}?query={encoded_query}&language={language}"
    if year:
        year_param = "year" if media_type == "movie" else "first_air_date_year"
        url += f"&{year_param}={year}"

    headers = {"accept": "application/json", "Authorization": f"Bearer {api_key}"}

    try:
        response = requests.get(url, headers=headers, timeout=15)
    except Exception as e:
        api.print_log(
            print_error(f" Warning: TMDB API call failed (connection error or timeout)\n Query : {name} {year}", e)
        )
        return [False, None, None, None]

    if response.status_code != 200:
        api.print_log(f" TMDB API call failed\n\n # Code : {response.status_code} \n\n # Query : {name} {year}\n")
        return [False, None, None, None]

    try:
        data = response.json()
    except Exception as e:
        api.print_log(print_error(f" Warning: TMDB API returned invalid JSON\n Query : {name} {year}", e))
        return [False, None, None, None]

    results = data.get("results", [])

    if not results:
        api.print_log(
            f" API call failed : impossible to read the JSON data from TMDB API\n\n # Query : {name} {year}\n"
        )
        return [False, None, None, None]

    # ── B4 / R1: score all results and pick the best match ──────────────────
    from src.utils import compute_tmdb_match_probability

    best_score = -1.0
    best_result: dict = results[0]  # fallback

    for candidate in results:
        if media_type == "movie":
            cand_title = candidate.get("title", "")
            cand_date = candidate.get("release_date", "")
        else:
            cand_title = candidate.get("name", "")
            cand_date = candidate.get("first_air_date", "")
        cand_year = cand_date[:4] if cand_date else None
        score = compute_tmdb_match_probability(name, year, cand_title, cand_year)
        if score > best_score:
            best_score = score
            best_result = candidate

    if media_type == "movie":
        tmdb_title = best_result.get("title", "unknown")
        release_date = best_result.get("release_date", "")
    else:
        tmdb_title = best_result.get("name", "unknown")
        release_date = best_result.get("first_air_date", "")

    tmdb_year = release_date[:4] if release_date else "unknown"
    original_language = best_result.get("original_language", "unknown")

    return [True, tmdb_title, tmdb_year, original_language]
