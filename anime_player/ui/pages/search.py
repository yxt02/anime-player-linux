"""Search page: gateway search + external danmaku search fallback."""

from __future__ import annotations

import logging
from typing import Optional

from PyQt6.QtCore import Qt, QObject, QRunnable, QThreadPool, pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget,
)

from ...core import danmaku as danmaku_mod, gateway, models
from .widgets import FlowGrid

log = logging.getLogger("anime_player.search")


class _Task(QRunnable):
    def __init__(self, fn, done):
        super().__init__()
        self.fn, self.done = fn, done
        self.setAutoDelete(True)

    def run(self):
        try:
            self.done(self.fn(), None)
        except RuntimeError:
            pass  # receiver destroyed (window closed before task finished)
        except Exception as exc:  # noqa: BLE001
            try:
                self.done(None, exc)
            except RuntimeError:
                pass


class _Bridge(QObject):
    finished = pyqtSignal(object, object)


class SearchPage(QWidget):
    video_open_requested = pyqtSignal(str)

    def __init__(self, gw: gateway.GatewayClient, dm: danmaku_mod.DanmakuClient,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._gw = gw
        self._dm = dm
        self._pool = QThreadPool.globalInstance()

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 14, 18, 10)
        root.setSpacing(12)

        head = QHBoxLayout()
        title = QLabel("搜索")
        title.setStyleSheet("font-size: 20px; font-weight: 700;")
        self.edit = QLineEdit()
        self.edit.setPlaceholderText("输入番剧名称…")
        self.edit.setClearButtonEnabled(True)
        self.edit.returnPressed.connect(self.search)
        btn = QPushButton("搜索")
        btn.setObjectName("primary")
        btn.clicked.connect(self.search)
        head.addWidget(title)
        head.addWidget(self.edit, stretch=1)
        head.addWidget(btn)
        root.addLayout(head)

        self.hint = QLabel("")
        self.hint.setProperty("class", "dim")
        root.addWidget(self.hint)

        self.grid = FlowGrid()
        self.grid.video_chosen.connect(self._on_video)
        root.addWidget(self.grid, stretch=1)

        self._bridge = _Bridge()
        self._bridge.finished.connect(self._on_done)

    def search(self) -> None:
        kw = self.edit.text().strip()
        if not kw:
            return
        self.grid.clear()
        self.hint.setText("搜索中…")

        def work():
            results: list[models.Video] = []
            try:
                results = self._gw.search_video(kw)
            except Exception:  # noqa: BLE001
                pass
            if not results:
                # fall back to the external danmaku index
                try:
                    results = self._dm.search_anime(kw)
                except Exception:  # noqa: BLE001
                    pass
            return results

        def done(result, exc):
            self._bridge.finished.emit(result, exc)

        self._pool.start(_Task(work, done))

    def _on_done(self, result, exc) -> None:
        if exc is not None:
            self.hint.setText(f"搜索失败：{exc}")
            return
        videos: list[models.Video] = result or []
        if not videos:
            self.hint.setText("未匹配到相关结果")
            return
        self.hint.setText(f"共 {len(videos)} 个结果")
        self.grid.add_videos(videos)

    def _on_video(self, video: models.Video) -> None:
        self.video_open_requested.emit(video.id)
