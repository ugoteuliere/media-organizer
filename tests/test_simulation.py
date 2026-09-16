import sys
from unittest.mock import patch
import pandas as pd

import main
from src import ui, files, utils


def test_simulation_mode_prevents_file_changes_and_emails(tmp_path, monkeypatch):
    # Setup folders
    downloads = tmp_path / "downloads"
    movies = tmp_path / "movies"
    tv_shows = tmp_path / "tv_shows"
    downloads.mkdir()
    movies.mkdir()
    tv_shows.mkdir()

    # Create dummy video file
    dummy_file = downloads / "Inception.2010.1080p.mkv"
    dummy_file.write_text("dummy content", encoding="utf-8")

    monkeypatch.setattr(ui, "MOVIES_FOLDER", str(movies))
    monkeypatch.setattr(ui, "TV_SHOWS_FOLDER", str(tv_shows))
    monkeypatch.setattr(files, "MOVIES_FOLDER", str(movies))
    monkeypatch.setattr(files, "TV_SHOWS_FOLDER", str(tv_shows))
    monkeypatch.setattr(files, "NOT_SORTED_MEDIA_FILES_FOLDER", str(downloads))
    monkeypatch.setattr(utils, "MOVIES_FOLDER", str(movies))
    monkeypatch.setattr(utils, "TV_SHOWS_FOLDER", str(tv_shows))
    monkeypatch.setattr(utils, "NOT_SORTED_MEDIA_FILES_FOLDER", str(downloads))

    # Mock search_media_files and get_corrected_media_filenames
    messy_df = pd.DataFrame(
        [
            {
                "File": "Inception.2010.1080p.mkv",
                "Folder": str(downloads),
                "Path": str(dummy_file),
                "Clean": "Inception",
                "Parse": None,
                "Media": "movie",
            }
        ]
    )
    clean_df = pd.DataFrame(
        [
            {
                "Original": "Inception.2010.1080p.mkv",
                "Corrected": "Inception (2010)",
                "Path": str(dummy_file),
                "Media": "movie",
            }
        ]
    )

    with (
        patch("src.files.search_media_files", return_value=(messy_df, pd.DataFrame())),
        patch("src.utils.get_corrected_media_filenames", return_value=clean_df),
        patch("src.files.rename_media_files") as mock_rename,
        patch("src.files.move_media_files") as mock_move,
        patch("src.mail.send_media_success_email") as mock_success_mail,
        patch("src.ui.rich_print_log") as mock_rich_log,
    ):
        monkeypatch.setattr(sys, "argv", ["main.py", "-s"])
        exit_code = main.main()

        assert exit_code == 0
        # Verify no file operations took place
        mock_rename.assert_not_called()
        mock_move.assert_not_called()
        mock_success_mail.assert_not_called()

        # Check simulation banner was printed
        log_text = " ".join([str(call[0][0]) for call in mock_rich_log.call_args_list if call[0]])
        assert "Simulation mode complete" in log_text

    # File on disk still has original name and exists
    assert dummy_file.exists()


def test_simulation_mode_with_only_rename(tmp_path, monkeypatch):
    dummy_file = tmp_path / "Dark.S01E01.mkv"
    dummy_file.write_text("dummy", encoding="utf-8")

    messy_df = pd.DataFrame([{"File": "Dark.S01E01.mkv", "Path": str(dummy_file), "Media": "tv"}])
    clean_df = pd.DataFrame(
        [
            {
                "Original": "Dark.S01E01.mkv",
                "Corrected": "Dark - S01E01",
                "Path": str(dummy_file),
                "Media": "tv",
                "Season": "01",
                "Episode": "01",
            }
        ]
    )

    with (
        patch("src.utils.verify_folders"),
        patch("src.files.search_media_files", return_value=(messy_df, pd.DataFrame())),
        patch("src.utils.get_corrected_media_filenames", return_value=clean_df),
        patch("src.files.sort_media_files") as mock_sort,
        patch("src.files.rename_media_files") as mock_rename,
        patch("src.ui.rich_print_log") as mock_rich_log,
    ):
        monkeypatch.setattr(sys, "argv", ["main.py", "--simulate", "--only-rename"])
        exit_code = main.main()

        assert exit_code == 0
        mock_sort.assert_not_called()
        mock_rename.assert_not_called()
        log_text = " ".join([str(call[0][0]) for call in mock_rich_log.call_args_list if call[0]])
        assert "Simulation mode complete" in log_text
