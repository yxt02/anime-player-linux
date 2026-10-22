"""libmpv video widget (X11 --wid embedding) with ASS danmaku support.

Handles video decoding, HLS, ASS danmaku rendering via libass, and
optional Anime4K GLSL shaders.
"""

from __future__ import annotations

import ctypes
import logging
import os
import tempfile
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import QWidget

from ...core import paths

log = logging.getLogger("anime_player.player")

_mpv_ready = False


def _ensure_mpv():
    global _mpv_ready
    if _mpv_ready:
        return
    # python-mpv loads libmpv by name; preload the conda build if needed.
    import sys
    for cand in (
        "libmpv.so.2",
        os.path.join(sys.prefix, "lib", "libmpv.so.2"),  # conda/venv prefix
        os.path.expanduser("~/anaconda3/lib/libmpv.so.2"),
        "/usr/lib/x86_64-linux-gnu/libmpv.so.2",
    ):
        try:
            ctypes.CDLL(cand)
            break
        except OSError:
            continue
    _mpv_ready = True


class MpvWidget(QWidget):
    """A widget that hosts an mpv render surface via --wid."""

    time_ms_changed = pyqtSignal(int)        # position updates
    duration_ms_changed = pyqtSignal(int)
    eof_reached = pyqtSignal()
    error_reached = pyqtSignal()             # 解码/网络错误（用于线路切换）
    file_loaded = pyqtSignal()
    paused_changed = pyqtSignal(bool)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        _ensure_mpv()
        import mpv  # deferred: needs libmpv preloaded

        self.setAttribute(Qt.WidgetAttribute.WA_DontCreateNativeAncestors)
        self.setAttribute(Qt.WidgetAttribute.WA_NativeWindow)
        self.setMinimumSize(480, 270)

        self._ass_path: Optional[str] = None
        self._player = mpv.MPV(
            wid=int(self.winId()),
            vo="gpu",
            hwdec="auto-safe",
            keep_open="yes",            # hold last frame at EOF instead of closing
            input_default_bindings="no",
            input_vo_keyboard="no",
            title="",
            ytdl="no",
            **self._extra_opts(),
        )

        @self._player.property_observer("time-pos")
        def _on_time(_name, value):
            if value is not None:
                self.time_ms_changed.emit(int(value * 1000))

        @self._player.property_observer("duration")
        def _on_dur(_name, value):
            if value is not None:
                self.duration_ms_changed.emit(int(value * 1000))

        @self._player.property_observer("eof-reached")
        def _on_eof(_name, value):
            if value:
                self.eof_reached.emit()

        @self._player.property_observer("pause")
        def _on_pause(_name, value):
            self.paused_changed.emit(bool(value))

        @self._player.event_callback("file-loaded")
        def _on_loaded(_event):
            self.file_loaded.emit()

        @self._player.event_callback("end-file")
        def _on_end_file(event):
            # mpv end-file reason: 0=eof 1=stop 2=quit 3=error 4=redirect
            reason = getattr(event, "reason", None)
            if reason is None and isinstance(event, dict):
                reason = event.get("reason")
            if reason in (3, "error", "END_FILE_REASON_ERROR"):
                self.error_reached.emit()

    @staticmethod
    def _extra_opts() -> dict:
        opts: dict = {}
        # GPU API selection for X11; falls back automatically inside mpv.
        opts["gpu_api"] = "auto"
        return opts

    # ------------------------------------------------------------------ api
    def play(self, url: str, *, headers: Optional[dict] = None) -> None:
        opts = []
        if headers:
            hdr = "".join(f"{k}: {v}\r\n" for k, v in headers.items())
            opts.append(f"http-header-fields={hdr}")
        log.info("mpv play %s", url)
        self._player.play(url, *opts)

    def toggle_pause(self) -> None:
        self._player.pause = not self._player.pause

    def set_paused(self, paused: bool) -> None:
        self._player.pause = paused

    @property
    def paused(self) -> bool:
        return bool(self._player.pause)

    def seek_ms(self, ms: int) -> None:
        self._player.command("seek", ms / 1000.0, "absolute")

    def seek_relative_ms(self, delta_ms: int) -> None:
        self._player.command("seek", delta_ms / 1000.0, "relative")

    def position_ms(self) -> int:
        try:
            v = self._player.time_pos
            return int(v * 1000) if v else 0
        except Exception:  # noqa: BLE001
            return 0

    def duration_ms(self) -> int:
        try:
            v = self._player.duration
            return int(v * 1000) if v else 0
        except Exception:  # noqa: BLE001
            return 0

    def set_volume(self, percent: int) -> None:
        self._player.volume = max(0, min(130, percent))

    def set_muted(self, muted: bool) -> None:
        self._player.mute = muted

    def set_speed(self, speed: float) -> None:
        self._player.speed = speed

    def stop(self) -> None:
        try:
            self._player.command("stop")
        except Exception:  # noqa: BLE001
            pass

    def show_danmaku(self, visible: bool) -> None:
        self._player["sub-visibility"] = bool(visible)

    def load_danmaku_ass(self, ass_text: str) -> None:
        """Replace the current danmaku ASS document."""
        try:
            self._player.command("sub-remove", "0")  # ignore errors
        except Exception:  # noqa: BLE001
            pass
        fd, path = tempfile.mkstemp(suffix=".ass", prefix="anime_player_danmaku_")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(ass_text)
        self._ass_path = path
        self._player.command("sub-add", path, "select", "danmaku")
        self._player["sub-delay"] = 0

    def apply_anime4k(self, enabled: bool, preset: str = "S") -> None:
        """Enable Anime4K GLSL shaders (included under assets/shaders, GPL-3.0)."""
        shader_dir = paths.asset_dir() / "shaders"
        order = {
            "S": [
                "Anime4K_Restore_CNN_S.glsl",
                "Anime4K_Upscale_CNN_x2_S.glsl",
                "Anime4K_AutoDownscalePre_x4.glsl",
                "Anime4K_Restore_CNN_S.glsl",
                "Anime4K_Upscale_CNN_x2_S.glsl",
            ],
            "M": [
                "Anime4K_Restore_CNN_M.glsl",
                "Anime4K_Upscale_CNN_x2_M.glsl",
                "Anime4K_AutoDownscalePre_x4.glsl",
                "Anime4K_Restore_CNN_M.glsl",
                "Anime4K_Upscale_CNN_x2_M.glsl",
            ],
        }.get(preset, [])
        if not enabled:
            self._player["glsl-shaders"] = ""
            return
        files = [str(shader_dir / n) for n in order if (shader_dir / n).exists()]
        if files:
            self._player["glsl-shaders"] = os.pathsep.join(files)

    def reload_wid(self) -> None:
        """Re-point mpv at the current native window (after reparenting)."""
        try:
            self._player["wid"] = int(self.winId())
        except Exception as exc:  # noqa: BLE001
            log.debug("reload_wid: %s", exc)

    def shutdown(self) -> None:
        try:
            self._player.terminate()
        except Exception:  # noqa: BLE001
            pass
        if self._ass_path:
            try:
                Path(self._ass_path).unlink(missing_ok=True)
            except OSError:
                pass

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        # mpv follows the wid automatically; nothing else needed.

    def mousePressEvent(self, event) -> None:  # noqa: N802
        # click-to-pause is handled by the overlay layer above us
        super().mousePressEvent(event)
