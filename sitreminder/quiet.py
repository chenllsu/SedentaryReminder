"""免打扰时段判断（纯逻辑，不依赖 Qt，可直接单测）。

用户可以在设置窗里划一个时间段（例如 22:00 – 08:00），这段时间内
到点也不弹提醒气泡，避免午休 / 夜里被打断。**计时不受影响**：
免打扰只是不上屏，该重置的这一轮照常重置。

之所以独立成一个模块：时段判断是纯粹的「时间数学」，
跨夜、边界、非法输入这些边界情况值得单独测，不该埋在窗口代码里。
"""

from __future__ import annotations

from datetime import datetime

# 默认时段：晚上 22:00 到次日早上 08:00（跨夜）
DEFAULT_START = "22:00"
DEFAULT_END = "08:00"


def parse_hhmm(value) -> tuple[int, int] | None:
    """把 "22:00" / "8:5" 解析成 (时, 分)；格式不合法返回 None。"""
    if not isinstance(value, str):
        return None
    parts = value.strip().split(":")
    if len(parts) != 2:
        return None
    try:
        hh, mm = int(parts[0]), int(parts[1])
    except ValueError:
        return None
    if not (0 <= hh <= 23) or not (0 <= mm <= 59):
        return None
    return hh, mm


def normalize_hhmm(value, fallback: str) -> str:
    """归一化成 "HH:MM"（补零）；非法输入退回 fallback。"""
    parsed = parse_hhmm(value)
    if parsed is None:
        return fallback
    return f"{parsed[0]:02d}:{parsed[1]:02d}"


def _minutes_of_day(hhmm) -> int | None:
    """转成「当天 0 点起的分钟数」；非法返回 None。"""
    parsed = parse_hhmm(hhmm)
    if parsed is None:
        return None
    return parsed[0] * 60 + parsed[1]


def in_quiet_hours(now_minutes: int, start, end) -> bool:
    """判断「当天第 now_minutes 分钟」是否落在免打扰时段内。

    三种情形：
      - start < end（如 12:30–13:30）：普通区间，左闭右开。
      - start > end（如 22:00–08:00）：跨夜区间，判断为
        「不早于 start」或「早于 end」。
      - start == end 或时间非法：**一律视为不生效**。
        否则 22:00–22:00 会被理解成"整天都免打扰"，跟用户本意相反。
    """
    s = _minutes_of_day(start)
    e = _minutes_of_day(end)
    if s is None or e is None or s == e:
        return False
    if s < e:
        return s <= now_minutes < e
    return now_minutes >= s or now_minutes < e


def is_quiet_now(now: datetime, start, end) -> bool:
    """is in_quiet_hours 的 datetime 便捷版。"""
    return in_quiet_hours(now.hour * 60 + now.minute, start, end)
