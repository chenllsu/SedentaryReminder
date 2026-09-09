"""日志初始化。

打包成 --noconsole 后没有控制台，回调里的异常会「静默消失」，
所以统一记一份滚动日志到用户数据目录，便于排查。
"""

from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler

from . import paths

ROOT_LOGGER_NAME = "sitreminder"


def setup_logging(level: int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger(ROOT_LOGGER_NAME)
    logger.setLevel(level)
    for h in list(logger.handlers):  # 避免重复初始化产生重复日志
        logger.removeHandler(h)

    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")

    if getattr(sys, "stderr", None) is not None:
        stream = logging.StreamHandler(sys.stderr)
        stream.setFormatter(fmt)
        logger.addHandler(stream)

    try:
        file_handler = RotatingFileHandler(
            os.path.join(paths.user_data_dir(), "sitreminder.log"),
            maxBytes=256 * 1024,
            backupCount=2,
            encoding="utf-8",
        )
        file_handler.setFormatter(fmt)
        logger.addHandler(file_handler)
    except OSError:
        pass  # 日志写不了也不能影响主程序运行

    return logger
