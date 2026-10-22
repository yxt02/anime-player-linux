"""Launcher dependency probe.

Mirrors mpv_widget._ensure_mpv's libmpv preload so that conda-style
installs (libmpv under the env prefix, not on the loader path) probe
the same way the app actually loads. Exit code 0 = environment usable.
"""

import ctypes
import os
import sys

import PyQt6.QtSvg  # noqa: F401
import PyQt6.QtWidgets  # noqa: F401
import requests  # noqa: F401

for cand in (
    "libmpv.so.2",
    os.path.join(sys.prefix, "lib", "libmpv.so.2"),  # conda/venv prefix
    os.path.expanduser("~/anaconda3/lib/libmpv.so.2"),
    "/usr/lib/x86_64-linux-gnu/libmpv.so.2",
):
    try:
        ctypes.CDLL(cand)
        break
    except OSError:
        continue

import mpv  # noqa: F401,E402
