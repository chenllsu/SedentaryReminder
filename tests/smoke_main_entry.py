"""入口冒烟：用 PySide6 解释器启动 QtController 完整路径并自动退出。

模拟「手动按 Ctrl+C 退出」之外的方式：在事件循环跑起来后立刻安排
一个 QTimer 触发 app.quit()，比 SIGTERM 更稳定（不会被外部信号打断）。
"""
import os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication


def schedule_quit():
    """QtController.run() 进入事件循环后，调度 1.5s 后退出。"""
    app = QApplication.instance()
    if app is None:
        print("[smoke] QApplication not yet ready", flush=True)
        return
    print("[smoke] event loop running, schedule quit in 1.5s", flush=True)
    QTimer.singleShot(1500, app.quit)

QTimer.singleShot(0, schedule_quit)
from sitreminder.qt.app import QtController
ctrl = QtController()
print("[smoke] QtController created, entering main loop…", flush=True)
ret = ctrl.run()
print(f"[smoke] main loop exited with {ret}", flush=True)
sys.exit(ret or 0)
