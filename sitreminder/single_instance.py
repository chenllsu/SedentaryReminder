"""单实例保护：只允许一个妮子在桌面上。

多开会导致两个问题：两只猫叠在一起，以及多个进程同时写 config.json。
Windows 用内核互斥体（不会触发防火墙），其他平台用文件锁。
任何异常都按「放行」处理——检测功能失效也不能让用户打不开程序。
"""

from __future__ import annotations

import logging
import os
import sys

from . import paths

log = logging.getLogger(__name__)

MUTEX_NAME = "Local\\SitReminder_SingleInstance_v1"
ERROR_ALREADY_EXISTS = 183


class SingleInstanceGuard:
    def __init__(self):
        self._mutex_handle = None
        self._lock_file = None
        self._lock_path = os.path.join(paths.user_data_dir(), ".single_instance.lock")

    def acquire(self) -> bool:
        """返回 True 表示「我是第一个实例」。"""
        try:
            if sys.platform == "win32":
                return self._acquire_win32()
            return self._acquire_posix()
        except Exception:
            log.debug("单实例检测不可用，放行", exc_info=True)
            return True

    def release(self) -> None:
        try:
            if self._mutex_handle is not None:
                import ctypes
                ctypes.windll.kernel32.CloseHandle(self._mutex_handle)
                self._mutex_handle = None
            if self._lock_file is not None:
                import fcntl
                fcntl.flock(self._lock_file, fcntl.LOCK_UN)
                self._lock_file.close()
                self._lock_file = None
        except Exception:
            log.debug("释放单实例锁时出错", exc_info=True)

    # Windows：命名互斥体
    def _acquire_win32(self) -> bool:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.windll.kernel32
        kernel32.CreateMutexW.restype = wintypes.HANDLE
        handle = kernel32.CreateMutexW(None, wintypes.BOOL(True), MUTEX_NAME)
        already_exists = ctypes.get_last_error() == ERROR_ALREADY_EXISTS

        if not handle:      # 创建失败 → 无法判断，放行
            return True
        if already_exists:  # 已有人持有 → 关掉自己这份句柄后退出
            kernel32.CloseHandle(handle)
            return False

        self._mutex_handle = handle
        return True

    # Linux / macOS：文件锁
    def _acquire_posix(self) -> bool:
        import fcntl

        self._lock_file = open(self._lock_path, "w")
        try:
            fcntl.flock(self._lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self._lock_file.close()
            self._lock_file = None
            return False
        return True
