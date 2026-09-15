"""核心逻辑单元测试（纯逻辑，不弹窗口）。

运行：python -m unittest discover -s tests -v
"""

import json
import os
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sitreminder import autostart, config, paths, quips, timer  # noqa: E402


class ConfigTests(unittest.TestCase):
    def test_missing_file_falls_back_to_defaults(self):
        cfg = config.load_config(os.path.join(tempfile.gettempdir(), "no_such_cfg.json"))
        self.assertEqual(cfg["interval_seconds"], config.DEFAULT_INTERVAL_SECONDS)
        self.assertFalse(cfg["autostart"])

    def test_broken_json_falls_back_to_defaults(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False,
                                         encoding="utf-8") as fh:
            fh.write("{ this is not json")
            path = fh.name
        try:
            cfg = config.load_config(path)
            self.assertEqual(cfg["interval_seconds"], config.DEFAULT_INTERVAL_SECONDS)
        finally:
            os.remove(path)

    def test_legacy_interval_minutes_is_migrated(self):
        """旧配置用 interval_minutes 字段，必须被换算成秒（曾经是死代码）。"""
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False,
                                         encoding="utf-8") as fh:
            fh.write('{"interval_minutes": 45}')
            path = fh.name
        try:
            self.assertEqual(config.load_config(path)["interval_seconds"], 2700)
        finally:
            os.remove(path)

    def test_interval_is_clamped(self):
        self.assertEqual(config.clamp_interval(1), config.MIN_INTERVAL_SECONDS)
        self.assertEqual(config.clamp_interval(999999), config.MAX_INTERVAL_SECONDS)
        self.assertEqual(config.clamp_interval("600"), 600)
        self.assertEqual(config.clamp_interval("abc"), config.DEFAULT_INTERVAL_SECONDS)

    def test_save_and_reload_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "config.json")
            payload = {"interval_seconds": 1200, "autostart": True,
                       "window_pos": [880, 460],
                       "capsule_always_visible": False,
                       "quip_style": "傲娇"}
            self.assertTrue(config.save_config(payload, path))
            self.assertEqual(config.load_config(path), payload)

    def test_capsule_always_visible_defaults_and_coercion(self):
        """新字段 capsule_always_visible：缺省 True，非法值规整为布尔。"""
        with tempfile.TemporaryDirectory() as tmp:
            # 缺省
            path = os.path.join(tmp, "missing.json")
            self.assertIs(config.load_config(path)["capsule_always_visible"], True)
            # 非法值 → True；0 → False
            for raw, expect in (("yes", True), (0, False)):
                path = os.path.join(tmp, f"raw_{expect}.json")
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(f'{{"capsule_always_visible": {json.dumps(raw)}}}')
                got = config.load_config(path)["capsule_always_visible"]
                self.assertIs(got, expect)
                os.remove(path)

    def test_window_pos_is_none_when_absent_or_invalid(self):
        """位置缺失/非法 → None，表示"首次启动"，由界面走默认右下角。"""
        cfg = config.load_config(os.path.join(tempfile.gettempdir(), "no_such_cfg.json"))
        self.assertIsNone(cfg["window_pos"])
        self.assertIsNone(config.sanitize_window_pos(None))
        self.assertIsNone(config.sanitize_window_pos([1]))
        self.assertIsNone(config.sanitize_window_pos("12,34"))
        self.assertIsNone(config.sanitize_window_pos(["a", "b"]))
        # 统一返回 list（与写盘的 JSON 数组一致），否则"未变则不写盘"会失效
        self.assertEqual(config.sanitize_window_pos((3, 4)), [3, 4])


class TimerTests(unittest.TestCase):
    def test_counts_down(self):
        t = timer.TimerState(30)
        self.assertAlmostEqual(t.remaining(), 30, delta=1)
        time.sleep(1.1)
        self.assertLessEqual(t.remaining(), 29)

    def test_pause_freezes_and_resume_continues(self):
        t = timer.TimerState(60)
        time.sleep(1.1)
        t.pause()
        frozen = t.remaining()
        time.sleep(1.1)
        self.assertEqual(t.remaining(), frozen)     # 暂停期间不前进
        t.resume()
        self.assertAlmostEqual(t.remaining(), frozen, delta=1)  # 从剩余点继续

    def test_paused_timer_is_never_due(self):
        # 直接把结束时间拨到过去，避免测试真等一个间隔
        from datetime import datetime, timedelta

        t = timer.TimerState(60)
        t._end = datetime.now() - timedelta(seconds=1)
        self.assertTrue(t.is_due())
        t.pause()
        self.assertFalse(t.is_due())

    def test_reset_restarts_full_interval(self):
        t = timer.TimerState(10)
        time.sleep(1.1)
        t.reset()
        self.assertAlmostEqual(t.remaining(), 10, delta=1)

    def test_interval_is_clamped(self):
        self.assertEqual(timer.TimerState(1).interval, config.MIN_INTERVAL_SECONDS)


class QuipTests(unittest.TestCase):
    def test_never_repeats_back_to_back(self):
        for _ in range(200):
            first, second = quips.pick_quip(), quips.pick_quip()
            self.assertNotEqual(first, second)

    def test_only_picks_from_builtin_library(self):
        for _ in range(50):
            self.assertIn(quips.pick_quip(), quips.QUIPS)

    def test_every_style_has_20_quips(self):
        for style in ("傲娇", "温柔", "呆萌", "冷漠", "可爱"):
            self.assertEqual(len(quips.QUIPS_BY_STYLE[style]), 20, style)

    def test_pick_from_given_style(self):
        for style in quips.STYLES:
            for _ in range(30):
                q = quips.pick_quip(style)
                pool = (quips._ALL_POOL if style == quips.MIX_STYLE
                        else quips.QUIPS_BY_STYLE.get(style, quips.QUIPS))
                self.assertIn(q, pool, style)

    def test_unknown_style_falls_back_to_default(self):
        for _ in range(30):
            self.assertIn(quips.pick_quip("不存在的风格"), quips.QUIPS)
        self.assertIn(quips.pick_quip(None), quips.QUIPS)

    def test_quip_style_config_sanitized(self):
        cases = {"傲娇": "傲娇", "随机": "随机", "胡写的": "默认",
                 None: "默认", 42: "默认", "": "默认"}
        for raw, want in cases.items():
            self.assertEqual(config._sanitize_quip_style(raw), want)


class AutostartTests(unittest.TestCase):
    """开机自启（FR-7）的启动命令构造与注册表读写。

    注册表用例只碰一个**专用的临时子键**（`Software\\SitReminderAutostartTest`），
    测完连值带键一起删掉 —— 绝不触碰真正的 Run 键，免得动到用户已有的启动项。
    """

    TEST_KEY = r"Software\SitReminderAutostartTest"
    TEST_NAME = "UnitTestEntry"

    def test_launch_command_quotes_every_argument(self):
        cmd = autostart.launch_command()
        self.assertTrue(cmd.startswith('"'), cmd)
        self.assertTrue(cmd.endswith('"'), cmd)
        # 至少两个参数（解释器 + 入口），每个都带引号 → 引号数必为偶数且 ≥4
        self.assertGreaterEqual(cmd.count('"'), 4, cmd)

    def test_launch_argv_source_mode_targets_main_py(self):
        argv = autostart.launch_argv()
        if paths.IS_FROZEN:
            self.assertEqual(len(argv), 1)      # 打包版就是 exe 自己
            return
        self.assertEqual(len(argv), 2)
        self.assertEqual(os.path.basename(argv[1]), "main.py")
        self.assertTrue(os.path.exists(argv[1]), argv[1])
        # 源码模式优先用 pythonw（无控制台窗口）；没有则退回当前解释器
        self.assertIn(os.path.basename(argv[0]).lower(),
                      ("python.exe", "pythonw.exe"))

    def test_platform_support_flag(self):
        expected = (sys.platform in ("win32", "darwin")
                    or sys.platform.startswith("linux"))
        self.assertEqual(autostart.is_supported(), expected)

    @unittest.skipUnless(sys.platform == "win32", "仅 Windows 注册表")
    def test_registry_roundtrip_in_temp_key(self):
        import winreg
        try:
            # 起点干净：确保本用例的临时值不存在
            autostart._win_remove(self.TEST_KEY, self.TEST_NAME)
            self.assertIsNone(autostart._win_read(self.TEST_KEY, self.TEST_NAME))

            # 写入 → 读回
            autostart._win_write(r'"C:\fake\SitReminder.exe"',
                                 self.TEST_KEY, self.TEST_NAME)
            self.assertEqual(
                autostart._win_read(self.TEST_KEY, self.TEST_NAME),
                r'"C:\fake\SitReminder.exe"')

            # 删除 → 读不到了
            self.assertTrue(autostart._win_remove(self.TEST_KEY, self.TEST_NAME))
            self.assertIsNone(autostart._win_read(self.TEST_KEY, self.TEST_NAME))

            # 再删一次：值本就不存在，应返回 False 而不是抛异常（幂等）
            self.assertFalse(autostart._win_remove(self.TEST_KEY, self.TEST_NAME))
        finally:
            try:
                winreg.DeleteKey(winreg.HKEY_CURRENT_USER, self.TEST_KEY)
            except OSError:
                pass

    @unittest.skipUnless(sys.platform == "win32", "仅 Windows 注册表")
    def test_reading_absent_key_returns_none(self):
        self.assertIsNone(
            autostart._win_read(r"Software\SitReminderNoSuchKey", "nope"))


if __name__ == "__main__":
    unittest.main()
