#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SitReminder —— 久坐提醒小工具（PySide6 版）。

完全本地运行，不联网。

用法：
    python main.py            # 正常启动
    python main.py --debug    # 输出调试日志

交互：
    悬停妮子 → 显示剩余倒计时；移开 → 隐藏
    右键妮子 → 菜单（设置 / 暂停继续 / 跳过本次 / 关闭…）；托盘图标右键同样有「设置」
    单击妮子 → 无动作（只用于拖动）；按住拖动 → 移动浮窗，松手记住位置
    打开设置 → 倒计时暂停；关闭设置 → 未改间隔则继续计时，改了间隔则按新间隔重新计时
    到点 → 弹出气泡提醒，点「知道了」后重新计时
"""

from __future__ import annotations

import logging
import sys

from sitreminder.logging_setup import setup_logging
from sitreminder.qt.app import QtController
from sitreminder.single_instance import SingleInstanceGuard


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    logger = setup_logging(logging.DEBUG if "--debug" in argv else logging.INFO)

    guard = SingleInstanceGuard()
    if not guard.acquire():
        _notify_already_running()
        return 0

    try:
        ctrl = QtController()
        return ctrl.run()
    except KeyboardInterrupt:
        logger.info("用户中断，退出")
        return 0
    except Exception:
        logger.exception("程序异常退出")
        return 1
    finally:
        guard.release()


def _notify_already_running():
    """已经有实例在跑时给个提示，避免用户以为程序没启动。"""
    try:
        from PySide6.QtWidgets import QApplication, QMessageBox

        app = QApplication.instance() or QApplication(sys.argv)
        QMessageBox.information(
            None, "久坐提醒", "妮子已经在桌面上啦～（程序已在运行）")
    except Exception:
        print("SitReminder 已在运行。")


if __name__ == "__main__":
    sys.exit(main())
