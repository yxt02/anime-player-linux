"""Detail page: cover/meta, episode grid, favorite toggle."""

from __future__ import annotations

import logging
from typing import Optional

from PyQt6.QtCore import Qt, QObject, QRunnable, QThreadPool, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QSizePolicy,
    QVBoxLayout, QWidget,
)

from ...core import config, gateway, localdb, models
from .. import icons, style

log = logging.getLogger("anime_player.detail")


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


class DetailPage(QWidget):
    play_requested = pyqtSignal(object, list, int)   # video, episodes, index
    back_requested = pyqtSignal()

    def __init__(self, gw: gateway.GatewayClient, db: localdb.LocalDB,
                 state: config.AppState, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._gw = gw
        self._db = db
        self._state = state
        self._pool = QThreadPool.globalInstance()
        self._video: Optional[models.Video] = None
        self._episodes: list[models.Episode] = []
        self._bridge = _Bridge()
        self._bridge.finished.connect(self._on_loaded)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 14, 18, 10)
        root.setSpacing(12)

        back_row = QHBoxLayout()
        back = QPushButton()
        back.setIcon(icons.icon("back"))
        back.setFixedSize(34, 34)
        back.setStyleSheet("background: transparent; border: none;")
        back.clicked.connect(self.back_requested.emit)
        self._lbl_title = QLabel("详情")
        self._lbl_title.setStyleSheet("font-size: 20px; font-weight: 700;")
        back_row.addWidget(back)
        back_row.addWidget(self._lbl_title)
        back_row.addStretch(1)
        self._btn_fav = QPushButton(" 收藏")
        self._btn_fav.clicked.connect(self._toggle_fav)
        back_row.addWidget(self._btn_fav)
        root.addLayout(back_row)

        hero = QFrame()
        hero.setObjectName("card")
        hero_lay = QHBoxLayout(hero)
        hero_lay.setContentsMargins(14, 14, 14, 14)
        self._cover = QLabel()
        self._cover.setFixedSize(140, 190)
        self._cover.setStyleSheet("border-radius: 8px; background: #2a2a3a;")
        meta = QVBoxLayout()
        self._meta_lines: list[QLabel] = []
        for _ in range(5):
            lb = QLabel("")
            lb.setWordWrap(True)
            meta.addWidget(lb)
            self._meta_lines.append(lb)
        meta.addStretch(1)
        hero_lay.addWidget(self._cover)
        hero_lay.addLayout(meta, stretch=1)
        root.addWidget(hero)

        ep_label = QLabel("选集")
        ep_label.setStyleSheet("font-size: 16px; font-weight: 600;")
        root.addWidget(ep_label)

        self._ep_wrap = QWidget()
        self._ep_wrap.setStyleSheet("background: transparent;")
        self._ep_lay = QHBoxLayout(self._ep_wrap)
        self._ep_lay.setContentsMargins(0, 0, 0, 0)
        self._ep_lay.setSpacing(8)
        self._ep_lay.addStretch(1)
        ep_scroll = QScrollArea()
        ep_scroll.setWidgetResizable(True)
        ep_scroll.setWidget(self._ep_wrap)
        ep_scroll.setFixedHeight(96)
        ep_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        ep_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        root.addWidget(ep_scroll)

        self._hint = QLabel("")
        self._hint.setProperty("class", "dim")
        root.addWidget(self._hint)
        root.addStretch(1)

    # ------------------------------------------------------------------ load
    def load(self, video_id: str) -> None:
        self._lbl_title.setText("加载中…")
        for lb in self._meta_lines:
            lb.setText("")

        def work():
            detail = self._gw.get_video_detail(video_id)
            episodes: list[models.Episode] = []
            for key in ("episodes", "parts", "playlist"):
                v = detail.get(key)
                if isinstance(v, list) and v:
                    episodes = [models.Episode.from_api(d) for d in v if isinstance(d, dict)]
                    break
            return detail, episodes

        def done(result, exc):
            self._bridge.finished.emit(result, exc)

        self._pool.start(_Task(work, done))

    def _on_loaded(self, result, exc) -> None:
        if exc is not None:
            self._lbl_title.setText("加载失败")
            self._hint.setText(str(exc))
            return
        detail, episodes = result
        video = models.Video.from_api(detail)
        self._video = video
        self._episodes = episodes
        self._lbl_title.setText(video.title or "详情")
        lines = [
            " / ".join(x for x in (video.year, video.area, video.tag) if x),
            " ".join(x for x in (f"评分 {video.rating}" if video.rating else "",
                                 video.status) if x),
            f"共 {video.episode_count or len(episodes)} 集",
            video.description[:180],
        ]
        for lb, text in zip(self._meta_lines, lines):
            lb.setText(text)
            lb.setStyleSheet("color: %s;" % (style.TEXT if text is video.description[:180] else style.TEXT_DIM))
        self._refresh_fav_button()
        # episodes
        while self._ep_lay.count() - 1 >= 0:  # keep trailing stretch
            item = self._ep_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for i, ep in enumerate(self._episodes):
            btn = QPushButton(ep.title or f"第{i + 1}集")
            btn.setFixedWidth(96)
            btn.clicked.connect(lambda _=False, idx=i: self._play(idx))
            self._ep_lay.addWidget(btn)
        self._ep_lay.addStretch(1)
        if not episodes:
            self._hint.setText("未找到剧集信息")
        if video.cover:
            from .widgets import fetch_pixmap
            def set_pm(pm):
                if pm:
                    from .widgets import rounded_pixmap
                    self._cover.setPixmap(rounded_pixmap(pm.scaled(
                        self._cover.size(), Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                        Qt.TransformationMode.SmoothTransformation)))
            fetch_pixmap(video.cover, set_pm)

    def _play(self, index: int) -> None:
        if not self._video or not (0 <= index < len(self._episodes)):
            return
        ep = self._episodes[index]
        if ep.video_url or ep.id:
            # resolve playable URL via play-key endpoint when missing
            if not ep.video_url and ep.id:
                def work():
                    payload = self._gw.get_play_key(ep.id)
                    sources = self._gw.play_sources(payload)
                    prefer = self._state.config.prefer_quality or "best"
                    ordered = gateway.choose_best_source(sources, prefer)
                    return [s.url for s in ordered if s.url]

                def done(result, exc):
                    urls = [u for u in (result or []) if isinstance(u, str)]
                    if exc is not None:
                        self._hint.setText(f"获取播放地址失败：{exc}")
                        return
                    if urls:
                        ep.video_url = urls[0]
                        ep.fallback_urls = urls[1:]
                        self.play_requested.emit(self._video, self._episodes, index)
                    else:
                        self._hint.setText("服务器未返回可用播放源（可能需要登录后观看此集）")
                self._pool.start(_Task(work, done))
                return
            # already resolved (detail payload carried urls) — still normalize order
            urls = [ep.video_url, *ep.fallback_urls]
            from ...core.models import PlaySource
            ordered = gateway.choose_best_source(
                [PlaySource(url=u, name="") for u in urls],
                self._state.config.prefer_quality or "best")
            if ordered:
                ep.video_url = ordered[0].url
                ep.fallback_urls = [s.url for s in ordered[1:]]
            self.play_requested.emit(self._video, self._episodes, index)

    def _toggle_fav(self) -> None:
        if not self._video:
            return
        vid = self._video.id
        if self._db.is_favorite(vid):
            self._db.remove_favorite(vid)
            try:
                self._gw.toggle_collect(vid)
            except Exception:  # noqa: BLE001
                pass
        else:
            self._db.put_favorite({
                "id": vid, "title": self._video.title, "cover": self._video.cover,
            })
            try:
                self._gw.toggle_collect(vid)
            except Exception:  # noqa: BLE001
                pass
        self._refresh_fav_button()

    def _refresh_fav_button(self) -> None:
        if not self._video:
            self._btn_fav.setText(" 收藏")
            return
        fav = self._db.is_favorite(self._video.id)
        self._btn_fav.setText(" ★ 已收藏" if fav else " ☆ 收藏")
