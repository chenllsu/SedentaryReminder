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


if __name__ == "__main__":
    unittest.main()
