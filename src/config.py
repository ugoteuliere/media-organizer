from __future__ import annotations
import os
import sys
import shutil
import tempfile
import configparser
from pathlib import Path

# Configuration Key Constants
KEY_MOVIES_FOLDER = "paths.movies_folder"
KEY_TV_SHOWS_FOLDER = "paths.tv_shows_folder"
KEY_INPUT_FOLDER = "paths.not_sorted_media_files_folder"

KEY_TMDB_API_KEY = "api.tmdb_api_key"
KEY_GEMINI_API_KEY = "api.gemini_api_key"
KEY_GROQ_API_KEY = "api.groq_api_key"
KEY_OPENROUTER_API_KEY = "api.openrouter_api_key"
KEY_CLOUDFLARE_API_TOKEN = "api.cloudflare_api_token"
KEY_CLOUDFLARE_ACCOUNT_ID = "api.cloudflare_account_id"

KEY_MAIL = "mail.mail"
KEY_MAIL_PSWD = "mail.mail_pswd"

KEY_BYPASS = "options.bypass"
KEY_AI = "options.ai"
KEY_LEARN = "options.learn"
KEY_LOG = "options.log"
KEY_VERBOSE = "options.verbose"
KEY_RESOLUTION = "options.resolution"
KEY_QUALITY = "options.quality"
KEY_NOTIFY_ON_SUCCESS = "options.notify_on_success"
KEY_NOTIFY_ON_ERROR = "options.notify_on_error"
KEY_NOTIFY_ON_TAG = "options.notify_on_tag"
KEY_DAEMON = "options.daemon"
KEY_POLLING_INTERVAL = "options.polling_interval"
KEY_AI_PROVIDER = "options.ai_provider"
KEY_TMDB_MIN_CONFIDENCE = "options.tmdb_min_confidence"
KEY_AI_MIN_CONFIDENCE = "options.ai_min_confidence"


class ConfigManager:
    SCHEMA = {
        "paths": ["movies_folder", "tv_shows_folder", "not_sorted_media_files_folder"],
        "api": [
            "tmdb_api_key",
            "gemini_api_key",
            "groq_api_key",
            "openrouter_api_key",
            "cloudflare_api_token",
            "cloudflare_account_id",
        ],
        "mail": ["mail", "mail_pswd"],
        "options": [
            "bypass",
            "ai",
            "log",
            "verbose",
            "resolution",
            "quality",
            "notify_on_success",
            "notify_on_error",
            "notify_on_tag",
            "daemon",
            "polling_interval",
            "learn",
            "ai_provider",
            "tmdb_min_confidence",
            "ai_min_confidence",
        ],
    }

    ENV_MAPPING = {
        KEY_MOVIES_FOLDER: "MOVIES_FOLDER",
        KEY_TV_SHOWS_FOLDER: "TV_SHOWS_FOLDER",
        KEY_INPUT_FOLDER: "INPUT_FOLDER",
        KEY_TMDB_API_KEY: "TMDB_API_KEY",
        KEY_GEMINI_API_KEY: "GEMINI_API_KEY",
        KEY_GROQ_API_KEY: "GROQ_API_KEY",
        KEY_OPENROUTER_API_KEY: "OPENROUTER_API_KEY",
        KEY_CLOUDFLARE_API_TOKEN: "CLOUDFLARE_API_TOKEN",
        KEY_CLOUDFLARE_ACCOUNT_ID: "CLOUDFLARE_ACCOUNT_ID",
        KEY_MAIL: "MAIL",
        KEY_MAIL_PSWD: "MAIL_PSWD",
        KEY_BYPASS: "BYPASS",
        KEY_AI: "AI",
        KEY_LEARN: "LEARN",
        KEY_LOG: "LOG",
        KEY_VERBOSE: "VERBOSE",
        KEY_RESOLUTION: "RESOLUTION",
        KEY_QUALITY: "QUALITY",
        KEY_NOTIFY_ON_SUCCESS: "NOTIFY_ON_SUCCESS",
        KEY_NOTIFY_ON_ERROR: "NOTIFY_ON_ERROR",
        KEY_NOTIFY_ON_TAG: "NOTIFY_ON_TAG",
        KEY_DAEMON: "DAEMON",
        KEY_POLLING_INTERVAL: "POLLING_INTERVAL",
        KEY_AI_PROVIDER: "AI_PROVIDER",
        KEY_TMDB_MIN_CONFIDENCE: "TMDB_MIN_CONFIDENCE",
        KEY_AI_MIN_CONFIDENCE: "AI_MIN_CONFIDENCE",
    }

    KEY_TO_ATTR = {
        KEY_MOVIES_FOLDER: "MOVIES_FOLDER",
        KEY_TV_SHOWS_FOLDER: "TV_SHOWS_FOLDER",
        KEY_INPUT_FOLDER: "NOT_SORTED_MEDIA_FILES_FOLDER",
        KEY_TMDB_API_KEY: "TMDB_API_KEY",
        KEY_GEMINI_API_KEY: "GEMINI_API_KEY",
        KEY_GROQ_API_KEY: "GROQ_API_KEY",
        KEY_OPENROUTER_API_KEY: "OPENROUTER_API_KEY",
        KEY_CLOUDFLARE_API_TOKEN: "CLOUDFLARE_API_TOKEN",
        KEY_CLOUDFLARE_ACCOUNT_ID: "CLOUDFLARE_ACCOUNT_ID",
        KEY_MAIL: "MAIL",
        KEY_MAIL_PSWD: "MAIL_PSWD",
        KEY_BYPASS: "BYPASS",
        KEY_AI: "AI",
        KEY_LEARN: "LEARN",
        KEY_LOG: "LOG",
        KEY_VERBOSE: "VERBOSE",
        KEY_RESOLUTION: "RESOLUTION",
        KEY_QUALITY: "QUALITY",
        KEY_NOTIFY_ON_SUCCESS: "NOTIFY_ON_SUCCESS",
        KEY_NOTIFY_ON_ERROR: "NOTIFY_ON_ERROR",
        KEY_NOTIFY_ON_TAG: "NOTIFY_ON_TAG",
        KEY_DAEMON: "DAEMON",
        KEY_POLLING_INTERVAL: "POLLING_INTERVAL",
        KEY_AI_PROVIDER: "AI_PROVIDER",
        KEY_TMDB_MIN_CONFIDENCE: "TMDB_MIN_CONFIDENCE",
        KEY_AI_MIN_CONFIDENCE: "AI_MIN_CONFIDENCE",
    }

    ATTR_TO_KEY = {v: k for k, v in KEY_TO_ATTR.items()}

    BOOLEAN_KEYS = {
        KEY_BYPASS,
        KEY_AI,
        KEY_LEARN,
        KEY_LOG,
        KEY_VERBOSE,
        KEY_RESOLUTION,
        KEY_QUALITY,
        KEY_NOTIFY_ON_SUCCESS,
        KEY_NOTIFY_ON_ERROR,
        KEY_NOTIFY_ON_TAG,
        KEY_DAEMON,
    }

    SECRET_KEYS = {
        KEY_TMDB_API_KEY,
        KEY_GEMINI_API_KEY,
        KEY_MAIL_PSWD,
        KEY_GROQ_API_KEY,
        KEY_OPENROUTER_API_KEY,
        KEY_CLOUDFLARE_API_TOKEN,
        KEY_CLOUDFLARE_ACCOUNT_ID,
    }

    def __init__(self, custom_path=None):
        self.custom_path = custom_path
        self.config_path = self._resolve_config_path(custom_path)
        self.parser = configparser.ConfigParser()
        self.load()

    @staticmethod
    def is_docker_environment() -> bool:
        return os.environ.get("DOCKER_CONTAINER") == "1" or os.path.exists("/.dockerenv")

    def _resolve_config_path(self, custom_path=None) -> Path:
        if custom_path:
            return Path(custom_path).resolve()

        env_config = os.environ.get("CONFIG_FILE")
        if env_config:
            return Path(env_config).resolve()

        # Check local project override in current working directory
        local_ini = Path(".rename.ini").resolve()
        if local_ini.is_file():
            return local_ini

        local_config_ini = Path("config.ini").resolve()
        if local_config_ini.is_file():
            return local_config_ini

        # Quarantine safeguard: Never touch real user configuration during automated pytest runs or scratch scripts
        script_name = str(sys.argv[0]).lower() if sys.argv else ""
        in_quarantine_mode = (
            "PYTEST_CURRENT_TEST" in os.environ or "PYTEST_VERSION" in os.environ or "scratch" in script_name
        )
        if in_quarantine_mode and not os.environ.get("RENAME_TEST_ALLOW_REAL_PATH"):
            base_dir = Path(tempfile.gettempdir()) / "pytest_rename_quarantine"
            return (base_dir / "config.ini").resolve()

        # Docker environment: Check /config volume first
        if self.is_docker_environment():
            docker_config = Path("/config/config.ini")
            if docker_config.is_file() or Path("/config").is_dir():
                return docker_config.resolve()

        # Standard user config directory
        base_dir = self._get_default_user_dir()
        return (base_dir / "config.ini").resolve()

    @staticmethod
    def _get_default_user_dir() -> Path:
        if os.name == "nt":
            appdata = os.environ.get("APPDATA")
            if appdata:
                return Path(appdata) / "media-organizer"
            return Path.home() / ".config" / "media-organizer"
        xdg = os.environ.get("XDG_CONFIG_HOME")
        if xdg:
            return Path(xdg) / "media-organizer"
        return Path.home() / ".config" / "media-organizer"

    def load(self):
        self.parser = configparser.ConfigParser()
        if self.config_path.is_file():
            self.parser.read(str(self.config_path), encoding="utf-8")
        elif self.is_docker_environment():
            self._init_docker_defaults()

    def _init_docker_defaults(self):
        if not self.parser.has_section("paths"):
            self.parser.add_section("paths")
        self.parser.set("paths", "movies_folder", "/data/Movies")
        self.parser.set("paths", "tv_shows_folder", "/data/TV_Shows")
        self.parser.set("paths", "not_sorted_media_files_folder", "/data/input")

        if not self.parser.has_section("options"):
            self.parser.add_section("options")
        self.parser.set("options", "daemon", "true")
        self.parser.set("options", "bypass", "true")
        self.parser.set("options", "verbose", "true")
        self.parser.set("options", "polling_interval", "15")
        self.parser.set("options", "ai", "false")
        self.parser.set("options", "learn", "false")
        self.parser.set("options", "log", "false")
        self.parser.set("options", "resolution", "false")
        self.parser.set("options", "quality", "false")
        self.parser.set("options", "notify_on_success", "false")
        self.parser.set("options", "notify_on_error", "false")
        self.parser.set("options", "notify_on_tag", "false")
        self.parser.set("options", "ai_provider", "auto")
        self.parser.set("options", "tmdb_min_confidence", "0.75")
        self.parser.set("options", "ai_min_confidence", "0.70")
        try:
            self.save()
        except OSError:
            pass

    def save(self):
        """Atomic write using temporary file to prevent corruption."""
        # Absolute safety check: Never overwrite the user's real config file in test/scratch contexts
        is_test = (
            "pytest" in sys.modules
            or "PYTEST_CURRENT_TEST" in os.environ
            or "PYTEST_VERSION" in os.environ
            or "scratch" in (sys.argv[0].lower() if sys.argv else "")
        )
        if is_test and not os.environ.get("RENAME_ALLOW_REAL_CONFIG_SAVE"):
            try:
                real_user_file = (self._get_default_user_dir() / "config.ini").resolve()
                if self.config_path.resolve() == real_user_file:
                    quarantine_dir = Path(tempfile.gettempdir()) / "pytest_rename_quarantine"
                    quarantine_dir.mkdir(parents=True, exist_ok=True)
                    self.config_path = (quarantine_dir / "config.ini").resolve()
            except (OSError, RuntimeError, ValueError, AttributeError):
                pass

        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        dir_to_use = self.config_path.parent

        with tempfile.NamedTemporaryFile("w", dir=dir_to_use, delete=False, encoding="utf-8") as tf:
            self.parser.write(tf)
            temp_path = tf.name

        shutil.move(temp_path, str(self.config_path))
        if os.name != "nt":
            try:
                os.chmod(self.config_path, 0o600)
            except OSError:
                pass

    def get_with_source(self, section_dot_key: str):
        """Returns tuple of (value, source) where source is 'ENV', 'INI', or 'DEFAULT'."""
        # 1. Check environment variables
        env_var = self.ENV_MAPPING.get(section_dot_key)
        if env_var and env_var in os.environ:
            val = os.environ[env_var]
            if section_dot_key in self.BOOLEAN_KEYS:
                return (val.strip().lower() in ("true", "1", "yes", "y", "t"), "ENV")
            return (val, "ENV")

        # 2. Check INI file
        if "." in section_dot_key:
            section, key = section_dot_key.split(".", 1)
            if self.parser.has_section(section) and self.parser.has_option(section, key):
                raw = self.parser.get(section, key)
                if section_dot_key in self.BOOLEAN_KEYS:
                    return (raw.strip().lower() in ("true", "1", "yes", "y", "t"), "INI")
                return (raw if raw.strip() else None, "INI")

        # 3. Default fallback
        if self.is_docker_environment():
            if section_dot_key == KEY_MOVIES_FOLDER:
                return ("/data/Movies", "DEFAULT")
            if section_dot_key == KEY_TV_SHOWS_FOLDER:
                return ("/data/TV_Shows", "DEFAULT")
            if section_dot_key == KEY_INPUT_FOLDER:
                return ("/data/input", "DEFAULT")
            if section_dot_key in (KEY_DAEMON, KEY_BYPASS, KEY_VERBOSE):
                return (True, "DEFAULT")
            if section_dot_key == KEY_NOTIFY_ON_ERROR:
                return (False, "DEFAULT")

        if section_dot_key == KEY_NOTIFY_ON_ERROR:
            return (True, "DEFAULT")
        if section_dot_key == KEY_POLLING_INTERVAL:
            return (15, "DEFAULT")
        if section_dot_key == KEY_AI_PROVIDER:
            return ("auto", "DEFAULT")
        if section_dot_key == KEY_TMDB_MIN_CONFIDENCE:
            return (0.75, "DEFAULT")
        if section_dot_key == KEY_AI_MIN_CONFIDENCE:
            return (0.70, "DEFAULT")
        if section_dot_key in self.BOOLEAN_KEYS:
            return (False, "DEFAULT")
        return (None, "DEFAULT")

    def get(self, section_dot_key: str, default=None):
        val, _ = self.get_with_source(section_dot_key)
        return val if val is not None else default

    def set(self, section_dot_key: str, value: str):
        if "." not in section_dot_key:
            raise ValueError(f"Key must be in format 'section.key', got '{section_dot_key}'")

        section, key = section_dot_key.split(".", 1)
        section = section.strip().lower()
        key = key.strip().lower()

        if section not in self.SCHEMA:
            raise ValueError(f"Unknown section '{section}'. Valid sections: {', '.join(self.SCHEMA.keys())}")
        if key not in self.SCHEMA[section]:
            raise ValueError(
                f"Unknown key '{key}' in section '{section}'. Valid keys: {', '.join(self.SCHEMA[section])}"
            )

        if not self.parser.has_section(section):
            self.parser.add_section(section)

        # Validate specific option types
        if section_dot_key == KEY_POLLING_INTERVAL:
            try:
                int_val = int(str(value).strip())
                if int_val < 1:
                    raise ValueError()
                self.parser.set(section, key, str(int_val))
            except ValueError:
                raise ValueError("Polling interval must be a positive integer (>= 1 minute).")
        elif section_dot_key == KEY_AI_PROVIDER:
            val_str = str(value).strip().lower()
            if val_str not in ("auto", "gemini", "groq", "openrouter", "cloudflare"):
                raise ValueError("AI provider must be one of: auto, gemini, groq, openrouter, cloudflare.")
            self.parser.set(section, key, val_str)
        elif section_dot_key in (KEY_TMDB_MIN_CONFIDENCE, KEY_AI_MIN_CONFIDENCE):
            try:
                val_f = float(str(value).strip())
                if not (0.0 <= val_f <= 1.0):
                    raise ValueError()
                self.parser.set(section, key, str(val_f))
            except ValueError:
                raise ValueError(f"{key} must be a float between 0.0 and 1.0.")
        # Normalize boolean values
        elif f"{section}.{key}" in self.BOOLEAN_KEYS:
            val_bool = str(value).strip().lower() in ("true", "1", "yes", "y", "t")
            str_val = "true" if val_bool else "false"
            self.parser.set(section, key, str_val)
        else:
            self.parser.set(section, key, str(value).strip())

        self.save()

    def unset(self, section_dot_key: str) -> bool:
        if "." not in section_dot_key:
            raise ValueError(f"Key must be in format 'section.key', got '{section_dot_key}'")

        section, key = section_dot_key.split(".", 1)
        section = section.strip().lower()
        key = key.strip().lower()

        if self.parser.has_section(section) and self.parser.remove_option(section, key):
            self.save()
            return True
        return False

    def list_all(self, show_secrets: bool = False):
        """Returns structured list of all settings across all schema sections."""
        items = []
        for section, keys in self.SCHEMA.items():
            for key in keys:
                full_key = f"{section}.{key}"
                val, source = self.get_with_source(full_key)
                is_secret = full_key in self.SECRET_KEYS

                display_val = val
                if is_secret and val and not show_secrets:
                    val_str = str(val)
                    if len(val_str) > 8:
                        display_val = f"{val_str[:4]}****{val_str[-4:]}"
                    else:
                        display_val = "****"

                items.append(
                    {
                        "section": section,
                        "key": key,
                        "full_key": full_key,
                        "value": val,
                        "display_value": display_val if display_val is not None else "(not configured)",
                        "source": source,
                        "is_secret": is_secret,
                    }
                )
        return items

    def run_gui(self) -> bool:
        """Launches the graphical configuration interface."""
        from src.gui import launch_config_gui

        return launch_config_gui(self)

    def wizard_paths(self, console=None):
        """Interactive setup for media storage folders.

        B10 / R3 fix: paths are only written to config when the directory
        exists on disk — invalid paths are rejected with a clear message.
        R2 fix: cross-field validation warns when two configured folders
        point to the same resolved path.
        """
        from rich.console import Console
        from rich.prompt import Prompt

        console = console or Console()

        console.print("\n[bold magenta]Folder Paths Configuration[/bold magenta]")
        console.print(
            "[dim]Best Practice: Keep incoming downloads in an unsorted folder, separate from your Movies and TV Shows libraries. Folders can be local drives, USB disks, or NAS network shares.[/dim]"
        )

        collected: dict[str, str] = {}

        def _prompt_and_validate_folder(label: str, key: str) -> None:
            current = self.get(key) or ""
            folder_input = Prompt.ask(label, default=current)
            folder_clean = folder_input.strip()
            if not folder_clean:
                return  # user left blank — keep existing setting unchanged
            if not os.path.isdir(folder_clean):
                console.print(
                    f"[bold red]Error: The directory '{folder_clean}' does not exist on disk or is not reachable.[/bold red]\n"
                    "[yellow]Skipping — the existing setting has not been changed.[/yellow]"
                )
                return  # B10 fix: do NOT save an invalid path
            self.set(key, folder_clean)
            collected[key] = str(Path(folder_clean).resolve())

        _prompt_and_validate_folder("Movies Folder", KEY_MOVIES_FOLDER)
        _prompt_and_validate_folder("TV Shows Folder", KEY_TV_SHOWS_FOLDER)
        _prompt_and_validate_folder("Unsorted Downloads Folder", KEY_INPUT_FOLDER)

        # R2: Cross-field validation — warn if any two folders resolve to the same path
        labels = {
            KEY_MOVIES_FOLDER: "Movies Folder",
            KEY_TV_SHOWS_FOLDER: "TV Shows Folder",
            KEY_INPUT_FOLDER: "Unsorted Downloads Folder",
        }
        seen: dict[str, str] = {}
        for key, resolved in collected.items():
            if resolved in seen:
                console.print(
                    f"[bold yellow]Warning: '{labels[key]}' and '{labels[seen[resolved]]}' "
                    f"both resolve to the same path: {resolved}.\n"
                    "This may cause files to be moved into an unexpected location.[/bold yellow]"
                )
            else:
                seen[resolved] = key

    def wizard_api(self, console=None):
        """Interactive setup for TMDB and Cloud AI providers."""
        from rich.console import Console
        from rich.prompt import Prompt

        console = console or Console()

        console.print("\n[bold magenta]🔑 API Keys Configuration[/bold magenta]")
        console.print(
            "[dim]Best Practice: TMDB API key is required to query official movie/series metadata. Cloud AI providers act as optional fallbacks for highly cryptic filenames.[/dim]"
        )

        current_tmdb = self.get(KEY_TMDB_API_KEY) or ""
        tmdb_masked = f"{current_tmdb[:4]}...{current_tmdb[-4:]}" if len(current_tmdb) > 8 else current_tmdb
        tmdb_input = Prompt.ask("TMDB API Key (Bearer/v3 token)", default=tmdb_masked)
        if tmdb_input.strip() and tmdb_input != tmdb_masked:
            self.set(KEY_TMDB_API_KEY, tmdb_input)

        current_gemini = self.get(KEY_GEMINI_API_KEY) or ""
        gemini_masked = f"{current_gemini[:4]}...{current_gemini[-4:]}" if len(current_gemini) > 8 else current_gemini
        gemini_input = Prompt.ask("Google Gemini API Key (Optional AI Fallback)", default=gemini_masked)
        if gemini_input.strip() and gemini_input != gemini_masked:
            self.set(KEY_GEMINI_API_KEY, gemini_input)

        current_groq = self.get(KEY_GROQ_API_KEY) or ""
        groq_masked = f"{current_groq[:4]}...{current_groq[-4:]}" if len(current_groq) > 8 else current_groq
        groq_input = Prompt.ask("Groq Cloud API Key (Optional AI Fallback)", default=groq_masked)
        if groq_input.strip() and groq_input != groq_masked:
            self.set(KEY_GROQ_API_KEY, groq_input)

        current_openrouter = self.get(KEY_OPENROUTER_API_KEY) or ""
        openrouter_masked = (
            f"{current_openrouter[:4]}...{current_openrouter[-4:]}"
            if len(current_openrouter) > 8
            else current_openrouter
        )
        openrouter_input = Prompt.ask("OpenRouter API Key (Optional AI Fallback)", default=openrouter_masked)
        if openrouter_input.strip() and openrouter_input != openrouter_masked:
            self.set(KEY_OPENROUTER_API_KEY, openrouter_input)

        current_cf_tok = self.get(KEY_CLOUDFLARE_API_TOKEN) or ""
        cf_tok_masked = f"{current_cf_tok[:4]}...{current_cf_tok[-4:]}" if len(current_cf_tok) > 8 else current_cf_tok
        cf_tok_input = Prompt.ask("Cloudflare Workers AI Token (Optional)", default=cf_tok_masked)
        if cf_tok_input.strip() and cf_tok_input != cf_tok_masked:
            self.set(KEY_CLOUDFLARE_API_TOKEN, cf_tok_input)

        current_cf_acc = self.get(KEY_CLOUDFLARE_ACCOUNT_ID) or ""
        cf_acc_masked = f"{current_cf_acc[:4]}...{current_cf_acc[-4:]}" if len(current_cf_acc) > 8 else current_cf_acc
        cf_acc_input = Prompt.ask("Cloudflare Account ID (Optional)", default=cf_acc_masked)
        if cf_acc_input.strip() and cf_acc_input != cf_acc_masked:
            self.set(KEY_CLOUDFLARE_ACCOUNT_ID, cf_acc_input)

    def wizard_email(self, console=None):
        """Interactive setup for email alerts."""
        from rich.console import Console
        from rich.prompt import Prompt

        console = console or Console()

        console.print("\n[bold magenta]📧 Email Alerts Configuration (Optional)[/bold magenta]")
        console.print(
            "[dim]Best Practice: Useful for headless/server cron jobs. Requires a 16-letter Gmail App Password created via Google Account Security.[/dim]"
        )
        current_mail = self.get(KEY_MAIL) or ""
        mail_input = Prompt.ask("Gmail Address", default=current_mail)
        if mail_input.strip():
            self.set(KEY_MAIL, mail_input)

        current_pswd = self.get(KEY_MAIL_PSWD) or ""
        pswd_masked = "****" if current_pswd else ""
        pswd_input = Prompt.ask("Gmail App Password (16-letter password)", default=pswd_masked)
        if pswd_input.strip() and pswd_input != pswd_masked:
            self.set(KEY_MAIL_PSWD, pswd_input)

    def wizard_options(self, console=None):
        """Interactive setup for automation and runtime options."""
        from rich.console import Console
        from rich.prompt import Prompt, Confirm

        console = console or Console()

        console.print("\n[bold magenta]⚙️ Automation & Runtime Options[/bold magenta]")
        console.print(
            "[dim]Best Practice: Set default execution behaviors so you do not need to specify flags on every run. CLI flags (-b, -i, -L, -l, -v, -t) will always override these defaults.[/dim]"
        )
        cur_bypass = bool(self.get(KEY_BYPASS, False))
        bypass_input = Confirm.ask("Bypass confirmation prompts and run non-interactively (-b)?", default=cur_bypass)
        self.set(KEY_BYPASS, "true" if bypass_input else "false")

        cur_daemon = bool(self.get(KEY_DAEMON, False))
        daemon_input = Confirm.ask("Enable background daemon watcher mode by default (-d)?", default=cur_daemon)
        self.set(KEY_DAEMON, "true" if daemon_input else "false")

        cur_interval = str(self.get(KEY_POLLING_INTERVAL) or "15")
        interval_input = Prompt.ask("Polling interval in minutes for daemon mode", default=cur_interval)
        try:
            int_val = int(interval_input.strip())
            if int_val >= 1:
                self.set(KEY_POLLING_INTERVAL, str(int_val))
            else:
                self.set(KEY_POLLING_INTERVAL, "15")
        except ValueError:
            self.set(KEY_POLLING_INTERVAL, "15")

        cur_ai = bool(self.get(KEY_AI, False))
        ai_input = Confirm.ask("Enable Cloud AI fallback by default for unrecognized filenames (-i)?", default=cur_ai)
        self.set(KEY_AI, "true" if ai_input else "false")

        cur_learn = bool(self.get(KEY_LEARN, False))
        learn_input = Confirm.ask(
            "Enable AI keyword learning by default (save missing tags discovered by AI) (-L)?", default=cur_learn
        )
        self.set(KEY_LEARN, "true" if learn_input else "false")

        cur_prov = str(self.get(KEY_AI_PROVIDER) or "auto")
        prov_input = Prompt.ask("Default AI Provider (auto, gemini, groq, openrouter, cloudflare)", default=cur_prov)
        if prov_input.strip().lower() in ("auto", "gemini", "groq", "openrouter", "cloudflare"):
            self.set(KEY_AI_PROVIDER, prov_input.strip().lower())

        cur_log = bool(self.get(KEY_LOG, False))
        log_input = Confirm.ask("Write execution logs to daily log files instead of terminal (-l)?", default=cur_log)
        self.set(KEY_LOG, "true" if log_input else "false")

        cur_verbose = bool(self.get(KEY_VERBOSE, False))
        verbose_input = Confirm.ask("Display detailed error logs and exception tracebacks (-v)?", default=cur_verbose)
        self.set(KEY_VERBOSE, "true" if verbose_input else "false")

        cur_succ = bool(self.get(KEY_NOTIFY_ON_SUCCESS, False))
        notify_succ_input = Confirm.ask("Send an email notification on successful processing?", default=cur_succ)
        self.set(KEY_NOTIFY_ON_SUCCESS, "true" if notify_succ_input else "false")

        cur_err = bool(self.get(KEY_NOTIFY_ON_ERROR, True))
        notify_err_input = Confirm.ask("Send an email notification when an error occurs?", default=cur_err)
        self.set(KEY_NOTIFY_ON_ERROR, "true" if notify_err_input else "false")

        cur_tag = bool(self.get(KEY_NOTIFY_ON_TAG, False))
        notify_tag_input = Confirm.ask(
            "Send an email notification when a new AI keyword tag is learned (-t)?", default=cur_tag
        )
        self.set(KEY_NOTIFY_ON_TAG, "true" if notify_tag_input else "false")

    def wizard_video(self, console=None):
        """Interactive setup for video stream FFmpeg tags."""
        from rich.console import Console
        from rich.prompt import Confirm

        console = console or Console()

        console.print("\n[bold magenta]🎞️ Video Stream Options (Requires FFmpeg)[/bold magenta]")
        console.print(
            "[dim]Best Practice: Extracts video stream metadata to append clean tags (e.g. [4K] [1080p] [BluRay]). Requires 'ffprobe' installed in System PATH.[/dim]"
        )
        cur_res = bool(self.get(KEY_RESOLUTION, False))
        res_input = Confirm.ask("Detect and append resolution tags (e.g., [4K], [FullHD])?", default=cur_res)
        self.set(KEY_RESOLUTION, "true" if res_input else "false")

        cur_qual = bool(self.get(KEY_QUALITY, False))
        qual_input = Confirm.ask("Detect and append quality tags (e.g., [BluRay], [WEB-DL])?", default=cur_qual)
        self.set(KEY_QUALITY, "true" if qual_input else "false")

        if (res_input or qual_input) and not shutil.which("ffprobe"):
            console.print("\n[bold red]❌ Error: 'ffprobe' (FFmpeg) was not found in your System PATH.[/bold red]")
            console.print(
                "[yellow]Resolution and quality tags will fail to be detected until FFmpeg is installed.[/yellow]"
            )
            console.print("[dim]Installation guide: docs/documentation.md#ffmpeg-setup[/dim]")

    def run_wizard(self, section: str | None = None, interactive_menu: bool = False):
        """Interactive terminal configuration wizard that guides the user through setup steps."""
        from rich.console import Console

        console = Console()
        console.print("\n[bold cyan]==============================================[/bold cyan]")
        console.print("[bold cyan]   🎬 media-organizer Setup Wizard   [/bold cyan]")
        console.print("[bold cyan]==============================================[/bold cyan]\n")
        console.print(f"Target Configuration File: [yellow]{self.config_path}[/yellow]\n")

        if section == "paths":
            self.wizard_paths(console)
        elif section == "ai":
            self.wizard_api(console)
        elif section == "email":
            self.wizard_email(console)
        elif section == "options":
            self.wizard_options(console)
        elif section == "video":
            self.wizard_video(console)
        else:
            console.print("Press [green]Enter[/green] to keep current value.\n")
            self.wizard_paths(console)
            self.wizard_api(console)
            self.wizard_email(console)
            self.wizard_options(console)
            self.wizard_video(console)

        console.print(
            f"\n[bold green]✅ Configuration successfully saved to:[/bold green] [yellow]{self.config_path}[/yellow]\n"
        )

    # Module-level property accessors
    @property
    def MOVIES_FOLDER(self):
        return self.get(KEY_MOVIES_FOLDER)

    @MOVIES_FOLDER.setter
    def MOVIES_FOLDER(self, value):
        if value is None:
            self.unset(KEY_MOVIES_FOLDER)
        else:
            self.set(KEY_MOVIES_FOLDER, str(value))

    @property
    def TV_SHOWS_FOLDER(self):
        return self.get(KEY_TV_SHOWS_FOLDER)

    @TV_SHOWS_FOLDER.setter
    def TV_SHOWS_FOLDER(self, value):
        if value is None:
            self.unset(KEY_TV_SHOWS_FOLDER)
        else:
            self.set(KEY_TV_SHOWS_FOLDER, str(value))

    @property
    def NOT_SORTED_MEDIA_FILES_FOLDER(self):
        return self.get(KEY_INPUT_FOLDER)

    @NOT_SORTED_MEDIA_FILES_FOLDER.setter
    def NOT_SORTED_MEDIA_FILES_FOLDER(self, value):
        if value is None:
            self.unset(KEY_INPUT_FOLDER)
        else:
            self.set(KEY_INPUT_FOLDER, str(value))

    @property
    def TMDB_API_KEY(self):
        return self.get(KEY_TMDB_API_KEY)

    @TMDB_API_KEY.setter
    def TMDB_API_KEY(self, value):
        if value is None:
            self.unset(KEY_TMDB_API_KEY)
        else:
            self.set(KEY_TMDB_API_KEY, str(value))

    @property
    def GEMINI_API_KEY(self):
        return self.get(KEY_GEMINI_API_KEY)

    @GEMINI_API_KEY.setter
    def GEMINI_API_KEY(self, value):
        if value is None:
            self.unset(KEY_GEMINI_API_KEY)
        else:
            self.set(KEY_GEMINI_API_KEY, str(value))

    @property
    def MAIL(self):
        return self.get(KEY_MAIL)

    @MAIL.setter
    def MAIL(self, value):
        if value is None:
            self.unset(KEY_MAIL)
        else:
            self.set(KEY_MAIL, str(value))

    @property
    def MAIL_PSWD(self):
        return self.get(KEY_MAIL_PSWD)

    @MAIL_PSWD.setter
    def MAIL_PSWD(self, value):
        if value is None:
            self.unset(KEY_MAIL_PSWD)
        else:
            self.set(KEY_MAIL_PSWD, str(value))

    @property
    def NOTIFY_ON_SUCCESS(self) -> bool:
        return bool(self.get(KEY_NOTIFY_ON_SUCCESS, False))

    @NOTIFY_ON_SUCCESS.setter
    def NOTIFY_ON_SUCCESS(self, value):
        self.set(KEY_NOTIFY_ON_SUCCESS, "true" if value else "false")

    @property
    def NOTIFY_ON_ERROR(self) -> bool:
        return bool(self.get(KEY_NOTIFY_ON_ERROR, True))

    @NOTIFY_ON_ERROR.setter
    def NOTIFY_ON_ERROR(self, value):
        self.set(KEY_NOTIFY_ON_ERROR, "true" if value else "false")

    @property
    def NOTIFY_ON_TAG(self) -> bool:
        return bool(self.get(KEY_NOTIFY_ON_TAG, False))

    @NOTIFY_ON_TAG.setter
    def NOTIFY_ON_TAG(self, value):
        self.set(KEY_NOTIFY_ON_TAG, "true" if value else "false")

    @property
    def BYPASS(self) -> bool:
        return bool(self.get(KEY_BYPASS, False))

    @BYPASS.setter
    def BYPASS(self, value):
        self.set(KEY_BYPASS, "true" if value else "false")

    @property
    def AI(self) -> bool:
        return bool(self.get(KEY_AI, False))

    @AI.setter
    def AI(self, value):
        self.set(KEY_AI, "true" if value else "false")

    @property
    def LEARN(self) -> bool:
        return bool(self.get(KEY_LEARN, False))

    @LEARN.setter
    def LEARN(self, value):
        self.set(KEY_LEARN, "true" if value else "false")

    @property
    def LOG(self) -> bool:
        return bool(self.get(KEY_LOG, False))

    @LOG.setter
    def LOG(self, value):
        self.set(KEY_LOG, "true" if value else "false")

    @property
    def VERBOSE(self) -> bool:
        return bool(self.get(KEY_VERBOSE, False))

    @VERBOSE.setter
    def VERBOSE(self, value):
        self.set(KEY_VERBOSE, "true" if value else "false")

    @property
    def RESOLUTION(self):
        return bool(self.get(KEY_RESOLUTION, False))

    @RESOLUTION.setter
    def RESOLUTION(self, value):
        self.set(KEY_RESOLUTION, "true" if value else "false")

    @property
    def QUALITY(self):
        return bool(self.get(KEY_QUALITY, False))

    @QUALITY.setter
    def QUALITY(self, value):
        self.set(KEY_QUALITY, "true" if value else "false")

    @property
    def DAEMON(self) -> bool:
        return bool(self.get(KEY_DAEMON, False))

    @DAEMON.setter
    def DAEMON(self, value):
        self.set(KEY_DAEMON, "true" if value else "false")

    @property
    def POLLING_INTERVAL(self) -> int:
        val = self.get(KEY_POLLING_INTERVAL, 15)
        try:
            val_int = int(val)
            return val_int if val_int >= 1 else 15
        except (ValueError, TypeError):
            return 15

    @POLLING_INTERVAL.setter
    def POLLING_INTERVAL(self, value):
        self.set(KEY_POLLING_INTERVAL, str(value))

    @property
    def GROQ_API_KEY(self):
        return self.get(KEY_GROQ_API_KEY)

    @GROQ_API_KEY.setter
    def GROQ_API_KEY(self, value):
        if value is None:
            self.unset(KEY_GROQ_API_KEY)
        else:
            self.set(KEY_GROQ_API_KEY, str(value))

    @property
    def OPENROUTER_API_KEY(self):
        return self.get(KEY_OPENROUTER_API_KEY)

    @OPENROUTER_API_KEY.setter
    def OPENROUTER_API_KEY(self, value):
        if value is None:
            self.unset(KEY_OPENROUTER_API_KEY)
        else:
            self.set(KEY_OPENROUTER_API_KEY, str(value))

    @property
    def CLOUDFLARE_API_TOKEN(self):
        return self.get(KEY_CLOUDFLARE_API_TOKEN)

    @CLOUDFLARE_API_TOKEN.setter
    def CLOUDFLARE_API_TOKEN(self, value):
        if value is None:
            self.unset(KEY_CLOUDFLARE_API_TOKEN)
        else:
            self.set(KEY_CLOUDFLARE_API_TOKEN, str(value))

    @property
    def CLOUDFLARE_ACCOUNT_ID(self):
        return self.get(KEY_CLOUDFLARE_ACCOUNT_ID)

    @CLOUDFLARE_ACCOUNT_ID.setter
    def CLOUDFLARE_ACCOUNT_ID(self, value):
        if value is None:
            self.unset(KEY_CLOUDFLARE_ACCOUNT_ID)
        else:
            self.set(KEY_CLOUDFLARE_ACCOUNT_ID, str(value))

    @property
    def AI_PROVIDER(self) -> str:
        val = self.get(KEY_AI_PROVIDER, "auto")
        return str(val).strip().lower() if val else "auto"

    @AI_PROVIDER.setter
    def AI_PROVIDER(self, value):
        self.set(KEY_AI_PROVIDER, str(value).strip().lower())

    @property
    def TMDB_MIN_CONFIDENCE(self) -> float:
        val = self.get(KEY_TMDB_MIN_CONFIDENCE, 0.75)
        try:
            val_f = float(val)
            return val_f if 0.0 <= val_f <= 1.0 else 0.75
        except (ValueError, TypeError):
            return 0.75

    @TMDB_MIN_CONFIDENCE.setter
    def TMDB_MIN_CONFIDENCE(self, value):
        self.set(KEY_TMDB_MIN_CONFIDENCE, str(value))

    @property
    def AI_MIN_CONFIDENCE(self) -> float:
        val = self.get(KEY_AI_MIN_CONFIDENCE, 0.70)
        try:
            val_f = float(val)
            return val_f if 0.0 <= val_f <= 1.0 else 0.70
        except (ValueError, TypeError):
            return 0.70

    @AI_MIN_CONFIDENCE.setter
    def AI_MIN_CONFIDENCE(self, value):
        self.set(KEY_AI_MIN_CONFIDENCE, str(value))


# Singleton instance
config = ConfigManager()
