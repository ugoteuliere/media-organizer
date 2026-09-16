from __future__ import annotations
import sys
import os
import re
import shutil
import types

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError, OSError):
        pass

from rich.console import Console
from rich.table import Table
from datetime import datetime, timedelta
from pathlib import Path
import argparse
import uuid

from src.config import config
from src.runtime_config import runtime

# ── Module-level config snapshots for backwards-compatible attribute access ──
# These are only used by parse_arguments() and should NOT be used elsewhere.
# All other modules should read `runtime.xxx` or `config.xxx` instead.
_last_log_cleanup_date = None


def is_double_clicked() -> bool:
    """Detects if application was launched by double-clicking in Windows Explorer."""
    if sys.platform == "win32" and len(sys.argv) == 1:
        try:
            import ctypes

            pids = (ctypes.c_uint * 2)()
            count = ctypes.windll.kernel32.GetConsoleProcessList(pids, 2)
            return count <= 1
        except Exception:
            return False
    return False


def hide_console_window() -> None:
    """Hides the host console window on Windows when launching the graphical interface."""
    if sys.platform == "win32":
        try:
            import ctypes

            hwnd = ctypes.windll.kernel32.GetConsoleWindow()
            if hwnd:
                ctypes.windll.user32.ShowWindow(hwnd, 0)
        except Exception:
            pass


def parse_arguments():
    global _last_log_cleanup_date

    description_text = (
        "media-organizer\n"
        "Automatically parses, renames, and sorts messy video files using TMDB and Multi-Cloud AI (Gemini, Groq, OpenRouter, Cloudflare)."
    )

    epilog_text = (
        "Examples:\n"
        "  media-organizer                    (Default: Renames AND moves files)\n"
        "  media-organizer -r                 (Only renames the files in place)\n"
        "  media-organizer -s                 (Simulation mode: preview changes without modifying disk)\n"
        "  media-organizer -d                 (Daemon mode: continuous background polling)\n"
        "  media-organizer -d --interval 10   (Daemon mode with 10-minute polling)\n"
        "  media-organizer -L                 (Enables AI keyword learning)\n"
        "  media-organizer -t                 (Sends email notification when an AI keyword is learned)\n"
        "  media-organizer -R -q              (Appends resolution & quality tags)\n"
        "  media-organizer --notify-success   (Sends email notification on success)\n"
        "  media-organizer configure          (Interactive configuration wizard)\n"
        "  media-organizer config --list      (List all configured settings)\n"
        '  media-organizer config --set paths.movies_folder "D:/Movies"\n\n'
        "Documentation & Updates: https://github.com/ugoteuliere/media-organizer"
    )

    parser = argparse.ArgumentParser(
        description=description_text, epilog=epilog_text, formatter_class=argparse.RawTextHelpFormatter
    )

    modes_group = parser.add_argument_group("Operational Modes")
    modes_group.add_argument(
        "-g", "--gui", action="store_true", help="Launch modern graphical configuration interface (GUI)."
    )
    modes_group.add_argument(
        "-r",
        "--only-rename",
        "--only_rename",
        action="store_true",
        dest="only_rename",
        help="Renames files in place without moving them to Movie/TV Show folders.",
    )
    modes_group.add_argument(
        "-s",
        "--simulate",
        action="store_true",
        help="Simulates renaming and sorting without modifying any files on disk.",
    )

    proc_group = parser.add_argument_group("Processing Options")
    proc_group.add_argument(
        "-R", "--resolution", action="store_true", help="Detect and append video resolution tags (e.g. [1080p], [4K])."
    )
    proc_group.add_argument(
        "-q",
        "--quality",
        action="store_true",
        help="Detect and append video encoding/quality tags (e.g. [FullHD BluRay]).",
    )
    proc_group.add_argument(
        "-a",
        "--ai",
        action="store_true",
        help="Enables the Gemini AI fallback to intelligently parse and correct highly obfuscated filenames.",
    )
    proc_group.add_argument(
        "-L",
        "--learn",
        action="store_true",
        help="Enable AI keyword learning to discover and save missing tags from Gemini.",
    )
    proc_group.add_argument(
        "--provider",
        choices=["auto", "gemini", "groq", "openrouter", "cloudflare"],
        default=None,
        help="Specify the AI cloud provider to use for fallback parsing (auto, gemini, groq, openrouter, cloudflare).",
    )
    proc_group.add_argument(
        "--path",
        type=str,
        default=None,
        help="Target a specific folder as source (overrides downloads folder, or renames in-place with -r).",
    )

    auto_group = parser.add_argument_group("Automation & Logging")
    auto_group.add_argument(
        "-d",
        "--daemon",
        action="store_true",
        dest="daemon",
        help="Run continuously in background daemon mode with periodic polling.",
    )
    auto_group.add_argument(
        "--interval",
        type=int,
        default=None,
        help="Polling interval in minutes for daemon mode (automatically enables daemon mode).",
    )
    auto_group.add_argument(
        "-b", "--bypass", action="store_true", help="Bypass user confirmation prompts before renaming or moving files."
    )
    auto_group.add_argument(
        "-l",
        "--log",
        action="store_true",
        help="Suppresses terminal output and writes all console messages to a dedicated log file instead.",
    )
    auto_group.add_argument(
        "-v", "--verbose", action="store_true", help="Display detailed error logs after error messages."
    )
    auto_group.add_argument(
        "--notify-success", action="store_true", help="Send an email notification on successful media processing."
    )
    auto_group.add_argument(
        "--notify-error", action="store_true", help="Send an email notification when a processing error occurs."
    )
    auto_group.add_argument(
        "-t",
        "--notify-tag",
        action="store_true",
        help="Send an email notification when a new AI keyword tag is discovered and saved.",
    )

    # Subparsers for config commands
    subparsers = parser.add_subparsers(dest="subcommand")

    config_parser = subparsers.add_parser(
        "config",
        help="View and manage configuration settings (INI file & environment variables).",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    config_parser.add_argument(
        "-g", "--gui", action="store_true", help="Launch modern graphical configuration interface (GUI)."
    )
    config_parser.add_argument(
        "-l", "--list", action="store_true", help="List all configured settings and their sources."
    )
    config_parser.add_argument(
        "--show-secrets", action="store_true", help="Display sensitive values (API keys, passwords) without masking."
    )
    config_parser.add_argument(
        "--get",
        metavar="KEY",
        help="Get the value for a specific setting (e.g. paths.movies_folder, api.tmdb_api_key).",
    )
    config_parser.add_argument(
        "--set",
        nargs=2,
        metavar=("KEY", "VALUE"),
        help="Set a configuration setting (e.g. paths.movies_folder 'D:/Movies').",
    )
    config_parser.add_argument("--unset", metavar="KEY", help="Remove a configuration setting from the INI file.")
    config_parser.add_argument("--path", action="store_true", help="Display the path of the active configuration file.")

    configure_parser = subparsers.add_parser(
        "configure",
        help="Launch interactive configuration wizard or GUI.",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    configure_parser.add_argument(
        "-g", "--gui", action="store_true", help="Launch modern graphical configuration tool (GUI)."
    )
    configure_parser.add_argument(
        "--paths", action="store_true", help="Configure storage and library folders directly."
    )
    configure_parser.add_argument(
        "--ai", action="store_true", help="Configure API keys and Cloud AI providers directly."
    )
    configure_parser.add_argument(
        "--email", action="store_true", help="Configure email alerts and SMTP credentials directly."
    )
    configure_parser.add_argument(
        "--options", action="store_true", help="Configure runtime and automation options directly."
    )
    configure_parser.add_argument("--video", action="store_true", help="Configure video stream options directly.")
    configure_parser.add_argument(
        "--full", action="store_true", help="Run full step-by-step setup wizard without menu."
    )

    args = parser.parse_args()

    # If running a configuration subcommand, return immediately
    if getattr(args, "subcommand", None) in ("config", "configure"):
        return args

    # Path check: must exist if specified
    if args.path:
        if not os.path.isdir(args.path):
            parser.error(f"Invalid path: The directory '{args.path}' does not exist or is not a valid folder.")

    # ── Populate the RuntimeConfig singleton ─────────────────────────────────
    current_mail = config.MAIL
    current_pswd = config.MAIL_PSWD
    runtime.mail_enabled = bool(current_mail and current_pswd)

    is_daemon = bool(
        (getattr(args, "daemon", False) or (args.interval is not None) or getattr(config, "DAEMON", False))
        and not getattr(args, "simulate", False)
    )
    if getattr(args, "simulate", False) and (getattr(args, "daemon", False) or args.interval is not None):
        print_log("Note: Continuous daemon polling is disabled in simulation mode. Running a single preview cycle.\n")
    runtime.daemon_enabled = is_daemon
    if args.interval is not None:
        if args.interval < 1:
            parser.error("Invalid interval: The '--interval' option requires a positive integer of at least 1 minute.")
        runtime.polling_interval = args.interval
    else:
        runtime.polling_interval = getattr(config, "POLLING_INTERVAL", 15)

    runtime.learn_enabled = bool(args.learn or getattr(config, "LEARN", False))
    runtime.ai_fallback_enabled = bool(args.ai or getattr(config, "AI", False) or runtime.learn_enabled)
    runtime.bypass_enabled = bool(args.bypass or getattr(config, "BYPASS", False) or runtime.daemon_enabled)
    is_docker = config.is_docker_environment()
    wants_log = bool(args.log or getattr(config, "LOG", False))
    if wants_log:
        log_dir = get_log_dir()
        has_perm, reason = check_log_dir_permissions(log_dir)
        if has_perm:
            runtime.log_mode = "both" if is_docker else "file"
            runtime.log_enabled = True
        else:
            sys.stderr.write(
                f"\nWarning: Log directory '{log_dir}' is not writable ({reason}).\n"
                "Falling back to console logging (stdout/stderr) only.\n\n"
            )
            runtime.log_mode = "console"
            runtime.log_enabled = False
    else:
        runtime.log_mode = "console"
        runtime.log_enabled = False
    runtime.verbose_enabled = bool(args.verbose or getattr(config, "VERBOSE", False))
    runtime.simulate_enabled = bool(args.simulate)
    runtime.resolution_enabled = bool(args.resolution or getattr(config, "RESOLUTION", False))
    runtime.quality_enabled = bool(args.quality or getattr(config, "QUALITY", False))
    runtime.notify_success_enabled = bool(args.notify_success)
    runtime.notify_error_enabled = bool(args.notify_error)
    runtime.notify_tag_enabled = bool(args.notify_tag)

    if (args.notify_success or args.notify_error or args.notify_tag) and not runtime.mail_enabled:
        parser.error(
            "Missing configuration: Email notification flags require 'mail' and 'mail_pswd' to be configured in [mail].\n\n"
            "How to fix:\n"
            "  1. Run the configuration wizard:\n"
            "     media-organizer configure\n"
            "  2. Or set credentials via CLI:\n"
            '     media-organizer config --set mail.mail "<your_email@gmail.com>"\n'
            '     media-organizer config --set mail.mail_pswd "<your_16_char_app_password>"'
        )

    if (args.resolution or args.quality) and not shutil.which("ffprobe"):
        parser.error(
            "Missing dependency: The '-R/--resolution' and '-q/--quality' options require 'ffprobe' (FFmpeg) to be installed in System PATH.\n\n"
            "How to fix:\n"
            "  Install FFmpeg and ensure 'ffprobe' is available in your PATH.\n"
            "  Guide: docs/documentation.md#ffmpeg-setup"
        )

    if getattr(args, "provider", None):
        config.AI_PROVIDER = args.provider

    if runtime.ai_fallback_enabled:
        from src.ai_api import get_available_providers

        available_ai = get_available_providers()

        if not available_ai:
            parser.error(
                "Missing configuration: The '--ai' (-a) and '--learn' (-L) options require an AI Cloud Provider API key to be configured (Gemini, Groq, OpenRouter, or Cloudflare).\n\n"
                "How to fix:\n"
                "  1. Run the configuration wizard:\n"
                "     media-organizer configure\n"
                "  2. Or set the key via CLI:\n"
                '     media-organizer config --set api.gemini_api_key "<your_gemini_key>"\n'
                '     media-organizer config --set api.groq_api_key "<your_groq_key>"\n'
                "  3. Or use environment variables:\n"
                '     export GEMINI_API_KEY="<your_gemini_key>"\n'
                '     export GROQ_API_KEY="<your_groq_key>"'
            )

        if args.provider and args.provider != "auto" and args.provider not in available_ai:
            parser.error(
                f"Missing configuration: AI provider '{args.provider}' requested via '--provider', but its credentials are not configured."
            )

    return args


def handle_config_command(args):
    from src.config import config

    if getattr(args, "gui", None) is True:
        config.run_gui()
        return

    if getattr(args, "subcommand", None) == "configure":
        section = None
        if getattr(args, "paths", None) is True:
            section = "paths"
        elif getattr(args, "ai", None) is True:
            section = "ai"
        elif getattr(args, "email", None) is True:
            section = "email"
        elif getattr(args, "options", None) is True:
            section = "options"
        elif getattr(args, "video", None) is True:
            section = "video"

        config.run_wizard(section=section, interactive_menu=False)
        return

    if getattr(args, "path", False):
        rich_print_log(f"\nActive configuration file: [green]{config.config_path}[/green]\n")
        return

    if getattr(args, "get", None):
        key = args.get.strip()
        val, source = config.get_with_source(key)
        if val is None:
            rich_print_log(f"[yellow]'{key}' is not set.[/yellow]")
        else:
            rich_print_log(f"[bold green]{key}[/bold green] = {val} [cyan]({source})[/cyan]")
        return

    if getattr(args, "set", None):
        key, val = args.set
        try:
            val_clean = val.strip()
            if key.startswith("paths.") and not os.path.isdir(val_clean):
                rich_print_log(
                    f"\n[bold red]Error:[/bold red] The directory '[white]{val_clean}[/white]' does not exist on disk or is not reachable."
                )

            if key in ("options.resolution", "options.quality"):
                val_bool = val_clean.lower() in ("true", "1", "yes", "y", "t")
                if val_bool and not shutil.which("ffprobe"):
                    rich_print_log(
                        "\n[bold red]Error:[/bold red] 'ffprobe' (FFmpeg) is not installed or not in System PATH.\nResolution and quality tags will fail to be detected until FFmpeg is installed."
                    )

            if key in ("options.notify_on_success", "options.notify_on_error"):
                val_bool = val_clean.lower() in ("true", "1", "yes", "y", "t")
                cur_mail = config.MAIL
                cur_pswd = config.MAIL_PSWD
                if val_bool and not (cur_mail and cur_pswd):
                    rich_print_log(
                        "\n[bold yellow]Notice:[/bold yellow] Email notifications are enabled, but Gmail credentials ('mail' and 'mail_pswd') are not yet configured in [mail]."
                    )

            config.set(key, val)
            rich_print_log(
                f"\nSet [bold green]{key}[/bold green] = [yellow]{val}[/yellow] in [green]{config.config_path}[/green]\n"
            )
        except ValueError as e:
            rich_print_log(f"\n[bold red]Configuration error:[/bold red] {e}\n")
            sys.exit(1)
        return

    if getattr(args, "unset", None):
        key = args.unset.strip()
        try:
            if config.unset(key):
                rich_print_log(f"\nUnset [bold green]{key}[/bold green] from [green]{config.config_path}[/green]\n")
            else:
                rich_print_log(f"\n[yellow]{key}[/yellow] was not found in [green]{config.config_path}[/green]\n")
        except ValueError as e:
            rich_print_log(f"\n[bold red]Configuration error:[/bold red] {e}\n")
            sys.exit(1)
        return

    # Default action for `config`: --list or display table
    display_config_table(show_secrets=getattr(args, "show_secrets", False))


def display_config_table(show_secrets=False):
    from src.config import config
    from rich.table import Table

    items = config.list_all(show_secrets=show_secrets)
    table = Table(title="[bold cyan]media-organizer Configuration[/bold cyan]", title_justify="left")
    table.add_column("Section", style="magenta", no_wrap=True)
    table.add_column("Setting", style="white", no_wrap=True)
    table.add_column("Value", style="green")
    table.add_column("Source", style="yellow")

    for item in items:
        source_color = {
            "ENV": "[bold cyan]ENV[/bold cyan]",
            "INI": "[bold green]INI[/bold green]",
            "LEGACY": "[yellow]config.py[/yellow]",
            "DEFAULT": "[dim]DEFAULT[/dim]",
        }.get(item["source"], item["source"])

        table.add_row(item["section"], item["key"], str(item["display_value"]), source_color)

    rich_print_log()
    rich_print_log(table)
    rich_print_log(f"Active INI file: [yellow]{config.config_path}[/yellow]")
    if not show_secrets:
        rich_print_log("Secrets masked. Use [cyan]--show-secrets[/cyan] to reveal.\n")


def get_log_dir() -> Path:
    """Resolve the log directory: current working directory when frozen, otherwise project root."""
    if getattr(sys, "frozen", False):
        try:
            cwd_log = Path.cwd() / "log"
            cwd_log.mkdir(parents=True, exist_ok=True)
            return cwd_log
        except (PermissionError, OSError):
            exe_log = Path(sys.executable).resolve().parent / "log"
            exe_log.mkdir(parents=True, exist_ok=True)
            return exe_log
    log_dir = Path(__file__).resolve().parent.parent / "log"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def cleanup_old_logs(log_dir: Path | None = None, max_age_days: int = 14) -> list[Path]:
    """Delete log files in log_dir older than max_age_days (default: 14 days / 2 weeks)."""
    if log_dir is None:
        log_dir = get_log_dir()
    if not log_dir.is_dir():
        return []

    deleted_files: list[Path] = []
    cutoff_datetime = datetime.now() - timedelta(days=max_age_days)
    cutoff_date = cutoff_datetime.date()
    cutoff_timestamp = cutoff_datetime.timestamp()

    try:
        entries = list(log_dir.iterdir())
    except OSError:
        return []

    for item in entries:
        try:
            if not item.is_file():
                continue
        except OSError:
            continue

        if item.suffix.lower() not in (".txt", ".log"):
            continue

        is_old = False
        stem_parts = item.stem.split("_")[0]
        try:
            file_date = datetime.strptime(stem_parts, "%Y-%m-%d").date()
            if file_date < cutoff_date:
                is_old = True
        except ValueError:
            try:
                if item.stat().st_mtime < cutoff_timestamp:
                    is_old = True
            except OSError:
                pass

        if is_old:
            try:
                item.unlink(missing_ok=True)
                deleted_files.append(item)
            except OSError:
                pass

    return deleted_files


def check_log_dir_permissions(log_dir: Path) -> tuple[bool, str]:
    """Verify read and write permissions on log directory using a probe file."""
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        probe_file = log_dir / f".log_probe_{uuid.uuid4().hex}"
        with open(probe_file, "w", encoding="utf-8") as f:
            f.write("probe")
        probe_file.unlink(missing_ok=True)
        return (True, "")
    except OSError as e:
        return (False, str(e))


def _strip_emoji(text: str) -> str:
    """Removes Unicode emoji characters from *text* (for daemon/Docker log output)."""
    # Remove characters in emoji ranges
    emoji_pattern = re.compile(
        "["
        "\U0001f300-\U0001f9ff"  # misc symbols and pictographs
        "\U0001fa00-\U0001fa6f"
        "\U0001fa70-\U0001faff"
        "\U00002702-\U000027b0"
        "\U000024c2-\U0001f251"
        "\u2600-\u26ff"
        "\u2700-\u27bf"
        "\ufe00-\ufe0f"  # variation selectors
        "]+",
        flags=re.UNICODE,
    )
    return emoji_pattern.sub("", text).strip()


def format_daemon_log(level: str, message: str, colorize: bool = False) -> str:
    """Formats a message for daemon mode: strictly single-line with timestamp and level.

    Docker/daemon log lines are stripped of emoji characters so they appear
    cleanly in structured log aggregators (e.g. Loki, Splunk, CloudWatch).
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    clean_msg = re.sub(r"\s+", " ", str(message)).strip()
    clean_msg = _strip_emoji(clean_msg)
    raw = f"{timestamp} [{level}] {clean_msg}"
    if colorize:
        if level == "ERROR":
            return f"\033[31m{raw}\033[0m"
        if level == "SUCCESS":
            return f"\033[32m{raw}\033[0m"
    return raw


def _emit_daemon_log(level: str, message: str, stream=None):
    """Outputs a single-line formatted log in daemon mode."""
    global _last_log_cleanup_date
    if stream is None:
        stream = sys.stderr if level == "ERROR" else sys.stdout

    line = format_daemon_log(level, message, colorize=False)
    should_write_file = runtime.log_enabled or runtime.log_mode in ("file", "both")
    should_print_console = (not should_write_file) or runtime.log_mode == "both"

    if should_write_file:
        try:
            log_dir = get_log_dir()
            today = datetime.now().strftime("%Y-%m-%d")
            if _last_log_cleanup_date != today:
                cleanup_old_logs(log_dir, max_age_days=14)
                _last_log_cleanup_date = today
            path = log_dir / f"{today}.txt"
            with open(path, "a", encoding="utf-8") as f:
                f.write(f"{line}\n")
        except OSError:
            pass

    if should_print_console:
        is_docker = config.is_docker_environment()
        console_line = format_daemon_log(level, message, colorize=(is_docker or False))
        stream.write(f"{console_line}\n")
        stream.flush()


def log_info(message: str) -> None:
    """Logs an operational/informational message (single line to stdout in daemon mode)."""
    if runtime.daemon_enabled:
        _emit_daemon_log("INFO", message, stream=sys.stdout)
    else:
        print_log(message)


def log_error(message: str) -> None:
    """Logs an error message (single line to stderr in daemon mode)."""
    if runtime.daemon_enabled:
        _emit_daemon_log("ERROR", message, stream=sys.stderr)
    else:
        print_log(message)


def log_success(original_name: str, new_name: str, destination_path: str) -> None:
    """Logs a successful media rename and move operation (single line to stdout in daemon mode)."""
    msg = f"'{original_name}' -> '{new_name}' (Destination: {destination_path})"
    if runtime.daemon_enabled:
        _emit_daemon_log("SUCCESS", msg, stream=sys.stdout)
    else:
        print_log(f"✅ {msg}")


def print_log(message, *, level: str | None = None) -> None:
    """Logs *message* to file and/or console depending on runtime configuration.

    B14 fix: accepts an optional explicit *level* parameter instead of relying
    on heuristic emoji/keyword scanning to determine severity in daemon mode.
    """
    global _last_log_cleanup_date
    if runtime.daemon_enabled:
        msg_str = str(message).strip()
        if level is not None:
            emit_level = level.upper()
        elif msg_str.startswith("[ERROR]") or "Error:" in msg_str:
            emit_level = "ERROR"
            msg_str = re.sub(r"^(?:\[ERROR\]\s*)", "", msg_str).strip()
        elif msg_str.startswith("[SUCCESS]"):
            emit_level = "SUCCESS"
            msg_str = re.sub(r"^\[SUCCESS\]\s*", "", msg_str).strip()
        elif msg_str.startswith("[INFO]"):
            emit_level = "INFO"
            msg_str = re.sub(r"^\[INFO\]\s*", "", msg_str).strip()
        else:
            emit_level = "INFO"
        _emit_daemon_log(emit_level, msg_str)
        return

    should_write_file = runtime.log_enabled or runtime.log_mode in ("file", "both")
    should_print_console = (not should_write_file) or runtime.log_mode == "both"

    if should_write_file:
        try:
            log_dir = get_log_dir()
            today = datetime.now().strftime("%Y-%m-%d")
            if _last_log_cleanup_date != today:
                cleanup_old_logs(log_dir, max_age_days=14)
                _last_log_cleanup_date = today
            path = log_dir / f"{today}.txt"
            hour = datetime.now().strftime("%H:%M:%S")
            with open(path, "a", encoding="utf-8") as f:
                f.write(f"[{hour}] {str(message)}\n")
        except OSError:
            pass

    if should_print_console:
        print(message)


def print_error(message: str, logs) -> str:
    """Formats an error message string (does NOT print — see B2 fix notes)."""
    if runtime.verbose_enabled:
        return f"\n {message} \n\n  Error logs: {logs} \n"
    else:
        return f"\n {message} \n"


def rich_print_log(*args, **kwargs) -> None:
    """Prints rich-formatted content to console and/or log file."""
    if runtime.daemon_enabled:
        console_capture = Console(force_terminal=False, no_color=True, width=150)
        with console_capture.capture() as capture:
            console_capture.print(*args, **kwargs)
        raw_text = " ".join(capture.get().strip().splitlines())
        if raw_text:
            _emit_daemon_log("INFO", raw_text)
        return

    should_write_file = runtime.log_enabled or runtime.log_mode in ("file", "both")
    should_print_console = (not should_write_file) or runtime.log_mode == "both"

    if should_write_file:
        console_capture = Console(force_terminal=False, no_color=True, width=150)
        with console_capture.capture() as capture:
            console_capture.print(*args, **kwargs)

        raw_text = capture.get()
        if raw_text.strip():
            saved_mode = runtime.log_mode
            try:
                if runtime.log_mode == "both":
                    runtime.log_mode = "file"
                print_log("\n" + raw_text.rstrip("\n"))
            finally:
                runtime.log_mode = saved_mode

    if should_print_console:
        console = Console()
        console.print(*args, **kwargs)


def display_corrected_filenames(clean_data_table) -> None:
    if clean_data_table.empty or "Media" not in clean_data_table:
        rich_print_log("[yellow]No media files detected.[/yellow]")
        return

    movies_df = clean_data_table[clean_data_table["Media"] == "movie"]
    tv_shows_df = clean_data_table[clean_data_table["Media"] == "tv"]

    if tv_shows_df.empty and movies_df.empty:
        rich_print_log("[yellow]No media files detected.[/yellow]")
        return

    # --- MOVIES Table ---
    if not movies_df.empty:
        rich_print_log()
        table_movies = Table(title="[bold magenta]Movies[/bold magenta]", title_justify="left")

        table_movies.add_column("Original", style="white", no_wrap=True, max_width=60, overflow="ellipsis")
        table_movies.add_column("Corrected", style="green", no_wrap=True, max_width=60, overflow="ellipsis")

        for _, row in movies_df.iterrows():
            if row["Original"] != row["Corrected"]:
                table_movies.add_row(str(row["Original"]), str(row["Corrected"]))

        rich_print_log(table_movies)

    # --- TV Shows table ---
    if not tv_shows_df.empty:
        rich_print_log()
        table_tv = Table(title="[bold blue]TV Shows[/bold blue]", title_justify="left")

        table_tv.add_column("Original", style="white", no_wrap=True, max_width=60, overflow="ellipsis")
        table_tv.add_column("Season", justify="center", style="yellow")
        table_tv.add_column("Episode", justify="center", style="yellow")
        table_tv.add_column("Corrected", style="green", no_wrap=True, max_width=60, overflow="ellipsis")

        for _, row in tv_shows_df.iterrows():
            orig = str(row.get("Original", ""))
            corr = str(row.get("Corrected", ""))
            if orig != corr:
                table_tv.add_row(orig, str(row.get("Season", "")), str(row.get("Episode", "")), corr)

        rich_print_log(table_tv)
        rich_print_log()


def display_sorted_files(paths) -> None:
    if not paths:
        rich_print_log("[yellow]No sorted files to display.[/yellow]")
        return

    movie_dir_str = config.MOVIES_FOLDER
    tv_dir_str = config.TV_SHOWS_FOLDER
    movie_dir = Path(movie_dir_str) if movie_dir_str else None
    tv_dir = Path(tv_dir_str) if tv_dir_str else None

    movies_data = []
    tv_shows_data = []

    for chemin_ancien, chemin_nouveau in paths:
        p_new = Path(chemin_nouveau)
        old_name = str(Path(chemin_ancien).name)

        if movie_dir and p_new.is_relative_to(movie_dir):
            short_path = Path(movie_dir.name) / p_new.relative_to(movie_dir)
            movies_data.append((old_name, str(short_path)))

        elif tv_dir and p_new.is_relative_to(tv_dir):
            short_path = Path(tv_dir.name) / p_new.relative_to(tv_dir)
            tv_shows_data.append((old_name, str(short_path)))
        else:
            movies_data.append((old_name, str(p_new.name)))

    # movies
    if movies_data:
        rich_print_log()
        table_movies = Table(title="[bold magenta]Sorted Movies[/bold magenta]", title_justify="left")

        table_movies.add_column("Old", style="white", no_wrap=True, max_width=40, overflow="ellipsis")
        table_movies.add_column("New Path", style="green", no_wrap=True, max_width=70, overflow="ellipsis")

        for old, new in movies_data:
            table_movies.add_row(old, new)

        rich_print_log(table_movies)

    # tv shows
    if tv_shows_data:
        rich_print_log()
        table_tv = Table(title="[bold blue]Sorted TV Shows[/bold blue]", title_justify="left")

        table_tv.add_column("Old", style="white", no_wrap=True, max_width=40, overflow="ellipsis")
        table_tv.add_column("New Path", style="green", no_wrap=True, max_width=70, overflow="ellipsis")

        for old, new in tv_shows_data:
            table_tv.add_row(old, new)

        rich_print_log(table_tv)
        rich_print_log()


def display_skipped_filenames(failed_files) -> None:
    if not failed_files:
        return

    if runtime.daemon_enabled:
        for fail in failed_files:
            orig = str(fail.get("Original", "Unknown"))
            reason = str(fail.get("Reason", "No reason provided"))
            log_error(f"Skipped file '{orig}': {reason}")
        return

    rich_print_log()

    table_skipped = Table(title="[bold red]Skipped Files[/bold red]", title_justify="left", border_style="red")

    table_skipped.add_column("Original Filename", style="white", no_wrap=True, max_width=100, overflow="ellipsis")
    table_skipped.add_column("Reason for Failure", style="yellow")

    for fail in failed_files:
        table_skipped.add_row(str(fail.get("Original", "Unknown")), str(fail.get("Reason", "No reason provided")))

    rich_print_log(table_skipped)
    rich_print_log()


def user_confirmation(message: str) -> None:
    """Prompts user for confirmation unless bypass mode is active."""
    if not runtime.bypass_enabled:
        console = Console()
        try:
            console.print(f"\n  Press [green][Enter][/green] to {message}, or [red][Ctrl+C][/red] to cancel...", end="")
            input()
        except KeyboardInterrupt:
            console.print("\n\n[red] Operation cancelled by the user. [/red]")
            sys.exit(1)


_RUNTIME_ATTR_MAP = {
    "LOG_ENABLED": "log_enabled",
    "LOG_MODE": "log_mode",
    "MAIL_ENABLED": "mail_enabled",
    "AI_FALLBACK_ENABLED": "ai_fallback_enabled",
    "LEARN_ENABLED": "learn_enabled",
    "BYPASS_ENABLED": "bypass_enabled",
    "VERBOSE_ENABLED": "verbose_enabled",
    "SIMULATE_ENABLED": "simulate_enabled",
    "RESOLUTION_ENABLED": "resolution_enabled",
    "QUALITY_ENABLED": "quality_enabled",
    "NOTIFY_SUCCESS_ENABLED": "notify_success_enabled",
    "NOTIFY_ERROR_ENABLED": "notify_error_enabled",
    "NOTIFY_TAG_ENABLED": "notify_tag_enabled",
    "DAEMON_ENABLED": "daemon_enabled",
    "POLLING_INTERVAL": "polling_interval",
}

_CONFIG_ATTRS = {
    "MOVIES_FOLDER",
    "TV_SHOWS_FOLDER",
    "GEMINI_API_KEY",
    "MAIL",
    "MAIL_PSWD",
}


class _UIModule(types.ModuleType):
    def __getattribute__(self, name: str):
        if name in _RUNTIME_ATTR_MAP:
            return getattr(runtime, _RUNTIME_ATTR_MAP[name])
        if name in _CONFIG_ATTRS:
            return getattr(config, name, None)
        return super().__getattribute__(name)

    def __setattr__(self, name: str, value):
        if name in _RUNTIME_ATTR_MAP:
            setattr(runtime, _RUNTIME_ATTR_MAP[name], value)
        elif name in _CONFIG_ATTRS:
            setattr(config, name, value)
        super().__setattr__(name, value)


sys.modules[__name__].__class__ = _UIModule
