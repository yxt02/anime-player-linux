"""Shared page widgets: cover cards, flow grid, banner carousel."""

from __future__ import annotations

import logging
from typing import Optional

from PyQt6.QtCore import Qt, QObject, QRunnable, QThreadPool, pyqtSignal, pyqtSlot, QTimer
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPixmap, QImage, QPen
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PyQt6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QLayout, QPushButton,
    QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)

from ...core import models
from .. import style

log = logging.getLogger("anime_player.ui")

_net: Optional[QNetworkAccessManager] = None


def net_manager() -> QNetworkAccessManager:
    global _net
    if _net is None:
        _net = QNetworkAccessManager()
    return _net


def fetch_pixmap(url: str, callback) -> None:
    """Fetch an image asynchronously; callback(QPixmap or None) on main thread."""
    if not url:
        callback(None)
        return
    req = QNetworkRequest(QUrl_of(url))
    reply = net_manager().get(req)

    def done():
        try:
            if reply.error() == QNetworkReply.NetworkError.NoError:
                data = reply.readAll().data()
                pm = QPixmap()
                if pm.loadFromData(data):
                    callback(pm)
                else:
                    callback(None)
            else:
                callback(None)
        finally:
            reply.deleteLater()

    reply.finished.connect(done)


def QUrl_of(url: str):
    from PyQt6.QtCore import QUrl
    return QUrl(url)


def rounded_pixmap(pm: QPixmap, radius: int = 10) -> QPixmap:
    out = QPixmap(pm.size())
    out.fill(Qt.GlobalColor.transparent)
    p = QPainter(out)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(0.0, 0.0, float(out.width()), float(out.height()), radius, radius)
    p.setClipPath(path)
    p.drawPixmap(0, 0, pm)
    p.end()
    return out


def placeholder_cover(title: str, w: int = 220, h: int = 300) -> QPixmap:
    """Deterministic colored placeholder (no external assets)."""
    hue = (hash(title) % 360 + 360) % 360
    pm = QPixmap(w, h)
    pm.fill(QColor.fromHsv(hue, 70, 60))
    p = QPainter(pm)
    p.setPen(QPen(QColor(255, 255, 255, 200)))
    f = p.font()
    f.setPixelSize(max(14, w // 9))
    f.setBold(True)
    p.setFont(f)
    p.drawText(pm.rect().adjusted(10, 10, -10, -10),
               Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, title[:16])
    p.end()
    return pm


class CoverCard(QFrame):
    """A video poster card."""

    clicked = pyqtSignal(object)

    def __init__(self, video: models.Video, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("card")
        self.setFixedSize(172, 268)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._video = video

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)

        self.cover = QLabel()
        self.cover.setFixedSize(156, 208)
        self.cover.setStyleSheet("border-radius: 8px; background: #2a2a3a;")
        self.cover.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cover.setPixmap(placeholder_cover(video.title).scaled(
            156, 208, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation))
        if video.status:
            badge = QLabel(video.status, self.cover)
            badge.setStyleSheet(
                "background: rgba(0,0,0,150); color: #ffd166; border-radius: 4px;"
                "padding: 2px 6px; font-size: 11px;")
            badge.move(6, 6)
            badge.show()
        if video.latest_episode:
            ep = QLabel(video.latest_episode, self.cover)
            ep.setStyleSheet(
                "background: rgba(0,0,0,160); color: white; border-radius: 4px;"
                "padding: 2px 6px; font-size: 11px;")
            ep.adjustSize()
            ep.move(156 - ep.width() - 6, 208 - ep.height() - 6)
            ep.show()

        self.title = QLabel(video.title)
        self.title.setProperty("class", "title")
        self.title.setWordWrap(True)
        self.title.setFixedHeight(38)
        self.title.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)

        sub = video.tag or video.year or video.rating
        self.sub = QLabel(sub)
        self.sub.setProperty("class", "dim")

        lay.addWidget(self.cover)
        lay.addWidget(self.title)
        lay.addWidget(self.sub)

        if video.cover:
            def set_pm(pm, c=self.cover, vid=video.id):
                if pm:
                    c.setPixmap(rounded_pixmap(pm.scaled(
                        c.size(), Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                        Qt.TransformationMode.SmoothTransformation)))
            fetch_pixmap(video.cover, set_pm)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        self.clicked.emit(self._video)
        super().mouseReleaseEvent(event)


class FlowGrid(QWidget):
    """Simple wrapping grid of cover cards."""

    video_chosen = pyqtSignal(object)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._container = QWidget()
        self._container.setStyleSheet("background: transparent;")
        self._grid = QGridLayout(self._container)
        self._grid.setContentsMargins(4, 4, 4, 4)
        self._grid.setSpacing(14)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.viewport().setStyleSheet("background: transparent;")
        scroll.setWidget(self._container)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(scroll)
        self._cards: list[CoverCard] = []

    def clear(self) -> None:
        while self._grid.count():
            item = self._grid.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self._cards.clear()

    def add_videos(self, videos: list[models.Video]) -> None:
        if not self._cards:
            cols = max(2, (self.width() - 20) // (172 + 14))
        else:
            cols = max(2, (self.width() - 20) // (172 + 14))
        start = len(self._cards)
        for i, v in enumerate(videos):
            card = CoverCard(v)
            card.clicked.connect(self.video_chosen.emit)
            self._grid.addWidget(card, (start + i) // cols, (start + i) % cols)
            self._cards.append(card)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)


class BannerCarousel(QWidget):
    """Auto-rotating banner strip."""

    item_clicked = pyqtSignal(object)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(180)
        self._banners: list[models.Banner] = []
        self._index = 0
        self._pm: dict[str, QPixmap] = {}
        self._timer = QTimer(self)
        self._timer.setInterval(5000)
        self._timer.timeout.connect(self._rotate)

    def set_banners(self, banners: list[models.Banner]) -> None:
        self._banners = banners[:8]
        self._index = 0
        if self._banners:
            self._timer.start()
            for b in self._banners:
                if b.image and b.image not in self._pm:
                    fetch_pixmap(b.image, lambda pm, k=b.image: self._cache(k, pm))
            self.update()
        else:
            self.update()

    def _cache(self, key: str, pm) -> None:
        if pm:
            self._pm[key] = pm
            self.update()

    def _rotate(self) -> None:
        if self._banners:
            self._index = (self._index + 1) % len(self._banners)
            self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(4, 4, -4, -4)
        p.setClipPath(QPainterPath())
        path = QPainterPath()
        path.addRoundedRect(rect.x(), rect.y(), rect.width(), rect.height(), 12, 12)
        p.setClipPath(path)
        if not self._banners:
            p.fillRect(rect, QColor(style.BG_CARD))
            p.setPen(QColor(style.TEXT_DIM))
            p.drawText(rect, Qt.AlignmentFlag.AlignCenter, "加载中…")
            p.end()
            return
        b = self._banners[self._index]
        pm = self._pm.get(b.image)
        if pm:
            p.drawPixmap(rect, pm.scaled(rect.size(), Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                         Qt.TransformationMode.SmoothTransformation))
        else:
            p.fillRect(rect, QColor(style.BG_CARD))
        # bottom gradient + title
        grad = rect.height() - 64
        for i in range(64):
            p.setPen(QColor(0, 0, 0, int(160 * (i / 63))))
            p.drawLine(rect.left(), rect.bottom() - 64 + i, rect.right(), rect.bottom() - 64 + i)
        p.setPen(QColor("white"))
        f = p.font()
        f.setPixelSize(20)
        f.setBold(True)
        p.setFont(f)
        p.drawText(rect.adjusted(16, 0, -16, -10), Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignLeft,
                   b.title)
        # dots
        x = rect.center().x() - (len(self._banners) * 12) / 2
        for i in range(len(self._banners)):
            col = QColor("white") if i == self._index else QColor(255, 255, 255, 90)
            p.setBrush(col)
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(int(x + i * 12), rect.bottom() - 16, 7, 7)
        p.end()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if self._banners:
            self.item_clicked.emit(self._banners[self._index])
        super().mouseReleaseEvent(event)
