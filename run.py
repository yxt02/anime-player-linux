#!/usr/bin/env python3
"""Entry point: crash logging + Qt application bootstrap.

Crash files rotate between crash.log and crash.prev.log.
"""

from __future__ import annotations

import logging
import sys
import traceback
from pathlib import Path


def _setup_logging() -> None:
    from anime_player.core import paths

    log_dir = paths.log_dir()
    crash = log_dir / "crash.log"
    if crash.exists():
        prev = log_dir / "crash.prev.log"
        try:
            if prev.exists():
                prev.unlink()
            crash.rename(prev)
        except OSError:
            pass

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(log_dir / "app.log", encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )


def _install_excepthook() -> None:
    from anime_player.core import paths

    def hook(exc_type, exc, tb) -> None:
        text = "".join(traceback.format_exception(exc_type, exc, tb))
        logging.getLogger("anime_player.crash").error("uncaught exception:\n%s", text)
        try:
            with open(paths.log_dir() / "crash.log", "a", encoding="utf-8") as f:
                f.write(text)
        except OSError:
            pass

    sys.excepthook = hook


def main() -> int:
    _setup_logging()
    _install_excepthook()

    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QApplication

    from anime_player import APP_NAME_LINUX, __version__
    from anime_player.ui import style
    from anime_player.ui.main_window import MainWindow

    # X11: required for mpv --wid embedding under Wayland sessions as well.
    import os
    if os.environ.get("XDG_SESSION_TYPE") == "wayland" and not os.environ.get("QT_QPA_PLATFORM"):
        os.environ["QT_QPA_PLATFORM"] = "xcb"

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME_LINUX)
    app.setApplicationVersion(__version__)
    app.setStyle("Fusion")
    app.setStyleSheet(style.STYLE_SHEET)

    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
