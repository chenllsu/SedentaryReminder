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

    def reset(self, keep_paused: bool = False) -> None:
        """把剩余时间归位到完整间隔，重新计这一轮。

        keep_paused=True 时「只归位剩余时间、暂停状态原样保留」。
        用于暂停期间的重置场景：
          - 设置窗打开时（倒计时冻结），窗内点「跳过本次」应只把本轮归零，
            而不是顺手把冻结也解掉；
          - 提醒气泡显示期间用户按了暂停，关掉气泡后暂停要仍然有效。
        这两种情况用户都只是「想重置这一轮」，并没有要求开始计时。
        """
        self._remaining = float(self.interval)
        self._end = datetime.now() + timedelta(seconds=self.interval)
        if not keep_paused:
            self.paused = False

    def skip(self, keep_paused: bool = False) -> None:
        """跳过本轮（等价于「刚活动过，重新计」）。

        keep_paused 语义同 reset()：暂停中调用时是否保持暂停。
        """
        self.reset(keep_paused=keep_paused)

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
