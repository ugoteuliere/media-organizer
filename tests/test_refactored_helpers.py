import os
import sys
import pytest
import pandas as pd
from pathlib import Path
from unittest.mock import patch, MagicMock

import src.files as files
import src.utils as utils


# =========================================================================
# Tests for src/utils.py refactored helpers
# =========================================================================

def test_check_folder_read_permission(tmp_path):
    # Success case
    can_read, err = utils.check_folder_read_permission(tmp_path)
    assert can_read is True
    assert err == ""

    # Failure case (mock OSError)
    with patch("os.scandir", side_effect=OSError("Read permission denied")):
        can_read, err = utils.check_folder_read_permission(tmp_path)
        assert can_read is False
        assert "Read permission denied" in err


def test_check_folder_write_permission(tmp_path):
    # Success case
    can_write, err = utils.check_folder_write_permission(tmp_path)
    assert can_write is True
    assert err == ""

    # Failure case (mock touch raising OSError)
    with patch.object(Path, "touch", side_effect=OSError("Write permission denied")):
        can_write, err = utils.check_folder_write_permission(tmp_path)
        assert can_write is False
        assert "Write permission denied" in err


def test_determine_required_folders_modes():
    # 1. Daemon mode
    req_daemon = utils.determine_required_folders(daemon=True)
    assert len(req_daemon) == 3
    assert req_daemon[0][0] == "paths.movies_folder"

    # 2. Custom path with only_rename
    req_custom_rename = utils.determine_required_folders(custom_path="/custom", only_rename=True)
    assert len(req_custom_rename) == 1
    assert req_custom_rename[0][0] == "cli.path"
    assert req_custom_rename[0][1] == "/custom"

    # 3. Custom path without only_rename
    req_custom_move = utils.determine_required_folders(custom_path="/custom", only_rename=False)
    assert len(req_custom_move) == 3
    assert req_custom_move[0][0] == "cli.path"

    # 4. Only rename without custom path
    req_only_rename = utils.determine_required_folders(only_rename=True)
    assert len(req_only_rename) == 1
    assert req_only_rename[0][0] == "paths.not_sorted_media_files_folder"

    # 5. Default mode (both false)
    req_default = utils.determine_required_folders(daemon=False, custom_path=None, only_rename=False)
    assert len(req_default) == 3


def test_format_missing_config_message():
    unconfigured = ["  • Movies folder (paths.movies_folder)"]

    msg_daemon = utils.format_missing_config_message(unconfigured, daemon=True)
    assert "Daemon mode requires" in msg_daemon

    msg_custom = utils.format_missing_config_message(unconfigured, custom_path="/custom")
    assert "Moving renamed files requires" in msg_custom

    msg_rename = utils.format_missing_config_message(unconfigured, only_rename=True)
    assert "The following required folder path is not configured" in msg_rename

    msg_default = utils.format_missing_config_message(unconfigured)
    assert "The following required folder paths are not configured" in msg_default


def test_validate_folder_existence_and_permissions(tmp_path):
    valid_folder = tmp_path / "valid"
    valid_folder.mkdir()
    required = [("key", str(valid_folder), "ATTR", "Label")]

    # Success
    utils.validate_folder_existence_and_permissions(required, simulate=False)

    # Missing folder exits
    missing = [("key", str(tmp_path / "non_existent"), "ATTR", "Label")]
    with pytest.raises(SystemExit):
        utils.validate_folder_existence_and_permissions(missing)

    # Permission issue exits
    with patch("src.utils.check_folder_permissions", return_value=(True, False, "Denied")):
        with pytest.raises(SystemExit):
            utils.validate_folder_existence_and_permissions(required, simulate=False)


# =========================================================================
# Tests for src/files.py refactored helpers
# =========================================================================

def test_resolve_search_directory(tmp_path, monkeypatch):
    # Valid custom path
    res = files.resolve_search_directory(str(tmp_path))
    assert res == tmp_path.resolve()

    # Non-existent path returns None
    res = files.resolve_search_directory(str(tmp_path / "does_not_exist"))
    assert res is None

    # Config path
    monkeypatch.setattr(files, "NOT_SORTED_MEDIA_FILES_FOLDER", str(tmp_path))
    res = files.resolve_search_directory()
    assert res == tmp_path.resolve()

    # No path configured
    monkeypatch.setattr(files, "NOT_SORTED_MEDIA_FILES_FOLDER", None)
    monkeypatch.setattr("src.config.ConfigManager.NOT_SORTED_MEDIA_FILES_FOLDER", property(lambda self: None))
    res = files.resolve_search_directory()
    assert res is None


def test_collect_candidate_video_files(tmp_path):
    # Create valid video
    valid_mkv = tmp_path / "movie.mkv"
    valid_mkv.touch()

    # Create partial download (should be ignored)
    part_file = tmp_path / "movie.crdownload"
    part_file.touch()

    # Create non-video file (should be ignored)
    text_file = tmp_path / "info.txt"
    text_file.touch()

    # Create locked video (should be skipped)
    locked_mkv = tmp_path / "downloading.mp4"
    locked_mkv.touch()

    def mock_is_locked(path):
        return path.name == "downloading.mp4"

    with patch("src.files.is_file_locked", side_effect=mock_is_locked):
        candidates = files.collect_candidate_video_files(tmp_path)
        candidate_names = [c.name for c in candidates]
        assert "movie.mkv" in candidate_names
        assert "movie.crdownload" not in candidate_names
        assert "info.txt" not in candidate_names
        assert "downloading.mp4" not in candidate_names


def test_append_resolution_quality_tags(tmp_path):
    file_path = tmp_path / "Movie (2020).mkv"
    file_path.touch()

    # When resolution and quality are disabled, returns unchanged
    with patch.object(utils, "RESOLUTION", False), patch.object(utils, "QUALITY", False):
        res = files.append_resolution_quality_tags(file_path, "Movie (2020)", (), "movie", True)
        assert res == "Movie (2020)"

    # When already has tags, returns unchanged
    with patch.object(utils, "RESOLUTION", True):
        res = files.append_resolution_quality_tags(file_path, "Movie (2020) [1080p]", (), "movie", True)
        assert res == "Movie (2020) [1080p]"

    # When enabled and metadata detected
    with patch.object(utils, "RESOLUTION", True), patch.object(utils, "QUALITY", True):
        with patch("src.utils.parse_resolution_quality", return_value=("1080p", "BluRay")):
            res = files.append_resolution_quality_tags(file_path, "Movie (2020)", ("title", 2020, "1080p", "BluRay"), "movie", True)
            assert res == "Movie (2020) [BluRay 1080p]"


def test_classify_video_file(tmp_path):
    messy = []
    clean = []

    # 1. Messy file
    messy_file = tmp_path / "Inception.2010.1080p.x264.mkv"
    messy_file.touch()
    with patch("src.utils.parse_filename", return_value=(("Inception", 2010), "movie")):
        with patch("src.utils.clean_filename", return_value="Inception (2010)"):
            files.classify_video_file(messy_file, messy, clean)
            assert len(messy) == 1
            assert messy[0]["File"] == messy_file.name

    # 2. Clean Movie
    clean_movie = tmp_path / "Inception (2010).mkv"
    clean_movie.touch()
    with patch("src.utils.parse_filename", return_value=(("Inception", 2010), "movie")):
        files.classify_video_file(clean_movie, messy, clean)
        assert len(clean) == 1
        assert clean[0]["Media"] == "movie"

    # 3. Clean Series
    clean_series = tmp_path / "Breaking Bad - S01E01.mkv"
    clean_series.touch()
    with patch("src.utils.parse_filename", return_value=(("Breaking Bad", None, "1", "1"), "tv")):
        files.classify_video_file(clean_series, messy, clean)
        assert len(clean) == 2
        assert clean[1]["Media"] == "tv"
        assert clean[1]["Season"] == "1"
        assert clean[1]["Episode"] == "1"


def test_build_search_result_tables():
    # Empty with exit_if_empty
    with pytest.raises(SystemExit):
        files.build_search_result_tables([], [], exit_if_empty=True)

    # Empty with exit_if_empty=False
    m_df, c_df = files.build_search_result_tables([], [], exit_if_empty=False)
    assert m_df.empty and c_df.empty

    # Populated tables
    messy_data = [{'File': 'bad.mkv', 'Folder': 'f', 'Path': '/bad.mkv', 'Clean': 'b', 'Parse': (), 'Media': 'movie'}]
    clean_data = [{'Original': 'Good', 'Corrected': 'Good (2020)', 'Path': '/Good.mkv', 'Media': 'movie', 'Season': None, 'Episode': None}]
    m_df, c_df = files.build_search_result_tables(messy_data, clean_data, exit_if_empty=False)
    assert len(m_df) == 1
    assert len(c_df) == 1
    assert c_df.iloc[0]['Corrected'] == 'Good (2020)'


def test_build_destination_lookup():
    # None or empty
    assert files.build_destination_lookup(None) == {}
    assert files.build_destination_lookup(pd.DataFrame()) == {}

    # Populated DataFrame
    df = pd.DataFrame([
        {'Corrected': 'Movie (2020)', 'Original': 'movie.raw', 'Media': 'movie'}
    ])
    lookup = files.build_destination_lookup(df)
    assert lookup.get('Movie (2020)') == ('movie.raw', 'movie')


def test_infer_media_type_from_destination(tmp_path):
    movies_dir = tmp_path / "Movies"
    tv_dir = tmp_path / "TV"
    movies_dir.mkdir()
    tv_dir.mkdir()

    movie_path = movies_dir / "Movie (2020)" / "Movie (2020).mkv"
    tv_path = tv_dir / "Show" / "Season 1" / "Show - S01E01.mkv"
    other_path = tmp_path / "Other" / "clip.mkv"

    assert files.infer_media_type_from_destination(movie_path, movies_dir, tv_dir) == "movie"
    assert files.infer_media_type_from_destination(tv_path, movies_dir, tv_dir) == "tv"
    assert files.infer_media_type_from_destination(other_path, movies_dir, tv_dir) == "unknown"


def test_execute_single_file_move(tmp_path):
    old_file = tmp_path / "old.mkv"
    old_file.touch()
    new_file = tmp_path / "new.mkv"

    lookup = {"new": ("old.mkv", "movie")}

    # Success case
    with patch("src.files.move_file") as mock_move, patch("src.mail.send_media_success_email") as mock_mail:
        success, failed = files.execute_single_file_move(old_file, new_file, lookup)
        assert success is True
        assert failed is None
        mock_move.assert_called_once_with(old_file, new_file)
        mock_mail.assert_called_once()

    # Error case (RuntimeError)
    with patch("src.files.move_file", side_effect=RuntimeError("Disk full")), patch("src.mail.send_error_email") as mock_err_mail:
        success, failed = files.execute_single_file_move(old_file, new_file, lookup)
        assert success is False
        assert failed == old_file.name
        mock_err_mail.assert_called_once()
