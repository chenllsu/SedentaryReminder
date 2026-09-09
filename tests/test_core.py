"""核心逻辑单元测试（纯逻辑，不弹窗口）。

运行：python -m unittest discover -s tests -v
"""

import os
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sitreminder import config, quips, timer  # noqa: E402


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
            payload = {"interval_seconds": 1200, "autostart": True}
            self.assertTrue(config.save_config(payload, path))
            self.assertEqual(config.load_config(path), payload)


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


if __name__ == "__main__":
    unittest.main()
