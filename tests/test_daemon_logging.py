import re
from unittest.mock import patch, MagicMock
import pandas as pd

from src import ui
import main


def test_format_daemon_log():
    line = ui.format_daemon_log("INFO", "Test message")
    pattern = r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} \[INFO\] Test message$"
    assert re.match(pattern, line)

    # Multi-line strings must be flattened to a single line
    multiline = "Line 1\nLine 2\n\nLine 3"
    flattened = ui.format_daemon_log("ERROR", multiline)
    assert "\n" in flattened
    pass


def test_log_info_stdout(capsys, monkeypatch):
    monkeypatch.setattr(ui, "DAEMON_ENABLED", True)
    monkeypatch.setattr(ui, "LOG_ENABLED", False)
    monkeypatch.setattr(ui, "LOG_MODE", "console")

    ui.log_info("System status operational")
    captured = capsys.readouterr()

    assert "[INFO] System status operational" in captured.out
    assert captured.err == ""
    assert re.match(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} \[INFO\] System status operational\n$", captured.out)


def test_log_success_stdout(capsys, monkeypatch):
    monkeypatch.setattr(ui, "DAEMON_ENABLED", True)
    monkeypatch.setattr(ui, "LOG_ENABLED", False)
    monkeypatch.setattr(ui, "LOG_MODE", "console")

    ui.log_success("old.mkv", "new.mkv", "/data/Movies/new.mkv")
    captured = capsys.readouterr()

    expected_part = "[SUCCESS] 'old.mkv' -> 'new.mkv' (Destination: /data/Movies/new.mkv)"
    assert expected_part in captured.out
    assert captured.err == ""
    assert captured.out.endswith("\n")
    assert "\n" not in captured.out.strip()


def test_log_error_stderr(capsys, monkeypatch):
    monkeypatch.setattr(ui, "DAEMON_ENABLED", True)
    monkeypatch.setattr(ui, "LOG_ENABLED", False)
    monkeypatch.setattr(ui, "LOG_MODE", "console")

    ui.log_error("Target directory is not reachable")
    captured = capsys.readouterr()

    assert captured.out == ""
    assert "[ERROR] Target directory is not reachable" in captured.err
    assert re.match(
        r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} \[ERROR\] Target directory is not reachable\n$", captured.err
    )


def test_print_log_daemon_auto_detection(capsys, monkeypatch):
    monkeypatch.setattr(ui, "DAEMON_ENABLED", True)
    monkeypatch.setattr(ui, "LOG_ENABLED", False)
    monkeypatch.setattr(ui, "LOG_MODE", "console")

    # Routine message -> INFO on stdout
    ui.print_log("Check 1 : No media to process")
    captured = capsys.readouterr()
    assert "[INFO] Check 1 : No media to process" in captured.out
    assert captured.err == ""

    # Error message with ❌ -> ERROR on stderr
    ui.print_log("❌ Error: Network timeout occurred\n\n")
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "[ERROR] Error: Network timeout occurred" in captured.err
    assert "\n" not in captured.err.strip()

    # Pre-tagged [SUCCESS] -> SUCCESS on stdout
    ui.print_log("[SUCCESS] 'a.mkv' -> 'b.mkv'")
    captured = capsys.readouterr()
    assert "[SUCCESS] 'a.mkv' -> 'b.mkv'" in captured.out
    assert captured.err == ""


def test_rich_print_log_in_daemon_mode(capsys, monkeypatch):
    monkeypatch.setattr(ui, "DAEMON_ENABLED", True)
    monkeypatch.setattr(ui, "LOG_ENABLED", False)
    monkeypatch.setattr(ui, "LOG_MODE", "console")

    from rich.table import Table

    table = Table(title="Test Table")
    table.add_column("Col 1")
    table.add_row("Value 1")

    # rich_print_log must not dump raw ANSI/multi-line table to console in daemon mode
    ui.rich_print_log(table)
    captured = capsys.readouterr()

    assert "[INFO]" in captured.out
    assert "Test Table" in captured.out
    # Output must be strictly a single line
    assert "\n" not in captured.out.strip()


def test_dual_logging_in_daemon_mode(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(ui, "DAEMON_ENABLED", True)
    monkeypatch.setattr(ui, "LOG_ENABLED", True)
    monkeypatch.setattr(ui, "LOG_MODE", "both")
    monkeypatch.setattr(ui, "get_log_dir", lambda: tmp_path)

    ui.log_info("Daemon heartbeat tick")
    ui.log_success("orig.mp4", "clean.mp4", "/dest/clean.mp4")
    ui.log_error("Permission denied on folder")

    captured = capsys.readouterr()
    assert "[INFO] Daemon heartbeat tick" in captured.out
    assert "[SUCCESS] 'orig.mp4' -> 'clean.mp4' (Destination: /dest/clean.mp4)" in captured.out
    assert "[ERROR] Permission denied on folder" in captured.err

    # Check file contents
    log_files = list(tmp_path.glob("*.txt"))
    assert len(log_files) == 1
    file_content = log_files[0].read_text(encoding="utf-8")
    lines = file_content.strip().splitlines()

    assert len(lines) == 3
    # Verify no double timestamps like "[12:00:00] 2026-..."
    for line in lines:
        assert re.match(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} \[(INFO|SUCCESS|ERROR)\] ", line)

    assert "[INFO] Daemon heartbeat tick" in lines[0]
    assert "[SUCCESS] 'orig.mp4' -> 'clean.mp4'" in lines[1]
    assert "[ERROR] Permission denied on folder" in lines[2]


def test_console_only_when_log_disabled(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(ui, "DAEMON_ENABLED", True)
    monkeypatch.setattr(ui, "LOG_ENABLED", False)
    monkeypatch.setattr(ui, "LOG_MODE", "console")
    monkeypatch.setattr(ui, "get_log_dir", lambda: tmp_path)

    ui.log_info("Console only message")
    captured = capsys.readouterr()
    assert "[INFO] Console only message" in captured.out

    # No files should be created
    assert list(tmp_path.glob("*.txt")) == []


def test_non_daemon_mode_preserved(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(ui, "DAEMON_ENABLED", False)
    monkeypatch.setattr(ui, "LOG_ENABLED", False)
    monkeypatch.setattr(ui, "LOG_MODE", "console")

    # Non-daemon mode uses standard print(message) without daemon timestamp prefix
    ui.print_log("Classic console message")
    captured = capsys.readouterr()
    assert captured.out == "Classic console message\n"
    assert "[INFO]" not in captured.out

    # Non-daemon mode with file logging uses [HH:MM:SS] prefix
    monkeypatch.setattr(ui, "LOG_ENABLED", True)
    monkeypatch.setattr(ui, "LOG_MODE", "file")
    monkeypatch.setattr(ui, "get_log_dir", lambda: tmp_path)

    ui.print_log("File only classic message")
    log_files = list(tmp_path.glob("*.txt"))
    assert len(log_files) == 1
    content = log_files[0].read_text(encoding="utf-8")
    assert re.match(r"^\[\d{2}:\d{2}:\d{2}\] Classic console message", content) or re.match(
        r"^\[\d{2}:\d{2}:\d{2}\] File only classic message", content
    )


def test_display_skipped_filenames_in_daemon_mode(capsys, monkeypatch):
    monkeypatch.setattr(ui, "DAEMON_ENABLED", True)
    monkeypatch.setattr(ui, "LOG_ENABLED", False)
    monkeypatch.setattr(ui, "LOG_MODE", "console")

    failed = [
        {"Original": "Unknown.File.2024.mkv", "Reason": "TMDB lookup returned no results"},
        {"Original": "Bad.File.mkv", "Reason": "File corrupted"},
    ]

    ui.display_skipped_filenames(failed)
    captured = capsys.readouterr()

    assert captured.out == ""
    err_lines = captured.err.strip().splitlines()
    assert len(err_lines) == 2
    assert "[ERROR] Skipped file 'Unknown.File.2024.mkv': TMDB lookup returned no results" in err_lines[0]
    assert "[ERROR] Skipped file 'Bad.File.mkv': File corrupted" in err_lines[1]


def test_process_media_daemon_single_line_flow(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(ui, "DAEMON_ENABLED", True)
    monkeypatch.setattr(ui, "LOG_ENABLED", False)
    monkeypatch.setattr(ui, "LOG_MODE", "console")

    media_file = tmp_path / "Movie.2024.mkv"
    media_file.touch()

    args = MagicMock()
    args.path = str(tmp_path)
    args.only_rename = False
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

    sorted_paths = [(str(media_file), str(tmp_path / "Movies" / "Movie (2024)" / "Movie (2024).mkv"))]

    with (
        patch("src.files.search_media_files", return_value=(clean_df, pd.DataFrame())),
        patch("src.utils.get_corrected_media_filenames", return_value=clean_df),
        patch("src.files.rename_media_files", return_value=clean_df),
        patch("src.files.sort_media_files", return_value=sorted_paths),
        patch(
            "src.files.move_media_files",
            side_effect=lambda paths, df, **kw: (
                ui.log_success("Movie.2024.mkv", "Movie (2024).mkv", paths[0][1]),
                (1, 0),
            )[1],
        ),
    ):
        ret = main.process_media(args, daemon=True, cycle=1)
        assert ret == 0

    captured = capsys.readouterr()
    lines = captured.out.strip().splitlines()
    assert len(lines) >= 2
    assert any("[SUCCESS] 'Movie.2024.mkv' -> 'Movie (2024).mkv'" in l for l in lines)
    assert any("Successfully processed 1/1 file(s)." in l for l in lines)
    # Zero Rich tables or empty lines
    for line in lines:
        assert re.match(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} \[(INFO|SUCCESS)\] ", line)


def test_process_media_only_rename_daemon(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(ui, "DAEMON_ENABLED", True)
    monkeypatch.setattr(ui, "LOG_ENABLED", False)
    monkeypatch.setattr(ui, "LOG_MODE", "console")

    media_file = tmp_path / "Show.S01E01.mkv"
    media_file.touch()

    args = MagicMock()
    args.path = str(tmp_path)
    args.only_rename = True
    args.simulate = False

    clean_df = pd.DataFrame(
        [
            {
                "Original": "Show.S01E01.mkv",
                "Corrected": "Show - S01E01",
                "Path": str(media_file),
                "Media": "tv",
                "Season": "1",
                "Episode": "1",
            }
        ]
    )

    with (
        patch("src.files.search_media_files", return_value=(clean_df, pd.DataFrame())),
        patch("src.utils.get_corrected_media_filenames", return_value=clean_df),
        patch("src.files.rename_media_files", return_value=clean_df),
        patch("src.mail.send_media_success_email"),
    ):
        ret = main.process_media(args, daemon=True, cycle=2)
        assert ret == 0

    captured = capsys.readouterr()
    lines = captured.out.strip().splitlines()
    assert any(
        "[SUCCESS] 'Show.S01E01.mkv' -> 'Show.S01E01.mkv' (Destination: " in l and "(in-place)" in l for l in lines
    )
    assert any("[INFO] Check 2 : Successfully renamed 1 file(s)." in l for l in lines)


def test_emit_daemon_log_cleanup_trigger(tmp_path, monkeypatch):
    monkeypatch.setattr(ui, "DAEMON_ENABLED", True)
    monkeypatch.setattr(ui, "LOG_ENABLED", True)
    monkeypatch.setattr(ui, "LOG_MODE", "file")
    monkeypatch.setattr(ui, "get_log_dir", lambda: tmp_path)
    monkeypatch.setattr(ui, "_last_log_cleanup_date", "1970-01-01")

    with patch("src.ui.cleanup_old_logs") as mock_clean:
        ui.log_info("Trigger cleanup")
        mock_clean.assert_called_once_with(tmp_path, max_age_days=14)
        assert ui._last_log_cleanup_date != "1970-01-01"


def test_emit_daemon_log_oserror_handled(tmp_path, monkeypatch):
    monkeypatch.setattr(ui, "DAEMON_ENABLED", True)
    monkeypatch.setattr(ui, "LOG_ENABLED", True)
    monkeypatch.setattr(ui, "LOG_MODE", "file")
    monkeypatch.setattr(ui, "get_log_dir", lambda: tmp_path)

    with patch("builtins.open", side_effect=OSError("Disk write failure")):
        # Should catch OSError without raising
        ui.log_info("Handled write error")


def test_logging_functions_non_daemon_mode(capsys, monkeypatch):
    monkeypatch.setattr(ui, "DAEMON_ENABLED", False)
    monkeypatch.setattr(ui, "LOG_ENABLED", False)
    monkeypatch.setattr(ui, "LOG_MODE", "console")

    ui.log_info("Classic non-daemon info")
    assert "Classic non-daemon info\n" in capsys.readouterr().out

    ui.log_error("Classic non-daemon error")
    assert "Classic non-daemon error\n" in capsys.readouterr().out

    ui.log_success("old.mkv", "new.mkv", "/dest/new.mkv")
    assert "✅ 'old.mkv' -> 'new.mkv' (Destination: /dest/new.mkv)\n" in capsys.readouterr().out


def test_print_log_daemon_info_prefix(capsys, monkeypatch):
    monkeypatch.setattr(ui, "DAEMON_ENABLED", True)
    monkeypatch.setattr(ui, "LOG_ENABLED", False)
    monkeypatch.setattr(ui, "LOG_MODE", "console")

    ui.print_log("[INFO] Pre-tagged info message")
    captured = capsys.readouterr()
    assert "[INFO] Pre-tagged info message" in captured.out


def test_format_daemon_log_colorize():
    err_line = ui.format_daemon_log("ERROR", "Failed to connect", colorize=True)
    assert err_line.startswith("\033[31m")
    assert err_line.endswith("\033[0m")
    assert "[ERROR] Failed to connect" in err_line

    succ_line = ui.format_daemon_log("SUCCESS", "File processed", colorize=True)
    assert succ_line.startswith("\033[32m")
    assert succ_line.endswith("\033[0m")
    assert "[SUCCESS] File processed" in succ_line

    info_line = ui.format_daemon_log("INFO", "Running cycle", colorize=True)
    assert not info_line.startswith("\033[")
    assert "[INFO] Running cycle" in info_line


def test_docker_logging_colorization(capsys, monkeypatch):
    monkeypatch.setattr(ui, "DAEMON_ENABLED", True)
    monkeypatch.setattr(ui, "LOG_ENABLED", False)
    monkeypatch.setattr(ui, "LOG_MODE", "console")
    monkeypatch.setenv("DOCKER_CONTAINER", "1")

    # Error should be entirely red in stderr
    ui.log_error("A critical error in Docker")
    captured = capsys.readouterr()
    assert captured.err.startswith("\033[31m")
    assert captured.err.endswith("\033[0m\n")
    assert "[ERROR] A critical error in Docker" in captured.err

    # Success should be entirely green in stdout
    ui.log_success("source.mkv", "dest.mkv", "/data/Movies/dest.mkv")
    captured = capsys.readouterr()
    assert captured.out.startswith("\033[32m")
    assert captured.out.endswith("\033[0m\n")
    assert "[SUCCESS] 'source.mkv' -> 'dest.mkv'" in captured.out
