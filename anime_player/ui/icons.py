"""Inline SVG icon glyphs (drawn from scratch for this project)."""

from __future__ import annotations

from PyQt6.QtCore import QByteArray, QSize, Qt
from PyQt6.QtGui import QIcon, QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtCore import QRectF

_ICONS: dict[str, str] = {
    "home": '<path d="M4 11.5 12 4l8 7.5V20a1 1 0 0 1-1 1h-5v-6h-4v6H5a1 1 0 0 1-1-1z" fill="none" stroke="{c}" stroke-width="1.8" stroke-linejoin="round"/>',
    "search": '<circle cx="10.5" cy="10.5" r="6" fill="none" stroke="{c}" stroke-width="1.8"/><path d="m15.2 15.2 4.6 4.6" stroke="{c}" stroke-width="1.8" stroke-linecap="round"/>',
    "history": '<circle cx="12" cy="12" r="8" fill="none" stroke="{c}" stroke-width="1.8"/><path d="M12 7.5V12l3.2 2" fill="none" stroke="{c}" stroke-width="1.8" stroke-linecap="round"/>',
    "star": '<path d="m12 4 2.35 5.1 5.65.6-4.2 3.85 1.15 5.45L12 16.1 7.05 19l1.15-5.45L4 9.7l5.65-.6z" fill="none" stroke="{c}" stroke-width="1.7" stroke-linejoin="round"/>',
    "user": '<circle cx="12" cy="8.5" r="3.6" fill="none" stroke="{c}" stroke-width="1.8"/><path d="M5 19.5c1.3-3.2 4-4.8 7-4.8s5.7 1.6 7 4.8" fill="none" stroke="{c}" stroke-width="1.8" stroke-linecap="round"/>',
    "settings": '<circle cx="12" cy="12" r="3" fill="none" stroke="{c}" stroke-width="1.8"/><path d="M12 3.5v2.2M12 18.3v2.2M3.5 12h2.2M18.3 12h2.2M6 6l1.6 1.6M16.4 16.4 18 18M18 6l-1.6 1.6M7.6 16.4 6 18" stroke="{c}" stroke-width="1.7" stroke-linecap="round"/>',
    "play": '<path d="M8.5 5.8v12.4c0 .8.9 1.3 1.6.9l9.4-6.2c.6-.4.6-1.4 0-1.8L10.1 4.9c-.7-.4-1.6.1-1.6.9z" fill="{c}"/>',
    "pause": '<rect x="7" y="5.5" width="3.4" height="13" rx="1" fill="{c}"/><rect x="13.6" y="5.5" width="3.4" height="13" rx="1" fill="{c}"/>',
    "danmaku-on": '<rect x="3.5" y="6" width="17" height="12" rx="2.5" fill="none" stroke="{c}" stroke-width="1.7"/><path d="M6.5 10h6M6.5 13.2h9" stroke="{c}" stroke-width="1.5" stroke-linecap="round"/>',
    "danmaku-off": '<rect x="3.5" y="6" width="17" height="12" rx="2.5" fill="none" stroke="{c}" stroke-width="1.7"/><path d="m6 6 12 12" stroke="{c}" stroke-width="1.7" stroke-linecap="round"/>',
    "vol": '<path d="M4.5 9.5v5h3.2L12 18V6L7.7 9.5zM14.8 9a4.2 4.2 0 0 1 0 6M17.2 6.8a7.5 7.5 0 0 1 0 10.4" fill="none" stroke="{c}" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/>',
    "fullscreen": '<path d="M4.5 9V4.5H9M15 4.5h4.5V9M19.5 15v4.5H15M9 19.5H4.5V15" fill="none" stroke="{c}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>',
    "next": '<path d="M6 5.8v12.4c0 .8.9 1.3 1.6.9l7.4-6.2c.6-.4.6-1.4 0-1.8L7.6 4.9c-.7-.4-1.6.1-1.6.9z" fill="{c}"/><rect x="16" y="5.5" width="2.6" height="13" rx="1" fill="{c}"/>',
    "back": '<path d="m14.5 5.5-7 6.5 7 6.5" fill="none" stroke="{c}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>',
    "close": '<path d="m6.5 6.5 11 11M17.5 6.5l-11 11" stroke="{c}" stroke-width="1.9" stroke-linecap="round"/>',
    "min": '<path d="M6 12.5h12" stroke="{c}" stroke-width="1.9" stroke-linecap="round"/>',
    "max": '<rect x="6" y="6" width="12" height="12" rx="2" fill="none" stroke="{c}" stroke-width="1.7"/>',
    "vip": '<path d="M5 8.5 8 12l4-6.5 4 6.5 3-3.5V18a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1z" fill="{c}"/>',
    "clock": '<circle cx="12" cy="12" r="8" fill="none" stroke="{c}" stroke-width="1.7"/><path d="M12 8v4.3l3 1.8" fill="none" stroke="{c}" stroke-width="1.7" stroke-linecap="round"/>',
}


def icon_pixmap(name: str, color: str = "#e8e8f0", size: int = 22) -> QPixmap:
    body = _ICONS.get(name, "")
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="{size}" height="{size}">{body.format(c=color)}</svg>'
    renderer = QSvgRenderer(QByteArray(svg.encode()))
    pm = QPixmap(size * 2, size * 2)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(p, QRectF(0, 0, size * 2, size * 2))
    p.end()
    return pm


def icon(name: str, color: str = "#e8e8f0", size: int = 22) -> QIcon:
    return QIcon(icon_pixmap(name, color, size))


def colored_icon_button_text(name: str) -> str:
    return name
