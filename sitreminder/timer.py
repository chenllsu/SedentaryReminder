"""倒计时状态机。

核心设计：剩余时间由「结束时间戳 - 当前时间」算出，而不是每帧自减。
这样即使主线程卡顿、刷新被推迟，倒计时依然准确，不会累积误差。
"""

from __future__ import annotations

from datetime import datetime, timedelta

from .config import clamp_interval


class TimerState:
    def __init__(self, seconds: int):
        self.interval = clamp_interval(seconds)
        self.paused = False
        self._remaining = float(self.interval)
        self._end: datetime = None
        self.reset()

    @property
    def is_paused(self) -> bool:
        return self.paused

    def reset(self) -> None:
        """从完整间隔重新开始。"""
        self._end = datetime.now() + timedelta(seconds=self.interval)
        self._remaining = float(self.interval)
        self.paused = False

    def skip(self) -> None:
        """跳过本轮（等价于「刚活动过，重新计」）。"""
        self.reset()

    def pause(self) -> None:
        if not self.paused:
            self._remaining = max(0.0, (self._end - datetime.now()).total_seconds())
            self.paused = True

    def resume(self) -> None:
        if self.paused:
            self._end = datetime.now() + timedelta(seconds=self._remaining)
            self.paused = False

    def toggle(self) -> None:
        self.resume() if self.paused else self.pause()

    def remaining(self) -> int:
        """剩余秒数（不会为负）。"""
        if self.paused:
            return int(self._remaining)
        return max(0, int((self._end - datetime.now()).total_seconds()))

    def is_due(self) -> bool:
        """是否到点需要提醒（暂停中不触发）。"""
        return not self.paused and self.remaining() <= 0

    def set_interval(self, seconds: int) -> None:
        """修改间隔并立即重新计时。"""
        self.interval = clamp_interval(seconds)
        self.reset()
