"""配置读写（本地 JSON，不联网）。"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict

from . import paths

log = logging.getLogger(__name__)

DEFAULT_INTERVAL_SECONDS = 1800          # 默认 30 分钟
MIN_INTERVAL_SECONDS = 5                 # 下限：低于 5 秒会变成「骚扰」
MAX_INTERVAL_SECONDS = 36000             # 上限 600 分钟（与设置窗口校验一致）

DEFAULT_CONFIG: Dict[str, Any] = {
    "interval_seconds": DEFAULT_INTERVAL_SECONDS,
    "autostart": False,
    "window_pos": None,          # [x, y] 浮窗最后位置；None = 从未记录（首次启动）
}


def clamp_interval(seconds: Any) -> int:
    """把任意输入收敛到合法区间，非法值退回默认值。"""
    try:
        value = int(seconds)
    except (TypeError, ValueError):
        value = DEFAULT_INTERVAL_SECONDS
    return max(MIN_INTERVAL_SECONDS, min(MAX_INTERVAL_SECONDS, value))


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
    }


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
