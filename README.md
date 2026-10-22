# anime-player-linux

独立开发的 Linux 桌面动漫视频播放器（应用内名称「动漫播放器」）：
内嵌 libmpv 播放、第三方弹幕、本地历史/收藏。
**仅供个人使用，不用于盈利或售卖**；本软件为独立实现，
与任何商业软件无关联。内置的 Anime4K 着色器沿用其上游 GPL-3.0 许可
（见 `anime_player/assets/shaders/LICENSE`）。

## 特性

- **免登录**：打开即用，历史/收藏/进度全部只存本机 SQLite；
  登录完全可选，仅用于多端同步。
- **无金币/无广告界面**：客户端不含金币、会员购买、充值入口；
  服务端公告弹窗默认关闭（可在设置中打开）。
- **画质优先**：播放时按画质自动排序线路（蓝光/4K → 1080P → 720P → …），
  可在设置切换"最高画质优先 / 流畅优先"；某条线路播放失败自动切换下一条。
- **弹幕**：第三方 B 站兼容弹幕源，转 ASS 交由 libass 渲染；
  字号、不透明度可调。
- **Anime4K 增强**：mpv `glsl-shaders` 画质增强（GPL-3.0）。
- 边界说明：本客户端**不做任何服务端校验的绕过**——只请求服务端对
  该会话实际返回的源；若某集服务端要求登录/会员，会如实提示。
  视频内容来自用户配置的公开服务接口，本软件本身不提供、不存储任何内容。

## 安装（发布包）

构建发布物（产出到 `dist/`）：

```bash
bash scripts/build_release.sh
```

两种安装方式，任选其一：

**A. 系统级 .deb（Ubuntu/Debian，需 sudo）**

```bash
sudo apt install ./dist/anime-player-linux_0.1.0_all.deb
# 之后：终端运行 anime-player-linux，或在应用菜单搜索"动漫播放器"
# 卸载：sudo apt remove anime-player-linux
```

依赖全部来自官方源（python3-pyqt6 / python3-pyqt6.qtsvg / python3-requests /
python3-mpv / libmpv2），`apt` 会自动装齐。

**B. 用户级安装器（无需 root，装到 ~/.local）**

```bash
./dist/anime-player-linux-0.1.0-userinstall.sh
# 启动：~/.local/bin/anime-player-linux（或应用菜单）
# 卸载：rm -rf ~/.local/share/anime-player-linux ~/.local/bin/anime-player-linux \
#          ~/.local/share/applications/anime-player-linux.desktop \
#          ~/.local/share/icons/hicolor/256x256/apps/anime-player-linux.png
```

启动器会自动选择带有所需依赖的 Python（apt 装的系统 Python 或 conda/pip
环境均可），并按运行时前缀预加载 libmpv。

## 运行（源码方式）

依赖：

- Python ≥ 3.10（conda 环境即可）
- PyQt6、requests、python-mpv：`pip install -r requirements.txt`
- libmpv：`conda install -c conda-forge mpv`（或系统 `libmpv2`）
- X11 会话（Wayland 下会自动回退 `QT_QPA_PLATFORM=xcb`，`--wid` 嵌入必需）

```bash
cd anime-player-linux
python run.py
```

网络说明：本机若使用 Clash 类 fake-IP DNS，请在 **设置 → 网络代理**
填入代理地址（如 `http://127.0.0.1:7890`），或手动填写 **API 地址**。
启动时会按候选网关逐个探测 `pc/config` 并记录失败列表。

## 测试

```bash
python scripts/smoke_test.py   # 离屏启动、七页截图、弹幕 ASS 生成断言
```

## 目录

```
run.py                    入口（崩溃日志 + Qt 启动）
anime_player/core/        网关客户端、弹幕客户端、配置/会话/SQLite
anime_player/ui/          主窗口、页面、播放器、登录对话框、主题
anime_player/assets/      Anime4K 着色器（GPL-3.0，含 LICENSE）
scripts/smoke_test.py     冒烟测试
scripts/build_release.sh  构建 .deb + 用户级安装器（产出 dist/）
packaging/                desktop 入口、应用图标、启动器模板、copyright
```

## 免责声明

本软件为独立开发的个人工具，不用于盈利或售卖，与任何商业软件无关联。
视频内容来自用户自行配置的公开服务接口，本软件不提供、不存储、不代理
任何内容；若相关服务要求登录或会员，本软件会如实提示而不做任何绕过。
