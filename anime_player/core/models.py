"""Domain models. Fields are normalized from the gateway's JSON payloads.

Server payloads drift over time, so parsing tolerates several key
spellings (animeId/animeTitle/episodeCount/bangumiId, ...).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


def _get(d: dict, *keys: str, default: Any = None) -> Any:
    for k in keys:
        if k in d and d[k] is not None:
            return d[k]
    return default


def _int(v: Any, default: int = 0) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _str(v: Any, default: str = "") -> str:
    if v is None:
        return default
    return str(v)


@dataclass
class Banner:
    id: str = ""
    title: str = ""
    image: str = ""
    jump_url: str = ""
    video_id: str = ""

    @classmethod
    def from_api(cls, d: dict) -> "Banner":
        return cls(
            id=_str(_get(d, "id", "banner_id")),
            title=_str(_get(d, "title", "name")),
            image=_str(_get(d, "image", "img", "pic", "cover", "url")),
            jump_url=_str(_get(d, "jump_url", "jumpUrl", "link", "url2")),
            video_id=_str(_get(d, "video_id", "videoId", "anime_id", "animeId")),
        )


@dataclass
class Channel:
    id: str = ""
    name: str = ""
    sort: int = 0

    @classmethod
    def from_api(cls, d: dict) -> "Channel":
        return cls(
            id=_str(_get(d, "id", "channel_id", "channelId")),
            name=_str(_get(d, "name", "channel_name", "channelName", "title")),
            sort=_int(_get(d, "sort", "priority", "index")),
        )


@dataclass
class Video:
    """An anime entry (server payloads use video/anime interchangeably)."""

    id: str = ""
    title: str = ""
    cover: str = ""
    description: str = ""
    status: str = ""            # e.g. 连载中 / 完结
    rating: str = ""
    year: str = ""
    area: str = ""
    tag: str = ""
    episode_count: int = 0
    latest_episode: str = ""

    @classmethod
    def from_api(cls, d: dict) -> "Video":
        return cls(
            id=_str(_get(d, "id", "video_id", "videoId", "anime_id", "animeId", "bangumiId")),
            title=_str(_get(d, "title", "name", "animeTitle", "video_title")),
            cover=_str(_get(d, "cover", "pic", "image", "img", "poster")),
            description=_str(_get(d, "description", "desc", "summary", "intro")),
            status=_str(_get(d, "status", "update_state", "state")),
            rating=_str(_get(d, "rating", "score", "fen")),
            year=_str(_get(d, "year", "release_year")),
            area=_str(_get(d, "area", "region")),
            tag=_str(_get(d, "tag", "type", "category")),
            episode_count=_int(_get(d, "episode_count", "episodeCount", "ep_count")),
            latest_episode=_str(_get(d, "latest_episode", "new_episode", "newest")),
        )


@dataclass
class Episode:
    id: str = ""
    title: str = ""
    number: int = 0
    video_url: str = ""         # filled by pc/video/key lookup when available
    is_vip: bool = False
    fallback_urls: list = field(default_factory=list)   # 其余线路（按画质排序后）

    @classmethod
    def from_api(cls, d: dict) -> "Episode":
        num = _get(d, "episode_number", "episodeNumber", "episode", "number")
        title = _str(_get(d, "episode_title", "episodeTitle", "title", "name"))
        return cls(
            id=_str(_get(d, "id", "episode_id", "episodeId", "pm_episode_id", "pmEpisodeId", "pid")),
            title=title,
            number=_int(num) or (_int(title) if title.isdigit() else 0),
            video_url=_str(_get(d, "video_url", "url", "play_url", "playUrl")),
            is_vip=bool(_get(d, "is_vip", "isVip", "vip", default=False)),
        )


@dataclass
class Comment:
    """A danmaku/comment item.

    Supports both the raw danmaku shape (time_ms/text/color/mode) and
    bilibili-style reply shape (content.message/ctime/member.uname).
    """

    text: str = ""
    time_ms: int = 0
    color: int = 0xFFFFFF
    mode: int = 1               # 1-3 scroll, 4 bottom, 5 top
    user: str = ""
    source: str = "external"
    send_time: int = 0

    @classmethod
    def from_api(cls, d: dict) -> "Comment":
        # danmaku shape
        text = _get(d, "text", "content_str", "msg")
        if text is None:
            content = _get(d, "content")
            if isinstance(content, dict):
                text = _get(content, "message", "msg", default="")
            elif isinstance(content, str):
                text = content
        member = _get(d, "member")
        user = _get(d, "user", "uname", "username")
        if user is None and isinstance(member, dict):
            user = _get(member, "uname", "name", default="")
        return cls(
            text=_str(text),
            time_ms=_int(_get(d, "time_ms", "timeMs", "progress", "ctime")) * (
                1 if _get(d, "time_ms", "timeMs", "progress") is not None else 1000
            ),
            color=_int(_get(d, "color", default=0xFFFFFF)) & 0xFFFFFF,
            mode=_int(_get(d, "mode", default=1)) or 1,
            user=_str(user),
            send_time=_int(_get(d, "send_time", "ctime", "created_at")),
        )


@dataclass
class PlaySource:
    """A playable stream for one episode (quality variants when provided)."""

    name: str = ""
    url: str = ""
    headers: dict = field(default_factory=dict)

    @classmethod
    def from_api(cls, d: dict) -> "PlaySource":
        return cls(
            name=_str(_get(d, "name", "quality", "title", "label")),
            url=_str(_get(d, "url", "video_url", "play_url", "playUrl", "src")),
            headers=_get(d, "headers", "header", default={}) if isinstance(_get(d, "headers", "header"), dict) else {},
        )


@dataclass
class UserInfo:
    user_id: str = ""
    nickname: str = ""
    avatar: str = ""
    phone: str = ""
    is_vip: bool = False
    vip_expire_at: int = 0
    gold: int = 0

    @classmethod
    def from_api(cls, d: dict) -> "UserInfo":
        vip = _get(d, "is_vip", "isVip", "vip")
        vip_info = _get(d, "vip_info", "vipInfo")
        if isinstance(vip_info, dict) and vip is None:
            vip = _get(vip_info, "is_vip", "isVip", "status")
        return cls(
            user_id=_str(_get(d, "user_id", "userId", "id", "uid")),
            nickname=_str(_get(d, "nickname", "nick_name", "name", "username")),
            avatar=_str(_get(d, "avatar", "head", "head_url", "face")),
            phone=_str(_get(d, "phone", "mobile")),
            is_vip=bool(vip),
            vip_expire_at=_int(_get(d, "vip_expire_at", "vipExpireAt", "expire_at")),
            gold=_int(_get(d, "gold", "balance")),
        )
