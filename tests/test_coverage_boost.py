import os
import sys
import json
import time
import runpy
import pytest
from pathlib import Path
from datetime import datetime
from configparser import ConfigParser
from unittest.mock import patch, MagicMock
import pandas as pd

import main
from src import ui, files, utils, mail, api
from src.config import ConfigManager, config

# =========================================================================
# 1. Tests for main.py execution flows and error handling
# =========================================================================


def test_main_no_media_files_found(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["main.py"])
    with (
        patch("src.ui.parse_arguments") as mock_args,
        patch("src.utils.verify_folders"),
        patch("src.files.search_media_files", return_value=(pd.DataFrame(), pd.DataFrame())),
        patch("src.ui.print_log") as mock_log,
    ):
        mock_args.return_value = MagicMock(subcommand=None, path=None, only_rename=False, simulate=False)
        assert main.main() == 0
        logged = " ".join([str(c[0][0]) for c in mock_log.call_args_list if c[0]])
        assert "No media files found to process" in logged


def test_main_no_media_files_to_rename(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["main.py"])
    df_messy = pd.DataFrame([{"File": "A.mkv"}])
    df_clean = pd.DataFrame([{"Original": "A.mkv", "Corrected": "A.mkv"}])

    with (
        patch("src.ui.parse_arguments") as mock_args,
        patch("src.utils.verify_folders"),
        patch("src.files.search_media_files", return_value=(df_messy, df_clean)),
        patch("src.utils.get_corrected_media_filenames", return_value=df_clean),
        patch("src.utils.has_files_to_rename", return_value=False),
        patch("src.ui.print_log") as mock_log,
    ):
        mock_args.return_value = MagicMock(subcommand=None, path=None, only_rename=True, simulate=False)
        assert main.main() == 0
        logged = " ".join([str(c[0][0]) for c in mock_log.call_args_list if c[0]])
        assert "No media files to rename" in logged


def test_main_only_rename_execution(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "argv", ["main.py", "--only-rename"])
    video_file = tmp_path / "Movie (2020).mkv"
    video_file.touch()

    df_messy = pd.DataFrame([{"File": "Movie.mkv"}])
    df_clean = pd.DataFrame(
        [
            {
                "File": "Movie.mkv",
                "Original": "Movie.mkv",
                "Corrected": "Movie (2020)",
                "Path": str(video_file),
                "Media": "movie",
            }
        ]
    )

    with (
        patch("src.ui.parse_arguments") as mock_args,
        patch("src.utils.verify_folders"),
        patch("src.files.search_media_files", return_value=(df_messy, pd.DataFrame())),
        patch("src.utils.get_corrected_media_filenames", return_value=df_clean),
        patch("src.utils.has_files_to_rename", return_value=True),
        patch("src.ui.display_corrected_filenames"),
        patch("src.ui.user_confirmation"),
        patch("src.files.rename_media_files", return_value=df_clean),
        patch("src.mail.send_media_success_email") as mock_mail,
    ):
        mock_args.return_value = MagicMock(subcommand=None, path=None, only_rename=True, simulate=False)
        assert main.main() == 0
        mock_mail.assert_called_once_with(
            media_name="Movie (2020).mkv",
            original_name="Movie.mkv",
            media_type="movie",
            destination_path=str(video_file),
        )


def test_main_normal_flow_success(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "argv", ["main.py"])
    old_f = tmp_path / "Old.mkv"
    new_f = tmp_path / "New.mkv"

    df_messy = pd.DataFrame([{"File": "Old.mkv"}])
    df_clean = pd.DataFrame(
        [{"File": "Old.mkv", "Original": "Old.mkv", "Corrected": "New", "Path": str(old_f), "Media": "movie"}]
    )

    with (
        patch("src.ui.parse_arguments") as mock_args,
        patch("src.utils.verify_folders"),
        patch("src.files.search_media_files", return_value=(df_messy, pd.DataFrame())),
        patch("src.utils.get_corrected_media_filenames", return_value=df_clean),
        patch("src.utils.has_files_to_rename", return_value=True),
        patch("src.ui.display_corrected_filenames"),
        patch("src.ui.user_confirmation"),
        patch("src.files.rename_media_files", return_value=df_clean),
        patch("src.files.sort_media_files", return_value=[(old_f, new_f)]),
        patch("src.ui.display_sorted_files"),
        patch("src.files.move_media_files", return_value=(1, 0)) as mock_move,
    ):
        mock_args.return_value = MagicMock(subcommand=None, path=None, only_rename=False, simulate=False)
        assert main.main() == 0
        mock_move.assert_called_once()


def test_main_normal_flow_empty_clean_after_rename(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["main.py"])
    df_messy = pd.DataFrame([{"File": "Old.mkv"}])
    df_clean = pd.DataFrame(
        [{"File": "Old.mkv", "Original": "Old.mkv", "Corrected": "New", "Path": "/tmp/old", "Media": "movie"}]
    )

    with (
        patch("src.ui.parse_arguments") as mock_args,
        patch("src.utils.verify_folders"),
        patch("src.files.search_media_files", return_value=(df_messy, pd.DataFrame())),
        patch("src.utils.get_corrected_media_filenames", return_value=df_clean),
        patch("src.utils.has_files_to_rename", return_value=True),
        patch("src.ui.display_corrected_filenames"),
        patch("src.ui.user_confirmation"),
        patch("src.files.rename_media_files", return_value=pd.DataFrame()),
        patch("src.ui.print_log") as mock_log,
    ):
        mock_args.return_value = MagicMock(subcommand=None, path=None, only_rename=False, simulate=False)
        assert main.main() == 0
        logged = " ".join([str(c[0][0]) for c in mock_log.call_args_list if c[0]])
        assert "No media files to sort and move" in logged


def test_main_runtime_error_handled(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["main.py"])
    with (
        patch("src.ui.parse_arguments", side_effect=RuntimeError("Fatal runtime err")),
        patch("src.ui.print_log"),
        patch("src.mail.send_error_email") as mock_mail,
    ):
        with pytest.raises(SystemExit) as exc_info:
            main.main()
        assert exc_info.value.code == 1
        mock_mail.assert_called_once_with(error_message="Fatal runtime err")


def test_main_generic_exception_handled(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["main.py"])
    with (
        patch("src.ui.parse_arguments", side_effect=ZeroDivisionError("division by zero")),
        patch("src.ui.print_log"),
        patch("src.mail.send_error_email") as mock_mail,
    ):
        with pytest.raises(SystemExit) as exc_info:
            main.main()
        assert exc_info.value.code == 1
        assert mock_mail.call_count == 1
        assert "division by zero" in mock_mail.call_args[1]["error_message"]


def test_main_dunder_main(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["main.py", "config", "--path"])
    with patch("src.ui.handle_config_command"):
        runpy.run_path("main.py", run_name="__main__")


def test_main_with_gui_flag(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["main.py", "--gui"])
    with (
        patch("src.config.config.run_gui", return_value=True) as mock_run_gui,
        patch("src.ui.hide_console_window") as mock_hide,
    ):
        import main

        assert main.main() == 0
        mock_run_gui.assert_called_once()
        mock_hide.assert_called_once()


def test_main_double_click_launches_gui(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["main.py"])
    with (
        patch("src.ui.is_double_clicked", return_value=True),
        patch("src.ui.hide_console_window") as mock_hide,
        patch("src.config.config.run_gui", return_value=True) as mock_run_gui,
    ):
        import main

        assert main.main() == 0
        mock_hide.assert_called_once()
        mock_run_gui.assert_called_once()


# =========================================================================
# 2. Tests for src/api.py (Gemini response parsing & error handling)
# =========================================================================


def test_gemini_api_call_success_with_missing_tags(monkeypatch):
    media_info = {
        "File": "Blade.Runner.mkv",
        "Folder": "test",
        "Path": "/test/Blade.Runner.mkv",
        "Clean": "Blade Runner",
        "Parse": None,
        "Media": "movie",
    }

    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = json.dumps(
        {
            "success": 1,
            "name": "Blade Runner",
            "year": "1982",
            "original_language": "en",
            "missing_tags": ["remux", "1080p"],
        }
    )
    mock_client.models.generate_content.return_value = mock_response

    with (
        patch("google.genai.Client", return_value=mock_client),
        patch("src.mail.send_tag_learned_email") as mock_send_tag_email,
        patch("src.api.print_log") as mock_print_log,
        patch("src.ui.VERBOSE_ENABLED", True),
        patch("src.ui.LEARN_ENABLED", True),
        patch("src.api.tag_manager.add_gemini_tags", return_value=["remux", "1080p"]) as mock_add_tags,
    ):
        res = api.gemini_api_call(media_info)
        assert res[0] is True
        assert res[1] == "Blade Runner"
        assert res[2] == "1982"
        assert res[3] == "en"
        assert res[4] == ["remux", "1080p"]
        mock_send_tag_email.assert_called_once_with(
            tags=["remux", "1080p"],
            filename="Blade.Runner.mkv",
            media_title="Blade Runner",
            file_path="/test/Blade.Runner.mkv",
        )
        mock_add_tags.assert_called_once_with(["remux", "1080p"])

    # When LEARN_ENABLED is True but no tags were added (e.g. duplicates/rejected)
    with (
        patch("google.genai.Client", return_value=mock_client),
        patch("src.mail.send_tag_learned_email") as mock_send_tag_email,
        patch("src.api.print_log") as mock_print_log,
        patch("src.ui.VERBOSE_ENABLED", True),
        patch("src.ui.LEARN_ENABLED", True),
        patch("src.api.tag_manager.add_gemini_tags", return_value=[]) as mock_add_tags,
    ):
        res = api.gemini_api_call(media_info)
        assert res[0] is True
        mock_send_tag_email.assert_not_called()

    # When LEARN_ENABLED is False
    with (
        patch("google.genai.Client", return_value=mock_client),
        patch("src.mail.send_tag_learned_email") as mock_send_tag_email,
        patch("src.api.print_log") as mock_print_log,
        patch("src.ui.VERBOSE_ENABLED", True),
        patch("src.ui.LEARN_ENABLED", False),
        patch("src.api.tag_manager.add_gemini_tags") as mock_add_tags,
    ):
        res = api.gemini_api_call(media_info)
        assert res[0] is True
        mock_send_tag_email.assert_not_called()
        mock_add_tags.assert_not_called()
        logged = " ".join([str(c[0][0]) for c in mock_print_log.call_args_list if c[0]])
        assert "learning disabled" in logged


def test_gemini_api_call_success_equals_zero(monkeypatch):
    media_info = {
        "File": "unrecognized.mkv",
        "Folder": "test",
        "Path": "/test",
        "Clean": "unknown",
        "Parse": None,
        "Media": "movie",
    }
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = json.dumps({"success": 0})
    mock_client.models.generate_content.return_value = mock_response

    with patch("google.genai.Client", return_value=mock_client), patch("src.api.print_log") as mock_print_log:
        res = api.gemini_api_call(media_info)
        assert res == [False, None, None, None, None]
        logged = " ".join([str(c[0][0]) for c in mock_print_log.call_args_list if c[0]])
        assert "Impossible to read the json data" in logged


def test_gemini_api_call_json_decode_error(monkeypatch):
    media_info = {
        "File": "corrupted.mkv",
        "Folder": "test",
        "Path": "/test",
        "Clean": "corrupted",
        "Parse": None,
        "Media": "movie",
    }
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = "NOT_JSON{{"
    mock_client.models.generate_content.return_value = mock_response

    with patch("google.genai.Client", return_value=mock_client), patch("src.api.print_error") as mock_err:
        res = api.gemini_api_call(media_info)
        assert res == [False, None, None, None, None]
        mock_err.assert_called_once()


def test_gemini_api_call_exception():
    media_info = {
        "File": "test.mkv",
        "Folder": "test",
        "Path": "/test",
        "Clean": "test",
        "Parse": None,
        "Media": "movie",
    }
    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = Exception("API connection dropped")

    with (
        patch("google.genai.Client", return_value=mock_client),
        patch("src.api.print_error") as mock_err,
        pytest.raises(RuntimeError),
    ):
        api.gemini_api_call(media_info)
        mock_err.assert_called_once()


# =========================================================================
# 3. Tests for src/config.py (paths resolution and properties)
# =========================================================================


def test_resolve_config_path_variations(tmp_path, monkeypatch):
    cm = ConfigManager.__new__(ConfigManager)

    # 1. Custom path parameter
    assert cm._resolve_config_path("custom.ini") == Path("custom.ini").resolve()

    # 2. Local config.ini in cwd
    local_config = tmp_path / "config.ini"
    local_config.touch()
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("CONFIG_FILE", raising=False)
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    assert cm._resolve_config_path() == local_config.resolve()
    local_config.unlink()

    # 3. Quarantine path when PYTEST_CURRENT_TEST is present
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "running")
    quarantine = cm._resolve_config_path()
    assert "pytest_rename_quarantine" in str(quarantine)
    monkeypatch.delenv("PYTEST_CURRENT_TEST")

    # 4. NT with and without APPDATA
    with patch("os.name", "nt"), patch("src.config.Path") as mock_p:
        mock_p(".rename.ini").resolve.return_value.is_file.return_value = False
        mock_p("config.ini").resolve.return_value.is_file.return_value = False
        with patch.dict(os.environ, {"APPDATA": "C:\\AppData", "MIN_FILE_SIZE_MB": "-1"}, clear=True):
            cm._resolve_config_path()
            mock_p.assert_any_call("C:\\AppData")

        mock_p.reset_mock()
        mock_p(".rename.ini").resolve.return_value.is_file.return_value = False
        mock_p("config.ini").resolve.return_value.is_file.return_value = False
        with patch.dict(os.environ, {"MIN_FILE_SIZE_MB": "-1"}, clear=True):
            cm._resolve_config_path()
            mock_p.home.assert_called_once()

    # 5. Posix with XDG_CONFIG_HOME
    with patch("os.name", "posix"), patch("src.config.Path") as mock_p:
        mock_p(".rename.ini").resolve.return_value.is_file.return_value = False
        mock_p("config.ini").resolve.return_value.is_file.return_value = False
        with patch.dict(os.environ, {"XDG_CONFIG_HOME": "/custom/xdg", "MIN_FILE_SIZE_MB": "-1"}, clear=True):
            cm._resolve_config_path()
            mock_p.assert_any_call("/custom/xdg")

    # 6. Posix without XDG_CONFIG_HOME
    with patch("os.name", "posix"), patch("src.config.Path") as mock_p:
        mock_p(".rename.ini").resolve.return_value.is_file.return_value = False
        mock_p("config.ini").resolve.return_value.is_file.return_value = False
        with patch.dict(os.environ, {"MIN_FILE_SIZE_MB": "-1"}, clear=True):
            cm._resolve_config_path()
            mock_p.home.assert_called_once()


def test_config_save_quarantine_guard(tmp_path):
    cm = ConfigManager(custom_path=str(tmp_path / "custom.ini"))
    real_user_path = (cm._get_default_user_dir() / "config.ini").resolve()
    cm.config_path = real_user_path

    # Verify that calling save() reroutes to quarantine instead of writing to real user config
    cm.save()
    assert "pytest_rename_quarantine" in str(cm.config_path)


def test_config_save_quarantine_guard_exception(tmp_path):
    cm = ConfigManager(custom_path=str(tmp_path / "custom.ini"))
    with patch.object(cm, "_get_default_user_dir", side_effect=RuntimeError("simulated error")):
        cm.save()


def test_config_property_setters_and_string_getters(tmp_path):
    test_ini = tmp_path / "props.ini"
    cm = ConfigManager(custom_path=str(test_ini))

    # MAIL and MAIL_PSWD
    cm.MAIL = "my@mail.com"
    assert cm.MAIL == "my@mail.com"
    cm.MAIL = None
    assert cm.MAIL is None

    cm.MAIL_PSWD = "secret_password"
    assert cm.MAIL_PSWD == "secret_password"
    cm.MAIL_PSWD = None
    assert cm.MAIL_PSWD is None

    # API Keys and Provider properties
    cm.TMDB_API_KEY = "tmdb_test_key"
    assert cm.TMDB_API_KEY == "tmdb_test_key"
    cm.TMDB_API_KEY = None
    assert cm.TMDB_API_KEY is None

    cm.GEMINI_API_KEY = "gemini_test_key"
    assert cm.GEMINI_API_KEY == "gemini_test_key"
    cm.GEMINI_API_KEY = None
    assert cm.GEMINI_API_KEY is None

    cm.GROQ_API_KEY = "groq_test_key"
    assert cm.GROQ_API_KEY == "groq_test_key"
    cm.GROQ_API_KEY = None
    assert cm.GROQ_API_KEY is None

    cm.OPENROUTER_API_KEY = "openrouter_test_key"
    assert cm.OPENROUTER_API_KEY == "openrouter_test_key"
    cm.OPENROUTER_API_KEY = None
    assert cm.OPENROUTER_API_KEY is None

    cm.CLOUDFLARE_API_TOKEN = "cf_token_key"
    assert cm.CLOUDFLARE_API_TOKEN == "cf_token_key"
    cm.CLOUDFLARE_API_TOKEN = None
    assert cm.CLOUDFLARE_API_TOKEN is None

    cm.CLOUDFLARE_ACCOUNT_ID = "cf_account_123"
    assert cm.CLOUDFLARE_ACCOUNT_ID == "cf_account_123"
    cm.CLOUDFLARE_ACCOUNT_ID = None
    assert cm.CLOUDFLARE_ACCOUNT_ID is None

    # NOTIFY_ON_SUCCESS
    cm.NOTIFY_ON_SUCCESS = True
    assert cm.NOTIFY_ON_SUCCESS is True
    cm.set("options.notify_on_success", "yes")
    assert cm.NOTIFY_ON_SUCCESS is True
    cm.NOTIFY_ON_SUCCESS = False
    assert cm.NOTIFY_ON_SUCCESS is False

    # NOTIFY_ON_ERROR
    cm.NOTIFY_ON_ERROR = True
    assert cm.NOTIFY_ON_ERROR is True
    cm.set("options.notify_on_error", "1")
    assert cm.NOTIFY_ON_ERROR is True
    cm.NOTIFY_ON_ERROR = False
    assert cm.NOTIFY_ON_ERROR is False

    # NOTIFY_ON_TAG
    cm.NOTIFY_ON_TAG = True
    assert cm.NOTIFY_ON_TAG is True
    cm.set("options.notify_on_tag", "1")
    assert cm.NOTIFY_ON_TAG is True
    cm.NOTIFY_ON_TAG = False
    assert cm.NOTIFY_ON_TAG is False

    # BYPASS
    cm.BYPASS = True
    assert cm.BYPASS is True
    cm.set("options.bypass", "true")
    assert cm.BYPASS is True
    cm.BYPASS = False
    assert cm.BYPASS is False

    # AI
    cm.AI = True
    assert cm.AI is True
    cm.set("options.ai", "y")
    assert cm.AI is True
    cm.AI = False
    assert cm.AI is False

    # LEARN
    cm.LEARN = True
    assert cm.LEARN is True
    cm.set("options.learn", "y")
    assert cm.LEARN is True
    cm.LEARN = False
    assert cm.LEARN is False

    # LOG
    cm.LOG = True
    assert cm.LOG is True
    cm.set("options.log", "t")
    assert cm.LOG is True
    cm.LOG = False
    assert cm.LOG is False

    # VERBOSE
    cm.VERBOSE = True
    assert cm.VERBOSE is True
    cm.set("options.verbose", "yes")
    assert cm.VERBOSE is True
    cm.VERBOSE = False
    assert cm.VERBOSE is False

    # RESOLUTION and QUALITY
    cm.set("options.resolution", "y")
    cm.set("options.quality", "n")
    assert cm.RESOLUTION is True
    assert cm.QUALITY is False


# =========================================================================
# 4. Tests for src/files.py coverage edges
# =========================================================================


def test_move_media_files_with_clean_data_table_and_fallback(tmp_path, monkeypatch):
    movies_dir = tmp_path / "Movies"
    tv_dir = tmp_path / "TV"
    downloads_dir = tmp_path / "Downloads"
    movies_dir.mkdir()
    tv_dir.mkdir()
    downloads_dir.mkdir()

    f1 = downloads_dir / "f1.mkv"
    f2 = downloads_dir / "f2.mkv"
    f1.write_text("1")
    f2.write_text("2")

    dest1 = movies_dir / "f1_dest.mkv"
    dest2 = tv_dir / "f2_dest.mkv"

    clean_df = pd.DataFrame([{"File": "f1.mkv", "Corrected": "f1_dest", "Media": "movie"}])

    monkeypatch.setattr(files, "MOVIES_FOLDER", str(movies_dir))
    monkeypatch.setattr(files, "TV_SHOWS_FOLDER", str(tv_dir))
    monkeypatch.setattr(files, "NOT_SORTED_MEDIA_FILES_FOLDER", str(downloads_dir))

    with patch("src.mail.send_media_success_email") as mock_success_mail, patch("src.files.remove_empty_folders"):
        files.move_media_files([(f1, dest1), (f2, dest2)], clean_data_table=clean_df)
        assert mock_success_mail.call_count == 2
        # First call has media from table
        assert mock_success_mail.call_args_list[0][1]["media_type"] == "movie"
        # Second call resolved fallback to tv
        assert mock_success_mail.call_args_list[1][1]["media_type"] == "tv"


def test_move_media_files_fallback_movie_and_exception(tmp_path, monkeypatch):
    movies_dir = tmp_path / "Movies"
    downloads_dir = tmp_path / "Downloads"
    other_dir = tmp_path / "other"
    movies_dir.mkdir()
    downloads_dir.mkdir()
    other_dir.mkdir()

    f1 = downloads_dir / "f1.mkv"
    f1.write_text("1")
    dest1 = movies_dir / "f1_dest.mkv"

    f2 = downloads_dir / "f2.mkv"
    f2.write_text("2")
    dest2 = other_dir / "f2_dest.mkv"

    monkeypatch.setattr(files, "MOVIES_FOLDER", str(movies_dir))
    monkeypatch.setattr(files, "TV_SHOWS_FOLDER", None)
    monkeypatch.setattr(files, "NOT_SORTED_MEDIA_FILES_FOLDER", str(downloads_dir))

    # Test movie fallback
    with patch("src.mail.send_media_success_email") as mock_mail, patch("src.files.remove_empty_folders"):
        files.move_media_files([(f1, dest1)], clean_data_table=None)
        assert mock_mail.call_args[1]["media_type"] == "movie"

    # Test is_relative_to raising exception (lines 257-258)
    with (
        patch("src.mail.send_media_success_email") as mock_mail,
        patch.object(Path, "is_relative_to", side_effect=Exception("mock err")),
        patch("src.files.remove_empty_folders"),
    ):
        files.move_media_files([(f2, dest2)], clean_data_table=None)
        assert mock_mail.call_args[1]["media_type"] == "unknown"


def test_move_media_files_error_email_failure_caught(tmp_path, monkeypatch):
    downloads = tmp_path / "dl"
    downloads.mkdir()
    bad_source = downloads / "non_existent.mkv"
    dest = tmp_path / "dest.mkv"

    monkeypatch.setattr(files, "NOT_SORTED_MEDIA_FILES_FOLDER", str(downloads))

    with (
        patch("src.mail.send_error_email", side_effect=Exception("SMTP Connection dead")),
        patch("src.ui.print_log") as mock_log,
        patch("src.files.remove_empty_folders"),
    ):
        files.move_media_files([(bad_source, dest)])
        logged = " ".join([str(c[0][0]) for c in mock_log.call_args_list if c[0]])
        assert "Error while trying to send the email" in logged


# =========================================================================
# 5. Tests for src/mail.py coverage edges
# =========================================================================


def test_dispatch_email_missing_credentials():
    with patch("src.mail._get_credentials", return_value=(None, None)), patch("src.mail.smtplib.SMTP_SSL") as mock_smtp:
        msg = MagicMock()
        mail._dispatch_email(msg)
        mock_smtp.assert_not_called()


def test_send_media_success_email_dispatch_error_logged():
    with (
        patch("src.mail.is_success_mail_enabled", return_value=True),
        patch("src.mail._get_credentials", return_value=("me@test.com", "pass")),
        patch("src.mail._dispatch_email", side_effect=Exception("Timeout")),
        patch("src.ui.print_log") as mock_log,
    ):
        mail.send_media_success_email("Test", "Test.mkv", "movie", "/dest/path")
        logged = " ".join([str(c[0][0]) for c in mock_log.call_args_list if c[0]])
        assert "Error while trying to send the email: Timeout" in logged


def test_send_email_with_exception_in_details():
    with (
        patch("src.mail.is_error_mail_enabled", return_value=True),
        patch("src.mail._get_credentials", return_value=("me@test.com", "pass")),
        patch("src.mail._dispatch_email"),
    ):
        # Exception string is not already in message
        exc = RuntimeError("Strange filesystem error")
        mail.send_email(message="A failure happened", exception=exc)


# =========================================================================
# 6. Tests for Docker features and dual logging
# =========================================================================


def test_docker_environment_detection(monkeypatch):
    monkeypatch.delenv("DOCKER_CONTAINER", raising=False)
    with patch("os.path.exists", return_value=False):
        assert ConfigManager.is_docker_environment() is False

    monkeypatch.setenv("DOCKER_CONTAINER", "1")
    assert ConfigManager.is_docker_environment() is True

    monkeypatch.delenv("DOCKER_CONTAINER")
    with patch("os.path.exists", side_effect=lambda p: str(p) == "/.dockerenv"):
        assert ConfigManager.is_docker_environment() is True


def test_docker_resolve_config_path(monkeypatch, tmp_path):
    cm = ConfigManager.__new__(ConfigManager)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("RENAME_TEST_ALLOW_REAL_PATH", "1")
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.delenv("CONFIG_FILE", raising=False)

    # 1. CONFIG_FILE environment variable
    custom_cfg = tmp_path / "custom.ini"
    monkeypatch.setenv("CONFIG_FILE", str(custom_cfg))
    assert cm._resolve_config_path() == custom_cfg.resolve()
    monkeypatch.delenv("CONFIG_FILE")

    # 2. In Docker, /config/config.ini is present
    def mock_path_file_call(p):
        path_obj = Path(p) if isinstance(p, str) else p
        mock_p = MagicMock()
        mock_p.resolve.return_value = path_obj
        if str(p) in (".rename.ini", "config.ini"):
            mock_p.is_file.return_value = False
        elif str(p) == "/config/config.ini":
            mock_p.is_file.return_value = True
        elif str(p) == "/config":
            mock_p.is_dir.return_value = False
        return mock_p

    with (
        patch.object(ConfigManager, "is_docker_environment", return_value=True),
        patch("src.config.Path", side_effect=mock_path_file_call),
    ):
        res = cm._resolve_config_path()
        assert res == Path("/config/config.ini")

    # 3. In Docker, /config is directory
    def mock_path_dir_call(p):
        path_obj = Path(p) if isinstance(p, str) else p
        mock_p = MagicMock()
        mock_p.resolve.return_value = path_obj
        if str(p) in (".rename.ini", "config.ini", "/config/config.ini"):
            mock_p.is_file.return_value = False
        elif str(p) == "/config":
            mock_p.is_dir.return_value = True
        return mock_p

    with (
        patch.object(ConfigManager, "is_docker_environment", return_value=True),
        patch("src.config.Path", side_effect=mock_path_dir_call),
    ):
        res = cm._resolve_config_path()
        assert res == Path("/config/config.ini")


def test_docker_defaults_init_and_fallback(monkeypatch, tmp_path):
    cm = ConfigManager(custom_path=str(tmp_path / "nonexistent.ini"))

    with patch.object(cm, "is_docker_environment", return_value=True):
        cm.load()
        assert cm.get("paths.movies_folder") == "/data/Movies"
        assert cm.get("paths.tv_shows_folder") == "/data/TV_Shows"
        assert cm.get("paths.not_sorted_media_files_folder") in ("/data/input", "/data/Downloads")
        assert cm.get("options.daemon") is True
        assert cm.get("options.bypass") is True
        assert cm.get("options.verbose") is True
        assert cm.get("options.notify_on_error") is False

        # Fallback values from get_with_source when section does not have keys
        cm.parser.clear()
        assert cm.get_with_source("paths.movies_folder") == ("/data/Movies", "DEFAULT")
        assert cm.get_with_source("paths.tv_shows_folder") == ("/data/TV_Shows", "DEFAULT")
        assert cm.get_with_source("paths.not_sorted_media_files_folder") == ("/data/Downloads", "DEFAULT")
        assert cm.get_with_source("options.daemon") == (True, "DEFAULT")
        assert cm.get_with_source("options.bypass") == (True, "DEFAULT")
        assert cm.get_with_source("options.verbose") == (True, "DEFAULT")
        assert cm.get_with_source("options.notify_on_error") == (False, "DEFAULT")

    # Test save OSError handling in _init_docker_defaults
    cm2 = ConfigManager.__new__(ConfigManager)
    cm2.parser = ConfigParser()
    with patch.object(cm2, "save", side_effect=OSError("Read only fs")):
        cm2._init_docker_defaults()
        assert cm2.parser.get("paths", "movies_folder") == "/data/Movies"


def test_clean_environment_variables(monkeypatch, tmp_path):
    cm = ConfigManager(custom_path=str(tmp_path / "test.ini"))

    # Test clean environment variables take effect
    monkeypatch.setenv("MOVIES_FOLDER", "/mnt/custom_movies")
    monkeypatch.setenv("TV_SHOWS_FOLDER", "/mnt/custom_tv")
    monkeypatch.setenv("INPUT_FOLDER", "/mnt/custom_input")
    monkeypatch.setenv("TMDB_API_KEY", "tmdb12345")
    monkeypatch.setenv("DAEMON", "true")
    monkeypatch.setenv("POLLING_INTERVAL", "30")
    monkeypatch.setenv("LOG", "true")

    val, source = cm.get_with_source("paths.movies_folder")
    assert val == "/mnt/custom_movies"
    assert source == "ENV"

    val, source = cm.get_with_source("paths.tv_shows_folder")
    assert val == "/mnt/custom_tv"
    assert source == "ENV"

    val, source = cm.get_with_source("paths.not_sorted_media_files_folder")
    assert val == "/mnt/custom_input"
    assert source == "ENV"

    val, source = cm.get_with_source("api.tmdb_api_key")
    assert val == "tmdb12345"
    assert source == "ENV"

    val, source = cm.get_with_source("options.daemon")
    assert val is True
    assert source == "ENV"

    val, source = cm.get_with_source("options.polling_interval")
    assert val == "30"
    assert source == "ENV"
    assert cm.POLLING_INTERVAL == 30

    val, source = cm.get_with_source("options.log")
    assert val is True
    assert source == "ENV"

    # Verify legacy RENAME_* is NOT recognized (no backward compatibility)
    monkeypatch.delenv("MOVIES_FOLDER", raising=False)
    monkeypatch.setenv("RENAME_MOVIES_FOLDER", "/mnt/legacy_movies")
    val, source = cm.get_with_source("paths.movies_folder")
    assert source != "ENV"
    assert val != "/mnt/legacy_movies"


def test_check_log_dir_permissions(tmp_path):
    # Success case
    ok, err = ui.check_log_dir_permissions(tmp_path)
    assert ok is True
    assert err == ""

    # Failure case: PermissionError on mkdir / open
    with patch("pathlib.Path.mkdir", side_effect=PermissionError("Permission denied")):
        ok, err = ui.check_log_dir_permissions(tmp_path / "sub")
        assert ok is False
        assert "Permission denied" in err


def test_parse_arguments_docker_and_logging(monkeypatch, tmp_path):
    # 1. Docker mode with --log and writable dir -> LOG_MODE == 'both'
    monkeypatch.setattr(sys, "argv", ["main.py", "--log"])
    monkeypatch.setenv("DOCKER_CONTAINER", "1")
    with (
        patch("src.ui.get_log_dir", return_value=tmp_path),
        patch("src.ui.check_log_dir_permissions", return_value=(True, "")),
    ):
        ui.parse_arguments()
        assert ui.LOG_MODE == "both"
        assert ui.LOG_ENABLED is True

    # 2. Classic mode with --log and writable dir -> LOG_MODE == 'file'
    monkeypatch.delenv("DOCKER_CONTAINER", raising=False)
    with (
        patch("os.path.exists", return_value=False),
        patch("src.ui.get_log_dir", return_value=tmp_path),
        patch("src.ui.check_log_dir_permissions", return_value=(True, "")),
    ):
        ui.parse_arguments()
        assert ui.LOG_MODE == "file"
        assert ui.LOG_ENABLED is True

    # 3. Log directory not writable -> fallback to console with stderr warning
    with (
        patch("src.ui.get_log_dir", return_value=tmp_path),
        patch("src.ui.check_log_dir_permissions", return_value=(False, "Read-only file system")),
        patch("sys.stderr.write") as mock_stderr,
    ):
        ui.parse_arguments()
        assert ui.LOG_MODE == "console"
        assert ui.LOG_ENABLED is False
        mock_stderr.assert_called()
        err_out = "".join([str(c[0][0]) for c in mock_stderr.call_args_list])
        assert "Warning: Log directory" in err_out
        assert "Falling back to console logging" in err_out

    # 4. Without --log -> LOG_MODE == 'console'
    monkeypatch.setattr(sys, "argv", ["main.py"])
    ui.parse_arguments()
    assert ui.LOG_MODE == "console"
    assert ui.LOG_ENABLED is False

    # 5. config.DAEMON is True, but --simulate is passed -> DAEMON_ENABLED is False
    monkeypatch.setattr(config, "DAEMON", True)
    monkeypatch.setattr(sys, "argv", ["main.py", "--simulate"])
    ui.parse_arguments()
    assert ui.DAEMON_ENABLED is False


def test_print_log_dual_and_error_handling(monkeypatch, tmp_path):
    monkeypatch.setattr("src.ui.get_log_dir", lambda: tmp_path)
    monkeypatch.setattr("src.ui._last_log_cleanup_date", None)

    # LOG_MODE == 'both': prints to console AND writes to file
    monkeypatch.setattr(ui, "LOG_MODE", "both")
    monkeypatch.setattr(ui, "LOG_ENABLED", True)
    with patch("builtins.print") as mock_print:
        ui.print_log("dual log message")
        mock_print.assert_called_once_with("dual log message")

    today = datetime.now().strftime("%Y-%m-%d")
    log_file = tmp_path / f"{today}.txt"
    assert log_file.is_file()
    assert "dual log message" in log_file.read_text(encoding="utf-8")

    # LOG_MODE == 'file': writes to file, console silent
    monkeypatch.setattr(ui, "LOG_MODE", "file")
    monkeypatch.setattr(ui, "LOG_ENABLED", True)
    with patch("builtins.print") as mock_print:
        ui.print_log("file-only log message")
        mock_print.assert_not_called()
    assert "file-only log message" in log_file.read_text(encoding="utf-8")

    # LOG_MODE == 'console': prints to console, does not write
    monkeypatch.setattr(ui, "LOG_MODE", "console")
    monkeypatch.setattr(ui, "LOG_ENABLED", False)
    log_file.unlink()
    with patch("builtins.print") as mock_print:
        ui.print_log("console-only log message")
        mock_print.assert_called_once_with("console-only log message")
    assert not log_file.exists()

    # OSError when writing log file is caught safely
    monkeypatch.setattr(ui, "LOG_MODE", "file")
    monkeypatch.setattr(ui, "LOG_ENABLED", True)
    with patch("builtins.open", side_effect=OSError("Disk full")):
        ui.print_log("safe fail")


def test_rich_print_log_modes(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr("src.ui.get_log_dir", lambda: tmp_path)

    # LOG_MODE == 'both'
    monkeypatch.setattr(ui, "LOG_MODE", "both")
    monkeypatch.setattr(ui, "LOG_ENABLED", True)
    with patch("src.ui.print_log") as mock_pl:
        ui.rich_print_log("dual rich message")
        mock_pl.assert_called()
        out = capsys.readouterr().out
        assert "dual rich message" in out

    # LOG_MODE == 'file'
    monkeypatch.setattr(ui, "LOG_MODE", "file")
    monkeypatch.setattr(ui, "LOG_ENABLED", True)
    with patch("src.ui.print_log") as mock_pl:
        ui.rich_print_log("file rich message")
        mock_pl.assert_called()
        out = capsys.readouterr().out
        assert out == ""

    # LOG_MODE == 'console'
    monkeypatch.setattr(ui, "LOG_MODE", "console")
    monkeypatch.setattr(ui, "LOG_ENABLED", False)
    with patch("src.ui.print_log") as mock_pl:
        ui.rich_print_log("console rich message")
        mock_pl.assert_not_called()
        out = capsys.readouterr().out
        assert "console rich message" in out

    # Empty text in rich_print_log
    monkeypatch.setattr(ui, "LOG_MODE", "both")
    monkeypatch.setattr(ui, "LOG_ENABLED", True)
    with patch("src.ui.print_log") as mock_pl:
        ui.rich_print_log("")
        mock_pl.assert_not_called()


def test_daemon_non_fatal_recovery_branches(monkeypatch, tmp_path):
    from src import api, files, utils

    monkeypatch.setattr(ui, "DAEMON_ENABLED", True)

    # 1. api_call missing TMDB key in daemon mode returns [False, None, None, None]
    monkeypatch.setattr(api, "TMDB_API_KEY", None)
    monkeypatch.setattr(api.config, "TMDB_API_KEY", None)
    res_tmdb = api.api_call("Inception", "2010", "en-US", "movie")
    assert res_tmdb == [False, None, None, None]

    # 2. gemini_api_call missing Gemini key in daemon mode returns [False, None, None, None, None]
    monkeypatch.setattr(api, "GEMINI_API_KEY", None)
    monkeypatch.setattr(api.config, "GEMINI_API_KEY", None)
    res_gemini = api.gemini_api_call(
        {"File": "t.mkv", "Folder": "d", "Path": "/d/t.mkv", "Clean": "t", "Parse": "t", "Media": "movie"}
    )
    assert res_gemini == [False, None, None, None, None]

    # 3. sort_media_files with empty paths in daemon mode returns []
    df_empty = pd.DataFrame([{"Path": "/tmp/f.mkv", "Corrected": "f", "Media": "unknown"}])
    res_paths = files.sort_media_files(df_empty)
    assert res_paths == []

    # 4. verify_folders unconfigured with exit_on_error=False returns 1
    monkeypatch.setattr(utils, "MOVIES_FOLDER", None)
    ret_unconf = utils.verify_folders(daemon=True, exit_on_error=False)
    assert ret_unconf == 1

    # 5. validate_folder_existence_and_permissions missing folder with exit_on_error=False returns 1
    req_missing = [("paths.movies_folder", tmp_path / "non_existent_folder", "MOVIES_FOLDER", "Movies folder")]
    ret_missing = utils.validate_folder_existence_and_permissions(req_missing, exit_on_error=False)
    assert ret_missing == 1

    # 6. validate_folder_existence_and_permissions permission issue with exit_on_error=False returns 1
    exist_folder = tmp_path / "exist"
    exist_folder.mkdir()
    req_perm = [("paths.movies_folder", exist_folder, "MOVIES_FOLDER", "Movies folder")]
    with patch("src.utils.check_folder_permissions", return_value=(False, False, "Permission denied")):
        ret_perm = utils.validate_folder_existence_and_permissions(req_perm, exit_on_error=False)
        assert ret_perm == 1


def test_folder_errors_dispatch_email(tmp_path, monkeypatch):
    # 1. Unconfigured folder dispatches email
    monkeypatch.setattr(utils, "MOVIES_FOLDER", None)
    with patch("src.mail.send_error_email") as mock_mail:
        utils.verify_folders(daemon=True, exit_on_error=False)
        mock_mail.assert_called_once()
        assert "Missing configuration" in mock_mail.call_args[1]["error_message"]

    # 2. Missing folder dispatches email
    req_missing = [("paths.movies_folder", tmp_path / "ghost_folder", "MOVIES_FOLDER", "Movies folder")]
    with patch("src.mail.send_error_email") as mock_mail:
        utils.validate_folder_existence_and_permissions(req_missing, exit_on_error=False)
        mock_mail.assert_called_once()
        assert "Missing required folder" in mock_mail.call_args[1]["error_message"]

    # 3. Permission issue dispatches email
    exist_folder = tmp_path / "exist_dir"
    exist_folder.mkdir()
    req_perm = [("paths.movies_folder", exist_folder, "MOVIES_FOLDER", "Movies folder")]
    with (
        patch("src.utils.check_folder_permissions", return_value=(False, False, "Permission denied")),
        patch("src.mail.send_error_email") as mock_mail,
    ):
        utils.validate_folder_existence_and_permissions(req_perm, exit_on_error=False)
        mock_mail.assert_called_once()
        assert "Permission error" in mock_mail.call_args[1]["error_message"]


def test_api_keys_missing_dispatch_email(monkeypatch):
    monkeypatch.setattr(ui, "DAEMON_ENABLED", True)
    monkeypatch.setattr(api, "TMDB_API_KEY", None)
    monkeypatch.setattr(api.config, "TMDB_API_KEY", None)

    with patch("src.mail.send_error_email") as mock_mail:
        res = api.api_call("Inception", "2010", "en-US", "movie")
        assert res == [False, None, None, None]
        mock_mail.assert_called_once()
        assert "TMDB API key is not configured" in mock_mail.call_args[1]["error_message"]

    monkeypatch.setattr(api, "GEMINI_API_KEY", None)
    monkeypatch.setattr(api.config, "GEMINI_API_KEY", None)
    with patch("src.mail.send_error_email") as mock_mail:
        res_gemini = api.gemini_api_call({"File": "Test.mkv"})
        assert res_gemini == [False, None, None, None, None]
        mock_mail.assert_called_once()
        assert "Gemini API key is not configured" in mock_mail.call_args[1]["error_message"]


def test_global_excepthook_handling():
    # 1. KeyboardInterrupt and SystemExit should pass through without sending email
    with patch("sys.__excepthook__") as mock_sys_hook, patch("src.mail.send_error_email") as mock_mail:
        main._global_excepthook(KeyboardInterrupt, KeyboardInterrupt(), None)
        mock_sys_hook.assert_called_once()
        mock_mail.assert_not_called()

    with patch("sys.__excepthook__") as mock_sys_hook, patch("src.mail.send_error_email") as mock_mail:
        main._global_excepthook(SystemExit, SystemExit(0), None)
        mock_sys_hook.assert_called_once()
        mock_mail.assert_not_called()

    # 2. Unhandled crash triggers error email and sys.__excepthook__
    with patch("sys.__excepthook__") as mock_sys_hook, patch("src.mail.send_error_email") as mock_mail:
        val_err = ValueError("Crash in background thread")
        main._global_excepthook(ValueError, val_err, None)
        mock_sys_hook.assert_called_once()
        mock_mail.assert_called_once()
        assert "Critical unhandled crash" in mock_mail.call_args[1]["error_message"]


def test_docker_notify_on_error_explicit(tmp_path):
    cm = ConfigManager(custom_path=str(tmp_path / "docker_test.ini"))
    with patch.object(cm, "is_docker_environment", return_value=True):
        cm.load()
        # Default in Docker: notify_on_error is False (zero emails sent)
        assert cm.get("options.notify_on_error") is False
        assert cm.get_with_source("options.notify_on_error") == (False, "INI")

        # Fallback when key is missing
        cm.parser.clear()
        assert cm.get_with_source("options.notify_on_error") == (False, "DEFAULT")

        # When user explicitly configures notify_on_error = true in INI:
        cm.set("options.notify_on_error", "true")
        assert cm.get("options.notify_on_error") is True
        assert cm.get_with_source("options.notify_on_error") == (True, "INI")

        # When user explicitly configures notify_on_error = false in INI:
        cm.set("options.notify_on_error", "false")
        assert cm.get("options.notify_on_error") is False
        assert cm.get_with_source("options.notify_on_error") == (False, "INI")


def test_determine_required_folders_daemon_only_rename(tmp_path):
    # 1. Daemon mode with only_rename=True and custom_path
    reqs = utils.determine_required_folders(daemon=True, custom_path="/custom/path", only_rename=True)
    assert len(reqs) == 1
    assert reqs[0][0] == "cli.path"
    assert reqs[0][1] == "/custom/path"

    # 2. Daemon mode with only_rename=True without custom_path
    reqs_def = utils.determine_required_folders(daemon=True, custom_path=None, only_rename=True)
    assert len(reqs_def) == 1
    assert reqs_def[0][0] == "paths.not_sorted_media_files_folder"


def test_is_file_locked_posix_and_stability(tmp_path, monkeypatch):
    test_file = tmp_path / "test.mkv"
    test_file.write_text("dummy video content")

    # Non-existent file
    assert files.is_file_locked(tmp_path / "nonexistent.mkv") is False

    # Windows lock branches
    with patch("os.rename", side_effect=OSError("File locked")):
        monkeypatch.setattr(os, "name", "nt")
        assert files.is_file_locked(test_file) is True

    with patch("os.rename", return_value=None):
        monkeypatch.setattr(os, "name", "nt")
        assert files.is_file_locked(test_file) is False

    # POSIX tests via _is_file_locked_posix directly
    with patch("time.sleep"):
        # Stable file (not locked)
        assert files._is_file_locked_posix(test_file, wait_interval=0.01) is False

        # File with OSError on stat
        with patch.object(Path, "stat", side_effect=OSError("Read error")):
            assert files._is_file_locked_posix(test_file, wait_interval=0.01) is True

        # File actively changing size
        mock_stat1 = MagicMock(st_mtime=time.time(), st_size=100)
        mock_stat2 = MagicMock(st_mtime=time.time(), st_size=200)
        with patch.object(Path, "stat", side_effect=[mock_stat1, mock_stat2]):
            assert files._is_file_locked_posix(test_file, wait_interval=0.01) is True

        # PermissionError on open (read-only file is not considered locked)
        with patch("builtins.open", side_effect=PermissionError("Permission denied")):
            assert files._is_file_locked_posix(test_file, wait_interval=0.01) is False

        # Generic OSError on open (ignored gracefully)
        with patch("builtins.open", side_effect=OSError("Generic error")):
            assert files._is_file_locked_posix(test_file, wait_interval=0.01) is False

        # POSIX fcntl flock branch
        mock_fcntl = MagicMock()
        with patch.dict(sys.modules, {"fcntl": mock_fcntl}):
            assert files._is_file_locked_posix(test_file, wait_interval=0.01) is False
            assert mock_fcntl.flock.call_count == 2

        # POSIX fcntl flock raises BlockingIOError
        mock_fcntl_locked = MagicMock()
        mock_fcntl_locked.flock.side_effect = BlockingIOError("Flock locked")
        with patch.dict(sys.modules, {"fcntl": mock_fcntl_locked}):
            assert files._is_file_locked_posix(test_file, wait_interval=0.01) is True

    # Test is_file_locked delegation when os.name != 'nt'
    monkeypatch.setattr(os, "name", "posix")
    with (
        patch("os.rename", return_value=None),
        patch("src.files._is_file_locked_posix", return_value=False) as mock_posix,
    ):
        assert files.is_file_locked(test_file) is False
        mock_posix.assert_called_once()


def test_email_safe_header_prevents_injection():
    # Embedded newlines and carriage returns must be stripped
    raw = "Malicious.File\r\nBcc: victim@example.com\n.mkv"
    cleaned = mail._safe_header(raw)
    assert "\r" not in cleaned
    assert "\n" not in cleaned
    assert cleaned == "Malicious.File Bcc: victim@example.com .mkv"

    # Verify sending error email with multiline affected file succeeds without ValueError
    with (
        patch("src.mail._dispatch_email") as mock_dispatch,
        patch("src.mail.is_error_mail_enabled", return_value=True),
        patch("src.mail._get_credentials", return_value=("me@test.com", "pass")),
    ):
        mail.send_email("Error occurred", affected_file=raw)
        mock_dispatch.assert_called_once()
        msg = mock_dispatch.call_args[0][0]
        assert "\n" not in msg["Subject"]
        assert "\r" not in msg["Subject"]
        assert "victim@example.com" in msg["Subject"]


def test_ui_simulate_with_daemon_notice(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["main.py", "--simulate", "--daemon"])
    with patch("src.ui.print_log") as mock_log:
        args = ui.parse_arguments()
        assert args.simulate is True
        assert ui.DAEMON_ENABLED is False
        logged = " ".join(str(call[0][0]) for call in mock_log.call_args_list if call[0])
        assert "simulation mode" in logged.lower()
