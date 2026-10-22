"""Main window: sidebar navigation + stacked pages + tray + startup bootstrap."""

from __future__ import annotations

import logging
import threading
from typing import Optional

from PyQt6.QtCore import Qt, QObject, QRunnable, QThreadPool, QTimer, pyqtSignal, QUrl
from PyQt6.QtGui import QAction, QCloseEvent, QDesktopServices, QIcon
from PyQt6.QtWidgets import (
    QLabel, QMainWindow, QMessageBox, QPushButton, QStackedWidget,
    QSystemTrayIcon, QVBoxLayout, QWidget, QHBoxLayout,
)

from .. import APP_NAME_LINUX, __version__
from ..core import config, danmaku as danmaku_mod, gateway, localdb, models
from . import icons, style
from .dialogs.login import LoginDialog
from .pages.detail import DetailPage
from .pages.home import HomePage
from .pages.library import FavoritesPage, HistoryPage
from .pages.search import SearchPage
from .pages.settings import SettingsPage

log = logging.getLogger("anime_player.main")


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


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self._state = config.app_state()
        self._gw = gateway.GatewayClient(self._state)
        self._dm = danmaku_mod.DanmakuClient(
            proxy=self._state.config.network_proxy)
        self._db = localdb.LocalDB()
        self._bridge = _Bridge()
        self._bridge.finished.connect(self._on_async)
        self._player = None

        self.setWindowTitle(f"{APP_NAME_LINUX} v{__version__}")
        self.resize(1200, 780)

        central = QWidget()
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ---------------------------------------------------------- sidebar
        side = QWidget()
        side.setObjectName("sidebar")
        side.setFixedWidth(190)
        sv = QVBoxLayout(side)
        sv.setContentsMargins(10, 8, 10, 12)
        sv.setSpacing(4)
        brand = QLabel("动漫播放器")
        brand.setObjectName("brand")
        sv.addWidget(brand)

        self._nav_btns: list[QPushButton] = []
        self._nav_specs = [
            ("home", "首页"),
            ("search", "搜索"),
            ("history", "历史"),
            ("star", "收藏"),
            ("user", "账号"),
            ("settings", "设置"),
        ]
        for i, (ic, label) in enumerate(self._nav_specs):
            b = QPushButton(f"  {label}")
            b.setProperty("class", "nav")
            b.setCheckable(True)
            b.setIcon(icons.icon(ic))
            b.clicked.connect(lambda _=False, idx=i: self.switch_page(idx))
            sv.addWidget(b)
            self._nav_btns.append(b)
        sv.addStretch(1)
        self._lbl_user = QLabel("游客模式")
        self._lbl_user.setProperty("class", "dim")
        self._lbl_user.setWordWrap(True)
        sv.addWidget(self._lbl_user)
        btn_login = QPushButton("登录（可选）")
        btn_login.clicked.connect(self.open_login)
        sv.addWidget(btn_login)

        # ----------------------------------------------------------- stack
        self.stack = QStackedWidget()
        self.page_home = HomePage(self._gw)
        self.page_search = SearchPage(self._gw, self._dm)
        self.page_history = HistoryPage(self._db, self._gw)
        self.page_fav = FavoritesPage(self._db, self._gw)
        self.page_detail = DetailPage(self._gw, self._db, self._state)
        self.page_settings = SettingsPage(self._state, self._gw)
        # account page reuses settings-like simple widget
        self.page_user = self._build_user_page()

        for p in (self.page_home, self.page_search, self.page_history,
                  self.page_fav, self.page_user, self.page_settings, self.page_detail):
            self.stack.addWidget(p)

        root.addWidget(side)
        root.addWidget(self.stack, stretch=1)
        self.setCentralWidget(central)

        self.page_home.video_open_requested.connect(self.open_detail)
        self.page_search.video_open_requested.connect(self.open_detail)
        self.page_history.video_open_requested.connect(self.open_detail)
        self.page_fav.video_open_requested.connect(self.open_detail)
        self.page_detail.back_requested.connect(lambda: self.switch_page(0))
        self.page_detail.play_requested.connect(self.open_player)

        self._nav_btns[0].setChecked(True)

        # ------------------------------------------------------------- tray
        self._tray: Optional[QSystemTrayIcon] = None
        if QSystemTrayIcon.isSystemTrayAvailable():
            self._tray = QSystemTrayIcon(QIcon(icons.icon_pixmap("danmaku-on", style.ACCENT, 48)), self)
            show = QAction("显示主窗口", self)
            show.triggered.connect(self._show_from_tray)
            quit_act = QAction("退出", self)
            quit_act.triggered.connect(self._quit_app)
            from PyQt6.QtWidgets import QMenu
            m = QMenu()
            m.addAction(show)
            m.addAction(quit_act)
            self._tray.setContextMenu(m)
            self._tray.activated.connect(
                lambda reason: self._show_from_tray()
                if reason == QSystemTrayIcon.ActivationReason.Trigger else None)
            self._tray.show()

        self._startup()

    # --------------------------------------------------------------- startup
    def _startup(self) -> None:
        if self._state.config.api_host:
            self._gw.set_base_url(self._state.config.api_host)

        def work():
            # discover gateway unless manually pinned; then fetch update/notice
            base = self._gw.base_url or self._gw.discover(timeout=8.0)
            update = affiche = None
            try:
                update = self._gw.get_update()
            except Exception:  # noqa: BLE001
                pass
            try:
                affiche = self._gw.get_affiche()
            except Exception:  # noqa: BLE001
                pass
            if self._state.session.logged_in:
                try:
                    info = self._gw.get_user_info()
                    self._state.session.nickname = info.nickname or self._state.session.nickname
                    self._state.session.is_vip = info.is_vip
                    self._state.session.save()
                except Exception:  # noqa: BLE001
                    pass
            return base, update, affiche

        def done(result, exc):
            try:
                if exc is not None:
                    self.page_settings.lbl_status.setText(str(exc))
                    return
                base, update, affiche = result
                self.refresh_user_label()
                if update and self._state.config.auto_update:
                    self._maybe_show_update(update)
                if affiche and self._state.config.announce_affiche:
                    self._show_affiche(affiche)
            except RuntimeError:
                # window already destroyed (e.g. shutdown during bootstrap)
                return

        QThreadPool.globalInstance().start(_Task(work, done))

    def _maybe_show_update(self, update: dict) -> None:
        ver = str(update.get("version", update.get("version_name", "")))
        url = str(update.get("url", update.get("download_url", "")))
        if ver and ver != self._state.runtime.update_seen_version:
            self._state.runtime.update_seen_version = ver
            self._state.save_runtime()
            if url and ver > __version__:
                ret = QMessageBox.question(
                    self, "发现新版本",
                    f"检测到新版本 {ver}（当前 v{__version__}）。\n是否打开下载页面？")
                if ret == QMessageBox.StandardButton.Yes:
                    QDesktopServices.openUrl(QUrl(url))

    def _show_affiche(self, affiche) -> None:
        text = ""
        if isinstance(affiche, dict):
            text = str(affiche.get("content") or affiche.get("text")
                      or affiche.get("message") or "")
        elif isinstance(affiche, list) and affiche:
            first = affiche[0]
            if isinstance(first, dict):
                text = str(first.get("content") or first.get("title") or "")
        if text:
            QMessageBox.information(self, "公告", text[:600])

    # ---------------------------------------------------------------- pages
    def switch_page(self, index: int) -> None:
        # nav index 0-5 map to stack pages 0-5 (detail is index 6)
        self.stack.setCurrentIndex(index)
        for i, b in enumerate(self._nav_btns):
            b.setChecked(i == index)
        if index == 0 and not self.page_home.loaded:
            self.page_home.reload()
        elif index == 2:
            self.page_history.reload()
        elif index == 3:
            self.page_fav.reload()

    def open_detail(self, video_id: str) -> None:
        self.stack.setCurrentWidget(self.page_detail)
        for b in self._nav_btns:
            b.setChecked(False)
        self.page_detail.load(video_id)

    def open_player(self, video: models.Video, episodes: list[models.Episode], index: int) -> None:
        if self._state.config.external_player:
            ep = episodes[index]
            url = ep.video_url
            if url:
                import shlex, subprocess
                cmd = shlex.split(self._state.config.external_player) + [url]
                try:
                    subprocess.Popen(cmd)
                    return
                except OSError as exc:
                    log.warning("external player failed: %s", exc)
        from .player.player_page import PlayerPage
        if self._player is None:
            self._player = PlayerPage(self._state, self._dm)
            self._player.history_updated.connect(self._on_history)
        self._player.open_video(video, episodes, index)

    def _on_history(self, item: dict) -> None:
        video = {"id": item.get("id"), "title": item.get("title"), "cover": item.get("cover")}
        self._db.put_history(
            video,
            str(item.get("episode_id", "")),
            str(item.get("episode_title", "")),
            int(item.get("position_ms", 0)),
            int(item.get("duration_ms", 0)),
        )
        gw = self._gw
        if self._state.session.logged_in:
            def push():
                gw.put_remote_history({
                    "video_id": item.get("id"),
                    "episode_id": item.get("episode_id"),
                    "position_ms": item.get("position_ms"),
                    "duration_ms": item.get("duration_ms"),
                })
            threading.Thread(target=push, daemon=True).start()

    # ----------------------------------------------------------------- user
    def _build_user_page(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(18, 14, 18, 10)
        v.setSpacing(12)
        title = QLabel("账号")
        title.setStyleSheet("font-size: 20px; font-weight: 700;")
        v.addWidget(title)
        self._user_info = QLabel("游客模式：无需登录，历史与收藏仅保存在本机。")
        self._user_info.setWordWrap(True)
        self._user_info.setStyleSheet("font-size: 15px;")
        v.addWidget(self._user_info)
        # 纯净版：不提供会员/金币/充值入口；登录仅用于可选的多端同步。
        self._vip_info = QLabel("登录是可选的，仅用于在多台设备之间同步历史与收藏。")
        self._vip_info.setWordWrap(True)
        self._vip_info.setProperty("class", "dim")
        v.addWidget(self._vip_info)
        row = QHBoxLayout()
        b_login = QPushButton("登录（可选）")
        b_login.clicked.connect(self.open_login)
        b_logout = QPushButton("退出登录")
        b_logout.clicked.connect(self._logout)
        row.addWidget(b_login)
        row.addWidget(b_logout)
        row.addStretch(1)
        v.addLayout(row)
        v.addStretch(1)
        return w

    def refresh_user_label(self) -> None:
        sess = self._state.session
        if sess.logged_in:
            name = sess.nickname or sess.phone_hint or sess.user_id or "已登录"
            self._lbl_user.setText(f"{name}\n（已登录·可同步）")
            self._user_info.setText(
                f"账号：{sess.phone_hint or sess.user_id}\n"
                f"昵称：{sess.nickname or '—'}\n"
                "已登录：历史与收藏将同步到云端（本地始终保留副本）。")
            self._vip_info.setText("登录仅用于多端同步，其余功能与游客模式完全一致。")
        else:
            self._lbl_user.setText("游客模式")
            self._user_info.setText("游客模式：无需登录，历史与收藏仅保存在本机。")
            self._vip_info.setText("登录是可选的，仅用于在多台设备之间同步历史与收藏。")

    def open_login(self) -> None:
        dlg = LoginDialog(self._gw, self._state, self)
        dlg.login_succeeded.connect(self._after_login)
        dlg.exec()

    def _after_login(self) -> None:
        self.refresh_user_label()
        self.switch_page(4)

    def _logout(self) -> None:
        if not self._state.session.logged_in:
            return
        ret = QMessageBox.question(self, "退出登录", "确定退出当前账号？")
        if ret == QMessageBox.StandardButton.Yes:
            self._state.session.clear()
            self.refresh_user_label()
            # best-effort remote logout without blocking the UI
            threading.Thread(target=lambda: self._gw.logout(), daemon=True).start()

    def _on_async(self, result, exc) -> None:  # generic sink
        log.debug("async done: %s / %s", result, exc)

    # ------------------------------------------------------------ windowing
    def _show_from_tray(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _quit_app(self) -> None:
        from PyQt6.QtWidgets import QApplication
        self._state.config.save()
        QApplication.quit()

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        # minimize to tray instead of exiting
        if self._tray is not None:
            event.ignore()
            self.hide()
            self._tray.showMessage(
                "动漫播放器", "已最小化到托盘，右键图标可退出。",
                QSystemTrayIcon.MessageIcon.Information, 2500)
        else:
            self._state.config.save()
            event.accept()
