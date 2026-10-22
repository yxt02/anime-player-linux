"""Persistent app state: config.json / session.json / runtime.json.

Stores api_host, language, theme, auto_update, network_proxy, boot_count,
last_gateway_base_url, last_window_name and related settings.
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

from . import paths


def _load(path: Path) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _save(path: Path, data: dict) -> None:
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    tmp.replace(path)


@dataclass
class AppConfig:
    """config.json — user preferences."""

    api_host: str = ""            # manual gateway override ("" = auto discovery)
    language: str = "zh-CN"
    theme: str = "dark"
    auto_update: bool = True
    network_proxy: str = ""       # e.g. http://127.0.0.1:7890 ; "" = direct
    boot_count: int = 0
    last_window_name: str = ""
    danmaku_enabled: bool = True
    danmaku_opacity: float = 1.0
    danmaku_font_size: int = 28
    autoplay_next: bool = True
    announce_affiche: bool = False   # 公告弹窗默认关闭（纯净模式）
    guest_mode: bool = True          # 游客优先：一切数据只存本机，登录完全可选
    prefer_quality: str = "best"     # best=最高画质优先 / low=流畅优先
    external_player: str = ""     # optional: shell command to play a URL externally

    @classmethod
    def load(cls) -> "AppConfig":
        cfg = cls(**{
            k: v for k, v in _load(paths.config_path()).items()
            if k in cls.__dataclass_fields__
        })
        return cfg

    def save(self) -> None:
        _save(paths.config_path(), asdict(self))


@dataclass
class SessionState:
    """session.json — auth material for the current account."""

    token: str = ""
    user_id: str = ""
    nickname: str = ""
    avatar: str = ""
    is_vip: bool = False
    vip_expire_at: int = 0
    phone_hint: str = ""          # masked phone shown as account hint
    updated_at_ms: int = 0

    @classmethod
    def load(cls) -> "SessionState":
        return cls(**{
            k: v for k, v in _load(paths.session_path()).items()
            if k in cls.__dataclass_fields__
        })

    def save(self) -> None:
        self.updated_at_ms = int(time.time() * 1000)
        _save(paths.session_path(), asdict(self))

    def clear(self) -> None:
        self.__init__()
        self.save()

    @property
    def logged_in(self) -> bool:
        return bool(self.token)


@dataclass
class RuntimeState:
    """runtime.json — bootstrap bookkeeping."""

    last_gateway_base_url: str = ""
    last_gateway_source: str = ""
    last_failed_gateway_candidates: list = field(default_factory=list)
    failed_at_ms: int = 0
    media_proxy_port: int = 0
    update_seen_version: str = ""

    @classmethod
    def load(cls) -> "RuntimeState":
        return cls(**{
            k: v for k, v in _load(paths.runtime_path()).items()
            if k in cls.__dataclass_fields__
        })

    def save(self) -> None:
        _save(paths.runtime_path(), asdict(self))


class AppState:
    """Convenience holder shared across the UI."""

    _lock = threading.Lock()

    def __init__(self) -> None:
        self.config = AppConfig.load()
        self.session = SessionState.load()
        self.runtime = RuntimeState.load()

    def save_config(self) -> None:
        with self._lock:
            self.config.save()

    def save_session(self) -> None:
        with self._lock:
            self.session.save()

    def save_runtime(self) -> None:
        with self._lock:
            self.runtime.save()


_state: Optional[AppState] = None


def app_state() -> AppState:
    global _state
    if _state is None:
        _state = AppState()
        _state.config.boot_count += 1
        _state.config.save()
    return _state
