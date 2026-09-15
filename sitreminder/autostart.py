"""开机自启（FR-7）：把本程序登记到操作系统的「开机自动运行」位置。

各平台落点：
- Windows：注册表 ``HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run``
- macOS：``~/Library/LaunchAgents/<label>.plist``
- Linux：``~/.config/autostart/<file>.desktop``

设计约定
--------
1. 只写 **当前用户** 范围（HKCU / ~ 家目录），不需要管理员权限，卸载也不留痕迹。
2. 对外只暴露 4 个动作：``is_enabled`` / ``enable`` / ``disable`` / ``set_enabled``。
3. **所有异常都在内部吞掉并记日志**，返回 False —— 「开机自启写不进去」不该让
   用户点一下「保存」就把设置窗崩掉，偏好照样存进 config.json。
4. 启动命令由 :func:`launch_command` 现场推导：打包版指向 exe 本身，
   源码版指向「pythonw + main.py」（用 pythonw 避免弹出黑框）。
"""

from __future__ import annotations

import logging
import os
import sys

from . import paths

log = logging.getLogger(__name__)

#: 自启项的名字（注册表值名 / plist Label 后缀 / .desktop 文件名）
APP_ID = "SitReminder"
MAC_LABEL = "com.chenllsu.sitreminder"
LINUX_FILE = "sitreminder.desktop"

WIN_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"

MAC_PLIST_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" \
"http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{label}</string>
    <key>ProgramArguments</key>
    <array>
{args}
    </array>
    <key>RunAtLoad</key>
    <true/>
</dict>
</plist>
"""

LINUX_DESKTOP_TEMPLATE = """[Desktop Entry]
Type=Application
Name=SitReminder
Comment=久坐提醒 · 妮子
Exec={exec_line}
Terminal=false
X-GNOME-Autostart-enabled=true
"""


# --------------------------------------------------------------------- 启动命令
def launch_argv() -> list[str]:
    """开机时要执行的命令（参数列表形式，便于拼 plist / .desktop）。"""
    if paths.IS_FROZEN:
        # 打包版：exe 自己就是入口
        return [sys.executable]
    exe = sys.executable
    # 源码版：优先用 pythonw，避免每次开机弹出一个黑色控制台窗口
    pyw = os.path.join(os.path.dirname(exe), "pythonw.exe")
    if os.path.exists(pyw):
        exe = pyw
    return [exe, os.path.join(paths.BASE_DIR, "main.py")]


def launch_command() -> str:
    """开机时要执行的命令行（各参数加双引号，可直接写进注册表 Run 值）。"""
    return " ".join(f'"{a}"' for a in launch_argv())


# --------------------------------------------------------------------- 平台判定
def _platform() -> str:
    if sys.platform == "win32":
        return "win"
    if sys.platform == "darwin":
        return "mac"
    if sys.platform.startswith("linux"):
        return "linux"
    return "unsupported"


def is_supported() -> bool:
    """当前平台是否支持开机自启。"""
    return _platform() != "unsupported"


# --------------------------------------------------------------------- Windows
def _win_read(key_path: str = WIN_RUN_KEY, name: str = APP_ID) -> str | None:
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as k:
            return winreg.QueryValueEx(k, name)[0]
    except OSError:
        return None


def _win_write(command: str, key_path: str = WIN_RUN_KEY,
               name: str = APP_ID) -> None:
    import winreg
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, key_path, 0,
                            winreg.KEY_SET_VALUE) as k:
        winreg.SetValueEx(k, name, 0, winreg.REG_SZ, command)


def _win_remove(key_path: str = WIN_RUN_KEY, name: str = APP_ID) -> bool:
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0,
                            winreg.KEY_SET_VALUE) as k:
            winreg.DeleteValue(k, name)
        return True
    except OSError:
        # 值本来就不存在 = 目标状态已达成
        return False


# --------------------------------------------------------------------- macOS
def _mac_plist_path() -> str:
    return os.path.join(os.path.expanduser("~/Library/LaunchAgents"),
                        MAC_LABEL + ".plist")


def _mac_write() -> None:
    path = _mac_plist_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    args = "\n".join(f"        <string>{a}</string>" for a in launch_argv())
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(MAC_PLIST_TEMPLATE.format(label=MAC_LABEL, args=args))


# --------------------------------------------------------------------- Linux
def _linux_desktop_path() -> str:
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(base, "autostart", LINUX_FILE)


def _linux_write() -> None:
    path = _linux_desktop_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(LINUX_DESKTOP_TEMPLATE.format(exec_line=launch_command()))


# --------------------------------------------------------------------- 对外接口
def is_enabled() -> bool:
    """系统里现在是否存在本程序的自启项。"""
    plat = _platform()
    try:
        if plat == "win":
            return _win_read() is not None
        if plat == "mac":
            return os.path.exists(_mac_plist_path())
        if plat == "linux":
            return os.path.exists(_linux_desktop_path())
    except Exception:      # noqa: BLE001 —— 探测失败一律当「没有」
        log.exception("读取开机自启状态失败")
    return False


def enable() -> bool:
    """写入自启项（已存在且指向当前程序时直接返回 True，不做多余写盘）。"""
    plat = _platform()
    try:
        if plat == "win":
            want = launch_command()
            if _win_read() == want:
                return True
            _win_write(want)
            log.info("开机自启已写入注册表：%s = %s", APP_ID, want)
            return True
        if plat == "mac":
            _mac_write()
            log.info("开机自启已写入 %s", _mac_plist_path())
            return True
        if plat == "linux":
            _linux_write()
            log.info("开机自启已写入 %s", _linux_desktop_path())
            return True
        log.info("当前平台不支持开机自启，已忽略")
        return False
    except Exception:      # noqa: BLE001 —— 写不进去不该让调用方崩
        log.exception("写入开机自启失败")
        return False


def disable() -> bool:
    """移除自启项（本来就没有也算成功）。"""
    plat = _platform()
    try:
        if plat == "win":
            if _win_remove():
                log.info("开机自启项已从注册表移除：%s", APP_ID)
            return True
        if plat == "mac":
            path = _mac_plist_path()
            if os.path.exists(path):
                os.remove(path)
                log.info("开机自启项已删除：%s", path)
            return True
        if plat == "linux":
            path = _linux_desktop_path()
            if os.path.exists(path):
                os.remove(path)
                log.info("开机自启项已删除：%s", path)
            return True
        return False
    except Exception:      # noqa: BLE001
        log.exception("移除开机自启失败")
        return False


def set_enabled(enabled: bool) -> bool:
    """按偏好开关自启。返回 False 表示「没能真正写进系统」。"""
    return enable() if enabled else disable()
