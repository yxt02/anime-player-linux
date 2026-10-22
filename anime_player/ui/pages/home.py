"""Home page: banners + channel tabs + video grid."""

from __future__ import annotations

import logging
from typing import Optional

from PyQt6.QtCore import Qt, QRunnable, QThreadPool, QObject, pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from ...core import gateway, models
from .widgets import BannerCarousel, FlowGrid

log = logging.getLogger("anime_player.home")


class _Task(QRunnable):
    def __init__(self, fn, on_ok, on_err):
        super().__init__()
        self.fn, self.on_ok, self.on_err = fn, on_ok, on_err
        self.setAutoDelete(True)

    def run(self):
        try:
            result = self.fn()
        except Exception as exc:  # noqa: BLE001
            try:
                self.on_err(exc)
            except RuntimeError:
                pass
            return
        try:
            self.on_ok(result)
        except RuntimeError:
            pass


class _Bridge(QObject):
    ok = pyqtSignal(object)
    err = pyqtSignal(object)


class HomePage(QWidget):
    def __init__(self, gw: gateway.GatewayClient, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._gw = gw
        self._threads = QThreadPool.globalInstance()
        self._channel_id = ""
        self._page = 1
        self._loading = False
        self._exhausted = False
        self.loaded = False

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 14, 18, 10)
        root.setSpacing(10)

        head = QHBoxLayout()
        title = QLabel("首页")
        title.setStyleSheet("font-size: 20px; font-weight: 700;")
        self._btn_refresh = QPushButton("刷新")
        self._btn_refresh.clicked.connect(self.reload)
        head.addWidget(title)
        head.addStretch(1)
        head.addWidget(self._btn_refresh)
        root.addLayout(head)

        self.banner = BannerCarousel()
        self.banner.item_clicked.connect(self._on_banner)
        root.addWidget(self.banner)

        self._channel_bar = QHBoxLayout()
        self._channel_bar.setSpacing(8)
        self._channel_btns: list[QPushButton] = []
        chan_wrap = QWidget()
        chan_wrap.setLayout(self._channel_bar)
        root.addWidget(chan_wrap)

        self.grid = FlowGrid()
        self.grid.video_chosen.connect(self._on_video)
        root.addWidget(self.grid, stretch=1)

    # ------------------------------------------------------------------ load
    def reload(self) -> None:
        self._page = 1
        self._exhausted = False
        self.grid.clear()
        self._load_async()

    def _load_async(self) -> None:
        if self._loading or self._exhausted:
            return
        self._loading = True
        page = self._page
        chan = self._channel_id
        bridge = _Bridge()
        bridge.ok.connect(self._on_page_ok)
        bridge.err.connect(self._on_page_err)

        def work():
            banners = self._gw.get_banners() if page == 1 else []
            channels = self._gw.get_channels() if page == 1 else []
            if chan:
                videos = self._gw.get_channel_detail(chan, page=page)
            else:
                videos = self._gw.get_video_list(page=page)
            return banners, channels, videos

        def ok(result):
            self._loading = False
            bridge.ok.emit(result)

        def err(exc):
            self._loading = False
            bridge.err.emit(exc)

        self._threads.start(_Task(work, ok, err))

    def _on_page_ok(self, result) -> None:
        banners, channels, videos = result
        self.loaded = True
        if banners:
            self.banner.set_banners(banners)
        if channels:
            self._set_channels(channels)
        if not videos:
            self._exhausted = True
        self.grid.add_videos(videos)
        self._page += 1

    def _on_page_err(self, exc) -> None:
        from PyQt6.QtWidgets import QMessageBox
        QMessageBox.warning(self, "加载失败", str(exc))

    def _set_channels(self, channels: list[models.Channel]) -> None:
        for b in self._channel_btns:
            b.deleteLater()
        self._channel_btns.clear()
        all_btn = QPushButton("全部")
        all_btn.setCheckable(True)
        all_btn.setChecked(True)
        all_btn.clicked.connect(lambda: self._select_channel(""))
        self._channel_bar.addWidget(all_btn)
        self._channel_btns.append(all_btn)
        for ch in sorted(channels, key=lambda c: c.sort):
            b = QPushButton(ch.name)
            b.setCheckable(True)
            b.clicked.connect(lambda _=False, cid=ch.id: self._select_channel(cid))
            self._channel_bar.addWidget(b)
            self._channel_btns.append(b)
        self._channel_bar.addStretch(1)

    def _select_channel(self, channel_id: str) -> None:
        if self._channel_id == channel_id:
            return
        self._channel_id = channel_id
        for b in self._channel_btns:
            b.setChecked(
                (b.text() == "全部" and channel_id == "")
                or (b.text() != "全部" and self._channel_btns.index(b) > 0
                    and b.isChecked())
            )
        self.reload()

    def _on_banner(self, banner: models.Banner) -> None:
        if banner.video_id:
            self.video_open_requested.emit(banner.video_id)
        elif banner.jump_url:
            from PyQt6.QtGui import QDesktopServices
            from PyQt6.QtCore import QUrl
            QDesktopServices.openUrl(QUrl(banner.jump_url))

    def _on_video(self, video: models.Video) -> None:
        self.video_open_requested.emit(video.id)

    # infinite scroll hook
    def scroll_value_changed(self, value: int, maximum: int) -> None:
        if maximum > 0 and value > maximum * 0.85:
            self._load_async()

    # signal for opening a detail page (connected by main window)
    from PyQt6.QtCore import pyqtSignal as _sig
    video_open_requested = _sig(str)
