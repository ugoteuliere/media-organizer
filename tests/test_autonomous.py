import os
import sys
import signal
import threading
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
import pandas as pd

from src import ui, files, utils, mail
from src.config import ConfigManager, config
import main


def test_ui_daemon_and_autonomous_flags(monkeypatch):
    # -d daemon flag
    monkeypatch.setattr(sys, "argv", ["main.py", "-d"])
    args = ui.parse_arguments()
    assert args.daemon is True
    assert args.autonomous is True
    assert ui.DAEMON_ENABLED is True
    assert ui.AUTONOMOUS_ENABLED is True
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
    assert ui.AUTONOMOUS_ENABLED is True
    assert ui.BYPASS_ENABLED is True
    assert ui.LOG_ENABLED is False
    assert ui.POLLING_INTERVAL == 30

    # Backward compatibility with -a / --autonomous
    monkeypatch.setattr(sys, "argv", ["main.py", "-a"])
    args = ui.parse_arguments()
    assert args.daemon is True
    assert args.autonomous is True
    assert ui.DAEMON_ENABLED is True
    assert ui.AUTONOMOUS_ENABLED is True
    assert ui.BYPASS_ENABLED is True
    assert ui.LOG_ENABLED is False

    monkeypatch.setattr(sys, "argv", ["main.py", "--autonomous", "-l"])
    args = ui.parse_arguments()
    assert args.daemon is True
    assert args.autonomous is True
    assert ui.DAEMON_ENABLED is True
    assert ui.AUTONOMOUS_ENABLED is True
    assert ui.LOG_ENABLED is True


def test_ui_interval_invalid(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["main.py", "-d", "--interval", "0"])
    with pytest.raises(SystemExit):
        ui.parse_arguments()

    monkeypatch.setattr(sys, "argv", ["main.py", "-a", "--interval", "-5"])
    with pytest.raises(SystemExit):
        ui.parse_arguments()


def test_ui_daemon_from_config(monkeypatch, tmp_path):
    test_ini = tmp_path / "auto_config.ini"
    cm = ConfigManager(custom_path=str(test_ini))
    cm.set("options.daemon", "true")
    cm.set("options.polling_interval", "20")

    monkeypatch.setattr("src.ui.config", cm)
    monkeypatch.setattr(sys, "argv", ["main.py"])

    args = ui.parse_arguments()
    assert ui.DAEMON_ENABLED is True
    assert ui.AUTONOMOUS_ENABLED is True
    assert ui.BYPASS_ENABLED is True
    assert ui.LOG_ENABLED is False
    assert ui.POLLING_INTERVAL == 20

    # Test file logging enabled via config
    cm.set("options.log", "true")
    ui.parse_arguments()
    assert ui.LOG_ENABLED is True

    # Test backward compatibility with options.autonomous
    test_ini2 = tmp_path / "auto_config2.ini"
    cm2 = ConfigManager(custom_path=str(test_ini2))
    cm2.set("options.autonomous", "true")
    monkeypatch.setattr("src.ui.config", cm2)
    ui.parse_arguments()
    assert ui.DAEMON_ENABLED is True
    assert ui.AUTONOMOUS_ENABLED is True


def test_config_autonomous_properties(tmp_path):
    test_ini = tmp_path / "prop_config.ini"
    cm = ConfigManager(custom_path=str(test_ini))

    assert cm.DAEMON is False
    assert cm.AUTONOMOUS is False
    cm.DAEMON = True
    assert cm.DAEMON is True
    assert cm.AUTONOMOUS is True
    cm.AUTONOMOUS = False
    assert cm.DAEMON is False
    assert cm.AUTONOMOUS is False

    # Legacy INI with only autonomous option (no daemon option)
    legacy_ini = tmp_path / "legacy.ini"
    legacy_ini.write_text("[options]\nautonomous = true\n", encoding="utf-8")
    cm_legacy = ConfigManager(custom_path=str(legacy_ini))
    assert cm_legacy.DAEMON is True
    assert cm_legacy.AUTONOMOUS is True

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


def test_config_wizard_autonomous_flow(tmp_path):
    test_ini = tmp_path / "wizard_auto.ini"
    cm = ConfigManager(custom_path=str(test_ini))

    # Test daemon enabled with valid interval
    with patch("rich.prompt.Prompt.ask", side_effect=[
        "D:/Movies", "D:/TV", "D:/Downloads",
        "tmdb", "gemini", "groq", "openrouter", "cf_tok", "cf_acc", "mail", "pass",
        "30",  # polling interval
        "auto" # ai provider
    ]):
        with patch("rich.prompt.Confirm.ask", side_effect=[
            False,  # bypass = False
            True,   # daemon = True
            False, False, False, False, False, True, False, False, False  # ai, learn, log, verbose, notify_succ, notify_err, notify_tag, res, qual
        ]):
            cm.run_wizard()

    assert cm.get("options.daemon") is True
    assert cm.get("options.autonomous") is True
    assert cm.DAEMON is True
    assert cm.AUTONOMOUS is True
    assert cm.get("options.polling_interval") == "30"

    # Test daemon enabled with invalid interval fallback
    with patch("rich.prompt.Prompt.ask", side_effect=[
        "D:/Movies", "D:/TV", "D:/Downloads",
        "tmdb", "gemini", "", "", "", "", "mail", "pass",
        "0",   # invalid interval -> fallback 15
        "auto" # ai provider
    ]):
        with patch("rich.prompt.Confirm.ask", side_effect=[
            False,  # bypass = False
            True,   # daemon = True
            False, False, False, False, False, True, False, False, False
        ]):
            cm.run_wizard()

    assert cm.get("options.polling_interval") == "15"

    # Test daemon enabled with non-numeric interval fallback
    with patch("rich.prompt.Prompt.ask", side_effect=[
        "D:/Movies", "D:/TV", "D:/Downloads",
        "tmdb", "gemini", "", "", "", "", "mail", "pass",
        "invalid_text",  # invalid string -> fallback 15
        "auto"           # ai provider
    ]):
        with patch("rich.prompt.Confirm.ask", side_effect=[
            False,  # bypass = False
            True,   # daemon = True
            False, False, False, False, False, True, False, False, False
        ]):
            cm.run_wizard()

    assert cm.get("options.polling_interval") == "15"

    # Test daemon disabled, interval still configured
    with patch("rich.prompt.Prompt.ask", side_effect=[
        "D:/Movies", "D:/TV", "D:/Downloads",
        "tmdb", "gemini", "", "", "", "", "mail", "pass",
        "25",  # polling interval
        "auto" # ai provider
    ]):
        with patch("rich.prompt.Confirm.ask", side_effect=[
            False,  # bypass = False
            False,  # daemon = False
            False, False, False, False, False, True, False, False, False
        ]):
            cm.run_wizard()

    assert cm.get("options.daemon") is False
    assert cm.get("options.autonomous") is False
    assert cm.DAEMON is False
    assert cm.AUTONOMOUS is False
    assert cm.get("options.polling_interval") == "25"


def test_verify_folders_daemon(tmp_path, monkeypatch):
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
    assert utils.verify_folders(autonomous=True) == 0

    # One folder unconfigured -> exits 1 with daemon=True
    monkeypatch.setattr(utils, "MOVIES_FOLDER", None)
    with patch("src.ui.print_log") as mock_log:
        with pytest.raises(SystemExit) as exc:
            utils.verify_folders(daemon=True)
        assert exc.value.code == 1
        log_text = "".join(str(call[0][0]) for call in mock_log.call_args_list)
        assert "Daemon mode requires all library and download folders" in log_text

    # Backwards compatibility: autonomous=True
    with patch("src.ui.print_log") as mock_log:
        with pytest.raises(SystemExit) as exc:
            utils.verify_folders(autonomous=True)
        assert exc.value.code == 1
        log_text = "".join(str(call[0][0]) for call in mock_log.call_args_list)
        assert "Daemon mode requires all library and download folders" in log_text

    # Folder missing on disk -> exits 1
    monkeypatch.setattr(utils, "MOVIES_FOLDER", str(tmp_path / "missing_movies"))
    with patch("src.ui.print_log") as mock_log:
        with pytest.raises(SystemExit) as exc:
            utils.verify_folders(daemon=True)
        assert exc.value.code == 1
        log_text = "".join(str(call[0][0]) for call in mock_log.call_args_list)
        assert "Missing required folder(s) on disk" in log_text


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


def test_run_autonomous_loop_basic(tmp_path, monkeypatch):
    args = MagicMock()
    args.path = str(tmp_path)
    args.only_rename = False
    args.simulate = False

    ui.POLLING_INTERVAL = 1

    # Mock process_media to run 1 cycle
    with patch("main.process_media") as mock_proc:
        ret = main.run_autonomous_loop(args, max_cycles=1)
        assert ret == 0
        assert mock_proc.call_count == 1


def test_run_autonomous_loop_interrupt(tmp_path):
    args = MagicMock()
    args.path = str(tmp_path)
    args.only_rename = False
    args.simulate = False

    stop_event = threading.Event()
    stop_event.set()

    ret = main.run_autonomous_loop(args, stop_event=stop_event)
    assert ret == 0


def test_run_autonomous_loop_keyboard_interrupt(tmp_path):
    args = MagicMock()
    args.path = str(tmp_path)
    args.only_rename = False
    args.simulate = False

    with patch("main.process_media", side_effect=KeyboardInterrupt):
        ret = main.run_autonomous_loop(args, max_cycles=1)
        assert ret == 0


def test_run_autonomous_loop_cycle_exception(tmp_path):
    args = MagicMock()
    args.path = str(tmp_path)
    args.only_rename = False
    args.simulate = False

    with patch("main.process_media", side_effect=RuntimeError("Transient API failure")), \
         patch("src.mail.send_error_email") as mock_mail:
        ret = main.run_autonomous_loop(args, max_cycles=1)
        assert ret == 0
        assert mock_mail.call_count == 1


def test_run_autonomous_loop_sleep_execution(tmp_path):
    args = MagicMock()
    args.path = str(tmp_path)
    args.only_rename = False
    args.simulate = False

    ui.POLLING_INTERVAL = 1
    call_count = 0

    def mock_proc(a, autonomous=True, **kwargs):
        nonlocal call_count
        call_count += 1

    # Time sequence:
    # 1. start_sleep = 1000.0
    # 2. while check: 1000.5 - 1000.0 = 0.5 < 60 -> enters loop
    # 3. time_remaining calculation: 1000.5
    # 4. while check: 1070.0 - 1000.0 = 70.0 >= 60 -> exits sleep loop
    times = iter([1000.0, 1000.5, 1000.5, 1070.0, 1070.0, 1070.0, 1070.0])

    with patch("main.process_media", side_effect=mock_proc), \
         patch("time.time", side_effect=lambda: next(times)):
        ret = main.run_autonomous_loop(args, max_cycles=2)
        assert ret == 0
        assert call_count == 2


def test_run_autonomous_loop_signals(tmp_path):
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
            ret = main.run_autonomous_loop(args, max_cycles=1, stop_event=stop_event)
            assert ret == 0
            assert int_handler is not None
            int_handler(signal.SIGINT, None)
            assert stop_event.is_set()


def test_run_autonomous_loop_signal_exceptions(tmp_path):
    args = MagicMock()
    args.path = str(tmp_path)
    args.only_rename = False
    args.simulate = False

    # Mock signal.signal raising ValueError during registration and restoration
    with patch("signal.signal", side_effect=ValueError("Signal only works in main thread")):
        ret = main.run_autonomous_loop(args, max_cycles=1)
        assert ret == 0


def test_run_autonomous_restore_signals_exception(tmp_path):
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

    with patch("signal.signal", side_effect=flaky_signal), \
         patch("main.process_media"):
        ret = main.run_autonomous_loop(args, max_cycles=1)
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

    # Test -a backward compatibility with patched run_autonomous_loop
    monkeypatch.setattr(sys, "argv", ["main.py", "-a"])
    mock_auto = MagicMock(return_value=0)
    with patch("main.run_autonomous_loop", mock_auto):
        ret = main.main()
        assert ret == 0
        assert mock_auto.call_count == 1


def test_process_media_empty_in_autonomous(tmp_path):
    args = MagicMock()
    args.path = str(tmp_path)
    args.only_rename = False
    args.simulate = False

    # Empty folder in autonomous mode logs idle notice and returns 0
    with patch("src.files.search_media_files", return_value=(pd.DataFrame(), pd.DataFrame())):
        assert main.process_media(args, autonomous=True) == 0

    # None returned by search_media_files
    with patch("src.files.search_media_files", return_value=None):
        assert main.process_media(args, autonomous=True) == 0


def test_process_media_full_flow(tmp_path):
    media_file = tmp_path / "Movie.2024.mkv"
    media_file.touch()

    args = MagicMock()
    args.path = str(tmp_path)
    args.only_rename = False
    args.simulate = False

    messy_df = pd.DataFrame([{
        'File': 'Movie.2024.mkv',
        'Folder': 'downloads',
        'Path': str(media_file),
        'Clean': 'Movie 2024',
        'Parse': ['Movie', '2024', None, None],
        'Media': 'movie'
    }])
    clean_df = pd.DataFrame([{
        'Original': 'Movie.2024.mkv',
        'Corrected': 'Movie (2024)',
        'Path': str(media_file),
        'Media': 'movie',
        'Season': None,
        'Episode': None
    }])

    sorted_paths = [(str(media_file), "D:/Movies/Movie (2024)/Movie (2024).mkv")]

    with patch("src.files.search_media_files", return_value=(messy_df, pd.DataFrame())), \
         patch("src.utils.get_corrected_media_filenames", return_value=clean_df), \
         patch("src.files.rename_media_files", return_value=clean_df) as mock_rename, \
         patch("src.files.sort_media_files", return_value=sorted_paths), \
         patch("src.ui.display_sorted_files"), \
         patch("src.files.move_media_files") as mock_move, \
         patch("src.ui.user_confirmation"):
        ret = main.process_media(args, autonomous=True)
        assert ret == 0
        assert mock_rename.call_count == 1
        assert mock_move.call_count == 1


def test_process_media_autonomous_edge_cases(tmp_path):
    media_file = tmp_path / "Movie.2024.mkv"
    media_file.touch()

    args = MagicMock()
    args.path = str(tmp_path)
    args.only_rename = True
    args.simulate = False

    clean_df = pd.DataFrame([{
        'Original': 'Movie.2024.mkv',
        'Corrected': 'Movie (2024)',
        'Path': str(media_file),
        'Media': 'movie',
        'Season': None,
        'Episode': None
    }])

    # 1. only_rename in autonomous mode prints cycle completion message
    with patch("src.files.search_media_files", return_value=(clean_df, pd.DataFrame())), \
         patch("src.utils.get_corrected_media_filenames", return_value=clean_df), \
         patch("src.files.rename_media_files", return_value=clean_df), \
         patch("src.ui.user_confirmation"), \
         patch("src.mail.send_media_success_email"):
        ret = main.process_media(args, autonomous=True)
        assert ret == 0

    # 2. clean_data_table has no files to rename
    unrenamed_df = pd.DataFrame([{
        'Original': 'Movie (2024)',
        'Corrected': 'Movie (2024)',
        'Path': str(media_file),
        'Media': 'movie',
        'Season': None,
        'Episode': None
    }])
    with patch("src.files.search_media_files", return_value=(unrenamed_df, pd.DataFrame())), \
         patch("src.utils.get_corrected_media_filenames", return_value=unrenamed_df), \
         patch("src.utils.has_files_to_rename", return_value=False):
        ret = main.process_media(args, autonomous=True)
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
    with patch.object(Path, "iterdir", side_effect=OSError("Permission denied")):
        assert ui.cleanup_old_logs(log_dir) == []

    # 4. is_file raising OSError
    err_file = log_dir / "err_file.txt"
    err_file.write_text("err", encoding="utf-8")
    with patch.object(Path, "is_file", side_effect=OSError("is_file error")):
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

    # 5. unlink raising OSError
    from datetime import datetime, timedelta
    old_date = (datetime.now() - timedelta(days=20)).strftime("%Y-%m-%d")
    old_file = log_dir / f"{old_date}.txt"
    old_file.write_text("old content", encoding="utf-8")
    with patch.object(Path, "unlink", side_effect=OSError("unlink error")):
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

