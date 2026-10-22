"""External danmaku service client + ASS subtitle conversion.

Fetches third-party danmaku through a Bilibili-compatible mirror service
and converts items to ASS for libmpv/libass rendering
(`danmaku.convert_to_ass`).
"""

from __future__ import annotations

import logging
import re
from typing import Optional

import requests

from . import models, net

log = logging.getLogger("anime_player.danmaku")

DEFAULT_BASE = "https://api.danmaku.weeblify.app/ddp/v1"


class DanmakuClient:
    def __init__(self, base_url: str = DEFAULT_BASE, proxy: str = "") -> None:
        self.base_url = base_url.rstrip("/")
        self._session = net.build_session(proxy)
        self._session.headers.update({"User-Agent": "Danmu API/1.0"})

    # ------------------------------------------------------------------ api
    def _get(self, path: str, params: dict):
        url = f"{self.base_url}/{path.lstrip('/')}"
        params = {**params, "path": f"/{path.lstrip('/')}"}
        try:
            r = self._session.get(url, params=params, timeout=15)
            if r.status_code != 200:
                log.debug("danmaku GET %s -> %s", path, r.status_code)
                return None
            return r.json()
        except Exception as exc:  # noqa: BLE001
            log.debug("danmaku GET %s failed: %s", path, exc)
            return None

    def search_anime(self, keyword: str) -> list[models.Video]:
        data = self._get("v2/search/anime", {"keyword": keyword})
        if not isinstance(data, dict) or not data.get("success", True):
            return []
        items = data.get("animes") or (data.get("data") or {}).get("animes") or []
        return [models.Video.from_api(d) for d in items if isinstance(d, dict)]

    def get_episodes(self, anime_id: str) -> list[models.Episode]:
        data = self._get(f"v2/bangumi/{anime_id}", {})
        if not isinstance(data, dict) or not data.get("success", True):
            return []
        items = data.get("episodes") or (data.get("data") or {}).get("episodes") or []
        eps: list[models.Episode] = []
        for d in items:
            if not isinstance(d, dict):
                continue
            ep = models.Episode.from_api(d)
            if not ep.title:
                ep.title = d.get("episodeTitle") or d.get("episode_title") or ep.id
            eps.append(ep)
        return eps

    def get_comments(self, episode_id: str) -> list[models.Comment]:
        data = self._get(
            f"v2/comment/{episode_id}",
            {"from": 0, "withRelated": "true", "chConvert": 1},
        )
        if data is None:
            return []
        items: list = []
        if isinstance(data, dict):
            if not data.get("success", True) and not data.get("comments"):
                return []
            items = data.get("comments") or []
            if isinstance(items, dict):
                items = items.get("replies") or items.get("list") or []
            # bilibili reply envelope
            result = data.get("result")
            if not items and isinstance(result, dict):
                items = result.get("replies") or result.get("list") or []
        elif isinstance(data, list):
            items = data
        out: list[models.Comment] = []
        for d in items:
            if isinstance(d, dict):
                c = models.Comment.from_api(d)
                if c.text:
                    c.source = "external"
                    out.append(c)
        return out


# --------------------------------------------------------------- ASS output
ASS_HEADER = """[Script Info]
ScriptType: v4.00+
PlayResX: {resx}
PlayResY: {resy}
WrapStyle: 2
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.709

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Danmaku,{font},{size},&H00FFFFFF,&H00FFFFFF,&H64000000,&H64000000,0,0,0,0,100,100,0,0,1,1.5,0,8,20,20,20,1
Style: DanmakuTop,{font},{size},&H00FFFFFF,&H00FFFFFF,&H64000000,&H64000000,0,0,0,0,100,100,0,0,1,1.5,0,8,20,20,20,1
Style: DanmakuBottom,{font},{size},&H00FFFFFF,&H00FFFFFF,&H64000000,&H64000000,0,0,0,0,100,100,0,0,1,1.5,0,2,20,20,20,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

_MODE_SCROLL = (1, 2, 3, 6)
_MODE_TOP = (4, 5)
_MODE_BOTTOM = (7, 8, 9)


def _ts(ms: int) -> str:
    ms = max(0, ms)
    h, rem = divmod(ms, 3600_000)
    m, rem = divmod(rem, 60_000)
    s, ms10 = divmod(rem, 1000)
    return f"{h}:{m:02d}:{s:02d}.{ms10 // 10:02d}"


def _ass_color(rgb: int) -> str:
    r = (rgb >> 16) & 0xFF
    g = (rgb >> 8) & 0xFF
    b = rgb & 0xFF
    return f"&H00{b:02X}{g:02X}{r:02X}"


def _sanitize(text: str) -> str:
    text = re.sub(r"[{}\\]", "", text)
    return text.replace("\n", " ").strip()


def convert_to_ass(
    comments: list[models.Comment],
    *,
    resx: int = 1920,
    resy: int = 1080,
    font: str = "Sans CJK SC",
    font_size: int = 28,
    opacity: float = 1.0,
    enabled_modes: Optional[set] = None,
    scroll_duration_ms: int = 9000,
    max_per_line: int = 4,
) -> str:
    """Render danmaku items to an ASS subtitle document.

    Mode mapping follows the common bilibili convention:
    1-3/6 scroll, 4/5 top, 7-9 bottom. Vertical lanes avoid heavy overlap.
    """
    alpha = int(max(0.0, min(1.0, opacity)) * 255)
    alpha_tag = f"\\alpha&H{(255 - alpha):02X}&" if alpha < 255 else ""
    lines = [ASS_HEADER.format(resx=resx, resy=resy, font=font, size=font_size)]

    lane_h = int(font_size * 1.25)
    scroll_lanes = max(1, resy // lane_h - 2)
    fixed_lanes = 3

    scroll_used: dict[int, int] = {}
    top_used: dict[int, int] = {}
    bottom_used: dict[int, int] = {}
    last_end: dict[int, int] = {}

    items = sorted(comments, key=lambda c: c.time_ms)
    for c in items:
        text = _sanitize(c.text)
        if not text:
            continue
        if enabled_modes is not None and c.mode not in enabled_modes:
            continue
        # approximate width: CJK ~1em, ascii ~0.55em
        width = sum(font_size if ord(ch) > 0x2E80 else int(font_size * 0.55) for ch in text)
        color = _ass_color(c.color)
        start_ms = c.time_ms

        if c.mode in _MODE_SCROLL:
            end_ms = start_ms + scroll_duration_ms
            track = (start_ms // 200) % scroll_lanes
            chosen = None
            for off in range(scroll_lanes):
                lane = (track + off) % scroll_lanes
                prev_end = last_end.get(("s", lane), -1)
                # require the previous danmaku on this lane to be far enough ahead
                if prev_end <= start_ms:
                    chosen = lane
                    break
            if chosen is None:
                continue
            last_end[("s", chosen)] = end_ms
            y = lane_h * chosen + lane_h
            speed = (resx + width) / (scroll_duration_ms / 1000.0)
            exit_ms = start_ms + int((width + 20) / speed * 1000)
            text_field = f"{{Move({resx + 10},{y},{-width - 20},{y}){alpha_tag}}}{text}"
            lines.append(
                f"Dialogue: 8,{_ts(start_ms)},{_ts(end_ms)},Danmaku,,0,0,0,,{text_field}"
            )
            _ = exit_ms  # exit time folded into duration
        elif c.mode in _MODE_TOP or c.mode in _MODE_BOTTOM:
            is_top = c.mode in _MODE_TOP
            bucket = top_used if is_top else bottom_used
            key = "t" if is_top else "b"
            end_ms = start_ms + 4000
            chosen = None
            for lane in range(fixed_lanes):
                if last_end.get((key, lane), -1) <= start_ms:
                    chosen = lane
                    break
            if chosen is None:
                continue
            last_end[(key, chosen)] = end_ms
            if is_top:
                y = int(lane_h * (chosen + 1) * 1.6)
                style = "DanmakuTop"
                an = r"\an8\pos(960,%d)" % y
            else:
                y = resy - int(lane_h * (chosen + 2) * 1.5)
                style = "DanmakuBottom"
                an = r"\an2\pos(960,%d)" % y
            text_field = f"{{{an}{alpha_tag}}}{text}"
            lines.append(
                f"Dialogue: 6,{_ts(start_ms)},{_ts(end_ms)},{style},,0,0,0,,{text_field}"
            )
        # unknown modes are skipped
    return "\n".join(lines) + "\n"
