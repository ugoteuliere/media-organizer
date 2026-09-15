import sys
import os
import shutil

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError, OSError):
        pass

from rich.console import Console
from rich.table import Table
from datetime import datetime, timedelta
from typing import Optional, List, Tuple
from pathlib import Path
import argparse
import uuid

from src.config import config
MOVIES_FOLDER = getattr(config, 'MOVIES_FOLDER', None)
TV_SHOWS_FOLDER = getattr(config, 'TV_SHOWS_FOLDER', None)
GEMINI_API_KEY = getattr(config, 'GEMINI_API_KEY', None)
MAIL = getattr(config, 'MAIL', None)
MAIL_PSWD = getattr(config, 'MAIL_PSWD', None)

LOG_ENABLED = False
LOG_MODE = "console"
MAIL_ENABLED = False
AI_FALLBACK_ENABLED = False
LEARN_ENABLED = False
BYPASS_ENABLED = False
VERBOSE_ENABLED = False
SIMULATE_ENABLED = False
RESOLUTION_ENABLED = False
QUALITY_ENABLED = False
NOTIFY_SUCCESS_ENABLED = False
NOTIFY_ERROR_ENABLED = False
NOTIFY_TAG_ENABLED = False
DAEMON_ENABLED = False
POLLING_INTERVAL = 15
_last_log_cleanup_date = None


def is_double_clicked() -> bool:
    """Detects if application was launched by double-clicking in Windows Explorer (single process attached to console)."""
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
    global LOG_ENABLED, LOG_MODE, MAIL_ENABLED, AI_FALLBACK_ENABLED, LEARN_ENABLED, BYPASS_ENABLED, VERBOSE_ENABLED, SIMULATE_ENABLED
    global RESOLUTION_ENABLED, QUALITY_ENABLED, NOTIFY_SUCCESS_ENABLED, NOTIFY_ERROR_ENABLED, NOTIFY_TAG_ENABLED
    global DAEMON_ENABLED, POLLING_INTERVAL

    description_text = (
        "🎬 Media Organizer & Renamer\n"
        "Automatically parses, renames, and sorts messy video files using TMDB and Multi-Cloud AI (Gemini, Groq, OpenRouter, Cloudflare)."
    )
    
    epilog_text = (
        "Examples:\n"
        "  python main.py                    (Default: Renames AND moves files)\n"
        "  python main.py -r                 (Only renames the files in place)\n"
        "  python main.py -s                 (Simulation mode: preview changes without modifying disk)\n"
        "  python main.py -d                 (Daemon mode: continuous background polling)\n"
        "  python main.py -d --interval 10   (Daemon mode with 10-minute polling)\n"
        "  python main.py -L                 (Enables AI keyword learning)\n"
        "  python main.py -t                 (Sends email notification when an AI keyword is learned)\n"
        "  python main.py -R -q              (Appends resolution & quality tags)\n"
        "  python main.py --notify-success   (Sends email notification on success)\n"
        "  python main.py configure          (Interactive configuration wizard)\n"
        "  python main.py config --list      (List all configured settings)\n"
        "  python main.py config --set paths.movies_folder \"D:/Movies\"\n\n"
        "Documentation & Updates: https://github.com/ugoteuliere/rename"
    )

    parser = argparse.ArgumentParser(
        description=description_text,
        epilog=epilog_text,
        formatter_class=argparse.RawTextHelpFormatter
    )

    modes_group = parser.add_argument_group("Operational Modes")
    modes_group.add_argument("-g", "--gui", action="store_true",
                             help="Launch modern graphical configuration interface (GUI).")
    modes_group.add_argument("-r", "--only-rename", "--only_rename", action="store_true", dest="only_rename",
                             help="Renames files in place without moving them to Movie/TV Show folders.")
    modes_group.add_argument("-s", "--simulate", action="store_true",
                             help="Simulates renaming and sorting without modifying any files on disk.")

    proc_group = parser.add_argument_group("Processing Options")
    proc_group.add_argument("-R", "--resolution", action="store_true",
                            help="Detect and append video resolution tags (e.g. [1080p], [4K]).")
    proc_group.add_argument("-q", "--quality", action="store_true",
                            help="Detect and append video encoding/quality tags (e.g. [FullHD BluRay]).")
    proc_group.add_argument("-a", "--ai", action="store_true", 
                            help="Enables the Gemini AI fallback to intelligently parse and correct highly obfuscated filenames.")
    proc_group.add_argument("-L", "--learn", action="store_true",
                            help="Enable AI keyword learning to discover and save missing tags from Gemini.")
    proc_group.add_argument("--provider", choices=["auto", "gemini", "groq", "openrouter", "cloudflare"], default=None,
                            help="Specify the AI cloud provider to use for fallback parsing (auto, gemini, groq, openrouter, cloudflare).")
    proc_group.add_argument("--path", type=str, default=None,
                            help="Target a specific folder as source (overrides downloads folder, or renames in-place with -r).")

    auto_group = parser.add_argument_group("Automation & Logging")
    auto_group.add_argument("-d", "--daemon", action="store_true", dest="daemon",
                            help="Run continuously in background daemon mode with periodic polling.")
    auto_group.add_argument("--once", "--no-daemon", action="store_true", dest="no_daemon",
                            help="Run once and exit immediately instead of running continuously as a daemon.")
    auto_group.add_argument("--interval", type=int, default=None,
                            help="Polling interval in minutes for daemon mode (overrides config).")
    auto_group.add_argument("-b", "--bypass", action="store_true", 
                            help="Bypass user confirmation prompts before renaming or moving files.")
    auto_group.add_argument("-l", "--log", action="store_true", 
                            help="Suppresses terminal output and writes all console messages to a dedicated log file instead.")
    auto_group.add_argument("-v", "--verbose", action="store_true", 
                            help="Display detailed error logs after error messages.")
    auto_group.add_argument("--notify-success", action="store_true",
                            help="Send an email notification on successful media processing.")
    auto_group.add_argument("--notify-error", action="store_true",
                            help="Send an email notification when a processing error occurs.")
    auto_group.add_argument("-t", "--notify-tag", action="store_true",
                            help="Send an email notification when a new AI keyword tag is discovered and saved.")

    # Subparsers for config commands
    subparsers = parser.add_subparsers(dest="subcommand")

    config_parser = subparsers.add_parser(
        "config",
        help="View and manage configuration settings (INI file & environment variables).",
        formatter_class=argparse.RawTextHelpFormatter
    )
    config_parser.add_argument("-g", "--gui", action="store_true", help="Launch modern graphical configuration interface (GUI).")
    config_parser.add_argument("-l", "--list", action="store_true", help="List all configured settings and their sources.")
    config_parser.add_argument("--show-secrets", action="store_true", help="Display sensitive values (API keys, passwords) without masking.")
    config_parser.add_argument("--get", metavar="KEY", help="Get the value for a specific setting (e.g. paths.movies_folder, api.tmdb_api_key).")
    config_parser.add_argument("--set", nargs=2, metavar=("KEY", "VALUE"), help="Set a configuration setting (e.g. paths.movies_folder 'D:/Movies').")
    config_parser.add_argument("--unset", metavar="KEY", help="Remove a configuration setting from the INI file.")
    config_parser.add_argument("--path", action="store_true", help="Display the path of the active configuration file.")

    configure_parser = subparsers.add_parser(
        "configure",
        help="Launch interactive configuration wizard or GUI.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    configure_parser.add_argument("-g", "--gui", action="store_true", help="Launch modern graphical configuration tool (GUI).")
    configure_parser.add_argument("--paths", action="store_true", help="Configure storage and library folders directly.")
    configure_parser.add_argument("--ai", action="store_true", help="Configure API keys and Cloud AI providers directly.")
    configure_parser.add_argument("--email", action="store_true", help="Configure email alerts and SMTP credentials directly.")
    configure_parser.add_argument("--options", action="store_true", help="Configure runtime and automation options directly.")
    configure_parser.add_argument("--video", action="store_true", help="Configure video stream options directly.")
    configure_parser.add_argument("--full", action="store_true", help="Run full step-by-step setup wizard without menu.")

    args = parser.parse_args()

    # If running a configuration subcommand, return immediately
    if getattr(args, "subcommand", None) in ("config", "configure"):
        return args

    # Path check: must exist if specified
    if args.path:
        if not os.path.isdir(args.path):
            parser.error(
                f"Invalid path: The directory '{args.path}' does not exist or is not a valid folder."
            )

    current_mail = MAIL or getattr(config, 'MAIL', None)
    current_pswd = MAIL_PSWD or getattr(config, 'MAIL_PSWD', None)
    MAIL_ENABLED = bool(current_mail and current_pswd)

    is_daemon = bool(
        (getattr(args, 'daemon', False) or (args.interval is not None) or getattr(config, 'DAEMON', False))
        and not getattr(args, 'no_daemon', False)
        and not getattr(args, 'simulate', False)
    )
    DAEMON_ENABLED = is_daemon
    if args.interval is not None:
        if args.interval < 1:
            parser.error(
                "Invalid interval: The '--interval' option requires a positive integer of at least 1 minute."
            )
        POLLING_INTERVAL = args.interval
    else:
        POLLING_INTERVAL = getattr(config, 'POLLING_INTERVAL', 15)

    LEARN_ENABLED = bool(args.learn or getattr(config, 'LEARN', False))
    AI_FALLBACK_ENABLED = bool(args.ai or getattr(config, 'AI', False) or LEARN_ENABLED)
    BYPASS_ENABLED = bool(args.bypass or getattr(config, 'BYPASS', False) or DAEMON_ENABLED)
    is_docker = os.environ.get("DOCKER_CONTAINER") == "1" or os.path.exists("/.dockerenv")
    wants_log = bool(args.log or getattr(config, 'LOG', False))
    if wants_log:
        log_dir = get_log_dir()
        has_perm, reason = check_log_dir_permissions(log_dir)
        if has_perm:
            LOG_MODE = "both" if is_docker else "file"
            LOG_ENABLED = True
        else:
            sys.stderr.write(
                f"\n⚠️ Warning: Log directory '{log_dir}' is not writable ({reason}).\n"
                "💡 Falling back to console logging (stdout/stderr) only.\n\n"
            )
            LOG_MODE = "console"
            LOG_ENABLED = False
    else:
        LOG_MODE = "console"
        LOG_ENABLED = False
    VERBOSE_ENABLED = bool(args.verbose or getattr(config, 'VERBOSE', False))
    SIMULATE_ENABLED = bool(args.simulate)
    RESOLUTION_ENABLED = bool(args.resolution or getattr(config, 'RESOLUTION', False))
    QUALITY_ENABLED = bool(args.quality or getattr(config, 'QUALITY', False))
    NOTIFY_SUCCESS_ENABLED = bool(args.notify_success)
    NOTIFY_ERROR_ENABLED = bool(args.notify_error)
    NOTIFY_TAG_ENABLED = bool(args.notify_tag)

    from src import utils as utils_module
    utils_module.RESOLUTION = RESOLUTION_ENABLED
    utils_module.QUALITY = QUALITY_ENABLED

    if (args.notify_success or args.notify_error or args.notify_tag) and not MAIL_ENABLED:
        parser.error(
            "❌ Missing configuration: Email notification flags require 'mail' and 'mail_pswd' to be configured in [mail].\n\n"
            "💡 How to fix:\n"
            "  1. Run the configuration wizard:\n"
            "     python main.py configure\n"
            "  2. Or set credentials via CLI:\n"
            "     python main.py config --set mail.mail \"<your_email@gmail.com>\"\n"
            "     python main.py config --set mail.mail_pswd \"<your_16_char_app_password>\""
        )

    if (args.resolution or args.quality) and not shutil.which("ffprobe"):
        parser.error(
            "❌ Missing dependency: The '-R/--resolution' and '-q/--quality' options require 'ffprobe' (FFmpeg) to be installed in System PATH.\n\n"
            "💡 How to fix:\n"
            "  Install FFmpeg and ensure 'ffprobe' is available in your PATH.\n"
            "  Guide: docs/documentation.md#ffmpeg-setup"
        )

    if getattr(args, "provider", None):
        config.AI_PROVIDER = args.provider

    if AI_FALLBACK_ENABLED:
        available_ai = []
        current_gemini = GEMINI_API_KEY or getattr(config, 'GEMINI_API_KEY', None)
        current_groq = getattr(config, 'GROQ_API_KEY', None)
        current_openrouter = getattr(config, 'OPENROUTER_API_KEY', None)
        current_cf_tok = getattr(config, 'CLOUDFLARE_API_TOKEN', None)
        current_cf_acc = getattr(config, 'CLOUDFLARE_ACCOUNT_ID', None)

        if current_gemini:
            available_ai.append("gemini")
        if current_groq:
            available_ai.append("groq")
        if current_openrouter:
            available_ai.append("openrouter")
        if current_cf_tok and current_cf_acc:
            available_ai.append("cloudflare")

        if not available_ai:
            parser.error(
                "❌ Missing configuration: The '--ai' (-a) and '--learn' (-L) options require an AI Cloud Provider API key to be configured (Gemini, Groq, OpenRouter, or Cloudflare).\n\n"
                "💡 How to fix:\n"
                "  1. Run the configuration wizard:\n"
                "     python main.py configure\n"
                "  2. Or set the key via CLI:\n"
                "     python main.py config --set api.gemini_api_key \"<your_gemini_key>\"\n"
                "     python main.py config --set api.groq_api_key \"<your_groq_key>\"\n"
                "  3. Or use environment variables:\n"
                "     export GEMINI_API_KEY=\"<your_gemini_key>\"\n"
                "     export GROQ_API_KEY=\"<your_groq_key>\""
            )

        if args.provider and args.provider != "auto" and args.provider not in available_ai:
            parser.error(
                f"❌ Missing configuration: AI provider '{args.provider}' requested via '--provider', but its credentials are not configured."
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
        rich_print_log(f"\n📂 Active configuration file: [green]{config.config_path}[/green]\n")
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
                rich_print_log(f"\n❌ [bold red]Error:[/bold red] The directory '[white]{val_clean}[/white]' does not exist on disk or is not reachable.")

            if key in ("options.resolution", "options.quality"):
                val_bool = val_clean.lower() in ("true", "1", "yes", "y", "t")
                if val_bool and not shutil.which("ffprobe"):
                    rich_print_log("\n❌ [bold red]Error:[/bold red] 'ffprobe' (FFmpeg) is not installed or not in System PATH.\nResolution and quality tags will fail to be detected until FFmpeg is installed.")

            if key in ("options.notify_on_success", "options.notify_on_error"):
                val_bool = val_clean.lower() in ("true", "1", "yes", "y", "t")
                cur_mail = getattr(config, 'MAIL', None)
                cur_pswd = getattr(config, 'MAIL_PSWD', None)
                if val_bool and not (cur_mail and cur_pswd):
                    rich_print_log("\n⚠️  [bold yellow]Notice:[/bold yellow] Email notifications are enabled, but Gmail credentials ('mail' and 'mail_pswd') are not yet configured in [mail].")

            config.set(key, val)
            rich_print_log(f"\n✅ Set [bold green]{key}[/bold green] = [yellow]{val}[/yellow] in [green]{config.config_path}[/green]\n")
        except ValueError as e:
            rich_print_log(f"\n❌ [bold red]Configuration error:[/bold red] {e}\n")
            sys.exit(1)
        return

    if getattr(args, "unset", None):
        key = args.unset.strip()
        try:
            if config.unset(key):
                rich_print_log(f"\n✅ Unset [bold green]{key}[/bold green] from [green]{config.config_path}[/green]\n")
            else:
                rich_print_log(f"\n⚠️  [yellow]{key}[/yellow] was not found in [green]{config.config_path}[/green]\n")
        except ValueError as e:
            rich_print_log(f"\n❌ [bold red]Configuration error:[/bold red] {e}\n")
            sys.exit(1)
        return

    # Default action for `config`: --list or display table
    display_config_table(show_secrets=getattr(args, "show_secrets", False))

def display_config_table(show_secrets=False):
    from src.config import config
    from rich.table import Table

    items = config.list_all(show_secrets=show_secrets)
    table = Table(title="⚙️  [bold cyan]Media Organizer & Renamer Configuration[/bold cyan]", title_justify="left")
    table.add_column("Section", style="magenta", no_wrap=True)
    table.add_column("Setting", style="white", no_wrap=True)
    table.add_column("Value", style="green")
    table.add_column("Source", style="yellow")

    for item in items:
        source_color = {
            "ENV": "[bold cyan]ENV[/bold cyan]",
            "INI": "[bold green]INI[/bold green]",
            "LEGACY": "[yellow]config.py[/yellow]",
            "DEFAULT": "[dim]DEFAULT[/dim]"
        }.get(item["source"], item["source"])
        
        table.add_row(item["section"], item["key"], str(item["display_value"]), source_color)

    rich_print_log()
    rich_print_log(table)
    rich_print_log(f"📄 Active INI file: [yellow]{config.config_path}[/yellow]")
    if not show_secrets:
        rich_print_log("🔒 Secrets masked. Use [cyan]--show-secrets[/cyan] to reveal.\n")

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

def cleanup_old_logs(log_dir: Optional[Path] = None, max_age_days: int = 14) -> List[Path]:
    """Delete log files in log_dir older than max_age_days (default: 14 days / 2 weeks)."""
    if log_dir is None:
        log_dir = get_log_dir()
    if not log_dir.is_dir():
        return []

    deleted_files: List[Path] = []
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

def check_log_dir_permissions(log_dir: Path) -> Tuple[bool, str]:
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

def print_log(message):
    global _last_log_cleanup_date
    should_write_file = LOG_ENABLED or LOG_MODE in ("file", "both")
    should_print_console = (not should_write_file) or LOG_MODE == "both"

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

def print_error(message, logs):
    if VERBOSE_ENABLED:
        return f"\n {message} \n\n ⤷ Error logs: {logs} \n"
    else:
        return f"\n {message} \n"

def rich_print_log(*args, **kwargs):
    global LOG_MODE
    should_write_file = LOG_ENABLED or LOG_MODE in ("file", "both")
    should_print_console = (not should_write_file) or LOG_MODE == "both"

    if should_write_file:
        console_capture = Console(force_terminal=False, no_color=True, width=150)
        with console_capture.capture() as capture:
            console_capture.print(*args, **kwargs)
            
        raw_text = capture.get()
        if raw_text.strip():
            saved_mode = LOG_MODE
            try:
                if LOG_MODE == "both":
                    LOG_MODE = "file"
                print_log("\n" + raw_text.rstrip("\n"))
            finally:
                LOG_MODE = saved_mode

    if should_print_console:
        console = Console()
        console.print(*args, **kwargs)

def display_corrected_filenames(clean_data_table):
    if clean_data_table.empty or 'Media' not in clean_data_table:
        rich_print_log("[yellow]No media files detected.[/yellow]")
        return

    movies_df = clean_data_table[clean_data_table['Media'] == 'movie']
    tv_shows_df = clean_data_table[clean_data_table['Media'] == 'tv']

    if tv_shows_df.empty and movies_df.empty:
        rich_print_log("[yellow]No media files detected.[/yellow]")
        return

    # --- MOVIES Table ---
    if not movies_df.empty:
        rich_print_log()
        table_movies = Table(title="🍿 [bold magenta]Movies[/bold magenta]", title_justify="left")
        
        table_movies.add_column("Original", style="white", no_wrap=True, max_width=60, overflow="ellipsis")
        table_movies.add_column("Corrected", style="green", no_wrap=True, max_width=60, overflow="ellipsis")

        for _, row in movies_df.iterrows():
            if row['Original'] != row['Corrected']:
                table_movies.add_row(str(row['Original']), str(row['Corrected']))

        rich_print_log(table_movies)

    # --- TV Shows table ---
    if not tv_shows_df.empty:
        rich_print_log()
        table_tv = Table(title="📺 [bold blue]TV Shows[/bold blue]", title_justify="left")
        
        table_tv.add_column("Original", style="white", no_wrap=True, max_width=60, overflow="ellipsis")
        table_tv.add_column("Season", justify="center", style="yellow")
        table_tv.add_column("Épisode", justify="center", style="yellow")
        table_tv.add_column("Corrected", style="green", no_wrap=True, max_width=60, overflow="ellipsis")

        for _, row in tv_shows_df.iterrows():
            orig = str(row.get('Original', ''))
            corr = str(row.get('Corrected', ''))
            if orig != corr:
                table_tv.add_row(
                    orig,
                    str(row.get('Season', '')),
                    str(row.get('Episode', '')),
                    corr
                )

        rich_print_log(table_tv)
        rich_print_log()

def display_sorted_files(paths):
    if not paths:
        rich_print_log("[yellow]No sorted files to display.[/yellow]")
        return

    movie_dir = Path(MOVIES_FOLDER) if MOVIES_FOLDER else None
    tv_dir = Path(TV_SHOWS_FOLDER) if TV_SHOWS_FOLDER else None

    movies_data = []
    tv_shows_data = []

    # sort
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
        table_movies = Table(title="🍿 [bold magenta]Sorted Movies[/bold magenta]", title_justify="left")
        
        table_movies.add_column("Old", style="white", no_wrap=True, max_width=40, overflow="ellipsis")
        table_movies.add_column("New Path", style="green", no_wrap=True, max_width=70, overflow="ellipsis")

        for old, new in movies_data:
            table_movies.add_row(old, new)

        rich_print_log(table_movies)

    # tv shows
    if tv_shows_data:
        rich_print_log()
        table_tv = Table(title="📺 [bold blue]Sorted TV Shows[/bold blue]", title_justify="left")
        
        table_tv.add_column("Old", style="white", no_wrap=True, max_width=40, overflow="ellipsis")
        table_tv.add_column("New Path", style="green", no_wrap=True, max_width=70, overflow="ellipsis")

        for old, new in tv_shows_data:
            table_tv.add_row(old, new)

        rich_print_log(table_tv)
        rich_print_log()

def display_skipped_filenames(failed_files):
    if not failed_files:
        return

    rich_print_log()
    
    table_skipped = Table(
        title="❌ [bold red]Skipped Files[/bold red]", 
        title_justify="left",
        border_style="red"
    )
    
    table_skipped.add_column("Original Filename", style="white", no_wrap=True, max_width=100, overflow="ellipsis")
    table_skipped.add_column("Reason for Failure", style="yellow")

    for fail in failed_files:
        table_skipped.add_row(
            str(fail.get('Original', 'Unknown')), 
            str(fail.get('Reason', 'No reason provided'))
        )

    rich_print_log(table_skipped)
    rich_print_log()

def user_confirmation(message):
    if not(BYPASS_ENABLED):
        console = Console()
        try:
            console.print(f"\n➡️  Press [green][Entrer][/green] to {message}, or [red][Ctrl+C][/red] to cancel...", end="")
            input()
        except KeyboardInterrupt:
            console.print("\n\n[red] ❌ Operation cancelled by the user. [/red]")
            sys.exit(1)