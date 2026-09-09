"""GUI 冒烟测试：真的把窗口、图片、动画都跑一遍，几秒后自动关闭。

用于验证「改造后还能不能起来」，不替代人眼验收。
运行：python tests/smoke_gui.py
"""

import os
import sys
import traceback

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from sitreminder.logging_setup import setup_logging  # noqa: E402

setup_logging()

from sitreminder.app import App  # noqa: E402

failures = []


def guard(label, func):
    try:
        func()
        print(f"  [ok] {label}")
    except Exception:
        failures.append(label)
        print(f"  [FAIL] {label}")
        traceback.print_exc()


def main():
    print("启动主浮窗…")
    app = App()

    def exercise():
        print("依次触发各界面…")
        guard("悬停倒计时胶囊", lambda: app._on_enter(None))
        guard("弹出提醒气泡", lambda: app.pop_bubble())
        guard("打开设置窗口", lambda: app.open_settings())
        guard("打开关闭选择框", lambda: app.on_close())
        guard("暂停/继续", lambda: (app.toggle_pause(), app.toggle_pause()))
        guard("跳过本次", lambda: app.on_skip())

    def finish():
        guard("销毁主窗口", lambda: app.root.destroy())

    app.root.after(600, exercise)
    app.root.after(2600, finish)
    app.run()

    print("\nSMOKE OK" if not failures else f"\nSMOKE FAILED: {failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
