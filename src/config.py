from __future__ import annotations
import os
import sys
import shutil
import tempfile
import configparser
from pathlib import Path
from typing import Optional, Any, Dict, List

class ConfigManager:
    SCHEMA = {
        "paths": ["movies_folder", "tv_shows_folder", "not_sorted_media_files_folder"],
        "api": [
            "tmdb_api_key", "gemini_api_key", "groq_api_key",
            "openrouter_api_key", "cloudflare_api_token", "cloudflare_account_id"
        ],
        "mail": ["mail", "mail_pswd"],
        "options": [
            "bypass", "ai", "log", "verbose", "resolution", "quality",
            "notify_on_success", "notify_on_error", "notify_on_tag", "daemon", "polling_interval", "learn",
            "ai_provider", "tmdb_min_confidence", "ai_min_confidence"
        ]
    }

    ENV_MAPPING = {
        "paths.movies_folder": "MOVIES_FOLDER",
        "paths.tv_shows_folder": "TV_SHOWS_FOLDER",
        "paths.not_sorted_media_files_folder": "INPUT_FOLDER",
        "api.tmdb_api_key": "TMDB_API_KEY",
        "api.gemini_api_key": "GEMINI_API_KEY",
        "api.groq_api_key": "GROQ_API_KEY",
        "api.openrouter_api_key": "OPENROUTER_API_KEY",
        "api.cloudflare_api_token": "CLOUDFLARE_API_TOKEN",
        "api.cloudflare_account_id": "CLOUDFLARE_ACCOUNT_ID",
        "mail.mail": "MAIL",
        "mail.mail_pswd": "MAIL_PSWD",
        "options.bypass": "BYPASS",
        "options.ai": "AI",
        "options.learn": "LEARN",
        "options.log": "LOG",
        "options.verbose": "VERBOSE",
        "options.resolution": "RESOLUTION",
        "options.quality": "QUALITY",
        "options.notify_on_success": "NOTIFY_ON_SUCCESS",
        "options.notify_on_error": "NOTIFY_ON_ERROR",
        "options.notify_on_tag": "NOTIFY_ON_TAG",
        "options.daemon": "DAEMON",
        "options.polling_interval": "POLLING_INTERVAL",
        "options.ai_provider": "AI_PROVIDER",
        "options.tmdb_min_confidence": "TMDB_MIN_CONFIDENCE",
        "options.ai_min_confidence": "AI_MIN_CONFIDENCE",
    }

    KEY_TO_ATTR = {
        "paths.movies_folder": "MOVIES_FOLDER",
        "paths.tv_shows_folder": "TV_SHOWS_FOLDER",
        "paths.not_sorted_media_files_folder": "NOT_SORTED_MEDIA_FILES_FOLDER",
        "api.tmdb_api_key": "TMDB_API_KEY",
        "api.gemini_api_key": "GEMINI_API_KEY",
        "api.groq_api_key": "GROQ_API_KEY",
        "api.openrouter_api_key": "OPENROUTER_API_KEY",
        "api.cloudflare_api_token": "CLOUDFLARE_API_TOKEN",
        "api.cloudflare_account_id": "CLOUDFLARE_ACCOUNT_ID",
        "mail.mail": "MAIL",
        "mail.mail_pswd": "MAIL_PSWD",
        "options.bypass": "BYPASS",
        "options.ai": "AI",
        "options.learn": "LEARN",
        "options.log": "LOG",
        "options.verbose": "VERBOSE",
        "options.resolution": "RESOLUTION",
        "options.quality": "QUALITY",
        "options.notify_on_success": "NOTIFY_ON_SUCCESS",
        "options.notify_on_error": "NOTIFY_ON_ERROR",
        "options.notify_on_tag": "NOTIFY_ON_TAG",
        "options.daemon": "DAEMON",
        "options.polling_interval": "POLLING_INTERVAL",
        "options.ai_provider": "AI_PROVIDER",
        "options.tmdb_min_confidence": "TMDB_MIN_CONFIDENCE",
        "options.ai_min_confidence": "AI_MIN_CONFIDENCE",
    }

    ATTR_TO_KEY = {v: k for k, v in KEY_TO_ATTR.items()}

    BOOLEAN_KEYS = {
        "options.bypass",
        "options.ai",
        "options.learn",
        "options.log",
        "options.verbose",
        "options.resolution",
        "options.quality",
        "options.notify_on_success",
        "options.notify_on_error",
        "options.notify_on_tag",
        "options.daemon"
    }

    SECRET_KEYS = {
        "api.tmdb_api_key", "api.gemini_api_key", "mail.mail_pswd",
        "api.groq_api_key", "api.openrouter_api_key", "api.cloudflare_api_token"
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
            "PYTEST_CURRENT_TEST" in os.environ
            or "PYTEST_VERSION" in os.environ
            or "scratch" in script_name
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
        if os.name == 'nt':
            appdata = os.environ.get('APPDATA')
            if appdata:
                return Path(appdata) / "rename"
            return Path.home() / ".config" / "rename"
        xdg = os.environ.get('XDG_CONFIG_HOME')
        if xdg:
            return Path(xdg) / "rename"
        return Path.home() / ".config" / "rename"

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
        if os.name != 'nt':
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
            if section_dot_key == "paths.movies_folder":
                return ("/data/Movies", "DEFAULT")
            if section_dot_key == "paths.tv_shows_folder":
                return ("/data/TV_Shows", "DEFAULT")
            if section_dot_key == "paths.not_sorted_media_files_folder":
                return ("/data/input", "DEFAULT")
            if section_dot_key in ("options.daemon", "options.bypass", "options.verbose"):
                return (True, "DEFAULT")
            if section_dot_key == "options.notify_on_error":
                return (False, "DEFAULT")

        if section_dot_key == "options.notify_on_error":
            return (True, "DEFAULT")
        if section_dot_key == "options.polling_interval":
            return (15, "DEFAULT")
        if section_dot_key == "options.ai_provider":
            return ("auto", "DEFAULT")
        if section_dot_key == "options.tmdb_min_confidence":
            return (0.75, "DEFAULT")
        if section_dot_key == "options.ai_min_confidence":
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
            raise ValueError(f"Unknown key '{key}' in section '{section}'. Valid keys: {', '.join(self.SCHEMA[section])}")

        if not self.parser.has_section(section):
            self.parser.add_section(section)

        # Validate specific option types
        if section_dot_key == "options.polling_interval":
            try:
                int_val = int(str(value).strip())
                if int_val < 1:
                    raise ValueError()
                self.parser.set(section, key, str(int_val))
            except ValueError:
                raise ValueError("Polling interval must be a positive integer (>= 1 minute).")
        elif section_dot_key == "options.ai_provider":
            val_str = str(value).strip().lower()
            if val_str not in ("auto", "gemini", "groq", "openrouter", "cloudflare"):
                raise ValueError("AI provider must be one of: auto, gemini, groq, openrouter, cloudflare.")
            self.parser.set(section, key, val_str)
        elif section_dot_key in ("options.tmdb_min_confidence", "options.ai_min_confidence"):
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

                items.append({
                    "section": section,
                    "key": key,
                    "full_key": full_key,
                    "value": val,
                    "display_value": display_val if display_val is not None else "(not configured)",
                    "source": source,
                    "is_secret": is_secret
                })
        return items

    def run_gui(self) -> bool:
        """Launches the graphical configuration interface."""
        from src.gui import launch_config_gui
        return launch_config_gui(self)

    def wizard_paths(self, console=None):
        """Interactive setup for media storage folders."""
        from rich.console import Console
        from rich.prompt import Prompt
        console = console or Console()

        console.print("\n[bold magenta]📂 Folder Paths Configuration[/bold magenta]")
        console.print("[dim]Best Practice: Keep incoming downloads in an unsorted folder, separate from your Movies and TV Shows libraries. Folders can be local drives, USB disks, or NAS network shares.[/dim]")

        def _prompt_and_validate_folder(label, key):
            current = self.get(key) or ""
            folder_input = Prompt.ask(label, default=current)
            folder_clean = folder_input.strip()
            if folder_clean:
                if not os.path.isdir(folder_clean):
                    console.print(f"[bold red]❌ Error: The directory '{folder_clean}' does not exist on disk or is not reachable.[/bold red]")
                self.set(key, folder_clean)

        _prompt_and_validate_folder("Movies Folder", "paths.movies_folder")
        _prompt_and_validate_folder("TV Shows Folder", "paths.tv_shows_folder")
        _prompt_and_validate_folder("Unsorted Downloads Folder", "paths.not_sorted_media_files_folder")

    def wizard_api(self, console=None):
        """Interactive setup for TMDB and Cloud AI providers."""
        from rich.console import Console
        from rich.prompt import Prompt
        console = console or Console()

        console.print("\n[bold magenta]🔑 API Keys Configuration[/bold magenta]")
        console.print("[dim]Best Practice: TMDB API key is required to query official movie/series metadata. Cloud AI providers act as optional fallbacks for highly cryptic filenames.[/dim]")

        current_tmdb = self.get("api.tmdb_api_key") or ""
        tmdb_masked = f"{current_tmdb[:4]}...{current_tmdb[-4:]}" if len(current_tmdb) > 8 else current_tmdb
        tmdb_input = Prompt.ask("TMDB API Key (Bearer/v3 token)", default=tmdb_masked)
        if tmdb_input.strip() and tmdb_input != tmdb_masked:
            self.set("api.tmdb_api_key", tmdb_input)

        current_gemini = self.get("api.gemini_api_key") or ""
        gemini_masked = f"{current_gemini[:4]}...{current_gemini[-4:]}" if len(current_gemini) > 8 else current_gemini
        gemini_input = Prompt.ask("Google Gemini API Key (Optional AI Fallback)", default=gemini_masked)
        if gemini_input.strip() and gemini_input != gemini_masked:
            self.set("api.gemini_api_key", gemini_input)

        current_groq = self.get("api.groq_api_key") or ""
        groq_masked = f"{current_groq[:4]}...{current_groq[-4:]}" if len(current_groq) > 8 else current_groq
        groq_input = Prompt.ask("Groq Cloud API Key (Optional AI Fallback)", default=groq_masked)
        if groq_input.strip() and groq_input != groq_masked:
            self.set("api.groq_api_key", groq_input)

        current_openrouter = self.get("api.openrouter_api_key") or ""
        openrouter_masked = f"{current_openrouter[:4]}...{current_openrouter[-4:]}" if len(current_openrouter) > 8 else current_openrouter
        openrouter_input = Prompt.ask("OpenRouter API Key (Optional AI Fallback)", default=openrouter_masked)
        if openrouter_input.strip() and openrouter_input != openrouter_masked:
            self.set("api.openrouter_api_key", openrouter_input)

        current_cf_tok = self.get("api.cloudflare_api_token") or ""
        cf_tok_masked = f"{current_cf_tok[:4]}...{current_cf_tok[-4:]}" if len(current_cf_tok) > 8 else current_cf_tok
        cf_tok_input = Prompt.ask("Cloudflare Workers AI Token (Optional)", default=cf_tok_masked)
        if cf_tok_input.strip() and cf_tok_input != cf_tok_masked:
            self.set("api.cloudflare_api_token", cf_tok_input)

        current_cf_acc = self.get("api.cloudflare_account_id") or ""
        cf_acc_masked = f"{current_cf_acc[:4]}...{current_cf_acc[-4:]}" if len(current_cf_acc) > 8 else current_cf_acc
        cf_acc_input = Prompt.ask("Cloudflare Account ID (Optional)", default=cf_acc_masked)
        if cf_acc_input.strip() and cf_acc_input != cf_acc_masked:
            self.set("api.cloudflare_account_id", cf_acc_input)

    def wizard_email(self, console=None):
        """Interactive setup for email alerts."""
        from rich.console import Console
        from rich.prompt import Prompt
        console = console or Console()

        console.print("\n[bold magenta]📧 Email Alerts Configuration (Optional)[/bold magenta]")
        console.print("[dim]Best Practice: Useful for headless/server cron jobs. Requires a 16-letter Gmail App Password created via Google Account Security.[/dim]")
        current_mail = self.get("mail.mail") or ""
        mail_input = Prompt.ask("Gmail Address", default=current_mail)
        if mail_input.strip():
            self.set("mail.mail", mail_input)

        current_pswd = self.get("mail.mail_pswd") or ""
        pswd_masked = "****" if current_pswd else ""
        pswd_input = Prompt.ask("Gmail App Password (16-letter password)", default=pswd_masked)
        if pswd_input.strip() and pswd_input != pswd_masked:
            self.set("mail.mail_pswd", pswd_input)

    def wizard_options(self, console=None):
        """Interactive setup for automation and runtime options."""
        from rich.console import Console
        from rich.prompt import Prompt, Confirm
        console = console or Console()

        console.print("\n[bold magenta]⚙️ Automation & Runtime Options[/bold magenta]")
        console.print("[dim]Best Practice: Set default execution behaviors so you do not need to specify flags on every run. CLI flags (-b, -i, -L, -l, -v, -t) will always override these defaults.[/dim]")
        cur_bypass = bool(self.get("options.bypass", False))
        bypass_input = Confirm.ask("Bypass confirmation prompts and run non-interactively (-b)?", default=cur_bypass)
        self.set("options.bypass", "true" if bypass_input else "false")

        cur_daemon = bool(self.get("options.daemon", False))
        daemon_input = Confirm.ask("Enable background daemon watcher mode by default (-d)?", default=cur_daemon)
        self.set("options.daemon", "true" if daemon_input else "false")

        cur_interval = str(self.get("options.polling_interval") or "15")
        interval_input = Prompt.ask("Polling interval in minutes for daemon mode", default=cur_interval)
        try:
            int_val = int(interval_input.strip())
            if int_val >= 1:
                self.set("options.polling_interval", str(int_val))
            else:
                self.set("options.polling_interval", "15")
        except ValueError:
            self.set("options.polling_interval", "15")

        cur_ai = bool(self.get("options.ai", False))
        ai_input = Confirm.ask("Enable Cloud AI fallback by default for unrecognized filenames (-i)?", default=cur_ai)
        self.set("options.ai", "true" if ai_input else "false")

        cur_learn = bool(self.get("options.learn", False))
        learn_input = Confirm.ask("Enable AI keyword learning by default (save missing tags discovered by AI) (-L)?", default=cur_learn)
        self.set("options.learn", "true" if learn_input else "false")

        cur_prov = str(self.get("options.ai_provider") or "auto")
        prov_input = Prompt.ask("Default AI Provider (auto, gemini, groq, openrouter, cloudflare)", default=cur_prov)
        if prov_input.strip().lower() in ("auto", "gemini", "groq", "openrouter", "cloudflare"):
            self.set("options.ai_provider", prov_input.strip().lower())

        cur_log = bool(self.get("options.log", False))
        log_input = Confirm.ask("Write execution logs to daily log files instead of terminal (-l)?", default=cur_log)
        self.set("options.log", "true" if log_input else "false")

        cur_verbose = bool(self.get("options.verbose", False))
        verbose_input = Confirm.ask("Display detailed error logs and exception tracebacks (-v)?", default=cur_verbose)
        self.set("options.verbose", "true" if verbose_input else "false")

        cur_succ = bool(self.get("options.notify_on_success", False))
        notify_succ_input = Confirm.ask("Send an email notification on successful processing?", default=cur_succ)
        self.set("options.notify_on_success", "true" if notify_succ_input else "false")

        cur_err = bool(self.get("options.notify_on_error", True))
        notify_err_input = Confirm.ask("Send an email notification when an error occurs?", default=cur_err)
        self.set("options.notify_on_error", "true" if notify_err_input else "false")

        cur_tag = bool(self.get("options.notify_on_tag", False))
        notify_tag_input = Confirm.ask("Send an email notification when a new AI keyword tag is learned (-t)?", default=cur_tag)
        self.set("options.notify_on_tag", "true" if notify_tag_input else "false")

    def wizard_video(self, console=None):
        """Interactive setup for video stream FFmpeg tags."""
        from rich.console import Console
        from rich.prompt import Confirm
        console = console or Console()

        console.print("\n[bold magenta]🎞️ Video Stream Options (Requires FFmpeg)[/bold magenta]")
        console.print("[dim]Best Practice: Extracts video stream metadata to append clean tags (e.g. [4K] [1080p] [BluRay]). Requires 'ffprobe' installed in System PATH.[/dim]")
        cur_res = bool(self.get("options.resolution", False))
        res_input = Confirm.ask("Detect and append resolution tags (e.g., [4K], [FullHD])?", default=cur_res)
        self.set("options.resolution", "true" if res_input else "false")

        cur_qual = bool(self.get("options.quality", False))
        qual_input = Confirm.ask("Detect and append quality tags (e.g., [BluRay], [WEB-DL])?", default=cur_qual)
        self.set("options.quality", "true" if qual_input else "false")

        if (res_input or qual_input) and not shutil.which("ffprobe"):
            console.print("\n[bold red]❌ Error: 'ffprobe' (FFmpeg) was not found in your System PATH.[/bold red]")
            console.print("[yellow]Resolution and quality tags will fail to be detected until FFmpeg is installed.[/yellow]")
            console.print("[dim]Installation guide: docs/documentation.md#ffmpeg-setup[/dim]")

    def run_wizard(self, section: Optional[str] = None, interactive_menu: bool = False):
        """Interactive terminal configuration wizard that guides the user through setup steps."""
        from rich.console import Console

        console = Console()
        console.print("\n[bold cyan]==============================================[/bold cyan]")
        console.print("[bold cyan]   🎬 Media Organizer & Renamer Setup Wizard   [/bold cyan]")
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

        console.print(f"\n[bold green]✅ Configuration successfully saved to:[/bold green] [yellow]{self.config_path}[/yellow]\n")

    # Module-level property accessors
    @property
    def MOVIES_FOLDER(self):
        return self.get("paths.movies_folder")

    @property
    def TV_SHOWS_FOLDER(self):
        return self.get("paths.tv_shows_folder")

    @property
    def NOT_SORTED_MEDIA_FILES_FOLDER(self):
        return self.get("paths.not_sorted_media_files_folder")

    @property
    def TMDB_API_KEY(self):
        return self.get("api.tmdb_api_key")

    @property
    def GEMINI_API_KEY(self):
        return self.get("api.gemini_api_key")

    @property
    def MAIL(self):
        return self.get("mail.mail")

    @MAIL.setter
    def MAIL(self, value):
        if value is None:
            self.unset("mail.mail")
        else:
            self.set("mail.mail", str(value))

    @property
    def MAIL_PSWD(self):
        return self.get("mail.mail_pswd")

    @MAIL_PSWD.setter
    def MAIL_PSWD(self, value):
        if value is None:
            self.unset("mail.mail_pswd")
        else:
            self.set("mail.mail_pswd", str(value))

    @property
    def NOTIFY_ON_SUCCESS(self) -> bool:
        return bool(self.get("options.notify_on_success", False))

    @NOTIFY_ON_SUCCESS.setter
    def NOTIFY_ON_SUCCESS(self, value):
        self.set("options.notify_on_success", "true" if value else "false")

    @property
    def NOTIFY_ON_ERROR(self) -> bool:
        return bool(self.get("options.notify_on_error", True))

    @NOTIFY_ON_ERROR.setter
    def NOTIFY_ON_ERROR(self, value):
        self.set("options.notify_on_error", "true" if value else "false")

    @property
    def NOTIFY_ON_TAG(self) -> bool:
        return bool(self.get("options.notify_on_tag", False))

    @NOTIFY_ON_TAG.setter
    def NOTIFY_ON_TAG(self, value):
        self.set("options.notify_on_tag", "true" if value else "false")

    @property
    def BYPASS(self) -> bool:
        return bool(self.get("options.bypass", False))

    @BYPASS.setter
    def BYPASS(self, value):
        self.set("options.bypass", "true" if value else "false")

    @property
    def AI(self) -> bool:
        return bool(self.get("options.ai", False))

    @AI.setter
    def AI(self, value):
        self.set("options.ai", "true" if value else "false")

    @property
    def LEARN(self) -> bool:
        return bool(self.get("options.learn", False))

    @LEARN.setter
    def LEARN(self, value):
        self.set("options.learn", "true" if value else "false")

    @property
    def LOG(self) -> bool:
        return bool(self.get("options.log", False))

    @LOG.setter
    def LOG(self, value):
        self.set("options.log", "true" if value else "false")

    @property
    def VERBOSE(self) -> bool:
        return bool(self.get("options.verbose", False))

    @VERBOSE.setter
    def VERBOSE(self, value):
        self.set("options.verbose", "true" if value else "false")

    @property
    def RESOLUTION(self):
        return bool(self.get("options.resolution", False))

    @property
    def QUALITY(self):
        return bool(self.get("options.quality", False))

    @property
    def DAEMON(self) -> bool:
        return bool(self.get("options.daemon", False))

    @DAEMON.setter
    def DAEMON(self, value):
        self.set("options.daemon", "true" if value else "false")

    @property
    def POLLING_INTERVAL(self) -> int:
        val = self.get("options.polling_interval", 15)
        try:
            val_int = int(val)
            return val_int if val_int >= 1 else 15
        except (ValueError, TypeError):
            return 15

    @POLLING_INTERVAL.setter
    def POLLING_INTERVAL(self, value):
        self.set("options.polling_interval", str(value))

    @property
    def GROQ_API_KEY(self):
        return self.get("api.groq_api_key")

    @GROQ_API_KEY.setter
    def GROQ_API_KEY(self, value):
        if value is None:
            self.unset("api.groq_api_key")
        else:
            self.set("api.groq_api_key", str(value))

    @property
    def OPENROUTER_API_KEY(self):
        return self.get("api.openrouter_api_key")

    @OPENROUTER_API_KEY.setter
    def OPENROUTER_API_KEY(self, value):
        if value is None:
            self.unset("api.openrouter_api_key")
        else:
            self.set("api.openrouter_api_key", str(value))

    @property
    def CLOUDFLARE_API_TOKEN(self):
        return self.get("api.cloudflare_api_token")

    @CLOUDFLARE_API_TOKEN.setter
    def CLOUDFLARE_API_TOKEN(self, value):
        if value is None:
            self.unset("api.cloudflare_api_token")
        else:
            self.set("api.cloudflare_api_token", str(value))

    @property
    def CLOUDFLARE_ACCOUNT_ID(self):
        return self.get("api.cloudflare_account_id")

    @CLOUDFLARE_ACCOUNT_ID.setter
    def CLOUDFLARE_ACCOUNT_ID(self, value):
        if value is None:
            self.unset("api.cloudflare_account_id")
        else:
            self.set("api.cloudflare_account_id", str(value))

    @property
    def AI_PROVIDER(self) -> str:
        val = self.get("options.ai_provider", "auto")
        return str(val).strip().lower() if val else "auto"

    @AI_PROVIDER.setter
    def AI_PROVIDER(self, value):
        self.set("options.ai_provider", str(value).strip().lower())

    @property
    def TMDB_MIN_CONFIDENCE(self) -> float:
        val = self.get("options.tmdb_min_confidence", 0.75)
        try:
            val_f = float(val)
            return val_f if 0.0 <= val_f <= 1.0 else 0.75
        except (ValueError, TypeError):
            return 0.75

    @TMDB_MIN_CONFIDENCE.setter
    def TMDB_MIN_CONFIDENCE(self, value):
        self.set("options.tmdb_min_confidence", str(value))

    @property
    def AI_MIN_CONFIDENCE(self) -> float:
        val = self.get("options.ai_min_confidence", 0.70)
        try:
            val_f = float(val)
            return val_f if 0.0 <= val_f <= 1.0 else 0.70
        except (ValueError, TypeError):
            return 0.70

    @AI_MIN_CONFIDENCE.setter
    def AI_MIN_CONFIDENCE(self, value):
        self.set("options.ai_min_confidence", str(value))


# Singleton instance
config = ConfigManager()
