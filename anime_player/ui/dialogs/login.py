"""Login dialog: password / SMS code / QR code tabs."""

from __future__ import annotations

import base64
import logging
import tempfile
from typing import Optional

from PyQt6.QtCore import Qt, QObject, QRunnable, QThreadPool, QTimer, pyqtSignal
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QPushButton, QTabWidget, QVBoxLayout, QWidget,
)

from ...core import config, gateway

log = logging.getLogger("anime_player.login")

QR_STATES = {
    "waiting_scan": "等待扫码",
    "scanned": "已扫码，请在手机上确认",
    "confirmed": "已确认",
    "success": "登录成功",
    "expired": "二维码已过期",
    "cancelled": "已取消",
}


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


class LoginDialog(QDialog):
    login_succeeded = pyqtSignal()

    def __init__(self, gw: gateway.GatewayClient, state: config.AppState,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._gw = gw
        self._state = state
        self._bridge = _Bridge()
        self._bridge.finished.connect(self._on_async)
        self._qr_session_id = ""
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(2500)
        self._poll_timer.timeout.connect(self._poll_qr)
        self._op: str = ""

        self.setWindowTitle("登录")
        self.setMinimumWidth(380)
        root = QVBoxLayout(self)
        tabs = QTabWidget()

        # ---- password
        pw = QWidget()
        form = QFormLayout(pw)
        self.ed_phone = QLineEdit()
        self.ed_phone.setPlaceholderText("手机号")
        self.ed_password = QLineEdit()
        self.ed_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.ed_password.setPlaceholderText("密码")
        btn_login = QPushButton("登 录")
        btn_login.setObjectName("primary")
        btn_login.clicked.connect(self._login_password)
        form.addRow("账号", self.ed_phone)
        form.addRow("密码", self.ed_password)
        form.addRow("", btn_login)
        tabs.addTab(pw, "密码登录")

        # ---- sms
        sms = QWidget()
        form2 = QFormLayout(sms)
        self.ed_phone2 = QLineEdit()
        self.ed_phone2.setPlaceholderText("手机号")
        self.ed_code = QLineEdit()
        self.ed_code.setPlaceholderText("短信验证码")
        row = QHBoxLayout()
        btn_send = QPushButton("获取验证码")
        btn_send.clicked.connect(self._send_sms)
        row.addWidget(btn_send)
        row.addWidget(self.ed_code)
        btn_login2 = QPushButton("登 录")
        btn_login2.setObjectName("primary")
        btn_login2.clicked.connect(self._login_code)
        form2.addRow("账号", self.ed_phone2)
        form2.addRow("验证码", row)
        form2.addRow("", btn_login2)
        tabs.addTab(sms, "验证码登录")

        # ---- qr
        qr = QWidget()
        v = QVBoxLayout(qr)
        self.lbl_qr = QLabel("点击刷新获取二维码")
        self.lbl_qr.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_qr.setFixedSize(220, 220)
        self.lbl_qr.setStyleSheet("background: white; border-radius: 8px;")
        self.lbl_qr_state = QLabel("")
        self.lbl_qr_state.setAlignment(Qt.AlignmentFlag.AlignCenter)
        btn_qr = QPushButton("获取二维码")
        btn_qr.clicked.connect(self._start_qr)
        v.addWidget(self.lbl_qr, alignment=Qt.AlignmentFlag.AlignHCenter)
        v.addWidget(self.lbl_qr_state)
        v.addWidget(btn_qr, alignment=Qt.AlignmentFlag.AlignHCenter)
        tabs.addTab(qr, "二维码登录")

        # ---- register / retrieve
        reg = QWidget()
        form3 = QFormLayout(reg)
        self.ed_phone3 = QLineEdit()
        self.ed_code3 = QLineEdit()
        self.ed_pwd3 = QLineEdit()
        self.ed_pwd3.setEchoMode(QLineEdit.EchoMode.Password)
        row3 = QHBoxLayout()
        btn_send3 = QPushButton("获取验证码")
        btn_send3.clicked.connect(lambda: self._send_sms(scene="register"))
        row3.addWidget(btn_send3)
        row3.addWidget(self.ed_code3)
        btn_reg = QPushButton("注册 / 找回密码")
        btn_reg.clicked.connect(self._register)
        form3.addRow("手机号", self.ed_phone3)
        form3.addRow("验证码", row3)
        form3.addRow("新密码", self.ed_pwd3)
        form3.addRow("", btn_reg)
        tabs.addTab(reg, "注册/找回")

        root.addWidget(tabs)
        self.lbl_msg = QLabel("")
        self.lbl_msg.setStyleSheet("color: #e05c5c;")
        self.lbl_msg.setWordWrap(True)
        root.addWidget(self.lbl_msg)

    # ------------------------------------------------------------ password
    def _login_password(self) -> None:
        phone = self.ed_phone.text().strip()
        pwd = self.ed_password.text()
        if not phone or not pwd:
            self.lbl_msg.setText("请输入账号和密码")
            return
        self._op = "login_password"
        self.lbl_msg.setText("登录中…")
        QThreadPool.globalInstance().start(
            _Task(lambda: self._gw.login_password(phone, pwd), self._bridge.finished.emit))

    # ----------------------------------------------------------------- sms
    def _send_sms(self, scene: str = "login") -> None:
        phone = (self.ed_phone2 if scene == "login" else self.ed_phone3).text().strip()
        if not phone:
            self.lbl_msg.setText("请输入手机号")
            return
        self._op = f"sms_{scene}"
        self.lbl_msg.setText("发送中…")

        def work():
            cap = self._gw.captcha_image()
            # pass along any captcha token the server provided
            token = str(cap.get("token", cap.get("captcha_id", ""))) if cap else ""
            return self._gw.send_sms(phone, token, scene=scene)

        QThreadPool.globalInstance().start(_Task(work, self._bridge.finished.emit))

    def _login_code(self) -> None:
        phone = self.ed_phone2.text().strip()
        code = self.ed_code.text().strip()
        if not phone or not code:
            self.lbl_msg.setText("请输入手机号和验证码")
            return
        self._op = "login_code"
        self.lbl_msg.setText("登录中…")
        QThreadPool.globalInstance().start(
            _Task(lambda: self._gw.login_code(phone, code), self._bridge.finished.emit))

    def _register(self) -> None:
        phone = self.ed_phone3.text().strip()
        code = self.ed_code3.text().strip()
        pwd = self.ed_pwd3.text()
        if not (phone and code and pwd):
            self.lbl_msg.setText("请完整填写")
            return
        self._op = "register"
        self.lbl_msg.setText("提交中…")
        QThreadPool.globalInstance().start(
            _Task(lambda: self._gw.register(phone, code, pwd), self._bridge.finished.emit))

    # ------------------------------------------------------------------ qr
    def _start_qr(self) -> None:
        self._op = "qr_start"
        QThreadPool.globalInstance().start(
            _Task(self._gw.qr_login_start, self._bridge.finished.emit))

    def _poll_qr(self) -> None:
        if not self._qr_session_id:
            return
        sid = self._qr_session_id

        def work():
            return self._gw.qr_login_query(sid)

        QThreadPool.globalInstance().start(
            _Task(work, lambda r, e: self._bridge.finished.emit(("qr_poll", r, e), None)))

    # -------------------------------------------------------------- results
    def _on_async(self, result, exc) -> None:
        if isinstance(result, tuple) and result and result[0] == "qr_poll":
            _, payload, poll_exc = result
            self._handle_qr_poll(payload, poll_exc)
            return
        if exc is not None:
            self.lbl_msg.setText(str(exc))
            return
        payload = result if isinstance(result, dict) else {}
        if self._op.startswith("sms_"):
            self.lbl_msg.setStyleSheet("color: #7cc98f;")
            self.lbl_msg.setText("验证码已发送")
            return
        if self._op == "qr_start":
            self._qr_session_id = str(payload.get("session_id", payload.get("sid", "")))
            content = str(payload.get("qr_content", payload.get("qr_url", payload.get("content", ""))))
            self._show_qr(content)
            self._poll_timer.start()
            return
        # login/register success → persist token + user info
        token = str(payload.get("token", payload.get("access_token", "")))
        user = payload.get("user") if isinstance(payload.get("user"), dict) else payload
        if token or user.get("id") or user.get("user_id"):
            sess = self._state.session
            sess.token = token or sess.token
            from ...core import models
            info = models.UserInfo.from_api(user if isinstance(user, dict) else {})
            sess.user_id = info.user_id or sess.user_id
            sess.nickname = info.nickname or sess.nickname
            sess.avatar = info.avatar or sess.avatar
            sess.is_vip = info.is_vip
            sess.vip_expire_at = info.vip_expire_at
            sess.phone_hint = info.phone
            self._state.save_session()
            self.login_succeeded.emit()
            self.accept()
        else:
            self.lbl_msg.setText(str(payload.get("message", payload.get("msg", "登录失败"))))

    def _handle_qr_poll(self, payload, exc) -> None:
        if exc is not None:
            return
        if not isinstance(payload, dict):
            return
        state = str(payload.get("state", payload.get("status", "")))
        self.lbl_qr_state.setText(QR_STATES.get(state, state))
        if state in ("success", "confirmed"):
            self._poll_timer.stop()
            # server returns auth material on success
            token = str(payload.get("token", payload.get("access_token", "")))
            if token:
                self._state.session.token = token
                self._state.save_session()
            self.login_succeeded.emit()
            self.accept()
        elif state in ("expired", "cancelled"):
            self._poll_timer.stop()

    def _show_qr(self, content: str) -> None:
        if not content:
            self.lbl_qr_state.setText("未返回二维码内容")
            return
        self.lbl_qr_state.setText(QR_STATES["waiting_scan"])
        # render QR without extra deps: use Qt's barcode-free fallback —
        # generate via qrcode lib if available, else show the raw text.
        try:
            import qrcode  # type: ignore
            img = qrcode.make(content)
            import io
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            pm = QPixmap()
            pm.loadFromData(buf.getvalue())
            self.lbl_qr.setPixmap(pm.scaled(
                self.lbl_qr.size(), Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation))
            return
        except Exception:  # noqa: BLE001
            pass
        # simple fallback: render text (user can copy)
        self.lbl_qr.setText(content[:60])
        self.lbl_qr.setStyleSheet("background: white; color: black; border-radius: 8px; padding: 8px;")

    def closeEvent(self, event) -> None:  # noqa: N802
        self._poll_timer.stop()
        if self._qr_session_id:
            import threading
            sid = self._qr_session_id
            threading.Thread(target=lambda: self._gw.qr_login_cancel(sid),
                             daemon=True).start()
        super().closeEvent(event)
