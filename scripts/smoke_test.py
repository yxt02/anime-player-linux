#!/usr/bin/env python3
"""Offscreen smoke test: launch main window, render pages, save screenshots."""

import os
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6.QtWidgets import QApplication  # noqa: E402
from anime_player.ui import style  # noqa: E402


def main() -> int:
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(style.STYLE_SHEET)

    from anime_player.ui.main_window import MainWindow
    win = MainWindow()
    win.resize(1200, 780)
    win.show()

    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shots")
    os.makedirs(out_dir, exist_ok=True)

    def shot(name: str) -> None:
        app.processEvents()
        pm = win.grab()
        pm.save(os.path.join(out_dir, f"{name}.png"))
        print(f"saved {name}.png {pm.width()}x{pm.height()}")

    app.processEvents()
    time.sleep(0.6)
    shot("01_home")

    win.switch_page(1)
    shot("02_search")
    win.switch_page(2)
    shot("03_history")
    win.switch_page(3)
    shot("04_favorites")
    win.switch_page(4)
    shot("05_user")
    win.switch_page(5)
    shot("06_settings")

    # detail page offline (gateway likely unreachable in CI env)
    win.open_detail("test-video-id")
    time.sleep(1.0)
    shot("07_detail")

    # danmaku ASS generation check
    from anime_player.core import danmaku, models
    comments = [
        models.Comment(text="前方高能！", time_ms=1000, mode=1, color=0xFF6A00),
        models.Comment(text="神作", time_ms=1500, mode=1, color=0xFFFFFF),
        models.Comment(text="顶部弹幕", time_ms=2000, mode=4, color=0x00BFFF),
        models.Comment(text="底部弹幕", time_ms=2500, mode=7, color=0x66FF66),
    ]
    ass = danmaku.convert_to_ass(comments, font_size=30)
    assert "Dialogue:" in ass and "前方高能" in ass, "ASS generation failed"
    print("danmaku ASS OK:", ass.count("Dialogue:"), "events")

    print("SMOKE_OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
