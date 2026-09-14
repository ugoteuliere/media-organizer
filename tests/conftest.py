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
_global_quarantine_file = _global_quarantine_dir / "config.ini"

# Determine source config to read API keys and credentials from: local config.ini (CI) or user APPDATA/XDG config
_source_ini = None
if Path("config.ini").is_file():
    _source_ini = Path("config.ini").resolve()
else:
    if os.name == 'nt':
        _appdata = os.environ.get('APPDATA')
        if _appdata and (Path(_appdata) / "rename" / "config.ini").is_file():
            _source_ini = Path(_appdata) / "rename" / "config.ini"
    else:
        _xdg = os.environ.get('XDG_CONFIG_HOME')
        if _xdg and (Path(_xdg) / "rename" / "config.ini").is_file():
            _source_ini = Path(_xdg) / "rename" / "config.ini"
        elif (Path.home() / ".config" / "rename" / "config.ini").is_file():
            _source_ini = Path.home() / ".config" / "rename" / "config.ini"

import shutil
import configparser

_q_parser = configparser.ConfigParser()
if _source_ini and _source_ini.is_file():
    try:
        _src_p = configparser.ConfigParser()
        _src_p.read(str(_source_ini), encoding="utf-8")
        # Copy credentials from api and mail so integration/api tests work seamlessly without affecting options or paths
        for _sec in ["api", "mail"]:
            if _src_p.has_section(_sec):
                _q_parser.add_section(_sec)
                for _k, _v in _src_p.items(_sec):
                    _q_parser.set(_sec, _k, _v)
    except Exception:
        pass

with open(_global_quarantine_file, "w", encoding="utf-8") as _f:
    _q_parser.write(_f)

os.environ.setdefault("RENAME_CONFIG_FILE", str(_global_quarantine_file))
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

    # 1. Point RENAME_CONFIG_FILE to the isolated file
    monkeypatch.setenv("RENAME_CONFIG_FILE", str(test_config_file))

    # 2. Also isolate APPDATA / XDG_CONFIG_HOME / HOME to the temp directory
    monkeypatch.setenv("APPDATA", str(test_config_dir))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(test_config_dir))
    monkeypatch.setenv("HOME", str(test_config_dir))

    # 3. Reload singleton config object with quarantined path
    config.config_path = test_config_file
    config.load()

    # 4. Reset runtime CLI flags
    from src import ui
    ui.NOTIFY_SUCCESS_ENABLED = False
    ui.NOTIFY_ERROR_ENABLED = False
    ui.RESOLUTION_ENABLED = False
    ui.QUALITY_ENABLED = False
    ui.SIMULATE_ENABLED = False
    ui.BYPASS_ENABLED = False
    ui.LOG_ENABLED = False
    ui.VERBOSE_ENABLED = False
    ui.AI_FALLBACK_ENABLED = False
    ui.DAEMON_ENABLED = False
    ui.POLLING_INTERVAL = 15

    yield

    # 5. Teardown: ensure config singleton points to quarantine, never user's real config
    config.config_path = _global_quarantine_file
    config.load()
