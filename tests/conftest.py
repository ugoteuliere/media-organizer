import os
import sys
import tempfile
from pathlib import Path

# Clean up oversized environment variables (e.g. from subagent IDE tools) to prevent Windows SetEnvironmentVariable limit crash
for _k, _v in list(os.environ.items()):
    if len(_v) > 10000:
        os.environ.pop(_k, None)

# Initialize global quarantine directory and point environment variables BEFORE importing src
_global_quarantine_dir = Path(tempfile.gettempdir()) / "pytest_rename_quarantine"
_global_quarantine_dir.mkdir(parents=True, exist_ok=True)
_global_quarantine_file = _global_quarantine_dir / "global_seed_config.ini"

import configparser

# Determine source config to read API keys and credentials from: local config.ini (CI) or user APPDATA/XDG config
_candidates = [Path("config.ini")]
if os.name == "nt":
    _appdata = os.environ.get("APPDATA")
    if _appdata:
        _candidates.append(Path(_appdata) / "media-organizer" / "config.ini")
        _candidates.append(Path(_appdata) / "rename" / "config.ini")
else:
    _xdg = os.environ.get("XDG_CONFIG_HOME")
    if _xdg:
        _candidates.append(Path(_xdg) / "media-organizer" / "config.ini")
        _candidates.append(Path(_xdg) / "rename" / "config.ini")
    _candidates.append(Path.home() / ".config" / "media-organizer" / "config.ini")
    _candidates.append(Path.home() / ".config" / "rename" / "config.ini")

_source_ini = None
for _c in _candidates:
    if _c and _c.is_file():
        try:
            _check_p = configparser.ConfigParser()
            _check_p.read(str(_c), encoding="utf-8")
            if _check_p.has_section("api") and any(_check_p.items("api")):
                _source_ini = _c.resolve()
                break
        except Exception:
            pass
if not _source_ini and any(c and c.is_file() for c in _candidates):
    _source_ini = next(c.resolve() for c in _candidates if c and c.is_file())

import shutil
import configparser

_q_parser = configparser.ConfigParser()
if _source_ini and _source_ini.is_file():
    try:
        _src_p = configparser.ConfigParser()
        _src_p.read(str(_source_ini), encoding="utf-8")
        # Copy credentials only from api (for live/integration tests), NEVER mail
        for _sec in ["api"]:
            if _src_p.has_section(_sec):
                _q_parser.add_section(_sec)
                for _k, _v in _src_p.items(_sec):
                    _q_parser.set(_sec, _k, _v)
    except Exception:
        pass

# Guarantee that the quarantined test config NEVER has real mail credentials
if not _q_parser.has_section("mail"):
    _q_parser.add_section("mail")
_q_parser.set("mail", "mail", "")
_q_parser.set("mail", "mail_pswd", "")

with open(_global_quarantine_file, "w", encoding="utf-8") as _f:
    _q_parser.write(_f)

os.environ.setdefault("CONFIG_FILE", str(_global_quarantine_file))
os.environ.setdefault("APPDATA", str(_global_quarantine_dir))
os.environ.setdefault("XDG_CONFIG_HOME", str(_global_quarantine_dir))
os.environ.setdefault("HOME", str(_global_quarantine_dir))

import pytest
from src.config import config


@pytest.fixture(autouse=True)
def isolate_user_config(tmp_path, monkeypatch):
    """
    Quarantine all tests to an isolated temporary configuration directory.
    Guarantees that pytest never reads or modifies the user's real config.ini.
    """
    test_config_dir = tmp_path / "quarantine_rename_config"
    test_config_dir.mkdir(parents=True, exist_ok=True)
    test_config_file = test_config_dir / "config.ini"

    # Seed isolated config with credentials from global quarantine
    if _global_quarantine_file.is_file():
        shutil.copyfile(str(_global_quarantine_file), str(test_config_file))

    # 1. Point CONFIG_FILE to the isolated file
    monkeypatch.setenv("CONFIG_FILE", str(test_config_file))

    # 2. Also isolate APPDATA / XDG_CONFIG_HOME / HOME to the temp directory
    monkeypatch.setenv("APPDATA", str(test_config_dir))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(test_config_dir))
    monkeypatch.setenv("HOME", str(test_config_dir))

    # 3. Reload singleton config object with quarantined path
    config.config_path = test_config_file
    config.load()

    # 4. Reset runtime CLI flags and email credentials
    from src import ui

    ui.NOTIFY_SUCCESS_ENABLED = False
    ui.NOTIFY_ERROR_ENABLED = False
    ui.RESOLUTION_ENABLED = False
    ui.QUALITY_ENABLED = False
    ui.SIMULATE_ENABLED = False
    ui.BYPASS_ENABLED = False
    ui.LOG_ENABLED = False
    ui.LOG_MODE = "console"
    ui.VERBOSE_ENABLED = False
    ui.AI_FALLBACK_ENABLED = False
    ui.DAEMON_ENABLED = False
    ui.POLLING_INTERVAL = 15

    if "src.mail" in sys.modules:
        _m = sys.modules["src.mail"]
        _m.MAIL = None
        _m.MAIL_PSWD = None

    yield

    ui.LOG_MODE = "console"
    if "src.mail" in sys.modules:
        _m = sys.modules["src.mail"]
        _m.MAIL = None
        _m.MAIL_PSWD = None

    # 5. Teardown: ensure config singleton points to quarantine, never user's real config
    config.config_path = _global_quarantine_file
    config.load()


@pytest.fixture(autouse=True)
def mock_smtp_network_guard(monkeypatch):
    """
    Global safety net: Ensure tests never establish live SMTP network connections
    or send real emails under any circumstances.
    Provides a safe in-memory dummy mock for smtplib.SMTP and smtplib.SMTP_SSL across the entire test suite.
    Any test with an explicit local mock (e.g. @patch('src.mail.smtplib.SMTP_SSL')) cleanly overrides this.
    """
    from unittest.mock import MagicMock
    import smtplib

    mock_server = MagicMock(name="SafeDummySMTPServer")
    mock_server.__enter__.return_value = mock_server
    mock_cls = MagicMock(name="SafeDummySMTPClass", return_value=mock_server)

    monkeypatch.setattr(smtplib, "SMTP_SSL", mock_cls)
    monkeypatch.setattr(smtplib, "SMTP", mock_cls)
    if "src.mail" in sys.modules:
        monkeypatch.setattr(sys.modules["src.mail"].smtplib, "SMTP_SSL", mock_cls)
        monkeypatch.setattr(sys.modules["src.mail"].smtplib, "SMTP", mock_cls)


import os
os.environ["MIN_FILE_SIZE_MB"] = "-1"
