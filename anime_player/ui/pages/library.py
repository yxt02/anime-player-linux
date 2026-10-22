"""History and favorites pages."""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt, QObject, QRunnable, QThreadPool, pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout, QLabel, QPushButton, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from ...core import gateway, localdb


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


def _progress_text(pos_ms: int, dur_ms: int) -> str:
    def fmt(ms):
        s = ms // 1000
        return f"{s // 60:02d}:{s % 60:02d}"
    pct = int(pos_ms * 100 / dur_ms) if dur_ms else 0
    return f"{fmt(pos_ms)} / {fmt(dur_ms)} ({pct}%)"


class HistoryPage(QWidget):
    video_open_requested = pyqtSignal(str)

    def __init__(self, db: localdb.LocalDB, gw: gateway.GatewayClient,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._db = db
        self._gw = gw

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 14, 18, 10)
        root.setSpacing(12)

        head = QHBoxLayout()
        title = QLabel("历史")
        title.setStyleSheet("font-size: 20px; font-weight: 700;")
        btn_sync = QPushButton("同步")
        btn_sync.clicked.connect(self._sync)
        btn_clear = QPushButton("清空")
        btn_clear.clicked.connect(self._clear)
        head.addWidget(title)
        head.addStretch(1)
        head.addWidget(btn_sync)
        head.addWidget(btn_clear)
        root.addLayout(head)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["番剧", "看到", "进度", "时间"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setColumnWidth(0, 320)
        self.table.setColumnWidth(1, 140)
        self.table.setColumnWidth(2, 180)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.cellDoubleClicked.connect(self._open_row)
        root.addWidget(self.table, stretch=1)
        self._rows: list[dict] = []

    def reload(self) -> None:
        self._rows = self._db.list_history()
        self.table.setRowCount(len(self._rows))
        import datetime
        for r, item in enumerate(self._rows):
            self.table.setItem(r, 0, QTableWidgetItem(str(item.get("title", ""))))
            ep = str(item.get("episode_title") or item.get("episode_id", ""))
            self.table.setItem(r, 1, QTableWidgetItem(ep))
            self.table.setItem(r, 2, QTableWidgetItem(
                _progress_text(int(item.get("position_ms", 0)), int(item.get("duration_ms", 0)))))
            ts = int(item.get("updated_at", 0)) // 1000
            when = datetime.datetime.fromtimestamp(ts).strftime("%m-%d %H:%M") if ts else ""
            self.table.setItem(r, 3, QTableWidgetItem(when))

    def _open_row(self, row: int, _col: int) -> None:
        if 0 <= row < len(self._rows):
            vid = str(self._rows[row].get("id", ""))
            if vid:
                self.video_open_requested.emit(vid)

    def _clear(self) -> None:
        self._db.clear_history()
        self.reload()

    def _sync(self) -> None:
        from ...core.config import app_state
        if not app_state().session.logged_in:
            self.reload()
            self._show_msg("游客模式：历史仅保存在本机（登录后可云端同步）。")
            return

        def work():
            remote = self._gw.get_remote_history()
            # store remote items locally (server is source of truth for merge)
            for item in remote:
                meta = {k: item.get(k) for k in ("id", "title", "cover")}
                self._db.put_history(
                    meta,
                    str(item.get("episode_id", "")),
                    str(item.get("episode_title", "")),
                    int(item.get("position_ms", 0) or 0),
                    int(item.get("duration_ms", 0) or 0),
                )
            # push local top items back
            for item in self._db.list_history(20):
                try:
                    self._gw.put_remote_history({
                        "video_id": item.get("id"),
                        "episode_id": item.get("episode_id"),
                        "position_ms": item.get("position_ms"),
                        "duration_ms": item.get("duration_ms"),
                        "updated_at": item.get("updated_at"),
                    })
                except Exception:  # noqa: BLE001
                    pass
            return True

        def done(_r, exc):
            self.reload()
            if exc:
                self._show_msg(f"同步失败：{exc}")

        QThreadPool.globalInstance().start(_Task(work, done))

    def _show_msg(self, text: str) -> None:
        from PyQt6.QtWidgets import QMessageBox
        QMessageBox.warning(self, "历史同步", text)


class FavoritesPage(QWidget):
    video_open_requested = pyqtSignal(str)

    def __init__(self, db: localdb.LocalDB, gw: gateway.GatewayClient,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._db = db
        self._gw = gw

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 14, 18, 10)
        root.setSpacing(12)

        head = QHBoxLayout()
        title = QLabel("收藏")
        title.setStyleSheet("font-size: 20px; font-weight: 700;")
        btn_sync = QPushButton("同步")
        btn_sync.clicked.connect(self._sync)
        head.addWidget(title)
        head.addStretch(1)
        head.addWidget(btn_sync)
        root.addLayout(head)

        from .widgets import FlowGrid
        self.grid = FlowGrid()
        self.grid.video_chosen.connect(
            lambda v: self.video_open_requested.emit(v.id))
        root.addWidget(self.grid, stretch=1)

    def reload(self) -> None:
        self.grid.clear()
        self.grid.add_videos(self._db.list_favorites())  # type: ignore[arg-type]

    def _sync(self) -> None:
        from ...core.config import app_state
        if not app_state().session.logged_in:
            self.reload()
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.information(
                self, "收藏同步", "游客模式：收藏仅保存在本机（登录后可云端同步）。")
            return

        def work():
            remote = self._gw.get_collect()
            for v in remote:
                self._db.put_favorite({
                    "id": v.id, "title": v.title, "cover": v.cover,
                })
            return True

        def done(_r, exc):
            self.reload()
            if exc:
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.warning(self, "收藏同步", f"同步失败：{exc}")

        QThreadPool.globalInstance().start(_Task(work, done))
