"""
Modern Graphical Configuration Hub for Media Organizer & Renamer.
Built with CustomTkinter for sleek, rounded-corner UI inspired by GitHub Desktop & Adobe Creative Cloud.
"""

import os
import sys
import tkinter as tk
from tkinter import filedialog, messagebox
from typing import Optional, Any
import customtkinter as ctk

from src.config import config as global_config, ConfigManager
from src import api, mail

# Configure CustomTkinter dark theme defaults
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# Design Tokens (GitHub Dark & Adobe Dark Palette)
COLOR_CANVAS = "#0d1117"       # Main content canvas (GitHub dark base)
COLOR_SIDEBAR = "#161b22"      # Left navigation sidebar (Elevated slate)
COLOR_CARD = "#161b22"         # Content card panels
COLOR_BORDER = "#30363d"       # Clean subtle border
COLOR_INPUT = "#090d16"        # Dark input background
COLOR_TEXT_MAIN = "#f0f6fc"    # High-contrast primary text
COLOR_TEXT_MUTED = "#8b949e"   # Secondary descriptive text
COLOR_TEXT_HINT = "#6e7681"    # Subtle path & hint text
COLOR_ACCENT = "#58a6ff"       # Sky/Cyan accent
COLOR_NAV_ACTIVE = "#1f6feb"   # Active nav pill background
COLOR_NAV_HOVER = "#21262d"    # Inactive nav hover
COLOR_BTN_SEC = "#21262d"      # Secondary button surface
COLOR_BTN_SEC_HOVER = "#30363d"
COLOR_BTN_PRIMARY = "#238636"  # Primary Save button (GitHub Green)
COLOR_BTN_PRIMARY_HOVER = "#2ea043"
COLOR_BTN_TEST = "#172554"     # Test badge button surface
COLOR_BTN_TEST_BORDER = "#1f6feb"
COLOR_SUCCESS = "#3fb950"      # Green status
COLOR_ERROR = "#f85149"        # Red status
FONT_FAMILY = "Segoe UI"


class ConfigGUI:
    """Modern dark configuration window featuring rounded corners, smooth switches, and sidebar navigation."""

    def __init__(self, root: Any, cm: Optional[ConfigManager] = None):
        self.root = root
        self.cm = cm or global_config
        self.root.title("🎬 Media Organizer & Renamer — Configuration Hub")
        self.root.geometry("900x700")
        self.root.minsize(820, 620)

        # Apply root background
        try:
            self.root.configure(fg_color=COLOR_CANVAS)
        except Exception:
            self.root.configure(bg=COLOR_CANVAS)

        # Windows 10/11 native immersive dark titlebar
        if sys.platform == "win32":  # pragma: no cover
            try:
                import ctypes
                self.root.update_idletasks()
                hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
                DWMWA_USE_IMMERSIVE_DARK_MODE = 20
                value = ctypes.c_int(1)
                ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE, ctypes.byref(value), ctypes.sizeof(value)
                )
            except Exception:
                pass

        self._init_variables()
        self._build_ui()
        self.load_values()

    def _init_variables(self):
        """Initializes state variables for all configuration options."""
        # Paths
        self.var_movies = tk.StringVar()
        self.var_tv = tk.StringVar()
        self.var_downloads = tk.StringVar()

        # API Keys & Provider Options
        self.var_tmdb = tk.StringVar()
        self.var_gemini = tk.StringVar()
        self.var_groq = tk.StringVar()
        self.var_openrouter = tk.StringVar()
        self.var_cf_tok = tk.StringVar()
        self.var_cf_acc = tk.StringVar()
        self.var_ai_provider = tk.StringVar(value="auto")
        self.var_tmdb_conf = tk.StringVar(value="0.75")
        self.var_ai_conf = tk.StringVar(value="0.70")
        self.var_show_secrets = tk.BooleanVar(value=False)

        # Automation Options
        self.var_resolution = tk.BooleanVar(value=False)
        self.var_quality = tk.BooleanVar(value=False)
        self.var_bypass = tk.BooleanVar(value=False)
        self.var_daemon = tk.BooleanVar(value=False)
        self.var_interval = tk.StringVar(value="15")
        self.var_ai = tk.BooleanVar(value=False)
        self.var_learn = tk.BooleanVar(value=False)
        self.var_log = tk.BooleanVar(value=False)
        self.var_verbose = tk.BooleanVar(value=False)

        # Email Alerts
        self.var_mail = tk.StringVar()
        self.var_mail_pswd = tk.StringVar()
        self.var_notify_success = tk.BooleanVar(value=False)
        self.var_notify_error = tk.BooleanVar(value=True)
        self.var_notify_tag = tk.BooleanVar(value=False)

        # Reactive Status Indicator
        self.var_status = tk.StringVar(value="Ready")

        self.api_entries = []
        self.nav_buttons = {}

    def _on_status_change(self, *args):
        """Reactively colors the status indicator badge based on current state."""
        text = self.var_status.get().lower()
        if "saved" in text or "verified" in text or "sent" in text or "success" in text:
            color = COLOR_SUCCESS
        elif "error" in text or "failed" in text:
            color = COLOR_ERROR
        elif "testing" in text or "sending" in text:
            color = COLOR_ACCENT
        else:
            color = COLOR_TEXT_MUTED

        if getattr(self, "status_dot", None) is not None:
            self.status_dot.configure(text_color=color)
        if getattr(self, "status_label", None) is not None:
            self.status_label.configure(text_color=color)

    def _build_ui(self):
        """Constructs the sidebar navigation and modular content panels."""
        # 1. Left Sidebar Navigation
        self.sidebar = ctk.CTkFrame(
            self.root,
            width=230,
            corner_radius=0,
            fg_color=COLOR_SIDEBAR,
            border_width=1,
            border_color=COLOR_BORDER
        )
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)

        # Branding Header
        lbl_brand = ctk.CTkLabel(
            self.sidebar,
            text="🎬 Media Renamer",
            font=ctk.CTkFont(family=FONT_FAMILY, size=16, weight="bold"),
            text_color=COLOR_TEXT_MAIN
        )
        lbl_brand.pack(anchor="w", padx=20, pady=(22, 2))

        lbl_sub = ctk.CTkLabel(
            self.sidebar,
            text="Configuration Hub",
            font=ctk.CTkFont(family=FONT_FAMILY, size=11),
            text_color=COLOR_TEXT_MUTED
        )
        lbl_sub.pack(anchor="w", padx=20, pady=(0, 16))

        # Nav Buttons
        nav_items = [
            ("paths", "📁  Storage Folders"),
            ("api", "🤖  AI & API Providers"),
            ("options", "⚙️  Automation & Tags"),
            ("email", "📧  Email Alerts")
        ]

        for key, label in nav_items:
            btn = ctk.CTkButton(
                self.sidebar,
                text=label,
                anchor="w",
                height=38,
                corner_radius=8,
                font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
                fg_color="transparent",
                hover_color=COLOR_NAV_HOVER,
                text_color=COLOR_TEXT_MAIN,
                command=lambda k=key: self._select_tab(k)
            )
            btn.pack(fill="x", padx=12, pady=3)
            self.nav_buttons[key] = btn

        # Config File Path Pill at bottom of sidebar
        card_path = ctk.CTkFrame(
            self.sidebar,
            corner_radius=8,
            fg_color=COLOR_CANVAS,
            border_width=1,
            border_color=COLOR_BORDER
        )
        card_path.pack(side="bottom", fill="x", padx=12, pady=16)

        ctk.CTkLabel(
            card_path,
            text="Active Config",
            font=ctk.CTkFont(family=FONT_FAMILY, size=9, weight="bold"),
            text_color=COLOR_ACCENT
        ).pack(anchor="w", padx=10, pady=(6, 0))

        lbl_path_text = ctk.CTkLabel(
            card_path,
            text=str(self.cm.config_path),
            font=ctk.CTkFont(family=FONT_FAMILY, size=8),
            text_color=COLOR_TEXT_MUTED,
            wraplength=180,
            justify="left"
        )
        lbl_path_text.pack(anchor="w", padx=10, pady=(0, 6))

        # 2. Right Workspace Container
        self.right_container = ctk.CTkFrame(self.root, corner_radius=0, fg_color=COLOR_CANVAS)
        self.right_container.pack(side="right", fill="both", expand=True)

        # Header Title Bar
        self.header_frame = ctk.CTkFrame(self.right_container, height=60, corner_radius=0, fg_color="transparent")
        self.header_frame.pack(fill="x", padx=24, pady=(20, 8))

        self.lbl_title = ctk.CTkLabel(
            self.header_frame,
            text="Storage Directories",
            font=ctk.CTkFont(family=FONT_FAMILY, size=18, weight="bold"),
            text_color=COLOR_TEXT_MAIN
        )
        self.lbl_title.pack(anchor="w")

        self.lbl_desc = ctk.CTkLabel(
            self.header_frame,
            text="Configure your media directories. Folders can be local drives, external disks, or NAS shares.",
            font=ctk.CTkFont(family=FONT_FAMILY, size=11),
            text_color=COLOR_TEXT_MUTED,
            wraplength=600,
            justify="left"
        )
        self.lbl_desc.pack(anchor="w", pady=(2, 0))

        # Content Views (stacked inside scrollable frame)
        self.content_scroll = ctk.CTkScrollableFrame(
            self.right_container,
            corner_radius=12,
            fg_color="transparent"
        )
        self.content_scroll.pack(fill="both", expand=True, padx=24, pady=(0, 12))

        self.pages = {}
        self._build_paths_page()
        self._build_api_page()
        self._build_options_page()
        self._build_email_page()

        # 3. Bottom Action Footer Bar
        self.footer = ctk.CTkFrame(
            self.right_container,
            height=54,
            corner_radius=10,
            fg_color=COLOR_SIDEBAR,
            border_width=1,
            border_color=COLOR_BORDER
        )
        self.footer.pack(fill="x", padx=24, pady=(0, 16))
        self.footer.pack_propagate(False)

        # Status Badge on Left
        status_box = ctk.CTkFrame(self.footer, corner_radius=6, fg_color=COLOR_CANVAS, border_width=1, border_color=COLOR_BORDER)
        status_box.pack(side="left", padx=12, pady=10)

        self.status_dot = ctk.CTkLabel(status_box, text="●", font=ctk.CTkFont(size=10), text_color=COLOR_TEXT_MUTED)
        self.status_dot.pack(side="left", padx=(8, 4), pady=4)

        self.status_label = ctk.CTkLabel(
            status_box,
            textvariable=self.var_status,
            font=ctk.CTkFont(family=FONT_FAMILY, size=10, weight="bold"),
            text_color=COLOR_TEXT_MUTED
        )
        self.status_label.pack(side="left", padx=(0, 10), pady=4)
        self.var_status.trace_add("write", self._on_status_change)

        # Action Buttons on Right
        btn_save = ctk.CTkButton(
            self.footer,
            text="💾 Save Configuration",
            font=ctk.CTkFont(family=FONT_FAMILY, size=11, weight="bold"),
            corner_radius=8,
            width=160,
            height=32,
            fg_color=COLOR_BTN_PRIMARY,
            hover_color=COLOR_BTN_PRIMARY_HOVER,
            command=self.save_values
        )
        btn_save.pack(side="right", padx=(4, 12), pady=10)

        btn_reload = ctk.CTkButton(
            self.footer,
            text="🔄 Reload",
            font=ctk.CTkFont(family=FONT_FAMILY, size=11),
            corner_radius=8,
            width=90,
            height=32,
            fg_color=COLOR_BTN_SEC,
            hover_color=COLOR_BTN_SEC_HOVER,
            command=self.load_values
        )
        btn_reload.pack(side="right", padx=4, pady=10)

        btn_close = ctk.CTkButton(
            self.footer,
            text="Close",
            font=ctk.CTkFont(family=FONT_FAMILY, size=11),
            corner_radius=8,
            width=70,
            height=32,
            fg_color=COLOR_BTN_SEC,
            hover_color=COLOR_BTN_SEC_HOVER,
            command=self.root.destroy
        )
        btn_close.pack(side="right", padx=4, pady=10)

        # Default to paths tab
        self._select_tab("paths")

    def _select_tab(self, tab_key: str):
        """Switches the active content view and highlights corresponding sidebar item."""
        titles = {
            "paths": ("Storage Directories", "Configure your media directories. Folders can be local drives, external disks, or NAS network shares."),
            "api": ("API Keys & Cloud AI", "TMDB API key is required for official metadata. Configured Cloud AI providers act as intelligent fallbacks."),
            "options": ("Automation & Video Tags", "Configure FFmpeg stream inspection, background monitoring daemon, and diagnostic logging."),
            "email": ("Email Alerts & SMTP", "Configure optional Gmail SMTP delivery for headless runs and critical processing alerts.")
        }

        title, desc = titles.get(tab_key, ("", ""))
        self.lbl_title.configure(text=title)
        self.lbl_desc.configure(text=desc)

        # Update button highlights
        for k, btn in self.nav_buttons.items():
            if k == tab_key:
                btn.configure(fg_color=COLOR_NAV_ACTIVE, hover_color=COLOR_NAV_ACTIVE)
            else:
                btn.configure(fg_color="transparent", hover_color=COLOR_NAV_HOVER)

        # Show target page
        for k, page in self.pages.items():
            if k == tab_key:
                page.pack(fill="x", expand=True)
            else:
                page.pack_forget()

    # --------------------------------------------------------------------------
    # Page 1: Paths
    # --------------------------------------------------------------------------
    def _build_paths_page(self):
        page = ctk.CTkFrame(self.content_scroll, fg_color="transparent")
        self.pages["paths"] = page

        def make_path_card(parent, title_text, var, browse_title):
            card = ctk.CTkFrame(parent, corner_radius=12, fg_color=COLOR_CARD, border_width=1, border_color=COLOR_BORDER)
            card.pack(fill="x", pady=8)

            ctk.CTkLabel(
                card,
                text=title_text,
                font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
                text_color=COLOR_ACCENT
            ).pack(anchor="w", padx=16, pady=(12, 6))

            row = ctk.CTkFrame(card, fg_color="transparent")
            row.pack(fill="x", padx=16, pady=(0, 14))

            entry = ctk.CTkEntry(
                row,
                textvariable=var,
                height=36,
                corner_radius=8,
                fg_color=COLOR_INPUT,
                border_color=COLOR_BORDER,
                text_color=COLOR_TEXT_MAIN
            )
            entry.pack(side="left", fill="x", expand=True, padx=(0, 8))

            btn = ctk.CTkButton(
                row,
                text="Browse...",
                width=90,
                height=36,
                corner_radius=8,
                font=ctk.CTkFont(family=FONT_FAMILY, size=11, weight="bold"),
                fg_color=COLOR_BTN_SEC,
                hover_color=COLOR_BTN_SEC_HOVER,
                text_color=COLOR_ACCENT,
                command=lambda: self._browse_folder(var, browse_title)
            )
            btn.pack(side="right")
            return entry

        self.entry_movies = make_path_card(page, "Movies Library Folder (Destination)", self.var_movies, "Select Movies Folder")
        self.entry_tv = make_path_card(page, "TV Shows Library Folder (Destination)", self.var_tv, "Select TV Shows Folder")
        self.entry_downloads = make_path_card(page, "Unsorted Incoming Downloads Folder (Source)", self.var_downloads, "Select Downloads Folder")

    def _browse_folder(self, var: tk.StringVar, title: str):
        chosen = filedialog.askdirectory(title=title, mustexist=False)
        if chosen:
            var.set(chosen)

    # --------------------------------------------------------------------------
    # Page 2: API & Cloud AI
    # --------------------------------------------------------------------------
    def _build_api_page(self):
        page = ctk.CTkFrame(self.content_scroll, fg_color="transparent")
        self.pages["api"] = page

        # Show / Hide Secrets Pill Switch
        top_bar = ctk.CTkFrame(page, fg_color="transparent")
        top_bar.pack(fill="x", pady=(0, 6))

        sw_secrets = ctk.CTkSwitch(
            top_bar,
            text="Show Secret Keys",
            variable=self.var_show_secrets,
            command=self._toggle_secret_visibility,
            progress_color=COLOR_NAV_ACTIVE,
            font=ctk.CTkFont(family=FONT_FAMILY, size=11),
            text_color=COLOR_TEXT_MUTED
        )
        sw_secrets.pack(side="right")

        # Credentials Card
        card_creds = ctk.CTkFrame(page, corner_radius=12, fg_color=COLOR_CARD, border_width=1, border_color=COLOR_BORDER)
        card_creds.pack(fill="x", pady=6)

        ctk.CTkLabel(
            card_creds,
            text="🔑 API Authentication Keys",
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            text_color=COLOR_ACCENT
        ).pack(anchor="w", padx=16, pady=(12, 8))

        def make_key_row(parent, label_text, var, test_callback=None):
            row = ctk.CTkFrame(parent, fg_color="transparent")
            row.pack(fill="x", padx=16, pady=5)

            lbl = ctk.CTkLabel(
                row,
                text=label_text,
                width=200,
                anchor="w",
                font=ctk.CTkFont(family=FONT_FAMILY, size=11),
                text_color=COLOR_TEXT_MAIN
            )
            lbl.pack(side="left")

            ent = ctk.CTkEntry(
                row,
                textvariable=var,
                show="*",
                height=34,
                corner_radius=8,
                fg_color=COLOR_INPUT,
                border_color=COLOR_BORDER,
                text_color=COLOR_TEXT_MAIN
            )
            ent.pack(side="left", fill="x", expand=True, padx=(0, 8))
            self.api_entries.append(ent)

            if test_callback:
                btn = ctk.CTkButton(
                    row,
                    text="Test",
                    width=65,
                    height=32,
                    corner_radius=8,
                    font=ctk.CTkFont(family=FONT_FAMILY, size=10, weight="bold"),
                    fg_color=COLOR_BTN_TEST,
                    hover_color="#1e3a8a",
                    border_width=1,
                    border_color=COLOR_BTN_TEST_BORDER,
                    text_color=COLOR_ACCENT,
                    command=test_callback
                )
                btn.pack(side="right")
            return ent

        make_key_row(card_creds, "TMDB API Key (v3/v4):", self.var_tmdb, self._test_tmdb)
        make_key_row(card_creds, "Google Gemini API Key:", self.var_gemini, lambda: self._test_provider_api("gemini"))
        make_key_row(card_creds, "Groq Cloud API Key:", self.var_groq, lambda: self._test_provider_api("groq"))
        make_key_row(card_creds, "OpenRouter API Key:", self.var_openrouter, lambda: self._test_provider_api("openrouter"))
        make_key_row(card_creds, "Cloudflare Workers AI Token:", self.var_cf_tok)
        make_key_row(card_creds, "Cloudflare Account ID:", self.var_cf_acc, lambda: self._test_provider_api("cloudflare"))

        ctk.CTkLabel(card_creds, text="").pack(pady=4)

        # Orchestration & Thresholds Card
        card_orch = ctk.CTkFrame(page, corner_radius=12, fg_color=COLOR_CARD, border_width=1, border_color=COLOR_BORDER)
        card_orch.pack(fill="x", pady=10)

        ctk.CTkLabel(
            card_orch,
            text="⚙️ Orchestration & Confidence Thresholds",
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            text_color=COLOR_ACCENT
        ).pack(anchor="w", padx=16, pady=(12, 8))

        # Default Provider Row
        r1 = ctk.CTkFrame(card_orch, fg_color="transparent")
        r1.pack(fill="x", padx=16, pady=5)
        ctk.CTkLabel(r1, text="Default AI Provider:", width=200, anchor="w", font=ctk.CTkFont(family=FONT_FAMILY, size=11), text_color=COLOR_TEXT_MAIN).pack(side="left")
        cbo = ctk.CTkOptionMenu(
            r1,
            variable=self.var_ai_provider,
            values=["auto", "gemini", "groq", "openrouter", "cloudflare"],
            height=32,
            corner_radius=8,
            fg_color=COLOR_BTN_SEC,
            button_color=COLOR_BORDER,
            text_color=COLOR_TEXT_MAIN,
            dropdown_fg_color=COLOR_CARD
        )
        cbo.pack(side="left")
        ctk.CTkLabel(r1, text="('auto' fails over across all configured providers)", font=ctk.CTkFont(size=10), text_color=COLOR_TEXT_MUTED).pack(side="left", padx=10)

        # TMDB Confidence Slider Row
        r2 = ctk.CTkFrame(card_orch, fg_color="transparent")
        r2.pack(fill="x", padx=16, pady=6)
        ctk.CTkLabel(r2, text="TMDB Min Confidence:", width=200, anchor="w", font=ctk.CTkFont(family=FONT_FAMILY, size=11), text_color=COLOR_TEXT_MAIN).pack(side="left")

        self.lbl_tmdb_conf = ctk.CTkLabel(r2, text="75% (0.75)", width=80, anchor="w", font=ctk.CTkFont(family=FONT_FAMILY, size=11, weight="bold"), text_color=COLOR_ACCENT)
        self.lbl_tmdb_conf.pack(side="right")

        self.slider_tmdb = ctk.CTkSlider(
            r2,
            from_=0.10,
            to=1.00,
            number_of_steps=18,
            corner_radius=6,
            progress_color=COLOR_NAV_ACTIVE,
            button_color=COLOR_ACCENT,
            command=self._on_tmdb_slider
        )
        self.slider_tmdb.pack(side="left", fill="x", expand=True, padx=(0, 10))

        # AI Confidence Slider Row
        r3 = ctk.CTkFrame(card_orch, fg_color="transparent")
        r3.pack(fill="x", padx=16, pady=6)
        ctk.CTkLabel(r3, text="AI Min Confidence:", width=200, anchor="w", font=ctk.CTkFont(family=FONT_FAMILY, size=11), text_color=COLOR_TEXT_MAIN).pack(side="left")

        self.lbl_ai_conf = ctk.CTkLabel(r3, text="70% (0.70)", width=80, anchor="w", font=ctk.CTkFont(family=FONT_FAMILY, size=11, weight="bold"), text_color=COLOR_ACCENT)
        self.lbl_ai_conf.pack(side="right")

        self.slider_ai = ctk.CTkSlider(
            r3,
            from_=0.10,
            to=1.00,
            number_of_steps=18,
            corner_radius=6,
            progress_color=COLOR_NAV_ACTIVE,
            button_color=COLOR_ACCENT,
            command=self._on_ai_slider
        )
        self.slider_ai.pack(side="left", fill="x", expand=True, padx=(0, 10))

        ctk.CTkLabel(card_orch, text="").pack(pady=4)

    def _on_tmdb_slider(self, val: float):
        rounded = round(float(val), 2)
        self.var_tmdb_conf.set(f"{rounded:.2f}")
        self.lbl_tmdb_conf.configure(text=f"{int(rounded * 100)}% ({rounded:.2f})")

    def _on_ai_slider(self, val: float):
        rounded = round(float(val), 2)
        self.var_ai_conf.set(f"{rounded:.2f}")
        self.lbl_ai_conf.configure(text=f"{int(rounded * 100)}% ({rounded:.2f})")

    def _toggle_secret_visibility(self):
        show_char = "" if self.var_show_secrets.get() else "*"
        for ent in self.api_entries:
            ent.configure(show=show_char)

    def _test_tmdb(self):
        key = self.var_tmdb.get().strip()
        if not key:
            messagebox.showwarning("TMDB Test", "Please enter a TMDB API Key first.")
            return
        self.var_status.set("Testing TMDB API...")
        self.root.update_idletasks()
        old_key = getattr(api, "TMDB_API_KEY", None)
        try:
            api.TMDB_API_KEY = key
            success, title, year, _ = api.api_call("Inception", "2010", "en-US", "movie")
            if success:
                messagebox.showinfo("TMDB Test Success", f"✅ TMDB connection successful!\nRetrieved: {title} ({year})")
                self.var_status.set("TMDB connection verified.")
            else:
                messagebox.showerror("TMDB Test Failed", "❌ TMDB responded but query did not match.")
                self.var_status.set("TMDB query failed.")
        except Exception as e:
            messagebox.showerror("TMDB Test Error", f"❌ Connection failed:\n{e}")
            self.var_status.set("TMDB error.")
        finally:
            api.TMDB_API_KEY = old_key

    def _test_provider_api(self, provider: str):
        self.var_status.set(f"Testing {provider.capitalize()} AI...")
        self.root.update_idletasks()

        test_item = [{
            'File': 'Inception.2010.1080p.mkv',
            'Folder': 'Movies',
            'Path': '/movies/Inception.2010.1080p.mkv',
            'Clean': 'Inception',
            'Parse': 'Inception',
            'Media': 'movie'
        }]

        keys_to_restore = []
        try:
            if provider == "gemini":
                key = self.var_gemini.get().strip()
                if not key:
                    messagebox.showwarning("Gemini Test", "Please enter a Gemini API Key first.")
                    return
                keys_to_restore.append(("GEMINI_API_KEY", getattr(api, "GEMINI_API_KEY", None)))
                api.GEMINI_API_KEY = key
                call_func = api.call_gemini_batch
            elif provider == "groq":
                key = self.var_groq.get().strip()
                if not key:
                    messagebox.showwarning("Groq Test", "Please enter a Groq API Key first.")
                    return
                keys_to_restore.append(("GROQ_API_KEY", getattr(api, "GROQ_API_KEY", None)))
                api.GROQ_API_KEY = key
                call_func = api.call_groq_batch
            elif provider == "openrouter":
                key = self.var_openrouter.get().strip()
                if not key:
                    messagebox.showwarning("OpenRouter Test", "Please enter an OpenRouter API Key first.")
                    return
                keys_to_restore.append(("OPENROUTER_API_KEY", getattr(api, "OPENROUTER_API_KEY", None)))
                api.OPENROUTER_API_KEY = key
                call_func = api.call_openrouter_batch
            elif provider == "cloudflare":
                tok = self.var_cf_tok.get().strip()
                acc = self.var_cf_acc.get().strip()
                if not tok or not acc:
                    messagebox.showwarning("Cloudflare Test", "Please enter both Cloudflare Token and Account ID.")
                    return
                keys_to_restore.append(("CLOUDFLARE_API_TOKEN", getattr(api, "CLOUDFLARE_API_TOKEN", None)))
                keys_to_restore.append(("CLOUDFLARE_ACCOUNT_ID", getattr(api, "CLOUDFLARE_ACCOUNT_ID", None)))
                api.CLOUDFLARE_API_TOKEN = tok
                api.CLOUDFLARE_ACCOUNT_ID = acc
                call_func = api.call_cloudflare_batch
            else:
                return

            try:
                resp = call_func(test_item)
            except Exception as e:
                messagebox.showerror(f"{provider.capitalize()} Error", f"❌ Call failed:\n{e}")
                self.var_status.set(f"{provider.capitalize()} call error.")
                return
        finally:
            for attr, orig_val in keys_to_restore:
                setattr(api, attr, orig_val)

        if resp and resp.items:
            item = resp.items[0]
            messagebox.showinfo(
                f"{provider.capitalize()} Success",
                f"✅ {provider.capitalize()} connection successful!\nTitle: {item.title}\nYear: {item.year}\nConfidence: {item.confidence_score}"
            )
            self.var_status.set(f"{provider.capitalize()} verified.")
        else:
            messagebox.showwarning(f"{provider.capitalize()} Test", "Response received but items list was empty.")

    # --------------------------------------------------------------------------
    # Page 3: Options & Automation
    # --------------------------------------------------------------------------
    def _build_options_page(self):
        page = ctk.CTkFrame(self.content_scroll, fg_color="transparent")
        self.pages["options"] = page

        # Video Stream Tags Card
        card_video = ctk.CTkFrame(page, corner_radius=12, fg_color=COLOR_CARD, border_width=1, border_color=COLOR_BORDER)
        card_video.pack(fill="x", pady=8)

        ctk.CTkLabel(
            card_video,
            text="🎞️ Video Stream Tags (FFmpeg)",
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            text_color=COLOR_ACCENT
        ).pack(anchor="w", padx=16, pady=(12, 6))

        ctk.CTkSwitch(
            card_video,
            text="Detect and append resolution tags (e.g., [1080p], [4K])",
            variable=self.var_resolution,
            progress_color=COLOR_BTN_PRIMARY,
            font=ctk.CTkFont(family=FONT_FAMILY, size=11),
            text_color=COLOR_TEXT_MAIN
        ).pack(anchor="w", padx=16, pady=4)

        ctk.CTkSwitch(
            card_video,
            text="Detect and append encoding quality tags (e.g., [BluRay], [WEB-DL])",
            variable=self.var_quality,
            progress_color=COLOR_BTN_PRIMARY,
            font=ctk.CTkFont(family=FONT_FAMILY, size=11),
            text_color=COLOR_TEXT_MAIN
        ).pack(anchor="w", padx=16, pady=(4, 12))

        # AI Options Card
        card_ai = ctk.CTkFrame(page, corner_radius=12, fg_color=COLOR_CARD, border_width=1, border_color=COLOR_BORDER)
        card_ai.pack(fill="x", pady=8)

        ctk.CTkLabel(
            card_ai,
            text="🧠 Cloud AI Fallback & Keyword Learning",
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            text_color=COLOR_ACCENT
        ).pack(anchor="w", padx=16, pady=(12, 6))

        ctk.CTkSwitch(
            card_ai,
            text="Enable Cloud AI fallback by default (-i)",
            variable=self.var_ai,
            progress_color=COLOR_BTN_PRIMARY,
            font=ctk.CTkFont(family=FONT_FAMILY, size=11),
            text_color=COLOR_TEXT_MAIN
        ).pack(anchor="w", padx=16, pady=4)

        ctk.CTkSwitch(
            card_ai,
            text="Enable AI keyword learning by default (-L) (save discovered tags)",
            variable=self.var_learn,
            progress_color=COLOR_BTN_PRIMARY,
            font=ctk.CTkFont(family=FONT_FAMILY, size=11),
            text_color=COLOR_TEXT_MAIN
        ).pack(anchor="w", padx=16, pady=(4, 12))

        # Automation & Watcher Card
        card_auto = ctk.CTkFrame(page, corner_radius=12, fg_color=COLOR_CARD, border_width=1, border_color=COLOR_BORDER)
        card_auto.pack(fill="x", pady=8)

        ctk.CTkLabel(
            card_auto,
            text="⚡ Automation & Background Watcher",
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            text_color=COLOR_ACCENT
        ).pack(anchor="w", padx=16, pady=(12, 6))

        ctk.CTkSwitch(
            card_auto,
            text="Bypass interactive confirmation prompts (-b)",
            variable=self.var_bypass,
            progress_color=COLOR_BTN_PRIMARY,
            font=ctk.CTkFont(family=FONT_FAMILY, size=11),
            text_color=COLOR_TEXT_MAIN
        ).pack(anchor="w", padx=16, pady=4)

        ctk.CTkSwitch(
            card_auto,
            text="Enable background daemon watcher by default (-d)",
            variable=self.var_daemon,
            progress_color=COLOR_BTN_PRIMARY,
            font=ctk.CTkFont(family=FONT_FAMILY, size=11),
            text_color=COLOR_TEXT_MAIN
        ).pack(anchor="w", padx=16, pady=4)

        row_int = ctk.CTkFrame(card_auto, fg_color="transparent")
        row_int.pack(fill="x", padx=16, pady=(6, 12))

        ctk.CTkLabel(
            row_int,
            text="Daemon polling interval (minutes):",
            font=ctk.CTkFont(family=FONT_FAMILY, size=11),
            text_color=COLOR_TEXT_MAIN
        ).pack(side="left")

        ctk.CTkEntry(
            row_int,
            textvariable=self.var_interval,
            width=65,
            height=30,
            corner_radius=6,
            fg_color=COLOR_INPUT,
            border_color=COLOR_BORDER,
            text_color=COLOR_TEXT_MAIN
        ).pack(side="left", padx=8)

        # Logging Card
        card_log = ctk.CTkFrame(page, corner_radius=12, fg_color=COLOR_CARD, border_width=1, border_color=COLOR_BORDER)
        card_log.pack(fill="x", pady=8)

        ctk.CTkLabel(
            card_log,
            text="📝 Logging & Diagnostics",
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            text_color=COLOR_ACCENT
        ).pack(anchor="w", padx=16, pady=(12, 6))

        ctk.CTkSwitch(
            card_log,
            text="Write console output to daily log files (log/YYYY-MM-DD.txt) (-l)",
            variable=self.var_log,
            progress_color=COLOR_BTN_PRIMARY,
            font=ctk.CTkFont(family=FONT_FAMILY, size=11),
            text_color=COLOR_TEXT_MAIN
        ).pack(anchor="w", padx=16, pady=4)

        ctk.CTkSwitch(
            card_log,
            text="Display verbose diagnostic logs and exception tracebacks (-v)",
            variable=self.var_verbose,
            progress_color=COLOR_BTN_PRIMARY,
            font=ctk.CTkFont(family=FONT_FAMILY, size=11),
            text_color=COLOR_TEXT_MAIN
        ).pack(anchor="w", padx=16, pady=(4, 12))

    # --------------------------------------------------------------------------
    # Page 4: Email Alerts
    # --------------------------------------------------------------------------
    def _build_email_page(self):
        page = ctk.CTkFrame(self.content_scroll, fg_color="transparent")
        self.pages["email"] = page

        # Credentials Card
        card_creds = ctk.CTkFrame(page, corner_radius=12, fg_color=COLOR_CARD, border_width=1, border_color=COLOR_BORDER)
        card_creds.pack(fill="x", pady=8)

        ctk.CTkLabel(
            card_creds,
            text="📧 Gmail SMTP Credentials",
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            text_color=COLOR_ACCENT
        ).pack(anchor="w", padx=16, pady=(12, 6))

        # Email Row
        r1 = ctk.CTkFrame(card_creds, fg_color="transparent")
        r1.pack(fill="x", padx=16, pady=5)
        ctk.CTkLabel(r1, text="Gmail Address:", width=180, anchor="w", font=ctk.CTkFont(family=FONT_FAMILY, size=11), text_color=COLOR_TEXT_MAIN).pack(side="left")
        ctk.CTkEntry(
            r1,
            textvariable=self.var_mail,
            height=34,
            corner_radius=8,
            fg_color=COLOR_INPUT,
            border_color=COLOR_BORDER,
            text_color=COLOR_TEXT_MAIN
        ).pack(side="left", fill="x", expand=True)

        # Password Row
        r2 = ctk.CTkFrame(card_creds, fg_color="transparent")
        r2.pack(fill="x", padx=16, pady=5)
        ctk.CTkLabel(r2, text="Gmail App Password:", width=180, anchor="w", font=ctk.CTkFont(family=FONT_FAMILY, size=11), text_color=COLOR_TEXT_MAIN).pack(side="left")
        ent_pswd = ctk.CTkEntry(
            r2,
            textvariable=self.var_mail_pswd,
            show="*",
            height=34,
            corner_radius=8,
            fg_color=COLOR_INPUT,
            border_color=COLOR_BORDER,
            text_color=COLOR_TEXT_MAIN
        )
        ent_pswd.pack(side="left", fill="x", expand=True)
        self.api_entries.append(ent_pswd)

        # Send Test Email Button
        btn_test = ctk.CTkButton(
            card_creds,
            text="Send Test Email",
            width=130,
            height=32,
            corner_radius=8,
            font=ctk.CTkFont(family=FONT_FAMILY, size=10, weight="bold"),
            fg_color=COLOR_BTN_TEST,
            hover_color="#1e3a8a",
            border_width=1,
            border_color=COLOR_BTN_TEST_BORDER,
            text_color=COLOR_ACCENT,
            command=self._send_test_email
        )
        btn_test.pack(anchor="e", padx=16, pady=(8, 12))

        # Notification Triggers Card
        card_triggers = ctk.CTkFrame(page, corner_radius=12, fg_color=COLOR_CARD, border_width=1, border_color=COLOR_BORDER)
        card_triggers.pack(fill="x", pady=8)

        ctk.CTkLabel(
            card_triggers,
            text="🔔 Notification Triggers",
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
            text_color=COLOR_ACCENT
        ).pack(anchor="w", padx=16, pady=(12, 6))

        ctk.CTkSwitch(
            card_triggers,
            text="Send notification email when media files are successfully renamed",
            variable=self.var_notify_success,
            progress_color=COLOR_BTN_PRIMARY,
            font=ctk.CTkFont(family=FONT_FAMILY, size=11),
            text_color=COLOR_TEXT_MAIN
        ).pack(anchor="w", padx=16, pady=4)

        ctk.CTkSwitch(
            card_triggers,
            text="Send notification email when an unexpected processing error occurs",
            variable=self.var_notify_error,
            progress_color=COLOR_BTN_PRIMARY,
            font=ctk.CTkFont(family=FONT_FAMILY, size=11),
            text_color=COLOR_TEXT_MAIN
        ).pack(anchor="w", padx=16, pady=4)

        ctk.CTkSwitch(
            card_triggers,
            text="Send notification email when a new AI keyword tag is discovered (-t)",
            variable=self.var_notify_tag,
            progress_color=COLOR_BTN_PRIMARY,
            font=ctk.CTkFont(family=FONT_FAMILY, size=11),
            text_color=COLOR_TEXT_MAIN
        ).pack(anchor="w", padx=16, pady=(4, 12))

    def _send_test_email(self):
        address = self.var_mail.get().strip()
        password = self.var_mail_pswd.get().strip()
        if not address or not password:
            messagebox.showwarning("Email Test", "Please provide both Gmail address and App Password.")
            return

        self.var_status.set("Sending test email...")
        self.root.update_idletasks()
        old_mail = getattr(mail, "MAIL", None)
        old_pswd = getattr(mail, "MAIL_PSWD", None)
        try:
            mail.MAIL = address
            mail.MAIL_PSWD = password

            import smtplib
            from email.mime.text import MIMEText
            msg = MIMEText("This is a test notification from Media Organizer & Renamer.", "plain", "utf-8")
            msg["Subject"] = "🎬 Media Organizer Test Email"
            msg["From"] = address
            msg["To"] = address

            server = smtplib.SMTP("smtp.gmail.com", 587, timeout=15)
            server.starttls()
            server.login(address, password)
            server.send_message(msg)
            server.quit()

            messagebox.showinfo("Email Test Success", f"✅ Test email successfully sent to:\n{address}")
            self.var_status.set("Test email sent.")
        except Exception as e:
            messagebox.showerror("Email Test Failed", f"❌ Failed to send test email:\n{e}")
            self.var_status.set("Email test error.")
        finally:
            mail.MAIL = old_mail
            mail.MAIL_PSWD = old_pswd

    # --------------------------------------------------------------------------
    # Load & Save Logic
    # --------------------------------------------------------------------------
    def load_values(self):
        """Loads configuration from active ConfigManager into UI variables."""
        self.var_movies.set(self.cm.get("paths.movies_folder") or "")
        self.var_tv.set(self.cm.get("paths.tv_shows_folder") or "")
        self.var_downloads.set(self.cm.get("paths.not_sorted_media_files_folder") or "")

        self.var_tmdb.set(self.cm.get("api.tmdb_api_key") or "")
        self.var_gemini.set(self.cm.get("api.gemini_api_key") or "")
        self.var_groq.set(self.cm.get("api.groq_api_key") or "")
        self.var_openrouter.set(self.cm.get("api.openrouter_api_key") or "")
        self.var_cf_tok.set(self.cm.get("api.cloudflare_api_token") or "")
        self.var_cf_acc.set(self.cm.get("api.cloudflare_account_id") or "")
        self.var_ai_provider.set(self.cm.get("options.ai_provider") or "auto")

        tmdb_conf_raw = str(self.cm.get("options.tmdb_min_confidence") or "0.75")
        self.var_tmdb_conf.set(tmdb_conf_raw)
        try:
            tmdb_conf = float(tmdb_conf_raw)
            if hasattr(self, "slider_tmdb"):
                self.slider_tmdb.set(tmdb_conf)
                self.lbl_tmdb_conf.configure(text=f"{int(tmdb_conf * 100)}% ({tmdb_conf:.2f})")
        except (ValueError, TypeError):
            pass

        ai_conf_raw = str(self.cm.get("options.ai_min_confidence") or "0.70")
        self.var_ai_conf.set(ai_conf_raw)
        try:
            ai_conf = float(ai_conf_raw)
            if hasattr(self, "slider_ai"):
                self.slider_ai.set(ai_conf)
                self.lbl_ai_conf.configure(text=f"{int(ai_conf * 100)}% ({ai_conf:.2f})")
        except (ValueError, TypeError):
            pass

        self.var_resolution.set(bool(self.cm.get("options.resolution", False)))
        self.var_quality.set(bool(self.cm.get("options.quality", False)))
        self.var_bypass.set(bool(self.cm.get("options.bypass", False)))
        self.var_daemon.set(bool(self.cm.get("options.daemon", False)))
        self.var_interval.set(str(self.cm.get("options.polling_interval") or "15"))
        self.var_ai.set(bool(self.cm.get("options.ai", False)))
        self.var_learn.set(bool(self.cm.get("options.learn", False)))
        self.var_log.set(bool(self.cm.get("options.log", False)))
        self.var_verbose.set(bool(self.cm.get("options.verbose", False)))

        self.var_mail.set(self.cm.get("mail.mail") or "")
        self.var_mail_pswd.set(self.cm.get("mail.mail_pswd") or "")
        self.var_notify_success.set(bool(self.cm.get("options.notify_on_success", False)))
        self.var_notify_error.set(bool(self.cm.get("options.notify_on_error", True)))
        self.var_notify_tag.set(bool(self.cm.get("options.notify_on_tag", False)))

        self.var_status.set("Configuration loaded from disk.")

    def save_values(self):
        """Saves user input into config.ini."""
        # Paths
        self.cm.set("paths.movies_folder", self.var_movies.get().strip())
        self.cm.set("paths.tv_shows_folder", self.var_tv.get().strip())
        self.cm.set("paths.not_sorted_media_files_folder", self.var_downloads.get().strip())

        # API Keys
        self.cm.set("api.tmdb_api_key", self.var_tmdb.get().strip())
        self.cm.set("api.gemini_api_key", self.var_gemini.get().strip())
        self.cm.set("api.groq_api_key", self.var_groq.get().strip())
        self.cm.set("api.openrouter_api_key", self.var_openrouter.get().strip())
        self.cm.set("api.cloudflare_api_token", self.var_cf_tok.get().strip())
        self.cm.set("api.cloudflare_account_id", self.var_cf_acc.get().strip())

        # Provider & Thresholds
        self.cm.set("options.ai_provider", self.var_ai_provider.get().strip())
        try:
            tmdb_val = float(self.var_tmdb_conf.get().strip())
            if 0.0 <= tmdb_val <= 1.0:
                self.cm.set("options.tmdb_min_confidence", str(tmdb_val))
        except ValueError:
            pass

        try:
            ai_val = float(self.var_ai_conf.get().strip())
            if 0.0 <= ai_val <= 1.0:
                self.cm.set("options.ai_min_confidence", str(ai_val))
        except ValueError:
            pass

        # Options
        self.cm.set("options.resolution", "true" if self.var_resolution.get() else "false")
        self.cm.set("options.quality", "true" if self.var_quality.get() else "false")
        self.cm.set("options.bypass", "true" if self.var_bypass.get() else "false")
        self.cm.set("options.daemon", "true" if self.var_daemon.get() else "false")
        try:
            int_val = int(self.var_interval.get().strip())
            if int_val >= 1:
                self.cm.set("options.polling_interval", str(int_val))
        except ValueError:
            pass

        self.cm.set("options.ai", "true" if self.var_ai.get() else "false")
        self.cm.set("options.learn", "true" if self.var_learn.get() else "false")
        self.cm.set("options.log", "true" if self.var_log.get() else "false")
        self.cm.set("options.verbose", "true" if self.var_verbose.get() else "false")

        # Email
        self.cm.set("mail.mail", self.var_mail.get().strip())
        self.cm.set("mail.mail_pswd", self.var_mail_pswd.get().strip())
        self.cm.set("options.notify_on_success", "true" if self.var_notify_success.get() else "false")
        self.cm.set("options.notify_on_error", "true" if self.var_notify_error.get() else "false")
        self.cm.set("options.notify_on_tag", "true" if self.var_notify_tag.get() else "false")

        self.var_status.set("Configuration successfully saved!")
        messagebox.showinfo("Saved", f"Configuration successfully saved to:\n{self.cm.config_path}")


def launch_config_gui(cm: Optional[ConfigManager] = None) -> bool:
    """Launches the graphical configuration tool using CustomTkinter."""
    try:
        root = ctk.CTk()
        app = ConfigGUI(root, cm=cm)
        root.mainloop()
        return True
    except (tk.TclError, Exception) as e:
        sys.stderr.write(f"\n❌ Unable to launch GUI: {e}\n💡 Running in headless/terminal mode? Use 'python main.py configure' instead.\n\n")
        return False
