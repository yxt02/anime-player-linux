#!/bin/sh
# anime-player-linux launcher: pick a Python that has our runtime deps, then run.
# Works both with distro packages (python3-pyqt6/python3-mpv) and with a
# conda/pip environment that provides PyQt6 + requests + python-mpv.
APPDIR="@APPDIR@"
for py in python3 /usr/bin/python3; do
    if command -v "$py" >/dev/null 2>&1 || [ -x "$py" ]; then
        if "$py" "$APPDIR/probe_env.py" >/dev/null 2>&1; then
            exec "$py" "$APPDIR/run.py" "$@"
        fi
    fi
done
echo "anime-player-linux: 未找到带有所需依赖的 Python（PyQt6 / requests / python-mpv / libmpv）。" >&2
echo "请安装：sudo apt install python3-pyqt6 python3-pyqt6.qtsvg python3-requests python3-mpv libmpv2" >&2
exit 1
