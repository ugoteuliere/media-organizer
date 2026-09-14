import os
import sys
import importlib
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock, PropertyMock, mock_open
import pandas as pd

from src import ui
from src.config import ConfigManager

def test_ui_stdout_reconfigure_exception():
    with patch.object(sys.stdout, "reconfigure", side_effect=ValueError("mock reconfigure fail")):
        importlib.reload(ui)
    with patch.object(sys, "stdout", object()):
        importlib.reload(ui)
    importlib.reload(ui)

def test_parse_arguments_default(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["main.py"])
    args = ui.parse_arguments()
    assert args.only_rename is False
    assert args.simulate is False
    assert args.bypass is False
    assert args.ai is False
    assert args.log is False
    assert args.verbose is False
    assert ui.SIMULATE_ENABLED is False

def test_parse_arguments_gui(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["main.py", "-g"])
    args = ui.parse_arguments()
    assert args.gui is True

    monkeypatch.setattr(sys, "argv", ["main.py", "--gui"])
    args = ui.parse_arguments()
    assert args.gui is True

def test_parse_arguments_simulate(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["main.py", "-s"])
    args = ui.parse_arguments()
    assert args.simulate is True
    assert ui.SIMULATE_ENABLED is True

    monkeypatch.setattr(sys, "argv", ["main.py", "--simulate"])
    args = ui.parse_arguments()
    assert args.simulate is True
    assert ui.SIMULATE_ENABLED is True

def test_parse_arguments_bypass(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["main.py", "-b"])
    args = ui.parse_arguments()
    assert args.bypass is True
    assert ui.BYPASS_ENABLED is True

    monkeypatch.setattr(sys, "argv", ["main.py", "--bypass"])
    args = ui.parse_arguments()
    assert args.bypass is True
    assert ui.BYPASS_ENABLED is True


def test_parse_arguments_daemon(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["main.py", "-d"])
    args = ui.parse_arguments()
    assert args.daemon is True
    assert ui.DAEMON_ENABLED is True
    assert ui.BYPASS_ENABLED is True
    assert ui.LOG_ENABLED is False

    monkeypatch.setattr(sys, "argv", ["main.py", "-d", "-l"])
    args = ui.parse_arguments()
    assert args.daemon is True
    assert ui.DAEMON_ENABLED is True
    assert ui.BYPASS_ENABLED is True
    assert ui.LOG_ENABLED is True

    monkeypatch.setattr(sys, "argv", ["main.py", "--daemon"])
    args = ui.parse_arguments()
    assert args.daemon is True
    assert ui.DAEMON_ENABLED is True
    assert ui.LOG_ENABLED is False

    # --interval implies daemon mode
    monkeypatch.setattr(sys, "argv", ["main.py", "--interval", "10"])
    args = ui.parse_arguments()
    assert ui.DAEMON_ENABLED is True
    assert ui.POLLING_INTERVAL == 10

    # Verify no backward compatibility for --autonomous
    monkeypatch.setattr(sys, "argv", ["main.py", "--autonomous"])
    with pytest.raises(SystemExit):
        ui.parse_arguments()

    # Verify -a is now the short flag for --ai
    monkeypatch.setattr(sys, "argv", ["main.py", "-a"])
    with patch("src.ui.GEMINI_API_KEY", "fake_key"):
        args = ui.parse_arguments()
        assert args.ai is True
        assert ui.AI_FALLBACK_ENABLED is True

    # -i is no longer a valid flag
    monkeypatch.setattr(sys, "argv", ["main.py", "-i"])
    with pytest.raises(SystemExit):
        ui.parse_arguments()

def test_parse_arguments_only_rename_aliases(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["main.py", "--only-rename"])
    args = ui.parse_arguments()
    assert args.only_rename is True

    monkeypatch.setattr(sys, "argv", ["main.py", "--only_rename"])
    args = ui.parse_arguments()
    assert args.only_rename is True

    monkeypatch.setattr(sys, "argv", ["main.py", "-r"])
    args = ui.parse_arguments()
    assert args.only_rename is True

def test_parse_arguments_path(monkeypatch, tmp_path):
    folder = tmp_path / "custom"
    folder.mkdir()
    # --path without -r -> only_rename is False (rename and move)
    monkeypatch.setattr(sys, "argv", ["main.py", f"--path={folder}"])
    args = ui.parse_arguments()
    assert args.path == str(folder)
    assert args.only_rename is False

    # --path with -r -> only_rename is True (rename only)
    monkeypatch.setattr(sys, "argv", ["main.py", "-r", f"--path={folder}"])
    args = ui.parse_arguments()
    assert args.path == str(folder)
    assert args.only_rename is True

def test_parse_arguments_path_nonexistent(monkeypatch, tmp_path):
    ghost = tmp_path / "ghost"
    monkeypatch.setattr(sys, "argv", ["main.py", "-r", f"--path={ghost}"])
    with pytest.raises(SystemExit):
        ui.parse_arguments()

def test_parse_arguments_ai_missing_key(monkeypatch):
    monkeypatch.setattr(ui, "GEMINI_API_KEY", None)
    with patch.object(ConfigManager, "GEMINI_API_KEY", new_callable=PropertyMock, return_value=None), \
         patch.object(ConfigManager, "GROQ_API_KEY", new_callable=PropertyMock, return_value=None), \
         patch.object(ConfigManager, "OPENROUTER_API_KEY", new_callable=PropertyMock, return_value=None), \
         patch.object(ConfigManager, "CLOUDFLARE_API_TOKEN", new_callable=PropertyMock, return_value=None):
        monkeypatch.setattr(sys, "argv", ["main.py", "-a"])
        with pytest.raises(SystemExit):
            ui.parse_arguments()


def test_parse_arguments_learn_flags(monkeypatch):
    with patch("src.ui.GEMINI_API_KEY", "fake_key"):
        monkeypatch.setattr(sys, "argv", ["main.py", "-L"])
        args = ui.parse_arguments()
        assert args.learn is True
        assert ui.LEARN_ENABLED is True
        assert ui.AI_FALLBACK_ENABLED is True

        monkeypatch.setattr(sys, "argv", ["main.py", "--learn"])
        args = ui.parse_arguments()
        assert args.learn is True
        assert ui.LEARN_ENABLED is True
        assert ui.AI_FALLBACK_ENABLED is True


def test_parse_arguments_learn_missing_key(monkeypatch):
    monkeypatch.setattr(ui, "GEMINI_API_KEY", None)
    with patch.object(ConfigManager, "GEMINI_API_KEY", new_callable=PropertyMock, return_value=None), \
         patch.object(ConfigManager, "GROQ_API_KEY", new_callable=PropertyMock, return_value=None), \
         patch.object(ConfigManager, "OPENROUTER_API_KEY", new_callable=PropertyMock, return_value=None), \
         patch.object(ConfigManager, "CLOUDFLARE_API_TOKEN", new_callable=PropertyMock, return_value=None):
        monkeypatch.setattr(sys, "argv", ["main.py", "-L"])
        with pytest.raises(SystemExit):
            ui.parse_arguments()


def test_parse_arguments_config_subcommand(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["main.py", "configure"])
    args = ui.parse_arguments()
    assert args.subcommand == "configure"

def test_parse_arguments_config_precedence(monkeypatch, tmp_path):
    test_ini = tmp_path / "prec.ini"
    test_ini.write_text("[options]\nbypass = y\nai = y\nlearn = y\nlog = y\nverbose = y\n", encoding="utf-8")
    cm = ConfigManager(custom_path=str(test_ini))

    with patch("src.ui.config", cm), patch("src.ui.GEMINI_API_KEY", "fake_gemini"):
        monkeypatch.setattr(sys, "argv", ["main.py"])
        args = ui.parse_arguments()
        assert ui.BYPASS_ENABLED is True
        assert ui.AI_FALLBACK_ENABLED is True
        assert ui.LEARN_ENABLED is True
        assert ui.LOG_ENABLED is True
        assert ui.VERBOSE_ENABLED is True

def test_handle_config_command_configure():
    args = MagicMock()
    args.subcommand = "configure"
    with patch("src.config.config.run_wizard") as mock_wiz:
        ui.handle_config_command(args)
        mock_wiz.assert_called_once()

def test_handle_config_command_path(capsys):
    args = MagicMock()
    args.subcommand = "config"
    args.path = True
    args.get = None
    args.set = None
    args.unset = None
    with patch("src.ui.rich_print_log") as mock_log:
        ui.handle_config_command(args)
        assert mock_log.call_count == 1
        assert "Active configuration file" in mock_log.call_args[0][0]

def test_handle_config_command_get(capsys):
    args = MagicMock()
    args.subcommand = "config"
    args.path = False
    args.set = None
    args.unset = None

    # Key exists
    args.get = "paths.movies_folder"
    with patch("src.config.config.get_with_source", return_value=("D:/Movies", "INI")):
        with patch("src.ui.rich_print_log") as mock_log:
            ui.handle_config_command(args)
            assert "paths.movies_folder" in mock_log.call_args[0][0]
            assert "D:/Movies" in mock_log.call_args[0][0]

    # Key unset
    args.get = "api.gemini_api_key"
    with patch("src.config.config.get_with_source", return_value=(None, "NONE")):
        with patch("src.ui.rich_print_log") as mock_log:
            ui.handle_config_command(args)
            assert "'api.gemini_api_key' is not set." in mock_log.call_args[0][0]

def test_handle_config_command_set(tmp_path):
    args = MagicMock()
    args.subcommand = "config"
    args.path = False
    args.get = None
    args.unset = None

    # Valid set
    args.set = ("options.bypass", "y")
    with patch("src.config.config.set") as mock_set:
        with patch("src.ui.rich_print_log") as mock_log:
            ui.handle_config_command(args)
            mock_set.assert_called_once_with("options.bypass", "y")

    # Set non-existent path
    ghost = tmp_path / "ghost_path"
    args.set = ("paths.movies_folder", str(ghost))
    with patch("src.config.config.set"):
        with patch("src.ui.rich_print_log") as mock_log:
            ui.handle_config_command(args)
            logged = " ".join([str(c[0][0]) for c in mock_log.call_args_list if c[0]])
            assert "does not exist on disk" in logged

    # Set resolution without ffprobe
    args.set = ("options.resolution", "true")
    with patch("shutil.which", return_value=None):
        with patch("src.config.config.set"):
            with patch("src.ui.rich_print_log") as mock_log:
                ui.handle_config_command(args)
                logged = " ".join([str(c[0][0]) for c in mock_log.call_args_list if c[0]])
                assert "'ffprobe' (FFmpeg) is not installed" in logged

    # Set notify without mail
    args.set = ("options.notify_on_success", "true")
    with patch.object(ConfigManager, "MAIL", new_callable=PropertyMock, return_value=None), \
         patch.object(ConfigManager, "MAIL_PSWD", new_callable=PropertyMock, return_value=None):
        with patch("src.config.config.set"):
            with patch("src.ui.rich_print_log") as mock_log:
                ui.handle_config_command(args)
                logged = " ".join([str(c[0][0]) for c in mock_log.call_args_list if c[0]])
                assert "Email notifications are enabled, but Gmail credentials" in logged

    # Set invalid key raises ValueError and exits 1
    args.set = ("invalid.key", "val")
    with patch("src.config.config.set", side_effect=ValueError("Unknown section")):
        with pytest.raises(SystemExit):
            ui.handle_config_command(args)

def test_parse_arguments_resolution_and_quality(monkeypatch):
    with patch("shutil.which", return_value="/usr/bin/ffprobe"):
        monkeypatch.setattr(sys, "argv", ["main.py", "-R", "-q"])
        args = ui.parse_arguments()
        assert args.resolution is True
        assert args.quality is True
        assert ui.RESOLUTION_ENABLED is True
        assert ui.QUALITY_ENABLED is True

def test_parse_arguments_resolution_quality_missing_ffprobe(monkeypatch):
    with patch("shutil.which", return_value=None):
        monkeypatch.setattr(sys, "argv", ["main.py", "-R"])
        with pytest.raises(SystemExit):
            ui.parse_arguments()

def test_parse_arguments_notify_flags_success(monkeypatch):
    with patch("src.ui.MAIL", "user@gmail.com"), patch("src.ui.MAIL_PSWD", "secret"):
        monkeypatch.setattr(sys, "argv", ["main.py", "--notify-success", "--notify-error", "-t"])
        args = ui.parse_arguments()
        assert args.notify_success is True
        assert args.notify_error is True
        assert args.notify_tag is True
        assert ui.NOTIFY_SUCCESS_ENABLED is True
        assert ui.NOTIFY_ERROR_ENABLED is True
        assert ui.NOTIFY_TAG_ENABLED is True

        monkeypatch.setattr(sys, "argv", ["main.py", "--notify-tag"])
        args = ui.parse_arguments()
        assert args.notify_tag is True
        assert ui.NOTIFY_TAG_ENABLED is True

def test_parse_arguments_notify_flags_missing_credentials(monkeypatch):
    with patch("src.ui.MAIL", None), patch("src.ui.MAIL_PSWD", None), \
         patch.object(ConfigManager, "MAIL", new_callable=PropertyMock, return_value=None), \
         patch.object(ConfigManager, "MAIL_PSWD", new_callable=PropertyMock, return_value=None):
        monkeypatch.setattr(sys, "argv", ["main.py", "--notify-success"])
        with pytest.raises(SystemExit):
            ui.parse_arguments()

        monkeypatch.setattr(sys, "argv", ["main.py", "-t"])
        with pytest.raises(SystemExit):
            ui.parse_arguments()

def test_handle_config_command_unset():
    args = MagicMock()
    args.subcommand = "config"
    args.path = False
    args.get = None
    args.set = None

    # Successfully unset
    args.unset = "api.gemini_api_key"
    with patch("src.config.config.unset", return_value=True):
        with patch("src.ui.rich_print_log") as mock_log:
            ui.handle_config_command(args)
            assert "Unset" in mock_log.call_args[0][0]

    # Key not found
    with patch("src.config.config.unset", return_value=False):
        with patch("src.ui.rich_print_log") as mock_log:
            ui.handle_config_command(args)
            assert "was not found" in mock_log.call_args[0][0]

    # Unset invalid key raises ValueError and exits 1
    with patch("src.config.config.unset", side_effect=ValueError("Invalid key")):
        with pytest.raises(SystemExit):
            ui.handle_config_command(args)

def test_display_config_table():
    with patch("src.ui.rich_print_log") as mock_log:
        ui.display_config_table(show_secrets=False)
        assert mock_log.call_count >= 3

    with patch("src.ui.rich_print_log") as mock_log:
        ui.display_config_table(show_secrets=True)
        assert mock_log.call_count >= 3

def test_logging_functions(tmp_path, monkeypatch):
    # print_log without LOG_ENABLED
    monkeypatch.setattr(ui, "LOG_ENABLED", False)
    with patch("builtins.print") as mock_print:
        ui.print_log("hello test")
        mock_print.assert_called_once_with("hello test")

    # print_log with LOG_ENABLED
    monkeypatch.setattr(ui, "LOG_ENABLED", True)
    with patch("builtins.open", mock_open()) as mock_f, patch("builtins.print") as mock_print:
        ui.print_log("file log message")
        mock_f.assert_called()
        mock_print.assert_not_called()
    
    # rich_print_log without LOG_ENABLED
    monkeypatch.setattr(ui, "LOG_ENABLED", False)
    with patch("rich.console.Console.print") as mock_console_print:
        ui.rich_print_log("test message")
        mock_console_print.assert_called_once()

    # rich_print_log with LOG_ENABLED
    monkeypatch.setattr(ui, "LOG_ENABLED", True)
    with patch("src.ui.print_log") as mock_pl:
        ui.rich_print_log("rich log enabled message")
        mock_pl.assert_called()

def test_get_log_dir(tmp_path, monkeypatch):
    # Non-frozen
    monkeypatch.delattr(sys, "frozen", raising=False)
    log_dir = ui.get_log_dir()
    assert log_dir.name == "log"

    # Frozen normal
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(Path, "cwd", lambda: tmp_path)
    log_dir_frozen = ui.get_log_dir()
    assert log_dir_frozen == tmp_path / "log"

    # Frozen permission error fallback
    orig_mkdir = Path.mkdir
    def mock_mkdir(self, *args, **kwargs):
        if self == tmp_path / "log":
            raise PermissionError("Access denied")
        return orig_mkdir(self, *args, **kwargs)
    
    monkeypatch.setattr(Path, "mkdir", mock_mkdir)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "bin" / "app.exe"))
    log_dir_fallback = ui.get_log_dir()
    assert log_dir_fallback == tmp_path / "bin" / "log"

def test_print_error():
    # Verbose False
    ui.VERBOSE_ENABLED = False
    msg = ui.print_error("Error msg", "Traceback details")
    assert "Error logs:" not in msg
    assert "Error msg" in msg

    # Verbose True
    ui.VERBOSE_ENABLED = True
    msg = ui.print_error("Error msg", "Traceback details")
    assert "Error logs:" in msg
    assert "Traceback details" in msg

def test_display_corrected_filenames():
    # Empty DataFrame
    with patch("src.ui.rich_print_log") as mock_log:
        ui.display_corrected_filenames(pd.DataFrame())
        mock_log.assert_called_once_with("[yellow]No media files detected.[/yellow]")

    # Missing Media column
    with patch("src.ui.rich_print_log") as mock_log:
        ui.display_corrected_filenames(pd.DataFrame({"Original": ["a"]}))
        mock_log.assert_called_once_with("[yellow]No media files detected.[/yellow]")

    # No movies and no tv (e.g. unknown only)
    with patch("src.ui.rich_print_log") as mock_log:
        ui.display_corrected_filenames(pd.DataFrame([{"Media": "other", "Original": "a", "Corrected": "b"}]))
        mock_log.assert_called_once_with("[yellow]No media files detected.[/yellow]")

    # Movies and TV Shows
    df = pd.DataFrame([
        {"Media": "movie", "Original": "Inception.mkv", "Corrected": "Inception (2010)"},
        {"Media": "tv", "Original": "Dark.S01E01.mkv", "Season": "01", "Episode": "01", "Corrected": "Dark - S01E01"},
        {"Media": "movie", "Original": "Same.mkv", "Corrected": "Same.mkv"},
    ])
    with patch("src.ui.rich_print_log") as mock_log:
        ui.display_corrected_filenames(df)
        assert mock_log.call_count >= 2

def test_display_sorted_files(tmp_path):
    # Empty paths
    with patch("src.ui.rich_print_log") as mock_log:
        ui.display_sorted_files([])
        mock_log.assert_called_once_with("[yellow]No sorted files to display.[/yellow]")

    movies_dir = tmp_path / "Movies"
    tv_dir = tmp_path / "TV Shows"
    movies_dir.mkdir()
    tv_dir.mkdir()

    with patch("src.ui.MOVIES_FOLDER", str(movies_dir)), patch("src.ui.TV_SHOWS_FOLDER", str(tv_dir)):
        paths = [
            (str(tmp_path / "m.mkv"), str(movies_dir / "Movie (2020)" / "Movie.mkv")),
            (str(tmp_path / "t.mkv"), str(tv_dir / "Show" / "Season 01" / "Show S01E01.mkv")),
            (str(tmp_path / "other.mkv"), str(tmp_path / "Other" / "other.mkv")),
        ]
        with patch("src.ui.rich_print_log") as mock_log:
            ui.display_sorted_files(paths)
            assert mock_log.call_count >= 2

def test_display_skipped_filenames():
    # Empty list
    with patch("src.ui.rich_print_log") as mock_log:
        ui.display_skipped_filenames([])
        mock_log.assert_not_called()

    # With failed items
    failed = [
        {"Original": "bad.mkv", "Reason": "File corrupted"},
        {"Reason": "No name"}
    ]
    with patch("src.ui.rich_print_log") as mock_log:
        ui.display_skipped_filenames(failed)
        assert mock_log.call_count >= 2

def test_user_confirmation():
    # BYPASS_ENABLED = True (bypasses input)
    ui.BYPASS_ENABLED = True
    with patch("builtins.input") as mock_input:
        ui.user_confirmation("test action")
        mock_input.assert_not_called()

    # BYPASS_ENABLED = False, user presses enter
    ui.BYPASS_ENABLED = False
    with patch("builtins.input", return_value=""):
        ui.user_confirmation("test action")

    # AUTO_ENABLED = False, user triggers KeyboardInterrupt
    with patch("builtins.input", side_effect=KeyboardInterrupt):
        with pytest.raises(SystemExit):
            ui.user_confirmation("test action")


def test_is_double_clicked(monkeypatch):
    # Non-win32
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(sys, "argv", ["main.py"])
    assert ui.is_double_clicked() is False

    # Win32 with multiple arguments
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(sys, "argv", ["main.py", "-r"])
    assert ui.is_double_clicked() is False

    # Win32 single process (double clicked from Explorer)
    monkeypatch.setattr(sys, "argv", ["main.py"])
    fake_kernel32 = MagicMock()
    fake_kernel32.GetConsoleProcessList.return_value = 1
    fake_windll = MagicMock(kernel32=fake_kernel32)
    fake_ctypes = MagicMock(windll=fake_windll)
    with patch.dict("sys.modules", {"ctypes": fake_ctypes}):
        assert ui.is_double_clicked() is True

    # Win32 multiple processes in console (e.g. run from terminal)
    fake_kernel32.GetConsoleProcessList.return_value = 2
    with patch.dict("sys.modules", {"ctypes": fake_ctypes}):
        assert ui.is_double_clicked() is False

    # Win32 exception handling
    fake_kernel32.GetConsoleProcessList.side_effect = RuntimeError("Console error")
    with patch.dict("sys.modules", {"ctypes": fake_ctypes}):
        assert ui.is_double_clicked() is False


def test_hide_console_window(monkeypatch):
    # Non-win32
    monkeypatch.setattr(sys, "platform", "linux")
    ui.hide_console_window()

    # Win32 with valid console window handle
    monkeypatch.setattr(sys, "platform", "win32")
    fake_kernel32 = MagicMock()
    fake_kernel32.GetConsoleWindow.return_value = 12345
    fake_user32 = MagicMock()
    fake_windll = MagicMock(kernel32=fake_kernel32, user32=fake_user32)
    fake_ctypes = MagicMock(windll=fake_windll)
    with patch.dict("sys.modules", {"ctypes": fake_ctypes}):
        ui.hide_console_window()
        fake_user32.ShowWindow.assert_called_once_with(12345, 0)

    # Win32 with no console window handle
    fake_kernel32.GetConsoleWindow.return_value = 0
    fake_user32.reset_mock()
    with patch.dict("sys.modules", {"ctypes": fake_ctypes}):
        ui.hide_console_window()
        fake_user32.ShowWindow.assert_not_called()

    # Win32 with exception
    fake_kernel32.GetConsoleWindow.side_effect = RuntimeError("Failed")
    with patch.dict("sys.modules", {"ctypes": fake_ctypes}):
        ui.hide_console_window()  # Should not raise

