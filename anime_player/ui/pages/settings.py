"""Settings page: gateway/proxy/theme/player options/about."""

from __future__ import annotations

import logging
from typing import Optional

from PyQt6.QtCore import QObject, QRunnable, QThreadPool, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QSpinBox, QVBoxLayout, QWidget,
)

from ... import __version__
from ...core import config, gateway, paths

log = logging.getLogger("anime_player.settings")


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


class SettingsPage(QWidget):
    def __init__(self, state: config.AppState, gw: gateway.GatewayClient,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._state = state
        self._gw = gw

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 14, 18, 10)
        root.setSpacing(16)

        title = QLabel("设置")
        title.setStyleSheet("font-size: 20px; font-weight: 700;")
        root.addWidget(title)

        form = QFormLayout()
        form.setSpacing(12)
        cfg = state.config

        self.ed_host = QLineEdit(cfg.api_host)
        self.ed_host.setPlaceholderText("留空自动发现；示例：http://tx.xn--vhqr42drhf5k7b.com")
        form.addRow("API 地址", self.ed_host)

        self.ed_proxy = QLineEdit(cfg.network_proxy)
        self.ed_proxy.setPlaceholderText("示例：http://127.0.0.1:7890（留空直连）")
        form.addRow("网络代理", self.ed_proxy)

        self.ck_danmaku = QCheckBox("启用弹幕")
        self.ck_danmaku.setChecked(cfg.danmaku_enabled)
        form.addRow("播放", self.ck_danmaku)

        self.spin_dm_size = QSpinBox()
        self.spin_dm_size.setRange(14, 48)
        self.spin_dm_size.setValue(cfg.danmaku_font_size)
        form.addRow("弹幕字号", self.spin_dm_size)

        self.spin_dm_opacity = QSpinBox()
        self.spin_dm_opacity.setRange(20, 100)
        self.spin_dm_opacity.setValue(int(cfg.danmaku_opacity * 100))
        form.addRow("弹幕不透明度 %", self.spin_dm_opacity)

        self.ck_next = QCheckBox("自动连播")
        self.ck_next.setChecked(cfg.autoplay_next)
        form.addRow("", self.ck_next)

        self.cb_quality = QComboBox()
        self.cb_quality.addItems(["最高画质优先", "流畅优先"])
        self.cb_quality.setCurrentIndex(0 if cfg.prefer_quality != "low" else 1)
        form.addRow("画质偏好", self.cb_quality)

        self.ck_affiche = QCheckBox("启动时显示服务端公告")
        self.ck_affiche.setChecked(cfg.announce_affiche)
        form.addRow("", self.ck_affiche)

        self.ed_ext_player = QLineEdit(cfg.external_player)
        self.ed_ext_player.setPlaceholderText("可选：使用外部播放器命令，如 mpv --fs")
        form.addRow("外部播放器", self.ed_ext_player)

        self.ck_update = QCheckBox("启动时检查更新")
        self.ck_update.setChecked(cfg.auto_update)
        form.addRow("", self.ck_update)

        root.addLayout(form)

        btn_row = QHBoxLayout()
        btn_test = QPushButton("测试连接")
        btn_test.clicked.connect(self._test)
        btn_save = QPushButton("保存设置")
        btn_save.setObjectName("primary")
        btn_save.clicked.connect(self._save)
        btn_row.addWidget(btn_test)
        btn_row.addWidget(btn_save)
        btn_row.addStretch(1)
        root.addLayout(btn_row)

        self.lbl_status = QLabel("")
        self.lbl_status.setWordWrap(True)
        self.lbl_status.setProperty("class", "dim")
        root.addWidget(self.lbl_status)

        rt = state.runtime
        info = QLabel(
            f"动漫播放器 v{__version__}（独立开发，仅供个人使用）\n"
            f"上次网关：{rt.last_gateway_base_url or '无'}"
            f"（{rt.last_gateway_source or '-'}）\n"
            f"数据目录：{paths.data_dir()}\n"
            "本软件为独立实现，与任何商业软件无关联；"
            "视频增强依赖 mpv（Anime4K 着色器为 GPL-3.0）。"
        )
        info.setProperty("class", "dim")
        info.setOpenExternalLinks(False)
        root.addWidget(info)
        root.addStretch(1)

    def _save(self) -> None:
        cfg = self._state.config
        cfg.api_host = self.ed_host.text().strip().rstrip("/")
        cfg.network_proxy = self.ed_proxy.text().strip()
        cfg.danmaku_enabled = self.ck_danmaku.isChecked()
        cfg.danmaku_font_size = self.spin_dm_size.value()
        cfg.danmaku_opacity = self.spin_dm_opacity.value() / 100.0
        cfg.autoplay_next = self.ck_next.isChecked()
        cfg.prefer_quality = "low" if self.cb_quality.currentIndex() == 1 else "best"
        cfg.announce_affiche = self.ck_affiche.isChecked()
        cfg.external_player = self.ed_ext_player.text().strip()
        cfg.auto_update = self.ck_update.isChecked()
        self._state.save_config()
        self._gw.set_proxy(cfg.network_proxy)
        if cfg.api_host:
            self._gw.set_base_url(cfg.api_host)
        self.lbl_status.setText("已保存。")

    def _test(self) -> None:
        self.lbl_status.setText("测试中…")
        self._save()

        def work():
            return self._gw.discover(timeout=8.0)

        def done(result, exc):
            if exc:
                self.lbl_status.setText(f"连接失败：{exc}")
            else:
                self.lbl_status.setText(f"连接成功：{result}")

        QThreadPool.globalInstance().start(_Task(work, done))
