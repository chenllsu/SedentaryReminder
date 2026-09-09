"""系统托盘（可选依赖：pystray + Pillow，缺失时静默降级）。"""

from __future__ import annotations

import logging
import os
import threading

from . import paths

log = logging.getLogger(__name__)


class TrayIcon:
    """托盘图标。

    关键点：pystray 的菜单回调运行在托盘自己的线程里，而 Tk 不是线程安全的，
    直接操作控件会偶发卡死。所有回调统一通过 root.after(0, ...) 切回主线程。
    """

    def __init__(self, root, handlers):
        """
        handlers: {"show": fn, "toggle_pause": fn, "skip": fn, "exit": fn}
        """
        self._root = root
        self._handlers = handlers or {}
        self._icon = None
        self._thread = None

    @property
    def available(self) -> bool:
        return self._icon is not None

    def start(self) -> bool:
        try:
            import pystray
            from PIL import Image
        except ImportError:
            log.info("未安装 pystray/Pillow，跳过系统托盘（其余功能不受影响）")
            return False

        try:
            image = self._load_icon(Image)
            menu = pystray.Menu(
                pystray.MenuItem("显示浮窗", lambda *_: self._call("show")),
                pystray.MenuItem("暂停/继续", lambda *_: self._call("toggle_pause")),
                pystray.MenuItem("跳过本次", lambda *_: self._call("skip")),
                pystray.MenuItem("退出", lambda *_: self._call("exit")),
            )
            self._icon = pystray.Icon("sit_reminder", image, "久坐提醒·妮子", menu)
            self._thread = threading.Thread(target=self._icon.run,
                                            daemon=True, name="TrayIcon")
            self._thread.start()
            return True
        except Exception:
            log.exception("系统托盘启动失败，已降级为无托盘模式")
            self._icon = None
            return False

    def stop(self) -> None:
        icon, self._icon = self._icon, None
        if icon is None:
            return
        try:
            icon.stop()
        except Exception:
            log.debug("托盘停止时出错", exc_info=True)

    def _load_icon(self, image_module):
        if os.path.exists(paths.MASCOT_PATH):
            return image_module.open(paths.MASCOT_PATH).convert("RGBA").resize((64, 64))
        return image_module.new("RGBA", (64, 64), (255, 200, 0, 255))

    def _call(self, name: str) -> None:
        handler = self._handlers.get(name)
        if handler:
            self._root.after(0, handler)
