"""Filesystem locations for config/state (XDG-compliant)."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

APP_DIR_NAME = "anime-player-linux"
_LEGACY_DIR_NAME = "dmghg-linux"  # pre-rename data directory
_DATA_FILES = (
    "config.json", "session.json", "runtime.json",
    "app.sqlite", "app.sqlite-wal", "app.sqlite-shm",
)


def data_dir() -> Path:
    """Per-user data directory (XDG_DATA_HOME aware).

    One-time migration: state files (config/session/history database)
    from the legacy dmghg-linux directory are moved over when missing
    here. The legacy app payload itself is left untouched.
    """
    base = os.environ.get("XDG_DATA_HOME") or os.path.join(
        os.path.expanduser("~"), ".local", "share"
    )
    p = Path(base) / APP_DIR_NAME
    p.mkdir(parents=True, exist_ok=True)
    legacy = Path(base) / _LEGACY_DIR_NAME
    if legacy.is_dir():
        for name in _DATA_FILES:
            src, dst = legacy / name, p / name
            if src.is_file() and not dst.exists():
                try:
                    shutil.move(str(src), str(dst))
                except OSError:
                    pass
    return p


def config_path() -> Path:
    return data_dir() / "config.json"


def session_path() -> Path:
    return data_dir() / "session.json"


def runtime_path() -> Path:
    return data_dir() / "runtime.json"


def log_dir() -> Path:
    p = data_dir() / "logs"
    p.mkdir(parents=True, exist_ok=True)
    return p


def db_path() -> Path:
    return data_dir() / "app.sqlite"


def asset_dir() -> Path:
    """Bundled assets shipped with this program (shaders, icons)."""
    return Path(__file__).resolve().parent.parent / "assets"
