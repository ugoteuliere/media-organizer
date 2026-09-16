import os
import tkinter as tk
from unittest.mock import MagicMock, patch
import pytest

from src.config import ConfigManager
from src.gui import ConfigGUI, launch_config_gui
from src import ui, api, mail


@pytest.fixture(autouse=True)
def preserve_global_credentials():
    """Ensure tests in test_gui do not permanently overwrite module-level credentials."""
    orig_tmdb = getattr(api, "TMDB_API_KEY", None)
    orig_gemini = getattr(api, "GEMINI_API_KEY", None)
    orig_groq = getattr(api, "GROQ_API_KEY", None)
    orig_openrouter = getattr(api, "OPENROUTER_API_KEY", None)
    orig_cf_tok = getattr(api, "CLOUDFLARE_API_TOKEN", None)
    orig_cf_acc = getattr(api, "CLOUDFLARE_ACCOUNT_ID", None)
    orig_mail = getattr(mail, "MAIL", None)
    orig_mail_pswd = getattr(mail, "MAIL_PSWD", None)
    yield
    api.TMDB_API_KEY = orig_tmdb
    api.GEMINI_API_KEY = orig_gemini
    api.GROQ_API_KEY = orig_groq
    api.OPENROUTER_API_KEY = orig_openrouter
    api.CLOUDFLARE_API_TOKEN = orig_cf_tok
    api.CLOUDFLARE_ACCOUNT_ID = orig_cf_acc
    mail.MAIL = orig_mail
    mail.MAIL_PSWD = orig_mail_pswd


@pytest.fixture
def temp_cm(tmp_path):
    ini_file = tmp_path / "gui_config.ini"
    cm = ConfigManager(custom_path=str(ini_file))
    cm.set("paths.movies_folder", "D:/Movies")
    cm.set("paths.tv_shows_folder", "D:/TV")
    cm.set("paths.not_sorted_media_files_folder", "D:/Downloads")
    cm.set("api.tmdb_api_key", "tmdb_test_123")
    cm.set("api.gemini_api_key", "gemini_test_123")
    cm.set("api.groq_api_key", "groq_test_123")
    cm.set("api.openrouter_api_key", "openrouter_test_123")
    cm.set("api.cloudflare_api_token", "cf_tok_123")
    cm.set("api.cloudflare_account_id", "cf_acc_123")
    cm.set("options.ai_provider", "groq")
    cm.set("options.tmdb_min_confidence", "0.80")
    cm.set("options.ai_min_confidence", "0.75")
    cm.set("options.resolution", "true")
    cm.set("options.quality", "true")
    cm.set("options.bypass", "true")
    cm.set("options.daemon", "true")
    cm.set("options.polling_interval", "20")
    cm.set("options.ai", "true")
    cm.set("options.learn", "true")
    cm.set("options.log", "true")
    cm.set("options.verbose", "true")
    cm.set("mail.mail", "test@gmail.com")
    cm.set("mail.mail_pswd", "abcdefghijklmnop")
    cm.set("options.notify_on_success", "true")
    cm.set("options.notify_on_error", "true")
    cm.set("options.notify_on_tag", "true")
    return cm


@pytest.fixture(scope="module")
def tk_root():
    """Creates a headless hidden Tk instance and ensures cleanup."""
    try:
        root = tk.Tk()
        root.withdraw()
        yield root
        try:
            root.destroy()
        except Exception:
            pass
    except tk.TclError:
        pytest.skip("Tkinter display not available in current environment")


def test_config_gui_init_and_load(tk_root, temp_cm):
    app = ConfigGUI(tk_root, cm=temp_cm)

    # Verify loaded values
    assert app.var_movies.get() == "D:/Movies"
    assert app.var_tv.get() == "D:/TV"
    assert app.var_downloads.get() == "D:/Downloads"
    assert app.var_tmdb.get() == "tmdb_test_123"
    assert app.var_gemini.get() == "gemini_test_123"
    assert app.var_groq.get() == "groq_test_123"
    assert app.var_openrouter.get() == "openrouter_test_123"
    assert app.var_cf_tok.get() == "cf_tok_123"
    assert app.var_cf_acc.get() == "cf_acc_123"
    assert app.var_ai_provider.get() == "groq"
    assert app.var_tmdb_conf.get() == "0.8"
    assert app.var_ai_conf.get() == "0.75"
    assert app.var_resolution.get() is True
    assert app.var_quality.get() is True
    assert app.var_bypass.get() is True
    assert app.var_daemon.get() is True
    assert app.var_interval.get() == "20"
    assert app.var_ai.get() is True
    assert app.var_learn.get() is True
    assert app.var_log.get() is True
    assert app.var_verbose.get() is True
    assert app.var_mail.get() == "test@gmail.com"
    assert app.var_mail_pswd.get() == "abcdefghijklmnop"
    assert app.var_notify_success.get() is True
    assert app.var_notify_error.get() is True
    assert app.var_notify_tag.get() is True

    # Test status color reactivity
    app.var_status.set("Saved successfully")
    app.var_status.set("Failed with error")
    app.var_status.set("Testing connection...")
    app.var_status.set("Normal status")

    # Test slider handlers
    app._on_tmdb_slider(0.85)
    assert app.var_tmdb_conf.get() == "0.85"
    app._on_ai_slider(0.90)
    assert app.var_ai_conf.get() == "0.90"

    # Test secret visibility toggle
    app.var_show_secrets.set(True)
    app._toggle_secret_visibility()
    app.var_show_secrets.set(False)
    app._toggle_secret_visibility()

    # Test tab navigation
    app._select_tab("api")
    app._select_tab("options")
    app._select_tab("email")
    app._select_tab("paths")
    app._select_tab("unknown_tab")

    # Test load with invalid confidence values from config file
    temp_cm.parser.set("options", "tmdb_min_confidence", "invalid")
    temp_cm.parser.set("options", "ai_min_confidence", "invalid")
    app.load_values()
    assert app.var_tmdb_conf.get() == "invalid"
    assert app.var_ai_conf.get() == "invalid"


def test_config_gui_save_values(tk_root, temp_cm):
    app = ConfigGUI(tk_root, cm=temp_cm)

    # Modify values in UI
    app.var_movies.set("E:/NewMovies")
    app.var_ai_provider.set("cloudflare")
    app.var_tmdb_conf.set("0.85")
    app.var_ai_conf.set("0.80")
    app.var_resolution.set(False)
    app.var_interval.set("30")

    with patch("tkinter.messagebox.showinfo") as mock_info:
        app.save_values()
        mock_info.assert_called_once()

    # Verify saved back to ConfigManager
    assert temp_cm.get("paths.movies_folder") == "E:/NewMovies"
    assert temp_cm.get("options.ai_provider") == "cloudflare"
    assert float(temp_cm.get("options.tmdb_min_confidence")) == 0.85
    assert float(temp_cm.get("options.ai_min_confidence")) == 0.80
    assert temp_cm.get("options.resolution") is False
    assert int(temp_cm.get("options.polling_interval")) == 30

    # Save with invalid values to hit ValueError branches
    app.var_tmdb_conf.set("not_a_float")
    app.var_ai_conf.set("not_a_float")
    app.var_interval.set("not_an_int")
    with patch("tkinter.messagebox.showinfo"):
        app.save_values()


def test_config_gui_toggle_secret_visibility(tk_root, temp_cm):
    app = ConfigGUI(tk_root, cm=temp_cm)
    assert app.var_show_secrets.get() is False

    # Toggle to show
    app.var_show_secrets.set(True)
    app._toggle_secret_visibility()
    for ent in app.api_entries:
        assert ent.cget("show") == ""

    # Toggle to hide
    app.var_show_secrets.set(False)
    app._toggle_secret_visibility()
    for ent in app.api_entries:
        assert ent.cget("show") == "*"


def test_config_gui_browse_folder(tk_root, temp_cm):
    app = ConfigGUI(tk_root, cm=temp_cm)
    with patch("tkinter.filedialog.askdirectory", return_value="D:/SelectedByDialog"):
        app._browse_folder(app.var_movies, "Select Movies")
        assert app.var_movies.get() == "D:/SelectedByDialog"

    # Cancelled dialog returns empty
    with patch("tkinter.filedialog.askdirectory", return_value=""):
        app._browse_folder(app.var_movies, "Select Movies")
        assert app.var_movies.get() == "D:/SelectedByDialog"


def test_config_gui_test_tmdb(tk_root, temp_cm):
    app = ConfigGUI(tk_root, cm=temp_cm)

    # 1. Empty key warning
    app.var_tmdb.set("")
    with patch("tkinter.messagebox.showwarning") as mock_warn:
        app._test_tmdb()
        mock_warn.assert_called_once()

    # 2. Successful query
    app.var_tmdb.set("valid_tmdb")
    with (
        patch("src.api.api_call", return_value=(True, "Inception", "2010", "en")),
        patch("tkinter.messagebox.showinfo") as mock_info,
    ):
        app._test_tmdb()
        mock_info.assert_called_once()
        assert "Inception" in mock_info.call_args[0][1]

    # 3. Query returned false
    with (
        patch("src.api.api_call", return_value=(False, None, None, None)),
        patch("tkinter.messagebox.showerror") as mock_err,
    ):
        app._test_tmdb()
        mock_err.assert_called_once()

    # 4. Exception
    with (
        patch("src.api.api_call", side_effect=RuntimeError("Network down")),
        patch("tkinter.messagebox.showerror") as mock_err,
    ):
        app._test_tmdb()
        mock_err.assert_called_once()


def test_config_gui_test_provider_api(tk_root, temp_cm):
    app = ConfigGUI(tk_root, cm=temp_cm)
    mock_batch_resp = MagicMock()
    item = MagicMock()
    item.title = "Test Movie"
    item.year = "2022"
    item.confidence_score = 0.95
    mock_batch_resp.items = [item]

    # 1. Gemini
    app.var_gemini.set("")
    with patch("tkinter.messagebox.showwarning") as mock_warn:
        app._test_provider_api("gemini")
        mock_warn.assert_called_once()

    app.var_gemini.set("g_key")
    with (
        patch("src.api.call_gemini_batch", return_value=mock_batch_resp),
        patch("tkinter.messagebox.showinfo") as mock_info,
    ):
        app._test_provider_api("gemini")
        mock_info.assert_called_once()

    # 2. Groq
    app.var_groq.set("")
    with patch("tkinter.messagebox.showwarning") as mock_warn:
        app._test_provider_api("groq")
        mock_warn.assert_called_once()

    app.var_groq.set("gr_key")
    with (
        patch("src.api.call_groq_batch", return_value=mock_batch_resp),
        patch("tkinter.messagebox.showinfo") as mock_info,
    ):
        app._test_provider_api("groq")
        mock_info.assert_called_once()

    # 3. OpenRouter
    app.var_openrouter.set("")
    with patch("tkinter.messagebox.showwarning") as mock_warn:
        app._test_provider_api("openrouter")
        mock_warn.assert_called_once()

    app.var_openrouter.set("or_key")
    with (
        patch("src.api.call_openrouter_batch", return_value=mock_batch_resp),
        patch("tkinter.messagebox.showinfo") as mock_info,
    ):
        app._test_provider_api("openrouter")
        mock_info.assert_called_once()

    # 4. Cloudflare
    app.var_cf_tok.set("")
    with patch("tkinter.messagebox.showwarning") as mock_warn:
        app._test_provider_api("cloudflare")
        mock_warn.assert_called_once()

    app.var_cf_tok.set("tok")
    app.var_cf_acc.set("acc")
    with (
        patch("src.api.call_cloudflare_batch", return_value=mock_batch_resp),
        patch("tkinter.messagebox.showinfo") as mock_info,
    ):
        app._test_provider_api("cloudflare")
        mock_info.assert_called_once()

    # 5. Empty items response
    empty_resp = MagicMock()
    empty_resp.items = []
    with (
        patch("src.api.call_groq_batch", return_value=empty_resp),
        patch("tkinter.messagebox.showwarning") as mock_warn,
    ):
        app._test_provider_api("groq")
        mock_warn.assert_called_once()

    # 6. Exception
    with (
        patch("src.api.call_groq_batch", side_effect=RuntimeError("Connection timeout")),
        patch("tkinter.messagebox.showerror") as mock_err,
    ):
        app._test_provider_api("groq")
        mock_err.assert_called_once()

    # Unknown provider
    app._test_provider_api("unknown_provider")


def test_config_gui_send_test_email(tk_root, temp_cm):
    app = ConfigGUI(tk_root, cm=temp_cm)

    # 1. Missing credentials
    app.var_mail.set("")
    with patch("tkinter.messagebox.showwarning") as mock_warn:
        app._send_test_email()
        mock_warn.assert_called_once()

    # 2. Success
    app.var_mail.set("user@gmail.com")
    app.var_mail_pswd.set("password123")
    mock_smtp = MagicMock()
    with patch("smtplib.SMTP", return_value=mock_smtp), patch("tkinter.messagebox.showinfo") as mock_info:
        app._send_test_email()
        mock_info.assert_called_once()
        mock_smtp.starttls.assert_called_once()
        mock_smtp.login.assert_called_once_with("user@gmail.com", "password123")
        mock_smtp.send_message.assert_called_once()
        mock_smtp.quit.assert_called_once()

    # 3. SMTP failure
    with (
        patch("smtplib.SMTP", side_effect=Exception("SMTP auth error")),
        patch("tkinter.messagebox.showerror") as mock_err,
    ):
        app._send_test_email()
        mock_err.assert_called_once()


def test_launch_config_gui():
    mock_ctk = MagicMock()
    with patch("customtkinter.CTk", return_value=mock_ctk), patch("src.gui.ConfigGUI"):
        assert launch_config_gui() is True
        mock_ctk.mainloop.assert_called_once()

    # TclError simulates headless environment
    with patch("customtkinter.CTk", side_effect=tk.TclError("no display name and no $DISPLAY environment variable")):
        assert launch_config_gui() is False


def test_config_run_gui_method():
    cm = ConfigManager()
    with patch("src.gui.launch_config_gui", return_value=True) as mock_launch:
        assert cm.run_gui() is True
        mock_launch.assert_called_once_with(cm)


def test_ui_handle_config_command_gui_flags():
    # 1. configure -g
    mock_args_configure_gui = MagicMock()
    mock_args_configure_gui.subcommand = "configure"
    mock_args_configure_gui.gui = True

    with patch("src.config.config.run_gui") as mock_gui:
        ui.handle_config_command(mock_args_configure_gui)
        mock_gui.assert_called_once()

    # 2. config -g
    mock_args_config_gui = MagicMock()
    mock_args_config_gui.subcommand = "config"
    mock_args_config_gui.gui = True

    with patch("src.config.config.run_gui") as mock_gui:
        ui.handle_config_command(mock_args_config_gui)
        mock_gui.assert_called_once()

    # 3. configure --paths
    mock_args_paths = MagicMock()
    mock_args_paths.subcommand = "configure"
    mock_args_paths.gui = False
    mock_args_paths.paths = True
    mock_args_paths.ai = False
    mock_args_paths.email = False
    mock_args_paths.options = False
    mock_args_paths.video = False
    mock_args_paths.full = False

    with patch("src.config.config.run_wizard") as mock_wiz:
        ui.handle_config_command(mock_args_paths)
        mock_wiz.assert_called_once_with(section="paths", interactive_menu=False)

    # 4. configure --ai
    mock_args_ai = MagicMock()
    mock_args_ai.subcommand = "configure"
    mock_args_ai.gui = False
    mock_args_ai.paths = False
    mock_args_ai.ai = True
    mock_args_ai.email = False
    mock_args_ai.options = False
    mock_args_ai.video = False
    mock_args_ai.full = False

    with patch("src.config.config.run_wizard") as mock_wiz:
        ui.handle_config_command(mock_args_ai)
        mock_wiz.assert_called_once_with(section="ai", interactive_menu=False)

    # 5. configure --email
    mock_args_email = MagicMock()
    mock_args_email.subcommand = "configure"
    mock_args_email.gui = False
    mock_args_email.paths = False
    mock_args_email.ai = False
    mock_args_email.email = True
    mock_args_email.options = False
    mock_args_email.video = False
    mock_args_email.full = False

    with patch("src.config.config.run_wizard") as mock_wiz:
        ui.handle_config_command(mock_args_email)
        mock_wiz.assert_called_once_with(section="email", interactive_menu=False)

    # 6. configure --options
    mock_args_opt = MagicMock()
    mock_args_opt.subcommand = "configure"
    mock_args_opt.gui = False
    mock_args_opt.paths = False
    mock_args_opt.ai = False
    mock_args_opt.email = False
    mock_args_opt.options = True
    mock_args_opt.video = False
    mock_args_opt.full = False

    with patch("src.config.config.run_wizard") as mock_wiz:
        ui.handle_config_command(mock_args_opt)
        mock_wiz.assert_called_once_with(section="options", interactive_menu=False)

    # 7. configure --video
    mock_args_vid = MagicMock()
    mock_args_vid.subcommand = "configure"
    mock_args_vid.gui = False
    mock_args_vid.paths = False
    mock_args_vid.ai = False
    mock_args_vid.email = False
    mock_args_vid.options = False
    mock_args_vid.video = True
    mock_args_vid.full = False

    with patch("src.config.config.run_wizard") as mock_wiz:
        ui.handle_config_command(mock_args_vid)
        mock_wiz.assert_called_once_with(section="video", interactive_menu=False)


def test_config_run_wizard_menu_options(tmp_path):
    ini_file = tmp_path / "menu_config.ini"
    cm = ConfigManager(custom_path=str(ini_file))

    orig_isdir = os.path.isdir

    def mock_isdir(p):
        return True if "D:/" in str(p) else orig_isdir(p)

    # Full setup wizard (runs all steps sequentially without category menu)
    with (
        patch(
            "rich.prompt.Prompt.ask",
            side_effect=["D:/F1", "D:/F2", "D:/F3", "k1", "k2", "k3", "k4", "k5", "k6", "m", "p", "15", "auto"],
        ),
        patch("rich.prompt.Confirm.ask", side_effect=[False] * 9 + [False, False]),
        patch("os.path.isdir", side_effect=mock_isdir),
    ):
        cm.run_wizard(interactive_menu=True)
        assert cm.get("paths.movies_folder") == "D:/F1"
        assert cm.get("api.tmdb_api_key") == "k1"
        assert cm.get("mail.mail") == "m"

    # Section direct calls
    with patch.object(cm, "wizard_paths") as mock_p:
        cm.run_wizard(section="paths")
        mock_p.assert_called_once()

    with patch.object(cm, "wizard_api") as mock_a:
        cm.run_wizard(section="ai")
        mock_a.assert_called_once()

    with patch.object(cm, "wizard_email") as mock_e:
        cm.run_wizard(section="email")
        mock_e.assert_called_once()

    with patch.object(cm, "wizard_options") as mock_o:
        cm.run_wizard(section="options")
        mock_o.assert_called_once()

    with patch.object(cm, "wizard_video") as mock_v:
        cm.run_wizard(section="video")
        mock_v.assert_called_once()
