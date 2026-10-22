"""HTTP plumbing: proxy support, DoH resolution, timeouts.

Resolves rotating gateway hostnames via public DoH providers
(alidns / tencent / quad9).
"""

from __future__ import annotations

import json
import logging
import socket
import ssl
from typing import Optional
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.ssl_ import create_urllib3_context

log = logging.getLogger("anime_player.net")

DOH_ENDPOINTS = [
    "https://223.5.5.5/resolve?name={name}&type=A",       # alidns
    "https://doh.pub/dns-query?name={name}&type=A",        # tencent
    "https://dns.alidns.com/dns-query?name={name}&type=A",
]

UA = "anime-player-linux/0.1"


def build_session(proxy: str = "") -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept": "application/json, */*"})
    if proxy:
        s.proxies.update({"http": proxy, "https": proxy})
    adapter = HTTPAdapter(pool_connections=8, pool_maxsize=8)
    s.mount("http://", adapter)
    s.mount("https://", adapter)
    return s


def resolve_via_doh(name: str, timeout: float = 6.0) -> list[str]:
    """Return A-record IPs for *name* using public DoH resolvers."""
    ips: list[str] = []
    for ep in DOH_ENDPOINTS:
        try:
            r = requests.get(
                ep.format(name=name),
                headers={"accept": "application/dns-json", "User-Agent": UA},
                timeout=timeout,
            )
            data = r.json()
            for ans in data.get("Answer", []):
                if ans.get("type") == 1:
                    ip = ans.get("data", "")
                    if ip and not ip.startswith("127.") and not ip.startswith("198.18."):
                        ips.append(ip)
        except Exception as exc:  # noqa: BLE001 - any resolver failure is non-fatal
            log.debug("DoH %s failed for %s: %s", ep, name, exc)
        if ips:
            break
    return list(dict.fromkeys(ips))


def get_json(
    session: requests.Session,
    url: str,
    *,
    params: Optional[dict] = None,
    timeout: float = 12.0,
    expected_keys: tuple = (),
) -> Optional[dict | list]:
    """GET *url* and parse JSON. Returns None on failure.

    If *expected_keys* is given, a dict response must contain at least one.
    """
    try:
        r = session.get(url, params=params, timeout=timeout)
        if r.status_code != 200:
            log.debug("GET %s -> HTTP %s", url, r.status_code)
            return None
        ctype = r.headers.get("content-type", "")
        if "json" not in ctype and not r.text[:1] in ("{", "["):
            log.debug("GET %s -> non-JSON (%s)", url, ctype)
            return None
        data = r.json()
        if expected_keys and isinstance(data, dict):
            if not any(k in data for k in expected_keys):
                log.debug("GET %s -> missing keys %s (got %s)", url, expected_keys, list(data)[:8])
                return None
        return data
    except Exception as exc:  # noqa: BLE001
        log.debug("GET %s failed: %s", url, exc)
        return None


def post_json(
    session: requests.Session,
    url: str,
    payload: dict,
    *,
    timeout: float = 12.0,
) -> Optional[dict]:
    try:
        r = session.post(url, json=payload, timeout=timeout)
        if r.status_code != 200:
            return None
        return r.json()
    except Exception as exc:  # noqa: BLE001
        log.debug("POST %s failed: %s", url, exc)
        return None


def unwrap_envelope(data) -> tuple[bool, object]:
    """Normalize server envelopes to (ok, payload).

    Observed shapes: {success, data...} / {code, data} / raw list / raw dict.
    """
    if isinstance(data, list):
        return True, data
    if not isinstance(data, dict):
        return False, None
    if "success" in data:
        ok = bool(data.get("success"))
        payload = data.get("data")
        if payload is None:
            payload = {k: v for k, v in data.items() if k not in ("success", "errorCode", "errorMessage", "error")}
        return ok, payload
    if "code" in data:
        code = data.get("code")
        ok = code in (0, 200, "0", "200")
        return ok, data.get("data", data)
    return True, data
