"""
Tests for new architecture components introduced in the refactor:
- RuntimeConfig reset and isolation (Phase 2)
- Exception hierarchy (Phase 1)
- TMDB top-N candidate selection and scoring (Phase 4 / B4 / R1)
- Filename processing functions (Phase 5)
- verify_folders with exit_on_error=False (TS7)
- sanitize_filename property and edge cases (TS6)
"""

import pytest
from unittest.mock import MagicMock, patch

from src.runtime_config import RuntimeConfig, runtime
from src.exceptions import (
    MediaOrganizerError,
    ConfigurationError,
    APIError,
    FileOperationError,
    FolderNotFoundError,
    PermissionError_,
)
from src.filename_processing import (
    sanitize_filename,
    clean_filename,
    parse_filename,
    format_season_and_episode,
    remove_url,
)
from src import tmdb_api, utils


# ── 1. RuntimeConfig Tests ───────────────────────────────────────────────────


def test_runtime_config_defaults_and_reset():
    rc = RuntimeConfig()
    assert rc.log_enabled is False
    assert rc.log_mode == "console"
    assert rc.daemon_enabled is False
    assert rc.simulate_enabled is False
    assert rc.bypass_enabled is False
    assert rc.verbose_enabled is False
    assert rc.ai_fallback_enabled is False
    assert rc.learn_enabled is False
    assert rc.resolution_enabled is False
    assert rc.quality_enabled is False

    # Mutate
    rc.log_enabled = True
    rc.daemon_enabled = True
    rc.simulate_enabled = True
    assert rc.log_enabled is True

    # Reset
    rc.reset()
    assert rc.log_enabled is False
    assert rc.daemon_enabled is False
    assert rc.simulate_enabled is False


def test_runtime_singleton_behavior():
    runtime.reset()
    assert runtime.log_enabled is False
    runtime.log_enabled = True
    assert runtime.log_enabled is True
    runtime.reset()
    assert runtime.log_enabled is False


# ── 2. Exception Hierarchy Tests ─────────────────────────────────────────────


def test_exception_hierarchy():
    assert issubclass(ConfigurationError, MediaOrganizerError)
    assert issubclass(ConfigurationError, ValueError)

    assert issubclass(APIError, MediaOrganizerError)
    assert issubclass(APIError, ValueError)
    assert issubclass(APIError, RuntimeError)

    assert issubclass(FileOperationError, MediaOrganizerError)
    assert issubclass(FileOperationError, OSError)
    assert issubclass(FileOperationError, RuntimeError)

    assert issubclass(FolderNotFoundError, FileOperationError)
    assert issubclass(FolderNotFoundError, FileNotFoundError)

    assert issubclass(PermissionError_, FileOperationError)
    assert issubclass(PermissionError_, PermissionError)


def test_exceptions_can_be_caught_by_standard_handlers():
    try:
        raise ConfigurationError("bad config")
    except ValueError as e:
        assert "bad config" in str(e)

    try:
        raise FolderNotFoundError("missing folder")
    except FileNotFoundError as e:
        assert "missing folder" in str(e)

    try:
        raise PermissionError_("access denied")
    except PermissionError as e:
        assert "access denied" in str(e)

    try:
        raise APIError("network fail")
    except RuntimeError as e:
        assert "network fail" in str(e)


# ── 3. TMDB Top-N Candidate Scoring (B4 / R1) ────────────────────────────────


def test_tmdb_top_n_candidate_selection(monkeypatch):
    monkeypatch.setattr("src.config.config.TMDB_API_KEY", "dummy_tmdb_key")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "results": [
            # Candidate 0: Low match score (wrong movie)
            {"title": "The Matrix Reloaded", "release_date": "2003-05-15", "original_language": "en"},
            # Candidate 1: Exact match score
            {"title": "The Matrix", "release_date": "1999-03-31", "original_language": "en"},
            # Candidate 2: Another sequel
            {"title": "The Matrix Revolutions", "release_date": "2003-11-05", "original_language": "en"},
        ]
    }

    with patch("requests.get", return_value=mock_resp):
        res = tmdb_api.api_call("The Matrix", "1999", "en-US", "movie")
        # Candidate 1 should be picked because its score against "The Matrix 1999" is highest
        assert res == [True, "The Matrix", "1999", "en"]


def test_tmdb_tv_show_candidate_selection(monkeypatch):
    monkeypatch.setattr("src.config.config.TMDB_API_KEY", "dummy_tmdb_key")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "results": [
            {"name": "Darkness", "first_air_date": "2010-01-01", "original_language": "en"},
            {"name": "Dark", "first_air_date": "2017-12-01", "original_language": "de"},
        ]
    }

    with patch("requests.get", return_value=mock_resp):
        res = tmdb_api.api_call("Dark", "2017", "en-US", "tv")
        assert res == [True, "Dark", "2017", "de"]


# ── 4. Filename Processing Functions (A4) ────────────────────────────────────


@pytest.mark.parametrize(
    "raw, expected_clean, expected_media",
    [
        ("Inception.2010.1080p.BluRay.mkv", "Inception", "movie"),
        ("Breaking.Bad.S01E05.720p.mkv", "Breaking Bad", "tv"),
        ("Stranger.Things.S04E01.2160p.mkv", "Stranger Things", "tv"),
    ],
)
def test_parse_filename_types(raw, expected_clean, expected_media):
    parse, media = parse_filename(raw)
    assert media == expected_media
    assert expected_clean.lower() in parse[0].lower()


def test_clean_filename_removes_tags_and_resolutions():
    clean_title, year, res, qual = clean_filename("The.Dark.Knight.2008.1080p.BluRay.x264.mkv")
    assert "1080p" not in clean_title
    assert "bluray" not in clean_title.lower()
    assert year == "2008"


def test_format_season_and_episode_zfill():
    assert format_season_and_episode(1, 2) == ("01", "02")
    assert format_season_and_episode("5", "9") == ("05", "09")
    assert format_season_and_episode(12, 105) == ("12", "105")


def test_remove_url_various_cases():
    assert "my.movie" in remove_url("www.torrent-site.org.my.movie.mkv").lower()
    assert "cool.film" in remove_url("cool.film.rarbg.to.mkv").lower()


# ── 5. verify_folders exit_on_error=False (TS7) ──────────────────────────────


def test_verify_folders_exit_on_error_false(monkeypatch, tmp_path):
    monkeypatch.setattr(utils, "MOVIES_FOLDER", None)
    monkeypatch.setattr(utils, "TV_SHOWS_FOLDER", None)
    monkeypatch.setattr(utils, "NOT_SORTED_MEDIA_FILES_FOLDER", None)

    # With exit_on_error=False, it should return 1 instead of raising SystemExit / FolderNotFoundError
    result = utils.verify_folders(exit_on_error=False)
    assert result == 1


# ── 6. Property-based / Edge Cases for sanitize_filename (TS6) ───────────────


@pytest.mark.parametrize(
    "bad_input, expected",
    [
        (None, ""),
        ("", ""),
        ("   ", ""),
        ("../../etc/passwd", "etc-passwd"),
        ("..\\..\\windows\\system32", "windows-system32"),
        ("Title: Subtitle", "Title - Subtitle"),
        ('Bad"Chars*In?Name<Test>|Here', "Bad-Chars-In-Name-Test-Here"),
        ("Normal Movie Name (2020)", "Normal Movie Name (2020)"),
        ("   Spaced   Out   Name   ", "Spaced Out Name"),
    ],
)
def test_sanitize_filename_edge_cases(bad_input, expected):
    assert sanitize_filename(bad_input) == expected
