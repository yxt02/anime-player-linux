#!/usr/bin/env bash
# Build release artifacts:
#   dist/anime-player-linux_<ver>_all.deb          —— 系统级安装：sudo apt install ./xxx.deb
#   dist/anime-player-linux-<ver>-userinstall.sh   —— 用户级安装（无需 root）：./xxx.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION="$(sed -n 's/^__version__ = "\(.*\)"/\1/p' "$ROOT/anime_player/__init__.py")"
PKG=anime-player-linux
BUILD="$ROOT/build"
DIST="$ROOT/dist"
STAGE="$BUILD/deb"

echo "==> 构建 $PKG v$VERSION"
rm -rf "$BUILD"
mkdir -p "$DIST"

# ---- 应用图标（原创设计，离屏渲染）--------------------------------------
python3 "$ROOT/scripts/gen_icon.py"

# ---- 公共：应用文件清单 ---------------------------------------------------
stage_app() { # $1 = 目标目录（内含 run.py + anime_player/ 等）
    mkdir -p "$1"
    cp "$ROOT/run.py" "$ROOT/requirements.txt" "$ROOT/README.md" "$1/"
    cp "$ROOT/packaging/probe_env.py" "$1/"
    cp -a "$ROOT/anime_player" "$1/"
    find "$1" -type d -name __pycache__ -prune -exec rm -rf {} +
    find "$1" -type f \( -name '*.pyc' -o -name '*.log' \) -delete
}

# ============================================================ .deb 包
APPDIR_DEB="/usr/lib/$PKG"
APP="$STAGE$APPDIR_DEB"
echo "==> 组装 deb 树：$STAGE"
stage_app "$APP"

mkdir -p "$STAGE/usr/bin"
sed "s|^APPDIR=.*|APPDIR=$APPDIR_DEB|" "$ROOT/packaging/anime-player-linux.sh" \
    > "$STAGE/usr/bin/$PKG"
chmod 755 "$STAGE/usr/bin/$PKG"
install -Dm644 "$ROOT/packaging/anime-player-linux.desktop" \
    "$STAGE/usr/share/applications/$PKG.desktop"
install -Dm644 "$ROOT/packaging/anime-player-linux.png" \
    "$STAGE/usr/share/icons/hicolor/256x256/apps/$PKG.png"
install -Dm644 "$ROOT/packaging/copyright" \
    "$STAGE/usr/share/doc/$PKG/copyright"
install -Dm644 "$ROOT/README.md" "$STAGE/usr/share/doc/$PKG/README.md"

SIZE_KB="$(du -sk "$STAGE" | cut -f1)"
mkdir -p "$STAGE/DEBIAN"
cat > "$STAGE/DEBIAN/control" <<EOF
Package: $PKG
Version: $VERSION
Section: video
Priority: optional
Architecture: all
Installed-Size: $SIZE_KB
Depends: python3 (>= 3.10), python3-pyqt6, python3-pyqt6.qtsvg, python3-requests, python3-mpv, libmpv2
Maintainer: anime-player-linux contributors <anime-player-linux@localhost>
Description: 独立开发的 Linux 动漫视频播放器。
 免登录即用，本地历史收藏，无广告界面；libmpv 内嵌播放，
 支持弹幕与 Anime4K 画质增强。仅供个人使用，不用于盈利或售卖。
 .
 Anime4K 着色器沿用其上游 GPL-3.0 许可。
EOF
chmod 644 "$STAGE/DEBIAN/control"

DEB="$DIST/${PKG}_${VERSION}_all.deb"
echo "==> 构建 $DEB"
if command -v fakeroot >/dev/null 2>&1; then
    fakeroot dpkg-deb --build --root-owner-group "$STAGE" "$DEB" >/dev/null
else
    dpkg-deb --build --root-owner-group "$STAGE" "$DEB" >/dev/null
fi
ls -lh "$DEB"

# ============================================================ 用户级安装器
PAY="$BUILD/userinstall"
stage_app "$PAY/app"
mkdir -p "$PAY/icon"
cp "$ROOT/packaging/anime-player-linux.png" "$PAY/icon/anime-player-linux.png"
cp "$ROOT/packaging/anime-player-linux.desktop" "$PAY/anime-player-linux.desktop"

INSTALLER="$DIST/${PKG}-${VERSION}-userinstall.sh"
echo "==> 构建 $INSTALLER"
sed "s/@VERSION@/$VERSION/g" "$ROOT/packaging/userinstall_header.sh" > "$INSTALLER"
tar -czf - -C "$PAY" app icon anime-player-linux.desktop >> "$INSTALLER"
chmod 755 "$INSTALLER"
ls -lh "$INSTALLER"

# ============================================================ 自检
echo "==> deb 内容抽检"
dpkg-deb -I "$DEB" | grep -E 'Package|Version|Depends|Installed-Size'
dpkg-deb -c "$DEB" | grep -E 'run\.py|bin/|desktop|png|shaders/LICENSE' | head -8
echo "==> 构建完成：$DIST"
