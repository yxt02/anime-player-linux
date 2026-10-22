"""Fullscreen-capable player window: mpv surface + overlay controls + danmaku."""

from __future__ import annotations

import logging
from typing import Optional

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QMenu, QPushButton, QSlider,
    QVBoxLayout, QWidget, QApplication,
)

from ...core import config, danmaku as danmaku_mod, models
from .. import icons, style
from .mpv_widget import MpvWidget

log = logging.getLogger("anime_player.playerui")


def _fmt_ms(ms: int) -> str:
    s = ms // 1000
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{sec:02d}"
    return f"{m:02d}:{sec:02d}"


class ControlBar(QFrame):
    def __init__(self, player_page: "PlayerPage") -> None:
        super().__init__()
        self._page = player_page
        self.setStyleSheet(f"ControlBar {{ background: rgba(10,10,16,200); border-radius: 10px; }}")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)

        self.btn_play = QPushButton()
        self.btn_play.setIcon(icons.icon("pause"))
        self.btn_play.setFixedSize(34, 34)
        self.btn_play.setStyleSheet("background: transparent; border: none;")
        self.btn_play.clicked.connect(page_toggle := player_page.toggle_pause)

        self.lbl_time = QLabel("00:00")
        self.lbl_time.setStyleSheet("color: #c8c8d8; background: transparent;")
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, 0)
        self.slider.sliderMoved.connect(player_page.seek)

        self.lbl_total = QLabel("00:00")
        self.lbl_total.setStyleSheet("color: #c8c8d8; background: transparent;")

        self.btn_dm = QPushButton()
        self.btn_dm.setIcon(icons.icon("danmaku-on", style.ACCENT))
        self.btn_dm.setFixedSize(34, 34)
        self.btn_dm.setStyleSheet("background: transparent; border: none;")
        self.btn_dm.clicked.connect(player_page.toggle_danmaku)

        self.btn_vol = QPushButton()
        self.btn_vol.setIcon(icons.icon("vol"))
        self.btn_vol.setFixedSize(34, 34)
        self.btn_vol.setStyleSheet("background: transparent; border: none;")
        vol_menu = QMenu(self.btn_vol)
        vol_slider = QSlider(Qt.Orientation.Vertical)
        vol_slider.setRange(0, 130)
        vol_slider.setValue(100)
        vol_slider.setFixedHeight(110)
        vol_widget = QWidget()
        vw = QVBoxLayout(vol_widget)
        vw.addWidget(vol_slider, alignment=Qt.AlignmentFlag.AlignHCenter)
        vol_widget.setStyleSheet("background: rgba(20,20,30,230); border-radius: 8px;")
        act = vol_menu.addWidget(vol_widget)
        act.setDefaultWidget(vol_widget)
        self.btn_vol.setMenu(vol_menu)
        vol_slider.valueChanged.connect(player_page.set_volume)

        self.btn_speed = QPushButton("1.0x")
        self.btn_speed.setStyleSheet("background: transparent; border: none; color: #c8c8d8;")
        speed_menu = QMenu(self.btn_speed)
        for sp in (0.5, 0.75, 1.0, 1.25, 1.5, 2.0):
            act = speed_menu.addAction(f"{sp:g}x")
            act.triggered.connect(lambda _=False, v=sp: player_page.set_speed(v))
        self.btn_speed.setMenu(speed_menu)

        self.btn_next = QPushButton()
        self.btn_next.setIcon(icons.icon("next"))
        self.btn_next.setFixedSize(34, 34)
        self.btn_next.setStyleSheet("background: transparent; border: none;")
        self.btn_next.clicked.connect(player_page.play_next)

        self.btn_fs = QPushButton()
        self.btn_fs.setIcon(icons.icon("fullscreen"))
        self.btn_fs.setFixedSize(34, 34)
        self.btn_fs.setStyleSheet("background: transparent; border: none;")
        self.btn_fs.clicked.connect(player_page.toggle_fullscreen)

        lay.addWidget(self.btn_play)
        lay.addWidget(self.lbl_time)
        lay.addWidget(self.slider, stretch=1)
        lay.addWidget(self.lbl_total)
        lay.addWidget(self.btn_dm)
        lay.addWidget(self.btn_vol)
        lay.addWidget(self.btn_speed)
        lay.addWidget(self.btn_next)
        lay.addWidget(self.btn_fs)

    def set_progress(self, pos_ms: int, dur_ms: int) -> None:
        self.lbl_time.setText(_fmt_ms(pos_ms))
        self.lbl_total.setText(_fmt_ms(dur_ms))
        if not self.slider.isSliderDown():
            self.slider.setRange(0, max(1, dur_ms))
            self.slider.setValue(pos_ms)

    def set_playing(self, playing: bool) -> None:
        self.btn_play.setIcon(icons.icon("pause" if playing else "play"))

    def set_danmaku(self, on: bool) -> None:
        self.btn_dm.setIcon(icons.icon("danmaku-on" if on else "danmaku-off",
                                       style.ACCENT if on else "#9a9aad"))

    def set_speed_label(self, sp: float) -> None:
        self.btn_speed.setText(f"{sp:g}x")


class PlayerPage(QWidget):
    """Standalone player window (also embeddable)."""

    closed = pyqtSignal()
    history_updated = pyqtSignal(dict)

    def __init__(self, state: config.AppState, danmaku_client: danmaku_mod.DanmakuClient):
        super().__init__()
        self._state = state
        self._dm = danmaku_client
        self._video: Optional[models.Video] = None
        self._episodes: list[models.Episode] = []
        self._ep_index = -1
        self._comments: list[models.Comment] = []
        self._danmaku_on = state.config.danmaku_enabled
        self._speed = 1.0
        self._fallback_urls: list[str] = []   # 其余线路（按画质排序）
        self._hide_cursor_timer = QTimer(self)
        self._hide_cursor_timer.setSingleShot(True)
        self._hide_cursor_timer.setInterval(3000)
        self._hide_cursor_timer.timeout.connect(self._on_hide_cursor)
        self._report_timer = QTimer(self)
        self._report_timer.setInterval(15000)
        self._report_timer.timeout.connect(self._report_progress)

        self.setWindowTitle("播放器")
        self.resize(1180, 700)
        self.setStyleSheet(f"background: #000;")

        self.video_host = QWidget(self)
        self.video_host.setStyleSheet("background: black;")
        self.mpv = MpvWidget(self.video_host)
        lay_host = QVBoxLayout(self.video_host)
        lay_host.setContentsMargins(0, 0, 0, 0)
        lay_host.addWidget(self.mpv)

        self.controls = ControlBar(self)
        self.controls.hide()

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(self.video_host, stretch=1)
        root.addWidget(self.controls)

        self.mpv.time_ms_changed.connect(self._on_time)
        self.mpv.duration_ms_changed.connect(lambda d: self.controls.set_progress(self.mpv.position_ms(), d))
        self.mpv.paused_changed.connect(self._on_pause_changed)
        self.mpv.eof_reached.connect(self._on_eof)
        self.mpv.error_reached.connect(self._on_play_error)

        QShortcut(QKeySequence(Qt.Key.Key_Space), self, self.toggle_pause)
        QShortcut(QKeySequence(Qt.Key.Key_F), self, self.toggle_fullscreen)
        QShortcut(QKeySequence(Qt.Key.Key_Left), self, lambda: self.mpv.seek_relative_ms(-5000))
        QShortcut(QKeySequence(Qt.Key.Key_Right), self, lambda: self.mpv.seek_relative_ms(5000))
        QShortcut(QKeySequence(Qt.Key.Key_Up), self, lambda: self.set_volume(self.controls.slider.value() + 5))
        QShortcut(QKeySequence(Qt.Key.Key_Down), self, lambda: self.set_volume(self.controls.slider.value() - 5))
        QShortcut(QKeySequence(Qt.Key.Key_D), self, self.toggle_danmaku)
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self, self._esc)
        QShortcut(QKeySequence(Qt.Key.Key_F11), self, self.toggle_fullscreen)

        self.setMouseTracking(True)

    # ------------------------------------------------------------------ api
    def open_video(self, video: models.Video, episodes: list[models.Episode], index: int) -> None:
        self._video = video
        self._episodes = episodes
        self._ep_index = index
        self._play_current()

    def _play_current(self) -> None:
        if not (0 <= self._ep_index < len(self._episodes)):
            return
        ep = self._episodes[self._ep_index]
        url = ep.video_url
        if not url:
            # Episode URL arrives from the gateway play-key lookup; the caller
            # (detail page) fills it before opening the player. If still empty,
            # try external danmaku-derived sources is not possible — show error.
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "无法播放", "该集暂无可用播放地址。")
            return
        self._fallback_urls = list(ep.fallback_urls)
        self.setWindowTitle(f"{self._video.title if self._video else ''} - {ep.title}")
        self.mpv.play(url)
        self.mpv.show_danmaku(self._danmaku_on and self._state.config.danmaku_enabled)
        self._load_danmaku(ep)
        self._report_timer.start()
        self.show()
        self.raise_()
        self.activateWindow()

    def _load_danmaku(self, ep: models.Episode) -> None:
        if not self._dm or not ep.id:
            return
        def work():
            try:
                return self._dm.get_comments(ep.id)
            except Exception as exc:  # noqa: BLE001
                log.debug("danmaku fetch failed: %s", exc)
                return []
        import threading
        def run():
            comments = work()
            self._comments = comments
            if comments:
                ass = danmaku_mod.convert_to_ass(
                    comments,
                    font_size=self._state.config.danmaku_font_size,
                    opacity=self._state.config.danmaku_opacity,
                )
                QTimer.singleShot(0, lambda: self.mpv.load_danmaku_ass(ass))
        threading.Thread(target=run, daemon=True).start()

    def play_next(self) -> None:
        if self._ep_index + 1 < len(self._episodes):
            self._ep_index += 1
            self._save_history()
            self._play_current()

    def play_index(self, index: int) -> None:
        if 0 <= index < len(self._episodes):
            self._save_history()
            self._ep_index = index
            self._play_current()

    # ------------------------------------------------------------- controls
    def toggle_pause(self) -> None:
        self.mpv.toggle_pause()

    def toggle_fullscreen(self) -> None:
        if self.isFullScreen():
            self.showNormal()
            self.controls.show()
        else:
            self.showFullScreen()

    def toggle_danmaku(self) -> None:
        self._danmaku_on = not self._danmaku_on
        self.mpv.show_danmaku(self._danmaku_on)
        self.controls.set_danmaku(self._danmaku_on)

    def set_volume(self, v: int) -> None:
        self.mpv.set_volume(v)
        self.mpv.set_muted(v == 0)

    def set_speed(self, sp: float) -> None:
        self._speed = sp
        self.mpv.set_speed(sp)
        self.controls.set_speed_label(sp)

    def seek(self, ms: int) -> None:
        self.mpv.seek_ms(ms)

    def _esc(self) -> None:
        if self.isFullScreen():
            self.showNormal()
            self.controls.show()
        else:
            self.close()

    # --------------------------------------------------------------- events
    def _on_time(self, ms: int) -> None:
        self.controls.set_progress(ms, self.mpv.duration_ms())

    def _on_pause_changed(self, paused: bool) -> None:
        self.controls.set_playing(not paused)
        self.controls.show()
        self._hide_cursor_timer.start()

    def _on_eof(self) -> None:
        if self._state.config.autoplay_next and self._ep_index + 1 < len(self._episodes):
            self.play_next()
        else:
            self.mpv.set_paused(True)

    def _on_play_error(self) -> None:
        """当前线路播放失败 → 自动切换下一条线路。"""
        if self._fallback_urls:
            next_url = self._fallback_urls.pop(0)
            self.mpv.play(next_url)
        else:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(
                self, "播放失败",
                "所有线路均无法播放。请检查网络/代理设置，或稍后重试。")

    def _on_hide_cursor(self) -> None:
        if self.isFullScreen() and self.controls.isVisible() and self.mpv.paused is False:
            self.controls.hide()
            self.setCursor(Qt.CursorShape.BlankCursor)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        super().mouseMoveEvent(event)
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.controls.show()
        self.controls.raise_()
        self._hide_cursor_timer.start()

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        self.toggle_fullscreen()
        super().mouseDoubleClickEvent(event)

    def _save_history(self) -> None:
        if not self._video or not (0 <= self._ep_index < len(self._episodes)):
            return
        ep = self._episodes[self._ep_index]
        item = {
            "id": self._video.id,
            "title": self._video.title,
            "cover": self._video.cover,
            "episode_id": ep.id,
            "episode_title": ep.title,
            "episode_index": self._ep_index,
            "position_ms": self.mpv.position_ms(),
            "duration_ms": self.mpv.duration_ms(),
        }
        self.history_updated.emit(item)

    def _report_progress(self) -> None:
        self._save_history()

    def closeEvent(self, event) -> None:  # noqa: N802
        self._save_history()
        self._report_timer.stop()
        self.mpv.shutdown()
        self.closed.emit()
        super().closeEvent(event)
