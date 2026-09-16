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
        # 本轮暂停的起始时刻；未暂停时为 None。用来算「已暂停多久」。
        self._pause_started: datetime = None
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
            self._pause_started = None

    def skip(self, keep_paused: bool = False) -> None:
        """跳过本轮（等价于「刚活动过，重新计」）。

        keep_paused 语义同 reset()：暂停中调用时是否保持暂停。
        """
        self.reset(keep_paused=keep_paused)

    def pause(self) -> None:
        if not self.paused:
            self._remaining = max(0.0, (self._end - datetime.now()).total_seconds())
            self.paused = True
            self._pause_started = datetime.now()

    def resume(self) -> None:
        if self.paused:
            self._end = datetime.now() + timedelta(seconds=self._remaining)
            self.paused = False
            self._pause_started = None

    def toggle(self) -> None:
        self.resume() if self.paused else self.pause()

    def remaining(self) -> int:
        """剩余秒数（不会为负）。"""
        if self.paused:
            return int(self._remaining)
        return max(0, int((self._end - datetime.now()).total_seconds()))

    def paused_seconds(self) -> int:
        """已暂停时长（秒）；未暂停返回 0。

        与 remaining() 互补：暂停期间剩余时间是「冻住」的、没有信息量，
        已暂停时长才是用户在意的那个数（是不是停太久了）。
        """
        if not self.paused or self._pause_started is None:
            return 0
        return max(0, int((datetime.now() - self._pause_started).total_seconds()))

    def defer(self, seconds: int) -> None:
        """把「本轮」提醒往后延（气泡里的「稍后提醒」）。

        只挪这一轮的结束时间，**不改动用户设定的 interval**——
        「这个提醒我先不处理」和「以后都改成 5 分钟一次」是两件事。
        顺带解除暂停：用户点了「稍后提醒」，就是想让提醒继续跑起来。
        """
        seconds = max(1, int(seconds))
        self.paused = False
        self._pause_started = None
        self._remaining = float(seconds)
        self._end = datetime.now() + timedelta(seconds=seconds)

    def restart_pause_clock(self) -> None:
        """把「已暂停多久」的计时起点挪到现在（不改暂停状态，未暂停则空操作）。

        用途：设置窗打开时计时会被程序冻结，那不是用户主动暂停。
        若不重置起点，开着设置窗待一会儿再关，就会被误判成「暂停超时」。
        """
        if self.paused:
            self._pause_started = datetime.now()

    def is_due(self) -> bool:
        """是否到点需要提醒（暂停中不触发）。"""
        return not self.paused and self.remaining() <= 0

    def set_interval(self, seconds: int) -> None:
        """修改间隔并立即重新计时。"""
        self.interval = clamp_interval(seconds)
        self.reset()
