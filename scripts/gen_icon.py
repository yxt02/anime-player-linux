#!/usr/bin/env python3
"""Render the app icon to packaging/anime-player-linux.png."""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# Icon design: dark rounded square + teal play glyph + danmaku bars.
_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256">
  <rect x="8" y="8" width="240" height="240" rx="52" fill="#1a1a26"/>
  <rect x="8" y="8" width="240" height="240" rx="52" fill="none"
        stroke="#3ec8a0" stroke-opacity="0.35" stroke-width="3"/>
  <path d="M104 78 L178 128 L104 178 Z" fill="#3ec8a0"
        stroke="#3ec8a0" stroke-width="14" stroke-linejoin="round"/>
  <rect x="40" y="60" width="52" height="10" rx="5" fill="#e8e8f0" opacity="0.85"/>
  <rect x="52" y="90" width="36" height="10" rx="5" fill="#e8e8f0" opacity="0.55"/>
  <rect x="44" y="168" width="44" height="10" rx="5" fill="#e8e8f0" opacity="0.65"/>
</svg>"""


def main() -> int:
    from PyQt6.QtCore import QByteArray, QRectF, Qt
    from PyQt6.QtGui import QPainter, QPixmap
    from PyQt6.QtSvg import QSvgRenderer
    from PyQt6.QtWidgets import QApplication

    app = QApplication(sys.argv)  # QPixmap requires a QGuiApplication

    out = Path(__file__).resolve().parent.parent / "packaging" / "anime-player-linux.png"
    out.parent.mkdir(parents=True, exist_ok=True)

    pm = QPixmap(256, 256)
    pm.fill(Qt.GlobalColor.transparent)
    renderer = QSvgRenderer(QByteArray(_SVG.encode()))
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(p, QRectF(0, 0, 256, 256))
    p.end()
    if not pm.save(str(out)):
        print(f"failed to save {out}", file=sys.stderr)
        return 1
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
