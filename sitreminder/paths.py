"""路径与运行时环境。

打包（PyInstaller）与源码运行的区别只有一处关键：
- 资源（assets）在 onefile 模式下被解包到临时目录 `sys._MEIPASS`；
- 配置 `config.json` 必须写到 exe 旁边，否则每次运行后配置都丢。
"""

from __future__ import annotations

import os
import sys

IS_FROZEN = bool(getattr(sys, "frozen", False))


def _app_dir() -> str:
    """源码运行=项目根目录；打包运行=exe 所在目录。"""
    if IS_FROZEN:
        return os.path.dirname(sys.executable)
    # 本文件位于 <项目根>/sitreminder/paths.py，上两级即项目根
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


BASE_DIR = _app_dir()
ASSET_DIR = os.path.join(getattr(sys, "_MEIPASS", BASE_DIR) if IS_FROZEN else BASE_DIR, "assets")

CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
MASCOT_PATH = os.path.join(ASSET_DIR, "nizi_clean.png")
MASCOT_PATH_QT = os.path.join(ASSET_DIR, "nizi_clean_qt.png")  # 去色晕版（Qt 用）
ICON_PATH = os.path.join(ASSET_DIR, "icon.ico")


def asset(name: str) -> str:
    """取 assets 目录下的资源绝对路径。"""
    return os.path.join(ASSET_DIR, name)


def user_data_dir() -> str:
    """跨平台的用户数据目录（放日志等），创建失败时回退到程序目录。"""
    try:
        if sys.platform == "win32":
            base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        elif sys.platform == "darwin":
            base = os.path.expanduser("~/Library/Application Support")
        else:
            base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
        target = os.path.join(base, "SitReminder")
        os.makedirs(target, exist_ok=True)
        return target
    except OSError:
        return BASE_DIR
