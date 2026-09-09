"""内置诙谐文案库（固定 10 条，用户不可自定义）。"""

from __future__ import annotations

import random

QUIPS = [
    "屁股已经和椅子谈恋爱了，去分开它们五分钟吧～",
    "你的脊椎正在默默吐槽：我就没直起来过？",
    "再不动一动，椅子就要长在你身上了哦。",
    "起来！别让血液只在屁股那一块循环。",
    "颈椎发来消息：主人，我也想伸个懒腰。",
    "据说站起来的人，比坐着的人更接近健康。",
    "你的腿：主人，你还记得我有吗？",
    "久坐一时爽，起来才发现——原来腿还是自己的。",
    "给眼睛和屁股都放个假吧，站起来看看远方。",
    "警告：检测到人类已进化成蘑菇，请起身恢复人形。",
]

_last: str = None


def pick_quip() -> str:
    """随机取一条，且尽量不与上一条重复（连着两次一样会很出戏）。"""
    global _last
    if not QUIPS:
        return "该起来活动一下啦～"
    if len(QUIPS) == 1:
        return QUIPS[0]

    idx = random.randrange(len(QUIPS))
    if QUIPS[idx] == _last:
        # 换一条不同的：在剩余 len-1 条里偏移一个随机量
        idx = (idx + 1 + random.randrange(len(QUIPS) - 1)) % len(QUIPS)
    _last = QUIPS[idx]
    return QUIPS[idx]
