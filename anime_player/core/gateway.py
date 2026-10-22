"""Gateway client: host discovery + the pc/* REST surface.

Discovers the backend through a bootstrap/search gateway with fallback
candidates (plus env overrides ANIME_PLAYER_SEARCH_GATEWAY_BASE_URL and
ANIME_PLAYER_LEGACY_DIRECT_HOST), then calls plain-JSON endpoints under the
selected base URL.

Unknowns kept explicit: exact response envelopes vary per deployment; we
normalize via net.unwrap_envelope and tolerate several key spellings.
"""

from __future__ import annotations

import logging
import os
import re
import threading
from typing import Optional
from urllib.parse import urljoin

from . import config, models, net

log = logging.getLogger("anime_player.gateway")

# Default gateway candidates (may rotate; override via settings or env).
DEFAULT_CANDIDATES = [
    "http://tx.xn--vhqr42drhf5k7b.com",
    "http://bkbf.xn--vhqr42drhf5k7b.com",
    "https://9ciyuan9cy.com",
    "https://whalece.org",
]


class GatewayError(Exception):
    def __init__(self, message: str, *, retryable: bool = True):
        super().__init__(message)
        self.retryable = retryable


def _source_height(src: models.PlaySource) -> int:
    """Best-effort resolution hint for sorting (1080P→1080, 4K→2160, 蓝光→2160)."""
    label = f"{src.name} {src.url}".lower()
    if any(k in label for k in ("4k", "2160", "蓝光", "原画")):
        return 2160
    if "2k" in label or "1440" in label:
        return 1440
    # 数字分辨率优先于关键词（避免“高清 720P”被误抬到 1080）
    m = re.search(r"(\d{3,4})", src.name) or re.search(r"(\d{3,4})", label)
    if m:
        base = int(m.group(1))
        return base * 10 if base < 100 else base
    if any(k in label for k in ("超清", "高清", "fhd", "hd")):
        return 1080
    if any(k in label for k in ("流畅", "标清", "低清", "sd")):
        return 360
    return 0


def choose_best_source(
    sources: list["models.PlaySource"], prefer: str = "best"
) -> list["models.PlaySource"]:
    """Return sources ordered by preference (best first by default)."""
    unique: dict[str, models.PlaySource] = {}
    for s in sources:
        if s.url and s.url not in unique:
            unique[s.url] = s
    ordered = sorted(unique.values(), key=_source_height, reverse=True)
    if prefer == "low":
        ordered.reverse()
    return ordered


class GatewayClient:
    """Thread-safe gateway accessor with lazy host discovery."""

    def __init__(self, state: config.AppState) -> None:
        self._state = state
        self._session = net.build_session(state.config.network_proxy)
        self._base_url = ""
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ host
    @property
    def base_url(self) -> str:
        with self._lock:
            return self._base_url

    def set_base_url(self, url: str) -> None:
        with self._lock:
            self._base_url = (url or "").rstrip("/")
            self._state.runtime.last_gateway_base_url = self._base_url
            self._state.runtime.last_gateway_source = "manual"
            self._state.save_runtime()

    def set_proxy(self, proxy: str) -> None:
        self._state.config.network_proxy = proxy
        self._state.save_config()
        self._session = net.build_session(proxy)

    def candidates(self) -> list[str]:
        out: list[str] = []
        env_gateway = os.environ.get("ANIME_PLAYER_SEARCH_GATEWAY_BASE_URL", "").strip()
        env_direct = os.environ.get("ANIME_PLAYER_LEGACY_DIRECT_HOST", "").strip()
        for c in (env_direct, env_gateway, self._state.config.api_host,
                  self._state.runtime.last_gateway_base_url, *DEFAULT_CANDIDATES):
            c = (c or "").strip().rstrip("/")
            if c and c not in out:
                out.append(c)
        return out

    def discover(self, timeout: float = 8.0) -> str:
        """Try candidate base URLs until one serves a sane pc/config."""
        tried: list[str] = []
        for base in self.candidates():
            url = f"{base}/pc/config"
            data = net.get_json(self._session, url, timeout=timeout)
            ok, payload = net.unwrap_envelope(data) if data is not None else (False, None)
            if ok and isinstance(payload, dict):
                with self._lock:
                    self._base_url = base
                rt = self._state.runtime
                rt.last_gateway_base_url = base
                rt.last_gateway_source = "discovery"
                rt.last_failed_gateway_candidates = tried
                rt.failed_at_ms = 0
                self._state.save_runtime()
                log.info("gateway discovered: %s", base)
                return base
            tried.append(base)
        rt = self._state.runtime
        rt.last_failed_gateway_candidates = tried
        rt.failed_at_ms = int(__import__("time").time() * 1000)
        self._state.save_runtime()
        raise GatewayError(
            "无法连接服务器：候选网关全部失败。可在设置中手动填写 API 地址或配置网络代理。"
        )

    def ensure_base(self) -> str:
        if not self.base_url:
            return self.discover()
        return self.base_url

    # ------------------------------------------------------------------ http
    def _apply_auth(self) -> None:
        """Attach the session token when (and only when) the user is logged in.

        游客模式下 session.token 为空，请求与未登录客户端完全一致。
        """
        token = self._state.session.token
        if token:
            self._session.headers["Authorization"] = f"Bearer {token}"
        else:
            self._session.headers.pop("Authorization", None)

    def _get(self, path: str, params: Optional[dict] = None, *, keys: tuple = ()):
        self._apply_auth()
        base = self.ensure_base()
        url = f"{base}/{path.lstrip('/')}"
        data = net.get_json(self._session, url, params=params, expected_keys=keys)
        if data is None:
            # one retry after re-discovery (host may have rotated)
            with self._lock:
                stale = self._base_url
            self._base_url = ""
            try:
                base = self.discover()
            except GatewayError:
                self._base_url = stale
                raise GatewayError(f"请求失败：{path}", retryable=True)
            url = f"{base}/{path.lstrip('/')}"
            data = net.get_json(self._session, url, params=params, expected_keys=keys)
            if data is None:
                raise GatewayError(f"请求失败：{path}")
        ok, payload = net.unwrap_envelope(data)
        if not ok:
            msg = ""
            if isinstance(data, dict):
                msg = str(data.get("errorMessage") or data.get("msg") or data.get("message") or "")
            raise GatewayError(msg or f"接口返回失败：{path}", retryable=False)
        return payload

    def _post(self, path: str, payload: dict):
        self._apply_auth()
        base = self.ensure_base()
        url = f"{base}/{path.lstrip('/')}"
        data = net.post_json(self._session, url, payload)
        if data is None:
            raise GatewayError(f"请求失败：{path}")
        ok, out = net.unwrap_envelope(data)
        if not ok:
            msg = ""
            if isinstance(data, dict):
                msg = str(data.get("errorMessage") or data.get("msg") or data.get("message") or "")
            raise GatewayError(msg or f"接口返回失败：{path}", retryable=False)
        return out

    @staticmethod
    def _as_list(payload) -> list[dict]:
        if isinstance(payload, list):
            return [x for x in payload if isinstance(x, dict)]
        if isinstance(payload, dict):
            for key in ("list", "rows", "data", "items", "banners", "channels", "videos", "animes"):
                v = payload.get(key)
                if isinstance(v, list):
                    return [x for x in v if isinstance(x, dict)]
            # single object
            return [payload]
        return []

    # ------------------------------------------------------------ app.* APIs
    def get_config(self) -> dict:
        p = self._get("pc/config")
        return p if isinstance(p, dict) else {}

    def get_player_config(self) -> dict:
        p = self._get("pc/config/player")
        return p if isinstance(p, dict) else {}

    def get_update(self) -> dict:
        p = self._get("pc/update")
        return p if isinstance(p, dict) else {}

    def get_affiche(self):
        return self._get("pc/affiche")

    def get_agreement(self):
        return self._get("app/agreement")

    # ---------------------------------------------------------- catalog.*
    def get_banners(self) -> list[models.Banner]:
        return [models.Banner.from_api(d) for d in self._as_list(self._get("pc/banners", keys=("list", "banners", "data")))]

    def get_channels(self) -> list[models.Channel]:
        return [models.Channel.from_api(d) for d in self._as_list(self._get("pc/channel", keys=("list", "channels", "data")))]

    def get_channel_detail(self, channel_id: str, page: int = 1) -> list[models.Video]:
        payload = self._get(f"pc/channel/{channel_id}", params={"page": page})
        return [models.Video.from_api(d) for d in self._as_list(payload)]

    def get_video_list(self, page: int = 1, channel_id: str = "", sort: str = "") -> list[models.Video]:
        params: dict = {"page": page}
        if channel_id:
            params["channel_id"] = channel_id
        if sort:
            params["sort"] = sort
        payload = self._get("pc/video/list", params=params, keys=("list", "rows", "data"))
        return [models.Video.from_api(d) for d in self._as_list(payload)]

    def search_video(self, keyword: str, page: int = 1) -> list[models.Video]:
        payload = self._get("pc/video/search", params={"key": keyword, "page": page},
                            keys=("list", "rows", "data"))
        return [models.Video.from_api(d) for d in self._as_list(payload)]

    def get_video_detail(self, video_id: str) -> dict:
        """Detail lookup; tries several endpoint shapes (pc/video/key, ...)."""
        last_err: Optional[Exception] = None
        for path, params in (
            ("pc/video/key", {"id": video_id}),
            ("pc/video/detail", {"id": video_id}),
            (f"pc/video/{video_id}", None),
        ):
            try:
                payload = self._get(path, params=params)
                if isinstance(payload, dict) and payload:
                    return payload
            except GatewayError as exc:
                last_err = exc
                if not exc.retryable:
                    break
        if last_err:
            raise last_err
        raise GatewayError(f"未找到番剧：{video_id}", retryable=False)

    def get_episodes(self, video_id: str) -> list[models.Episode]:
        detail = self.get_video_detail(video_id)
        for key in ("episodes", "parts", "playlist"):
            v = detail.get(key)
            if isinstance(v, list):
                return [models.Episode.from_api(d) for d in v if isinstance(d, dict)]
        return [models.Episode.from_api(detail)] if detail.get("id") else []

    def get_play_key(self, episode_id: str, authenticate_nonce: str = "") -> dict:
        """Fetch playable stream info for an episode (pc/video/key)."""
        params = {"episode_id": episode_id}
        if authenticate_nonce:
            params["nonce"] = authenticate_nonce
        payload = self._get("pc/video/key", params=params)
        return payload if isinstance(payload, dict) else {}

    def play_sources(self, payload: dict) -> list[models.PlaySource]:
        for key in ("sources", "urls", "lines", "play_urls"):
            v = payload.get(key)
            if isinstance(v, list) and v:
                return [models.PlaySource.from_api(d) for d in v if isinstance(d, dict)]
        src = models.PlaySource.from_api(payload)
        return [src] if src.url else []

    # ---------------------------------------------------------- remote state
    def get_remote_history(self) -> list[dict]:
        return self._as_list(self._get("pc/history"))

    def put_remote_history(self, item: dict) -> None:
        try:
            self._post("pc/history", item)
        except GatewayError as exc:
            log.debug("put_remote_history ignored: %s", exc)

    def get_collect(self) -> list[models.Video]:
        return [models.Video.from_api(d) for d in self._as_list(self._get("pc/collect"))]

    def toggle_collect(self, video_id: str) -> bool:
        payload = self._post("pc/collect", {"video_id": video_id, "action": "toggle"})
        if isinstance(payload, dict):
            return bool(payload.get("collected", payload.get("status", True)))
        return True

    def report_play(self, episode_id: str, position_ms: int, duration_ms: int, finished: bool = False) -> None:
        try:
            self._post("pc/video/play", {
                "episode_id": episode_id,
                "position_ms": position_ms,
                "duration_ms": duration_ms,
                "finished": finished,
            })
        except GatewayError as exc:
            log.debug("report_play ignored: %s", exc)

    # ------------------------------------------------------------- auth.* APIs
    def login_password(self, phone: str, password: str, captcha: str = "") -> dict:
        payload = self._post("pc/users/login", {
            "phone": phone, "password": password, "captcha": captcha,
        })
        return payload if isinstance(payload, dict) else {}

    def login_code(self, phone: str, sms_code: str) -> dict:
        payload = self._post("pc/users/login", {
            "phone": phone, "code": sms_code, "type": "sms",
        })
        return payload if isinstance(payload, dict) else {}

    def send_sms(self, phone: str, captcha: str, scene: str = "login") -> dict:
        payload = self._post("pc/users/smscode", {
            "phone": phone, "captcha": captcha, "scene": scene,
        })
        return payload if isinstance(payload, dict) else {}

    def captcha_image(self) -> dict:
        payload = self._get("pc/users/captcha")
        return payload if isinstance(payload, dict) else {}

    def register(self, phone: str, code: str, password: str) -> dict:
        payload = self._post("pc/users/register", {
            "phone": phone, "code": code, "password": password,
        })
        return payload if isinstance(payload, dict) else {}

    def retrieve_password(self, phone: str, code: str, password: str) -> dict:
        payload = self._post("pc/users/retrieve", {
            "phone": phone, "code": code, "password": password,
        })
        return payload if isinstance(payload, dict) else {}

    def get_user_info(self) -> models.UserInfo:
        payload = self._get("pc/users/me")
        return models.UserInfo.from_api(payload if isinstance(payload, dict) else {})

    def logout(self) -> None:
        try:
            self._post("pc/users/logout", {})
        except GatewayError:
            pass
        self._state.session.clear()

    def qr_login_start(self) -> dict:
        payload = self._post("pc/users/qr", {"action": "start"})
        return payload if isinstance(payload, dict) else {}

    def qr_login_query(self, session_id: str) -> dict:
        payload = self._get("pc/users/qr", params={"session_id": session_id})
        return payload if isinstance(payload, dict) else {}

    def qr_login_cancel(self, session_id: str) -> None:
        try:
            self._post("pc/users/qr", {"action": "cancel", "session_id": session_id})
        except GatewayError:
            pass

    # -------------------------------------------------------------- user/vip
    def user_vip(self) -> dict:
        payload = self._get("pc/users/vip")
        return payload if isinstance(payload, dict) else {}

    def order_create(self, product: str) -> dict:
        payload = self._post("pc/users/order", {"product": product, "action": "create"})
        return payload if isinstance(payload, dict) else {}

    def pay_url(self, order: dict) -> str:
        for key in ("payment_url", "paymentUrl", "pay_url", "payUrl", "url"):
            v = order.get(key)
            if isinstance(v, str) and v.startswith("http"):
                return v
        return ""
