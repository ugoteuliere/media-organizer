import os
import sys
import signal
import threading
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
import pandas as pd

from src import ui, files, utils
from src.config import ConfigManager
from src.exceptions import MediaOrganizerError
import main


@pytest.fixture(autouse=True)
def preserve_signal_handlers():
    orig_int = None
    orig_term = None
    try:
        orig_int = signal.getsignal(signal.SIGINT)
    except Exception:
        pass
    try:
        if hasattr(signal, "SIGTERM"):
            orig_term = signal.getsignal(signal.SIGTERM)
    except Exception:
        pass
    yield
    if orig_int is not None:
        try:
            signal.signal(signal.SIGINT, orig_int)
        except Exception:
            pass
    if orig_term is not None and hasattr(signal, "SIGTERM"):
        try:
            signal.signal(signal.SIGTERM, orig_term)
        except Exception:
            pass


def test_ui_daemon_flags(monkeypatch):
    # -d daemon flag
    monkeypatch.setattr(sys, "argv", ["main.py", "-d"])
    args = ui.parse_arguments()
    assert args.daemon is True
    assert ui.DAEMON_ENABLED is True
    assert ui.BYPASS_ENABLED is True
    assert ui.LOG_ENABLED is False
    assert ui.POLLING_INTERVAL == 15

    # -d with -l enables file logging
    monkeypatch.setattr(sys, "argv", ["main.py", "-d", "-l"])
    args = ui.parse_arguments()
    assert args.daemon is True
    assert ui.DAEMON_ENABLED is True
    assert ui.LOG_ENABLED is True

    # --daemon with custom interval
    monkeypatch.setattr(sys, "argv", ["main.py", "--daemon", "--interval", "30"])
    args = ui.parse_arguments()
    assert args.daemon is True
    assert ui.DAEMON_ENABLED is True
    assert ui.BYPASS_ENABLED is True
    assert ui.LOG_ENABLED is False
    assert ui.POLLING_INTERVAL == 30

    # No backward compatibility with --autonomous -> Must raise SystemExit
    monkeypatch.setattr(sys, "argv", ["main.py", "--autonomous"])
    with pytest.raises(SystemExit):
        ui.parse_arguments()

    # -a is now assigned to --ai, not daemon/autonomous
    monkeypatch.setattr(sys, "argv", ["main.py", "-a"])
    with patch("src.ui.GEMINI_API_KEY", "fake_key"):
        args_ai = ui.parse_arguments()
        assert args_ai.ai is True
        assert args_ai.daemon is False
        assert ui.DAEMON_ENABLED is False


def test_ui_interval_invalid(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["main.py", "-d", "--interval", "0"])
    with pytest.raises(SystemExit):
        ui.parse_arguments()

    monkeypatch.setattr(sys, "argv", ["main.py", "-d", "--interval", "-5"])
    with pytest.raises(SystemExit):
        ui.parse_arguments()


def test_ui_daemon_from_config(monkeypatch, tmp_path):
    test_ini = tmp_path / "auto_config.ini"
    cm = ConfigManager(custom_path=str(test_ini))
    cm.set("options.daemon", "true")
    cm.set("options.polling_interval", "20")

    monkeypatch.setattr("src.ui.config", cm)
    monkeypatch.setattr(sys, "argv", ["main.py"])

    ui.parse_arguments()
    assert ui.DAEMON_ENABLED is True
    assert ui.BYPASS_ENABLED is True
    assert ui.LOG_ENABLED is False
    assert ui.POLLING_INTERVAL == 20

    # Test file logging enabled via config
    cm.set("options.log", "true")
    ui.parse_arguments()
    assert ui.LOG_ENABLED is True


def test_config_daemon_properties(tmp_path):
    test_ini = tmp_path / "prop_config.ini"
    cm = ConfigManager(custom_path=str(test_ini))

    assert cm.DAEMON is False
    cm.DAEMON = True
    assert cm.DAEMON is True
    cm.DAEMON = False
    assert cm.DAEMON is False

    assert cm.POLLING_INTERVAL == 15
    cm.POLLING_INTERVAL = 25
    assert cm.POLLING_INTERVAL == 25

    # Invalid values raise ValueError
    with pytest.raises(ValueError):
        cm.POLLING_INTERVAL = 0
    with pytest.raises(ValueError):
        cm.POLLING_INTERVAL = -10
    with pytest.raises(ValueError):
        cm.POLLING_INTERVAL = "not_int"

    # Test set method validation
    cm.set("options.polling_interval", "45")
    assert cm.POLLING_INTERVAL == 45

    with pytest.raises(ValueError, match="Polling interval must be a positive integer"):
        cm.set("options.polling_interval", "0")

    with pytest.raises(ValueError, match="Polling interval must be a positive integer"):
        cm.set("options.polling_interval", "invalid")

    # Corrupt value in INI file falls back to 15
    cm.parser.set("options", "polling_interval", "-99")
    assert cm.POLLING_INTERVAL == 15
    cm.parser.set("options", "polling_interval", "not_a_number")
    assert cm.POLLING_INTERVAL == 15


def test_config_wizard_daemon_flow(tmp_path):
    test_ini = tmp_path / "wizard_auto.ini"
    cm = ConfigManager(custom_path=str(test_ini))

    # Test daemon enabled with valid interval
    with patch(
        "rich.prompt.Prompt.ask",
        side_effect=[
            "D:/Movies",
            "D:/TV",
            "D:/Downloads",
            "tmdb",
            "gemini",
            "groq",
            "openrouter",
            "cf_tok",
            "cf_acc",
            "mail",
            "pass",
            "30",  # polling interval
            "auto",  # ai provider
        ],
    ):
        with patch(
            "rich.prompt.Confirm.ask",
            side_effect=[
                False,  # bypass = False
                True,  # daemon = True
                False,
                False,
                False,
                False,
                False,
                True,
                False,
                False,
                False,  # ai, learn, log, verbose, notify_succ, notify_err, notify_tag, res, qual
            ],
        ):
            cm.run_wizard()

    assert cm.get("options.daemon") is True
    assert cm.DAEMON is True
    assert cm.get("options.polling_interval") == "30"

    # Test daemon enabled with invalid interval fallback
    with patch(
        "rich.prompt.Prompt.ask",
        side_effect=[
            "D:/Movies",
            "D:/TV",
            "D:/Downloads",
            "tmdb",
            "gemini",
            "",
            "",
            "",
            "",
            "mail",
            "pass",
            "0",  # invalid interval -> fallback 15
            "auto",  # ai provider
        ],
    ):
        with patch(
            "rich.prompt.Confirm.ask",
            side_effect=[
                False,  # bypass = False
                True,  # daemon = True
                False,
                False,
                False,
                False,
                False,
                True,
                False,
                False,
                False,
            ],
        ):
            cm.run_wizard()

    assert cm.get("options.polling_interval") == "15"

    # Test daemon enabled with non-numeric interval fallback
    with patch(
        "rich.prompt.Prompt.ask",
        side_effect=[
            "D:/Movies",
            "D:/TV",
            "D:/Downloads",
            "tmdb",
            "gemini",
            "",
            "",
            "",
            "",
            "mail",
            "pass",
            "invalid_text",  # invalid string -> fallback 15
            "auto",  # ai provider
        ],
    ):
        with patch(
            "rich.prompt.Confirm.ask",
            side_effect=[
                False,  # bypass = False
                True,  # daemon = True
                False,
                False,
                False,
                False,
                False,
                True,
                False,
                False,
                False,
            ],
        ):
            cm.run_wizard()

    assert cm.get("options.polling_interval") == "15"

    # Test daemon disabled, interval still configured
    with patch(
        "rich.prompt.Prompt.ask",
        side_effect=[
            "D:/Movies",
            "D:/TV",
            "D:/Downloads",
            "tmdb",
            "gemini",
            "",
            "",
            "",
            "",
            "mail",
            "pass",
            "25",  # polling interval
            "auto",  # ai provider
        ],
    ):
        with patch(
            "rich.prompt.Confirm.ask",
            side_effect=[
                False,  # bypass = False
                False,  # daemon = False
                False,
                False,
                False,
                False,
                False,
                True,
                False,
                False,
                False,
            ],
        ):
            cm.run_wizard()

    assert cm.get("options.daemon") is False
    assert cm.DAEMON is False
    assert cm.get("options.polling_interval") == "25"


def test_check_folder_permissions(tmp_path):
    # Valid folder with read and write
    folder = tmp_path / "valid_folder"
    folder.mkdir()
    can_read, can_write, err = utils.check_folder_permissions(folder)
    assert can_read is True
    assert can_write is True
    assert err == ""

    # Read permission denied
    with patch("os.scandir", side_effect=PermissionError("Scan not allowed")):
        can_read, can_write, err = utils.check_folder_permissions(folder)
        assert can_read is False
        assert can_write is False
        assert "Read permission denied" in err

    # Write permission denied
    orig_touch = Path.touch

    def fake_touch(self, *args, **kwargs):
        if ".rename_perm_probe" in self.name:
            raise PermissionError("Touch denied")
        return orig_touch(self, *args, **kwargs)

    with patch.object(Path, "touch", fake_touch):
        can_read, can_write, err = utils.check_folder_permissions(folder)
        assert can_read is True
        assert can_write is False
        assert "Write permission denied" in err

    # Probe unlink error handled gracefully
    orig_unlink = Path.unlink

    def fake_unlink(self, *args, **kwargs):
        if ".rename_perm_probe" in self.name:
            raise OSError("Unlink failed")
        return orig_unlink(self, *args, **kwargs)

    with patch.object(Path, "unlink", fake_unlink):
        can_read, can_write, err = utils.check_folder_permissions(folder)
        assert can_read is True
        assert can_write is True
        assert err == ""


def test_verify_folders_daemon_and_permissions(tmp_path, monkeypatch):
    movies = tmp_path / "movies"
    tv = tmp_path / "tv"
    dl = tmp_path / "dl"
    movies.mkdir()
    tv.mkdir()
    dl.mkdir()

    monkeypatch.setattr(utils, "MOVIES_FOLDER", str(movies))
    monkeypatch.setattr(utils, "TV_SHOWS_FOLDER", str(tv))
    monkeypatch.setattr(utils, "NOT_SORTED_MEDIA_FILES_FOLDER", str(dl))

    # All valid -> returns 0
    assert utils.verify_folders(daemon=True) == 0

    # One folder unconfigured -> exits 1 with daemon=True
    monkeypatch.setattr(utils, "MOVIES_FOLDER", None)
    with patch("src.ui.print_log") as mock_log:
        with pytest.raises((SystemExit, MediaOrganizerError)) as exc:
            utils.verify_folders(daemon=True)
        if isinstance(exc.value, SystemExit):
            assert exc.value.code == 1
        log_text = "".join(str(call[0][0]) for call in mock_log.call_args_list)
        assert "Daemon mode requires all library and download folders" in log_text

    # Folder missing on disk -> exits 1
    monkeypatch.setattr(utils, "MOVIES_FOLDER", str(tmp_path / "missing_movies"))
    with patch("src.ui.print_log") as mock_log:
        with pytest.raises((SystemExit, MediaOrganizerError)) as exc:
            utils.verify_folders(daemon=True)
        if isinstance(exc.value, SystemExit):
            assert exc.value.code == 1
        log_text = "".join(str(call[0][0]) for call in mock_log.call_args_list)
        assert "Missing required folder(s) on disk" in log_text

    # Folder permission error (read or write denied) -> exits 1 with clean explanation
    monkeypatch.setattr(utils, "MOVIES_FOLDER", str(movies))
    with patch(
        "src.utils.check_folder_permissions", return_value=(True, False, "Write permission denied: Permission denied")
    ):
        with patch("src.ui.print_log") as mock_log:
            with pytest.raises((SystemExit, MediaOrganizerError)) as exc:
                utils.verify_folders(daemon=True)
            if isinstance(exc.value, SystemExit):
                assert exc.value.code == 1
            log_text = "".join(str(call[0][0]) for call in mock_log.call_args_list)
            assert "Permission error" in log_text
            assert "chmod -R u+rwX" in log_text
            assert "PUID=1000, PGID=1000" in log_text

    # Custom path with only_rename
    custom_dir = tmp_path / "custom_rename"
    custom_dir.mkdir()
    assert utils.verify_folders(only_rename=True, custom_path=str(custom_dir)) == 0

    # Custom path with only_rename permission failure
    with patch(
        "src.utils.check_folder_permissions", return_value=(False, False, "Read permission denied: Permission denied")
    ):
        with patch("src.ui.print_log") as mock_log:
            with pytest.raises((SystemExit, MediaOrganizerError)) as exc:
                utils.verify_folders(only_rename=True, custom_path=str(custom_dir))
            if isinstance(exc.value, SystemExit):
                assert exc.value.code == 1
            log_text = "".join(str(call[0][0]) for call in mock_log.call_args_list)
            assert "Permission error" in log_text

    # Custom path without only_rename
    assert utils.verify_folders(only_rename=False, custom_path=str(custom_dir)) == 0


def test_remove_empty_folders_preserves_target_and_handles_busy_devices(tmp_path):
    target_dir = tmp_path / "input_folder"
    target_dir.mkdir()

    # Create nested empty subdirectories
    sub1 = target_dir / "empty_sub1"
    sub1.mkdir()
    sub2 = target_dir / "empty_sub2"
    sub2.mkdir()
    sub_nested = sub1 / "nested_empty"
    sub_nested.mkdir()

    # Create a non-empty subdirectory
    non_empty = target_dir / "has_file"
    non_empty.mkdir()
    (non_empty / "file.txt").touch()

    # Execute remove_empty_folders: target_dir itself MUST be preserved!
    files.remove_empty_folders(target_dir)

    assert target_dir.exists(), "Target root directory must NOT be deleted!"
    assert not sub1.exists()
    assert not sub2.exists()
    assert not sub_nested.exists()
    assert non_empty.exists()
    assert (non_empty / "file.txt").exists()

    # Target directory with no subdirectories at all should still never be deleted
    files.remove_empty_folders(target_dir)
    assert target_dir.exists()

    # Non-existent folder logs message and returns
    with patch("src.ui.print_log") as mock_log:
        files.remove_empty_folders(tmp_path / "non_existent")
        mock_log.assert_called_once()
        assert "does not exist" in mock_log.call_args[0][0]

    # OSError during os.listdir (e.g. permission or I/O error) logs warning and does not crash
    test_sub = target_dir / "listdir_err_sub"
    test_sub.mkdir()
    with patch("os.listdir", side_effect=OSError("Device I/O error")):
        with patch("src.ui.print_log") as mock_log:
            files.remove_empty_folders(target_dir)
            warning_logs = [str(c[0][0]) for c in mock_log.call_args_list if "Warning" in str(c[0][0])]
            assert len(warning_logs) > 0
            assert "Could not inspect folder" in warning_logs[0]

    # OSError during os.rmdir (e.g. Errno 16 Device or resource busy) logs warning and does not crash
    with patch("os.rmdir", side_effect=OSError(16, "Device or resource busy", str(test_sub))):
        with patch("src.ui.print_log") as mock_log:
            files.remove_empty_folders(target_dir)
            warning_logs = [str(c[0][0]) for c in mock_log.call_args_list if "Warning" in str(c[0][0])]
            assert len(warning_logs) > 0
            assert "Could not delete empty folder" in warning_logs[0]


def test_files_locked_and_partial_extensions(tmp_path):
    target_dir = tmp_path / "downloads"
    target_dir.mkdir()

    # Create a partial file
    partial_file = target_dir / "Incomplete.Movie.2024.mkv.crdownload"
    partial_file.touch()

    # Create a normal media file with uppercase extension
    normal_file = target_dir / "Normal.Movie.2024.MKV"
    normal_file.touch()

    # Create a locked media file
    locked_file = target_dir / "Locked.Movie.2024.mkv"
    locked_file.touch()

    # Create a read-only media file
    ro_file = target_dir / "ReadOnly.Movie.2024.mp4"
    ro_file.touch()
    import stat

    os.chmod(str(ro_file), stat.S_IREAD)

    # Test is_file_locked
    non_existent = target_dir / "non_existent.mkv"
    assert files.is_file_locked(non_existent) is False
    assert files.is_file_locked(normal_file) is False
    try:
        assert files.is_file_locked(ro_file) is False
    finally:
        os.chmod(str(ro_file), stat.S_IWRITE)

    # Mock os.rename raising PermissionError for locked_file
    orig_rename = os.rename

    def fake_rename(src, dst):
        if str(src) == str(locked_file):
            raise PermissionError("File locked by process")
        return orig_rename(src, dst)

    with patch("os.rename", side_effect=fake_rename):
        assert files.is_file_locked(locked_file) is True

        # search_media_files should skip partial and locked files, but include uppercase extensions
        messy_df, clean_df = files.search_media_files(str(target_dir), exit_if_empty=False)
        assert len(messy_df) == 2
        file_names = list(messy_df["File"])
        assert "Normal.Movie.2024.MKV" in file_names
        assert "ReadOnly.Movie.2024.mp4" in file_names

    # Test empty folder with exit_if_empty=False returns empty dataframes
    empty_dir = tmp_path / "empty_dir"
    empty_dir.mkdir()
    m_df, c_df = files.search_media_files(str(empty_dir), exit_if_empty=False)
    assert m_df.empty
    assert c_df.empty


def test_run_daemon_loop_basic(tmp_path, monkeypatch):
    args = MagicMock()
    args.path = str(tmp_path)
    args.only_rename = False
    args.simulate = False

    ui.POLLING_INTERVAL = 1

    # Mock process_media to run 1 cycle
    with patch("main.process_media") as mock_proc:
        ret = main.run_daemon_loop(args, max_cycles=1)
        assert ret == 0
        assert mock_proc.call_count == 1


def test_run_daemon_loop_interrupt(tmp_path):
    args = MagicMock()
    args.path = str(tmp_path)
    args.only_rename = False
    args.simulate = False

    stop_event = threading.Event()
    stop_event.set()

    ret = main.run_daemon_loop(args, stop_event=stop_event)
    assert ret == 0


def test_run_daemon_loop_keyboard_interrupt(tmp_path):
    args = MagicMock()
    args.path = str(tmp_path)
    args.only_rename = False
    args.simulate = False

    with patch("main.process_media", side_effect=KeyboardInterrupt):
        ret = main.run_daemon_loop(args, max_cycles=1)
        assert ret == 0


def test_run_daemon_loop_cycle_exception(tmp_path):
    args = MagicMock()
    args.path = str(tmp_path)
    args.only_rename = False
    args.simulate = False

    with (
        patch("main.process_media", side_effect=RuntimeError("Transient API failure")),
        patch("src.mail.send_error_email") as mock_mail,
    ):
        ret = main.run_daemon_loop(args, max_cycles=1)
        assert ret == 0
        assert mock_mail.call_count == 1


def test_run_daemon_loop_sleep_execution(tmp_path):
    args = MagicMock()
    args.path = str(tmp_path)
    args.only_rename = False
    args.simulate = False

    ui.POLLING_INTERVAL = 1
    call_count = 0

    def mock_proc(a, daemon=True, **kwargs):
        nonlocal call_count
        call_count += 1

    # Time sequence:
    # 1. start_sleep = 1000.0
    # 2. while check: 1000.5 - 1000.0 = 0.5 < 60 -> enters loop
    # 3. time_remaining calculation: 1000.5
    # 4. while check: 1070.0 - 1000.0 = 70.0 >= 60 -> exits sleep loop
    with (
        patch("main.process_media", side_effect=mock_proc),
        patch.object(threading.Event, "wait", return_value=False),
    ):
        ret = main.run_daemon_loop(args, max_cycles=2)
        assert ret == 0
        assert call_count == 2


def test_run_daemon_loop_signals(tmp_path):
    args = MagicMock()
    args.path = str(tmp_path)
    args.only_rename = False
    args.simulate = False

    int_handler = None

    def mock_signal(sig, handler):
        nonlocal int_handler
        if sig == signal.SIGINT and int_handler is None:
            int_handler = handler
        return MagicMock()

    with patch("signal.signal", side_effect=mock_signal):
        stop_event = threading.Event()
        with patch("main.process_media"):
            ret = main.run_daemon_loop(args, max_cycles=1, stop_event=stop_event)
            assert ret == 0
            assert int_handler is not None
            int_handler(signal.SIGINT, None)
            assert stop_event.is_set()


def test_run_daemon_loop_signal_exceptions(tmp_path):
    args = MagicMock()
    args.path = str(tmp_path)
    args.only_rename = False
    args.simulate = False

    # Mock signal.signal raising ValueError during registration and restoration
    with patch("signal.signal", side_effect=ValueError("Signal only works in main thread")):
        ret = main.run_daemon_loop(args, max_cycles=1)
        assert ret == 0


def test_run_daemon_restore_signals_exception(tmp_path):
    args = MagicMock()
    args.path = str(tmp_path)
    args.only_rename = False
    args.simulate = False

    calls = 0

    def flaky_signal(sig, handler):
        nonlocal calls
        calls += 1
        if calls > 2:  # restoration calls
            raise RuntimeError("Restore error")
        return MagicMock()

    with patch("signal.signal", side_effect=flaky_signal), patch("main.process_media"):
        ret = main.run_daemon_loop(args, max_cycles=1)
        assert ret == 0


def test_main_daemon_execution(monkeypatch, tmp_path):
    movies = tmp_path / "movies"
    tv = tmp_path / "tv"
    dl = tmp_path / "dl"
    movies.mkdir()
    tv.mkdir()
    dl.mkdir()

    monkeypatch.setattr(utils, "MOVIES_FOLDER", str(movies))
    monkeypatch.setattr(utils, "TV_SHOWS_FOLDER", str(tv))
    monkeypatch.setattr(utils, "NOT_SORTED_MEDIA_FILES_FOLDER", str(dl))

    # Test -d calls run_daemon_loop
    monkeypatch.setattr(sys, "argv", ["main.py", "-d"])
    with patch("main.run_daemon_loop", return_value=0) as mock_loop:
        ret = main.main()
        assert ret == 0
        assert mock_loop.call_count == 1


def test_process_media_empty_in_daemon(tmp_path):
    args = MagicMock()
    args.path = str(tmp_path)
    args.only_rename = False
    args.simulate = False

    # Empty folder in daemon mode logs idle notice and returns 0
    with patch("src.files.search_media_files", return_value=(pd.DataFrame(), pd.DataFrame())):
        assert main.process_media(args, daemon=True) == 0

    # None returned by search_media_files
    with patch("src.files.search_media_files", return_value=None):
        assert main.process_media(args, daemon=True) == 0


def test_process_media_full_flow(tmp_path):
    media_file = tmp_path / "Movie.2024.mkv"
    media_file.touch()

    args = MagicMock()
    args.path = str(tmp_path)
    args.only_rename = False
    args.simulate = False

    messy_df = pd.DataFrame(
        [
            {
                "File": "Movie.2024.mkv",
                "Folder": "downloads",
                "Path": str(media_file),
                "Clean": "Movie 2024",
                "Parse": ["Movie", "2024", None, None],
                "Media": "movie",
            }
        ]
    )
    clean_df = pd.DataFrame(
        [
            {
                "Original": "Movie.2024.mkv",
                "Corrected": "Movie (2024)",
                "Path": str(media_file),
                "Media": "movie",
                "Season": None,
                "Episode": None,
            }
        ]
    )

    sorted_paths = [(str(media_file), "D:/Movies/Movie (2024)/Movie (2024).mkv")]

    with (
        patch("src.files.search_media_files", return_value=(messy_df, pd.DataFrame())),
        patch("src.utils.get_corrected_media_filenames", return_value=clean_df),
        patch("src.files.rename_media_files", return_value=clean_df) as mock_rename,
        patch("src.files.sort_media_files", return_value=sorted_paths),
        patch("src.ui.display_sorted_files"),
        patch("src.files.move_media_files", return_value=(1, 0)) as mock_move,
        patch("src.ui.user_confirmation"),
    ):
        ret = main.process_media(args, daemon=True)
        assert ret == 0
        assert mock_rename.call_count == 1
        assert mock_move.call_count == 1


def test_process_media_daemon_edge_cases(tmp_path):
    media_file = tmp_path / "Movie.2024.mkv"
    media_file.touch()

    args = MagicMock()
    args.path = str(tmp_path)
    args.only_rename = True
    args.simulate = False

    clean_df = pd.DataFrame(
        [
            {
                "Original": "Movie.2024.mkv",
                "Corrected": "Movie (2024)",
                "Path": str(media_file),
                "Media": "movie",
                "Season": None,
                "Episode": None,
            }
        ]
    )

    # 1. only_rename in daemon mode prints cycle completion message
    with (
        patch("src.files.search_media_files", return_value=(clean_df, pd.DataFrame())),
        patch("src.utils.get_corrected_media_filenames", return_value=clean_df),
        patch("src.files.rename_media_files", return_value=clean_df),
        patch("src.ui.user_confirmation"),
        patch("src.mail.send_media_success_email"),
    ):
        ret = main.process_media(args, daemon=True)
        assert ret == 0

    # 2. clean_data_table has no files to rename
    unrenamed_df = pd.DataFrame(
        [
            {
                "Original": "Movie (2024)",
                "Corrected": "Movie (2024)",
                "Path": str(media_file),
                "Media": "movie",
                "Season": None,
                "Episode": None,
            }
        ]
    )
    with (
        patch("src.files.search_media_files", return_value=(unrenamed_df, pd.DataFrame())),
        patch("src.utils.get_corrected_media_filenames", return_value=unrenamed_df),
        patch("src.utils.has_files_to_rename", return_value=False),
    ):
        ret = main.process_media(args, daemon=True)
        assert ret == 0


def test_cleanup_old_logs_retention(tmp_path):
    from datetime import datetime, timedelta

    log_dir = tmp_path / "logs"
    log_dir.mkdir()

    today = datetime.now()
    d20 = (today - timedelta(days=20)).strftime("%Y-%m-%d")
    d15 = (today - timedelta(days=15)).strftime("%Y-%m-%d")
    d10 = (today - timedelta(days=10)).strftime("%Y-%m-%d")
    d0 = today.strftime("%Y-%m-%d")

    # Dated log files
    f_old1 = log_dir / f"{d20}.txt"
    f_old1.write_text("old log 1", encoding="utf-8")
    f_old2 = log_dir / f"{d15}_backup.log"
    f_old2.write_text("old log 2", encoding="utf-8")

    f_keep1 = log_dir / f"{d10}.txt"
    f_keep1.write_text("recent log 1", encoding="utf-8")
    f_keep2 = log_dir / f"{d0}.txt"
    f_keep2.write_text("today log", encoding="utf-8")

    # Non-date log files (tested via mtime fallback)
    f_mtime_old = log_dir / "custom_old.log"
    f_mtime_old.write_text("custom old", encoding="utf-8")
    old_time = (today - timedelta(days=25)).timestamp()
    os.utime(str(f_mtime_old), (old_time, old_time))

    f_mtime_new = log_dir / "custom_new.log"
    f_mtime_new.write_text("custom new", encoding="utf-8")

    # Non-log files (must be preserved regardless of age)
    f_other = log_dir / "data.json"
    f_other.write_text("{}", encoding="utf-8")
    os.utime(str(f_other), (old_time, old_time))

    # Subdirectory (must be preserved)
    sub_dir = log_dir / "archive"
    sub_dir.mkdir()

    deleted = ui.cleanup_old_logs(log_dir, max_age_days=14)
    deleted_names = {p.name for p in deleted}

    assert f_old1.name in deleted_names
    assert f_old2.name in deleted_names
    assert f_mtime_old.name in deleted_names
    assert not f_old1.exists()
    assert not f_old2.exists()
    assert not f_mtime_old.exists()

    # Retained files
    assert f_keep1.exists()
    assert f_keep2.exists()
    assert f_mtime_new.exists()
    assert f_other.exists()
    assert sub_dir.exists()


def test_cleanup_old_logs_edge_cases(tmp_path, monkeypatch):
    # 1. Non-existent directory returns []
    assert ui.cleanup_old_logs(tmp_path / "does_not_exist") == []

    # 2. Default log_dir (log_dir is None)
    with patch("src.ui.get_log_dir", return_value=tmp_path):
        assert isinstance(ui.cleanup_old_logs(), list)

    # 3. iterdir raising OSError
    log_dir = tmp_path / "err_logs"
    log_dir.mkdir()
    orig_iterdir = Path.iterdir

    def fake_iterdir(self, *args, **kwargs):
        if self.name == "err_logs":
            raise OSError("Permission denied")
        return orig_iterdir(self, *args, **kwargs)

    with patch.object(Path, "iterdir", fake_iterdir):
        assert ui.cleanup_old_logs(log_dir) == []

    # 4. is_file raising OSError
    err_file = log_dir / "err_file.txt"
    err_file.write_text("err", encoding="utf-8")
    orig_is_file = Path.is_file

    def fake_is_file(self, *args, **kwargs):
        if self.name == "err_file.txt":
            raise OSError("is_file error")
        return orig_is_file(self, *args, **kwargs)

    with patch.object(Path, "is_file", fake_is_file):
        assert ui.cleanup_old_logs(log_dir) == []

    # 5. stat raising OSError on non-date file
    bad_stat_file = log_dir / "unknown.log"
    bad_stat_file.write_text("bad stat", encoding="utf-8")
    orig_stat = Path.stat

    def fake_stat(self, *args, **kwargs):
        if self.name == "unknown.log":
            import inspect

            stack = [f.function for f in inspect.stack()]
            if "cleanup_old_logs" in stack and "is_file" not in stack and "is_dir" not in stack:
                raise OSError("stat error")
        return orig_stat(self, *args, **kwargs)

    with patch.object(Path, "stat", fake_stat):
        # Should not crash, and should not delete
        ui.cleanup_old_logs(log_dir)
        assert bad_stat_file.exists()

    # 6. unlink raising OSError
    from datetime import datetime, timedelta

    old_date = (datetime.now() - timedelta(days=20)).strftime("%Y-%m-%d")
    old_file = log_dir / f"{old_date}.txt"
    old_file.write_text("old content", encoding="utf-8")
    orig_unlink = Path.unlink

    def fake_unlink(self, *args, **kwargs):
        if self.name == f"{old_date}.txt":
            raise OSError("unlink error")
        return orig_unlink(self, *args, **kwargs)

    with patch.object(Path, "unlink", fake_unlink):
        # Should not crash even if unlink fails
        deleted = ui.cleanup_old_logs(log_dir)
        assert deleted == []


def test_cleanup_old_logs_in_print_log(tmp_path, monkeypatch):
    monkeypatch.setattr(ui, "LOG_ENABLED", True)
    monkeypatch.setattr("src.ui.get_log_dir", lambda: tmp_path)
    monkeypatch.setattr("src.ui._last_log_cleanup_date", None)

    from datetime import datetime, timedelta

    old_date = (datetime.now() - timedelta(days=25)).strftime("%Y-%m-%d")
    old_file = tmp_path / f"{old_date}.txt"
    old_file.write_text("old log", encoding="utf-8")

    with patch("src.ui.cleanup_old_logs", wraps=ui.cleanup_old_logs) as mock_cleanup:
        ui.print_log("First log message today")
        assert mock_cleanup.call_count == 1
        assert not old_file.exists()

        # Second call on same day should not invoke cleanup_old_logs again
        ui.print_log("Second log message today")
        assert mock_cleanup.call_count == 1

def test_failed_files_cooldown(tmp_path, monkeypatch):
    import datetime
    from src import files
    
    # Setup test file
    test_file = tmp_path / "video.mkv"
    test_file.touch()
    
    # Ensure it's large enough if MIN_FILE_SIZE_MB is active (which it defaults to 0)
    with open(test_file, "wb") as f:
        f.write(b"0" * 1024 * 1024)
        
    # Reset cooldown
    files._failed_files_cooldown.clear()
    
    # 1. Normal collection -> finds file
    candidates = files.collect_candidate_video_files(tmp_path)
    assert test_file in candidates
    
    # 2. Add to cooldown (simulating a failure)
    test_key = str(test_file.resolve())
    files._failed_files_cooldown[test_key] = datetime.datetime.now()
    
    # 3. Collection should now skip it
    candidates = files.collect_candidate_video_files(tmp_path)
    assert test_file not in candidates
    
    # 4. Fast forward time by 25 hours
    old_time = datetime.datetime.now() - datetime.timedelta(hours=25)
    files._failed_files_cooldown[test_key] = old_time
    
    # 5. Collection should now find it again and clean up the old entry
    candidates = files.collect_candidate_video_files(tmp_path)
    assert test_file in candidates
    assert test_key not in files._failed_files_cooldown
