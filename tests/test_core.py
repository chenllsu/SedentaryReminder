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

from sitreminder import autostart, config, paths, quips, quiet, timer  # noqa: E402


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
            payload = {
                "interval_seconds": 1200,
                "autostart": True,
                "window_pos": [880, 460],
                "capsule_always_visible": False,
                "quip_style": "傲娇",
                "mascot_size": 132,
                "pause_auto_resume_seconds": 600,
                "snooze_seconds": 300,
                "quiet_enabled": True,
                "quiet_start": "23:00",
                "quiet_end": "07:30",
            }
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

    # ---------------- v1.2 新增字段 ----------------
    def test_mascot_size_snaps_to_nearest_preset(self):
        """妮子尺寸只认三档，任意数值都收敛到最近的一档。"""
        for raw, want in ((88, 88), (110, 110), (132, 132),
                          (100, 110), (120, 110), ("132", 132),
                          (999, 132), (None, config.DEFAULT_MASCOT_SIZE),
                          ("abc", config.DEFAULT_MASCOT_SIZE)):
            self.assertEqual(config.sanitize_mascot_size(raw), want, raw)

    def test_pause_auto_resume_zero_means_disabled(self):
        """0 / 负数 = 关闭自动恢复；正值收敛到 [1 分钟, 上限]。"""
        self.assertEqual(config.clamp_pause_auto_resume(0), 0)
        self.assertEqual(config.clamp_pause_auto_resume(-5), 0)
        self.assertEqual(config.clamp_pause_auto_resume(600), 600)
        self.assertEqual(config.clamp_pause_auto_resume(1),
                         config.MIN_PAUSE_AUTO_RESUME_SECONDS)
        self.assertEqual(config.clamp_pause_auto_resume("abc"),
                         config.DEFAULT_PAUSE_AUTO_RESUME_SECONDS)

    def test_snooze_is_clamped(self):
        self.assertEqual(config.clamp_snooze(300), 300)
        self.assertEqual(config.clamp_snooze(0), config.MIN_SNOOZE_SECONDS)
        self.assertEqual(config.clamp_snooze(99999), config.MAX_SNOOZE_SECONDS)
        self.assertEqual(config.clamp_snooze("abc"), config.DEFAULT_SNOOZE_SECONDS)

    def test_new_fields_defaults(self):
        cfg = config.load_config(os.path.join(tempfile.gettempdir(), "no_such_cfg.json"))
        self.assertEqual(cfg["mascot_size"], config.DEFAULT_MASCOT_SIZE)
        self.assertEqual(cfg["pause_auto_resume_seconds"],
                         config.DEFAULT_PAUSE_AUTO_RESUME_SECONDS)
        self.assertEqual(cfg["snooze_seconds"], config.DEFAULT_SNOOZE_SECONDS)
        self.assertIs(cfg["quiet_enabled"], False)
        self.assertEqual(cfg["quiet_start"], quiet.DEFAULT_START)
        self.assertEqual(cfg["quiet_end"], quiet.DEFAULT_END)

    def test_quiet_hhmm_is_normalized_on_load(self):
        """免打扰时间被手改成 "7:5"/乱码时，读取端要能补零或退回默认。"""
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "cfg.json")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write('{"quiet_start": "7:5", "quiet_end": "乱七八糟"}')
            cfg = config.load_config(path)
            self.assertEqual(cfg["quiet_start"], "07:05")
            self.assertEqual(cfg["quiet_end"], quiet.DEFAULT_END)


class QuietTests(unittest.TestCase):
    """免打扰时段判断 —— 纯时间数学，边界（跨夜/相等/非法）最容易出错。"""

    def test_parse_hhmm(self):
        self.assertEqual(quiet.parse_hhmm("22:00"), (22, 0))
        self.assertEqual(quiet.parse_hhmm(" 8:5 "), (8, 5))
        for bad in (None, "", "22", "22:00:00", "24:00", "22:60", "aa:bb", 2200):
            self.assertIsNone(quiet.parse_hhmm(bad), bad)

    def test_normalize_hhmm(self):
        self.assertEqual(quiet.normalize_hhmm("8:5", "00:00"), "08:05")
        self.assertEqual(quiet.normalize_hhmm("bad", "22:00"), "22:00")
        self.assertEqual(quiet.normalize_hhmm(None, "08:00"), "08:00")

    def test_normal_range_is_left_closed_right_open(self):
        # 午休 12:30–13:30：含起点、不含终点
        self.assertTrue(quiet.in_quiet_hours(12 * 60 + 30, "12:30", "13:30"))
        self.assertTrue(quiet.in_quiet_hours(13 * 60 + 29, "12:30", "13:30"))
        self.assertFalse(quiet.in_quiet_hours(13 * 60 + 30, "12:30", "13:30"))
        self.assertFalse(quiet.in_quiet_hours(12 * 60 + 29, "12:30", "13:30"))

    def test_cross_midnight_range(self):
        # 夜里 22:00–次日 08:00
        self.assertTrue(quiet.in_quiet_hours(23 * 60, "22:00", "08:00"))
        self.assertTrue(quiet.in_quiet_hours(0, "22:00", "08:00"))
        self.assertTrue(quiet.in_quiet_hours(7 * 60 + 59, "22:00", "08:00"))
        self.assertFalse(quiet.in_quiet_hours(8 * 60, "22:00", "08:00"))
        self.assertFalse(quiet.in_quiet_hours(12 * 60, "22:00", "08:00"))

    def test_same_or_invalid_bounds_disable_the_window(self):
        # 起止相同 → 不生效（否则等于「整天免打扰」，跟用户本意相反）
        self.assertFalse(quiet.in_quiet_hours(22 * 60, "22:00", "22:00"))
        self.assertFalse(quiet.in_quiet_hours(22 * 60, "bad", "08:00"))
        self.assertFalse(quiet.in_quiet_hours(22 * 60, "22:00", None))


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

    # ---------------- v1.2 暂停体验 / 稍后提醒 ----------------
    def test_paused_seconds_tracks_pause_duration(self):
        t = timer.TimerState(60)
        self.assertEqual(t.paused_seconds(), 0)      # 未暂停 → 0
        t.pause()
        time.sleep(1.1)
        self.assertGreaterEqual(t.paused_seconds(), 1)
        t.resume()
        self.assertEqual(t.paused_seconds(), 0)      # 恢复后清零

    def test_reset_without_keep_paused_clears_pause_clock(self):
        t = timer.TimerState(60)
        t.pause()
        time.sleep(0.05)
        t.reset()                                    # 默认会解除暂停
        self.assertFalse(t.is_paused)
        self.assertEqual(t.paused_seconds(), 0)

    def test_reset_keep_paused_keeps_counting(self):
        t = timer.TimerState(60)
        t.pause()
        time.sleep(1.1)
        t.reset(keep_paused=True)                    # 只归位，暂停继续
        self.assertTrue(t.is_paused)
        self.assertGreaterEqual(t.paused_seconds(), 1)

    def test_restart_pause_clock_resets_origin_only_when_paused(self):
        t = timer.TimerState(60)
        t.restart_pause_clock()                      # 未暂停 → 空操作
        self.assertEqual(t.paused_seconds(), 0)
        t.pause()
        time.sleep(1.1)
        t.restart_pause_clock()
        self.assertLess(t.paused_seconds(), 1)

    def test_defer_pushes_current_round_only(self):
        t = timer.TimerState(1800)
        t.defer(300)
        self.assertAlmostEqual(t.remaining(), 300, delta=1)
        self.assertEqual(t.interval, 1800)           # 用户设定的间隔没被动
        self.assertFalse(t.is_paused)

    def test_defer_resumes_a_paused_timer(self):
        t = timer.TimerState(60)
        t.pause()
        t.defer(300)
        self.assertFalse(t.is_paused)
        self.assertAlmostEqual(t.remaining(), 300, delta=1)


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


# 窗口几何是纯常量 + 纯函数，但 window.py 顶层会 import PySide6；
# 在只跑核心单测的环境（如 D:\python 无 Qt）里需要优雅跳过。
try:
    from sitreminder.qt import window as win
    from sitreminder.qt.window import (
        WIN_W, WIN_H, SHADOW_PAD, MASCOT_SIZE, MASCOT_VISIBLE_BOTTOM_RATIO,
        CAPSULE_BODY_W, CAPSULE_STICKER_PAD, window_size_for, pose_blend,
    )
    _QT_MORPH_OK = True
except ModuleNotFoundError:
    _QT_MORPH_OK = False


@unittest.skipUnless(_QT_MORPH_OK, "PySide6 未安装，跳过窗口相关单测")
class WindowGeometryTests(unittest.TestCase):
    """窗口几何必须容得下姿态图，否则猫会被窗口边缘裁掉。"""

    def test_window_height_covers_pose_for_every_size(self):
        """三档尺寸下，素材都要能完整放进窗口（上下各留够透明边距）。"""
        for size in config.MASCOT_SIZE_PRESETS:
            _, win_h = window_size_for(size)
            foot = size * MASCOT_VISIBLE_BOTTOM_RATIO
            self.assertLessEqual(SHADOW_PAD + foot + SHADOW_PAD, win_h, size)

    def test_default_size_matches_module_constants(self):
        """模块级 WIN_W/WIN_H 就是默认档的尺寸（旧引用不能算错）。"""
        self.assertEqual(window_size_for(MASCOT_SIZE), (WIN_W, WIN_H))

    def test_capsule_fits_in_narrowest_window(self):
        """最小档时胶囊（含白剪纸外框）也必须比窗口窄，否则会被裁切。"""
        min_w, _ = window_size_for(min(config.MASCOT_SIZE_PRESETS))
        self.assertLess(CAPSULE_BODY_W + CAPSULE_STICKER_PAD * 2, min_w)


@unittest.skipUnless(_QT_MORPH_OK, "PySide6 未安装，跳过姿态过渡单测")
class PoseTransitionTests(unittest.TestCase):
    """坐姿 ↔ 睡姿过渡的两层绘制参数。

    这里有两个"改坏了也看不出来、只能靠盯动画才发现"的不变式：
      · 两层不透明度必须互补 —— 否则过渡中途整只猫会忽明忽暗；
      · 坐姿淡化必须比线性快 —— 否则中途两张同等清晰，叠起来糊成一团。
    """

    def test_endpoints_are_pure_poses(self):
        """e=0 必须完全是坐姿、e=1 必须完全是睡姿（端点不能有余量）。"""
        (a_sit, dy_sit, sc_sit), (a_sleep, dy_sleep, sc_sleep) = pose_blend(0.0)
        self.assertAlmostEqual(a_sit, 1.0)
        self.assertAlmostEqual(a_sleep, 0.0)
        self.assertAlmostEqual(dy_sit, 0.0)
        self.assertAlmostEqual(dy_sleep, -win.POSE_SWAP_DY)
        self.assertAlmostEqual(sc_sit, 1.0)
        self.assertAlmostEqual(sc_sleep, win.POSE_SWAP_SCALE)

        (a_sit, dy_sit, sc_sit), (a_sleep, dy_sleep, sc_sleep) = pose_blend(1.0)
        self.assertAlmostEqual(a_sit, 0.0)
        self.assertAlmostEqual(a_sleep, 1.0)
        self.assertAlmostEqual(dy_sit, win.POSE_SWAP_DY)
        self.assertAlmostEqual(dy_sleep, 0.0)
        self.assertAlmostEqual(sc_sit, win.POSE_SWAP_SCALE)
        self.assertAlmostEqual(sc_sleep, 1.0)

    def test_opacities_are_complementary(self):
        """全程相加恒为 1 —— 这是"不忽明忽暗"的硬条件。"""
        for i in range(11):
            (a_sit, _, _), (a_sleep, _, _) = pose_blend(i / 10.0)
            self.assertAlmostEqual(a_sit + a_sleep, 1.0, places=9)

    def test_sit_fades_faster_than_linear(self):
        """坐姿要退得比线性快，中途由睡姿占主导。"""
        self.assertGreater(win.POSE_SWAP_CURVE, 1.0)
        self.assertLess(pose_blend(0.5)[0][0], 0.4)

    def test_out_of_range_progress_is_clamped(self):
        self.assertEqual(pose_blend(-1.0), pose_blend(0.0))
        self.assertEqual(pose_blend(2.0), pose_blend(1.0))

    def test_ease_curve_is_anchored_and_monotonic(self):
        """缓动曲线两端必须锚在 0/1（否则过渡会"差一点到位"），且单调不减。"""
        f = win.SitReminderWindow._ease_in_out_cubic
        self.assertAlmostEqual(f(0.0), 0.0)
        self.assertAlmostEqual(f(1.0), 1.0)
        self.assertAlmostEqual(f(0.5), 0.5)
        prev = -1.0
        for i in range(21):
            v = f(i / 20.0)
            self.assertGreater(v, prev - 1e-12)
            prev = v


# settings.py 顶层也 import PySide6，同样要能优雅跳过。
try:
    from sitreminder.qt.settings import clamp_into_area
    _QT_SETTINGS_OK = True
except ModuleNotFoundError:
    _QT_SETTINGS_OK = False


class _FakeArea:
    """最小可用区替身。clamp_into_area 只认 x/y/width/height 四个方法（鸭子类型）。"""

    def __init__(self, x, y, w, h):
        self._r = (x, y, w, h)

    def x(self):
        return self._r[0]

    def y(self):
        return self._r[1]

    def width(self):
        return self._r[2]

    def height(self):
        return self._r[3]


@unittest.skipUnless(_QT_SETTINGS_OK, "PySide6 未安装，跳过设置窗定位单测")
class SettingsPositionTests(unittest.TestCase):
    """设置窗必须**整体**（含标题栏外框）落在屏幕可用区内。

    回归 bug：贴屏幕底部时窗口底部溢出约 30px（标题栏高），「保存」一行被切掉，
    得手动把窗口拖上来。根因是拿客户区尺寸去算外框的位置。
    """

    AREA = _FakeArea(0, 0, 1536, 816)

    def test_rect_already_inside_is_untouched(self):
        """已经完整可见的窗口不该被挪动。"""
        self.assertEqual(clamp_into_area(200, 200, 300, 381, self.AREA), (200, 200))

    def test_bottom_overflow_is_pulled_up(self):
        """核心回归：外框底部越过下沿 → 整窗上收到刚好贴边（816-381=435）。"""
        self.assertEqual(clamp_into_area(100, 500, 300, 381, self.AREA), (100, 435))

    def test_right_overflow_is_pulled_left(self):
        self.assertEqual(clamp_into_area(1400, 100, 300, 381, self.AREA), (1236, 100))

    def test_offscreen_left_top_is_pushed_back_in(self):
        self.assertEqual(clamp_into_area(-50, -80, 300, 381, self.AREA), (0, 0))

    def test_oversized_rect_pins_to_top_left(self):
        """整窗比屏幕还高时贴顶/贴左，保住标题栏一侧，不产生负坐标。"""
        self.assertEqual(clamp_into_area(10, 10, 300, 900, self.AREA), (10, 0))

    def test_does_not_use_inclusive_bottom_right(self):
        """防止有人改回 QRect.right()/bottom()（包含式坐标，会凭空少 1 像素）。

        用「右下角刚好贴边」验证：宽 1536 的区里放 1536 宽的窗，左边必须落在 0。
        """
        area = _FakeArea(0, 0, 1536, 816)
        self.assertEqual(clamp_into_area(0, 0, 1536, 816, area), (0, 0))


if __name__ == "__main__":
    unittest.main()
