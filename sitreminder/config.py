"""配置读写（本地 JSON，不联网）。"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict

from . import paths, quiet
from .quips import DEFAULT_STYLE, STYLES

log = logging.getLogger(__name__)

DEFAULT_INTERVAL_SECONDS = 1800          # 默认 30 分钟
MIN_INTERVAL_SECONDS = 5                 # 下限：低于 5 秒会变成「骚扰」
MAX_INTERVAL_SECONDS = 36000             # 上限 600 分钟（与设置窗口校验一致）

# 妮子显示边长的三档预设（小 / 中 / 大），默认中档。
# 浮窗尺寸、素材缩放、胶囊位置全由它推导（见 qt/window.window_size_for）。
MASCOT_SIZE_PRESETS = (88, 110, 132)
DEFAULT_MASCOT_SIZE = 110

# 暂停体验：暂停超过这个时长就自动恢复计时（免得"停着停着忘了"再没被提醒过）。
# 0 = 不自动恢复，暂停完全由用户手动解除。
DEFAULT_PAUSE_AUTO_RESUME_SECONDS = 1800
MIN_PAUSE_AUTO_RESUME_SECONDS = 60

# 提醒气泡里「稍后提醒」按钮延后的时长（只挪这一轮，不改用户设定的间隔）。
DEFAULT_SNOOZE_SECONDS = 300
MIN_SNOOZE_SECONDS = 60
MAX_SNOOZE_SECONDS = 3600

DEFAULT_CONFIG: Dict[str, Any] = {
    "interval_seconds": DEFAULT_INTERVAL_SECONDS,
    "autostart": False,
    "window_pos": None,          # [x, y] 浮窗最后位置；None = 从未记录（首次启动）
    "capsule_always_visible": True,  # 倒计时贴纸是否常驻显示；False = 悬停/暂停才出现
    "quip_style": DEFAULT_STYLE,     # 话术风格；「随机」= 每次从全部风格里抽
    "mascot_size": DEFAULT_MASCOT_SIZE,                   # 妮子大小（三档）
    "pause_auto_resume_seconds": DEFAULT_PAUSE_AUTO_RESUME_SECONDS,
    "snooze_seconds": DEFAULT_SNOOZE_SECONDS,
    "quiet_enabled": False,                               # 免打扰时段开关
    "quiet_start": quiet.DEFAULT_START,
    "quiet_end": quiet.DEFAULT_END,
}


def clamp_interval(seconds: Any) -> int:
    """把任意输入收敛到合法区间，非法值退回默认值。"""
    try:
        value = int(seconds)
    except (TypeError, ValueError):
        value = DEFAULT_INTERVAL_SECONDS
    return max(MIN_INTERVAL_SECONDS, min(MAX_INTERVAL_SECONDS, value))


def sanitize_mascot_size(raw: Any) -> int:
    """妮子尺寸收敛到**最接近的预设档位**（手改配置、旧配置都能兜住）。"""
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_MASCOT_SIZE
    return min(MASCOT_SIZE_PRESETS, key=lambda p: abs(p - value))


def clamp_pause_auto_resume(seconds: Any) -> int:
    """暂停自动恢复时长（秒）：0 或负数 = 关闭；其余收敛到 [60, MAX_INTERVAL_SECONDS]。"""
    try:
        value = int(seconds)
    except (TypeError, ValueError):
        return DEFAULT_PAUSE_AUTO_RESUME_SECONDS
    if value <= 0:
        return 0
    return max(MIN_PAUSE_AUTO_RESUME_SECONDS, min(MAX_INTERVAL_SECONDS, value))


def clamp_snooze(seconds: Any) -> int:
    """「稍后提醒」延后时长（秒），收敛到 [1 分钟, 1 小时]。"""
    try:
        value = int(seconds)
    except (TypeError, ValueError):
        return DEFAULT_SNOOZE_SECONDS
    return max(MIN_SNOOZE_SECONDS, min(MAX_SNOOZE_SECONDS, value))


def sanitize_window_pos(raw: Any):
    """把窗口位置收敛为 [x, y]；缺失或非法 → None。

    返回 None 是有意义的语义：表示「用户还没拖过窗口」，
    调用方据此走首次启动的默认位置（屏幕右下角）。

    统一返回 list（而非 tuple）：save_config 写出的就是 JSON 数组，
    读回来保持一致，调用方才能用 == 判断"位置未变、无需重复写盘"。
    """
    if isinstance(raw, (list, tuple)) and len(raw) == 2:
        try:
            return [int(raw[0]), int(raw[1])]
        except (TypeError, ValueError):
            return None
    return None


def load_config(path: str = None) -> Dict[str, Any]:
    """读取配置；文件缺失或损坏时返回默认配置，绝不抛异常。"""
    path = path or paths.CONFIG_PATH
    raw: Dict[str, Any] = {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            loaded = json.load(fh)
        if isinstance(loaded, dict):
            raw = dict(loaded)
    except FileNotFoundError:
        log.info("未找到配置文件，使用默认配置：%s", path)
    except (OSError, ValueError) as exc:
        log.warning("配置文件读取失败，使用默认配置：%s", exc)

    # 旧版本曾用 interval_minutes 字段。迁移必须放在补默认值之前：
    # 一旦先 setdefault("interval_seconds")，这里就永远判断不到，迁移会变成死代码。
    if "interval_minutes" in raw and "interval_seconds" not in raw:
        try:
            raw["interval_seconds"] = int(raw["interval_minutes"]) * 60
        except (TypeError, ValueError):
            raw["interval_seconds"] = DEFAULT_INTERVAL_SECONDS

    return {
        "interval_seconds": clamp_interval(
            raw.get("interval_seconds", DEFAULT_INTERVAL_SECONDS)
        ),
        "autostart": bool(raw.get("autostart", False)),
        "window_pos": sanitize_window_pos(raw.get("window_pos")),
        "capsule_always_visible": bool(raw.get("capsule_always_visible", True)),
        # 话术风格：只认 STYLES 里的值，其他一律回退「默认」
        "quip_style": _sanitize_quip_style(raw.get("quip_style")),
        "mascot_size": sanitize_mascot_size(raw.get("mascot_size")),
        "pause_auto_resume_seconds": clamp_pause_auto_resume(
            raw.get("pause_auto_resume_seconds", DEFAULT_PAUSE_AUTO_RESUME_SECONDS)
        ),
        "snooze_seconds": clamp_snooze(
            raw.get("snooze_seconds", DEFAULT_SNOOZE_SECONDS)
        ),
        "quiet_enabled": bool(raw.get("quiet_enabled", False)),
        "quiet_start": quiet.normalize_hhmm(
            raw.get("quiet_start"), quiet.DEFAULT_START),
        "quiet_end": quiet.normalize_hhmm(
            raw.get("quiet_end"), quiet.DEFAULT_END),
    }


def _sanitize_quip_style(raw: Any) -> str:
    """话术风格收敛：缺失/非法/手改配置 → 回退「默认」。"""
    style = raw if isinstance(raw, str) else None
    return style if style in STYLES else DEFAULT_STYLE


def in_quiet_hours(now=None) -> bool:
    """当前是否处于「免打扰时段」（按配置判断，未启用一律 False）。

    now 可注入（测试用）；默认取本机当前时间。
    """
    cfg = load_config()
    if not cfg.get("quiet_enabled"):
        return False
    from datetime import datetime
    return quiet.is_quiet_now(now or datetime.now(),
                              cfg.get("quiet_start"), cfg.get("quiet_end"))


def save_config(cfg: Dict[str, Any], path: str = None) -> bool:
    """原子写入配置（先写 .tmp 再替换），避免写到一半崩溃导致配置损坏。"""
    path = path or paths.CONFIG_PATH
    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(cfg, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
        return True
    except OSError as exc:
        log.warning("配置保存失败：%s", exc)
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except OSError:
            pass
        return False
