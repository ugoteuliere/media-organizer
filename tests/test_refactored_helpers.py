import pytest
import pandas as pd
from pathlib import Path
from unittest.mock import patch

import src.files as files
import src.utils as utils
import src.ui as ui
from src.exceptions import FolderNotFoundError, PermissionError_


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
    with pytest.raises((SystemExit, FolderNotFoundError)):
        utils.validate_folder_existence_and_permissions(missing)

    # Permission issue exits
    with patch("src.utils.check_folder_permissions", return_value=(True, False, "Denied")):
        with pytest.raises((SystemExit, PermissionError_)):
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
            res = files.append_resolution_quality_tags(
                file_path, "Movie (2020)", ("title", 2020, "1080p", "BluRay"), "movie", True
            )
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
    assert m_df.empty
    assert c_df.empty

    # Populated tables
    messy_data = [{"File": "bad.mkv", "Folder": "f", "Path": "/bad.mkv", "Clean": "b", "Parse": (), "Media": "movie"}]
    clean_data = [
        {
            "Original": "Good",
            "Corrected": "Good (2020)",
            "Path": "/Good.mkv",
            "Media": "movie",
            "Season": None,
            "Episode": None,
        }
    ]
    m_df, c_df = files.build_search_result_tables(messy_data, clean_data, exit_if_empty=False)
    assert len(m_df) == 1
    assert len(c_df) == 1
    assert c_df.iloc[0]["Corrected"] == "Good (2020)"


def test_build_destination_lookup():
    # None or empty
    assert files.build_destination_lookup(None) == {}
    assert files.build_destination_lookup(pd.DataFrame()) == {}

    # Populated DataFrame
    df = pd.DataFrame([{"Corrected": "Movie (2020)", "Original": "movie.raw", "Media": "movie"}])
    lookup = files.build_destination_lookup(df)
    assert lookup.get("Movie (2020)") == ("movie.raw", "movie")


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
    with (
        patch("src.files.move_file", side_effect=RuntimeError("Disk full")),
        patch("src.mail.send_error_email") as mock_err_mail,
    ):
        success, failed = files.execute_single_file_move(old_file, new_file, lookup)
        assert success is False
        assert failed == old_file.name
        mock_err_mail.assert_called_once()


def test_execute_single_file_move_daemon_mode(tmp_path, monkeypatch):
    old_file = tmp_path / "old.mkv"
    old_file.touch()
    new_file = tmp_path / "new.mkv"
    lookup = {"new": ("old.mkv", "movie")}

    monkeypatch.setattr(ui, "DAEMON_ENABLED", True)

    # 1. Success in daemon mode -> ui.log_success called
    with (
        patch("src.files.move_file") as mock_move,
        patch("src.mail.send_media_success_email") as mock_mail,
        patch("src.ui.log_success") as mock_log_succ,
    ):
        success, failed = files.execute_single_file_move(old_file, new_file, lookup)
        assert success is True
        assert failed is None
        mock_move.assert_called_once_with(old_file, new_file)
        mock_mail.assert_called_once()
        mock_log_succ.assert_called_once_with("old.mkv", "new.mkv", str(new_file))

    # 2. Move failure in daemon mode -> ui.log_error called
    with (
        patch("src.files.move_file", side_effect=RuntimeError("Disk full")),
        patch("src.mail.send_error_email"),
        patch("src.ui.log_error") as mock_log_err,
    ):
        success, failed = files.execute_single_file_move(old_file, new_file, lookup)
        assert success is False
        assert failed == old_file.name
        mock_log_err.assert_called_once_with("Failed to move 'old.mkv': Disk full")

    # 3. Mail error in daemon mode -> second ui.log_error called
    with (
        patch("src.files.move_file", side_effect=RuntimeError("Disk full")),
        patch("src.mail.send_error_email", side_effect=RuntimeError("SMTP down")),
        patch("src.ui.log_error") as mock_log_err,
    ):
        success, failed = files.execute_single_file_move(old_file, new_file, lookup)
        assert success is False
        assert failed == old_file.name
        assert mock_log_err.call_count == 2
        mock_log_err.assert_any_call("Error while trying to send the email: SMTP down")


def test_extract_parse_tokens():
    # Movie with full parse
    movie_parse = ("Inception", "2010", "1080p", "BluRay")
    res, qual = files.extract_parse_tokens(movie_parse, media="movie", is_movie=True)
    assert res == "1080p"
    assert qual == "BluRay"

    # Movie with short parse
    short_parse = ("Inception", "2010")
    res, qual = files.extract_parse_tokens(short_parse, media="movie", is_movie=True)
    assert res is None
    assert qual is None

    # Series with full parse
    tv_parse = ("Breaking Bad", "2008", "1", "1", "720p", "WEBRip")
    res, qual = files.extract_parse_tokens(tv_parse, media="tv", is_movie=False)
    assert res == "720p"
    assert qual == "WEBRip"

    # Series with short parse
    short_tv_parse = ("Breaking Bad", "2008")
    res, qual = files.extract_parse_tokens(short_tv_parse, media="tv", is_movie=False)
    assert res is None
    assert qual is None


def test_format_stream_tags():
    # Both enabled and present
    tags = files.format_stream_tags("1080p", "BluRay", res_enabled=True, qual_enabled=True)
    assert tags == ["BluRay", "1080p"]

    # Only quality enabled
    tags_qual = files.format_stream_tags("1080p", "BluRay", res_enabled=False, qual_enabled=True)
    assert tags_qual == ["BluRay"]

    # Only resolution enabled
    tags_res = files.format_stream_tags("1080p", "BluRay", res_enabled=True, qual_enabled=False)
    assert tags_res == ["1080p"]

    # Empty / whitespace values
    tags_empty = files.format_stream_tags("   ", "", res_enabled=True, qual_enabled=True)
    assert tags_empty == []

    # Disabled
    tags_none = files.format_stream_tags(None, None, res_enabled=False, qual_enabled=False)
    assert tags_none == []


def test_extract_season_episode():
    # Extracted from parse tuple
    parse_with_se = ("Show", "2020", "2", "5")
    s, e = files.extract_season_episode("Show - S01E03", parse_with_se)
    assert s == "2"
    assert e == "5"

    # Fallback to regex when parse tuple is empty
    s_fallback, e_fallback = files.extract_season_episode("Show - S03E14", ())
    assert s_fallback == "3"
    assert e_fallback == "14"

    # No match at all
    s_none, e_none = files.extract_season_episode("Movie (2020)", ())
    assert s_none is None
    assert e_none is None


def test_build_clean_media_entry(tmp_path):
    movie_file = tmp_path / "Inception (2010).mkv"
    tv_file = tmp_path / "Show - S01E01.mkv"
    other_file = tmp_path / "clip.mkv"

    # Movie entry
    entry_movie = files.build_clean_media_entry(
        movie_file, "Inception (2010)", (), "movie", is_movie=True, is_series=False
    )
    assert entry_movie is not None
    assert entry_movie["Media"] == "movie"
    assert entry_movie["Season"] is None
    assert entry_movie["Episode"] is None
    assert entry_movie["Corrected"] == "Inception (2010)"

    # TV entry
    entry_tv = files.build_clean_media_entry(tv_file, "Show - S01E01", (), "tv", is_movie=False, is_series=True)
    assert entry_tv is not None
    assert entry_tv["Media"] == "tv"
    assert entry_tv["Season"] == "1"
    assert entry_tv["Episode"] == "1"

    # Unknown / Neither entry
    entry_none = files.build_clean_media_entry(other_file, "clip", (), "unknown", is_movie=False, is_series=False)
    assert entry_none is None


def test_folder_scan_report_permutations():
    """Validates dynamic folder scan report formatting, pluralization, and optional sections."""
    from unittest.mock import patch
    from src import files

    with patch("src.ui.log_info") as mock_log_info:
        # Case 1: Empty folder (no media files) -> line is NOT printed
        files.build_search_result_tables([], [], exit_if_empty=False, ignored_files_count=0)
        mock_log_info.assert_not_called()

    with patch("src.ui.log_info") as mock_log_info:
        # Case 2: 1 file to rename -> singular '1 file to rename'
        messy_1 = [{"File": "a.mkv", "Folder": "f", "Path": "/a.mkv", "Clean": "a", "Parse": (), "Media": "movie"}]
        files.build_search_result_tables(messy_1, [], exit_if_empty=False, ignored_files_count=0)
        mock_log_info.assert_called_once_with("Folder scan report: 1 file to rename")

    with patch("src.ui.log_info") as mock_log_info:
        # Case 3: 2 files to rename -> plural '2 files to rename'
        messy_2 = [
            {"File": "a.mkv", "Folder": "f", "Path": "/a.mkv", "Clean": "a", "Parse": (), "Media": "movie"},
            {"File": "b.mkv", "Folder": "f", "Path": "/b.mkv", "Clean": "b", "Parse": (), "Media": "movie"},
        ]
        files.build_search_result_tables(messy_2, [], exit_if_empty=False, ignored_files_count=0)
        mock_log_info.assert_called_once_with("Folder scan report: 2 files to rename")

    with patch("src.ui.log_info") as mock_log_info:
        # Case 4: Only clean files (1 file with clean filename) -> singular
        clean_1 = [
            {
                "Original": "Good (2020)",
                "Corrected": "Good (2020)",
                "Path": "/Good.mkv",
                "Media": "movie",
                "Season": None,
                "Episode": None,
            }
        ]
        files.build_search_result_tables([], clean_1, exit_if_empty=False, ignored_files_count=0)
        mock_log_info.assert_called_once_with("Folder scan report: 1 file with clean filename")

    with patch("src.ui.log_info") as mock_log_info:
        # Case 5: 2 clean files -> plural '2 files with clean filename'
        clean_2 = [
            {
                "Original": "A (2020)",
                "Corrected": "A (2020)",
                "Path": "/A.mkv",
                "Media": "movie",
                "Season": None,
                "Episode": None,
            },
            {
                "Original": "B (2021)",
                "Corrected": "B (2021)",
                "Path": "/B.mkv",
                "Media": "movie",
                "Season": None,
                "Episode": None,
            },
        ]
        files.build_search_result_tables([], clean_2, exit_if_empty=False, ignored_files_count=0)
        mock_log_info.assert_called_once_with("Folder scan report: 2 files with clean filename")

    with patch("src.ui.log_info") as mock_log_info:
        # Case 6: Only ignored files -> singular & plural
        files.build_search_result_tables([], [], exit_if_empty=False, ignored_files_count=1)
        mock_log_info.assert_called_once_with("Folder scan report: 1 file ignored because of previous errors")

    with patch("src.ui.log_info") as mock_log_info:
        files.build_search_result_tables([], [], exit_if_empty=False, ignored_files_count=3)
        mock_log_info.assert_called_once_with("Folder scan report: 3 files ignored because of previous errors")

    with patch("src.ui.log_info") as mock_log_info:
        # Case 7: Combined sections with comma separator
        messy = [{"File": "a.mkv", "Folder": "f", "Path": "/a.mkv", "Clean": "a", "Parse": (), "Media": "movie"}]
        clean = [
            {
                "Original": "A (2020)",
                "Corrected": "A (2020)",
                "Path": "/A.mkv",
                "Media": "movie",
                "Season": None,
                "Episode": None,
            },
            {
                "Original": "B (2021)",
                "Corrected": "B (2021)",
                "Path": "/B.mkv",
                "Media": "movie",
                "Season": None,
                "Episode": None,
            },
        ]
        files.build_search_result_tables(messy, clean, exit_if_empty=False, ignored_files_count=1)
        mock_log_info.assert_called_once_with(
            "Folder scan report: 1 file to rename, 2 files with clean filename, 1 file ignored because of previous errors"
        )


def test_analysing_files_docker_suppression():
    """Validates that 'Analysing X files. Please wait...' is suppressed in Docker mode."""
    import pandas as pd
    from unittest.mock import patch
    from src import utils
    from src.runtime_config import runtime
    from src.config import config

    messy_df = pd.DataFrame([{"File": "A.mkv", "Path": "/A.mkv", "Media": "movie", "Parse": ("A", "2020", None, None)}])
    clean_df = pd.DataFrame()

    saved_ai = runtime.ai_fallback_enabled
    runtime.ai_fallback_enabled = False
    try:
        with patch.object(config, "is_docker_environment", return_value=True), patch("src.ui.print_log") as mock_log:
            with patch("src.utils.correct_movie_filename", return_value="A (2020).mkv"):
                utils.get_corrected_media_filenames(messy_df, clean_df)
                for call_item in mock_log.call_args_list:
                    assert "Please wait" not in str(call_item)

        with patch.object(config, "is_docker_environment", return_value=False), patch("src.ui.print_log") as mock_log:
            with patch("src.utils.correct_movie_filename", return_value="A (2020).mkv"):
                utils.get_corrected_media_filenames(messy_df, clean_df)
                logged = " ".join([str(c[0][0]) for c in mock_log.call_args_list if c[0]])
                assert "Analysing 1 file. Please wait..." in logged
    finally:
        runtime.ai_fallback_enabled = saved_ai
