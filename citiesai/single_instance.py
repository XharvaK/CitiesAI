"""Ensure only one CitiesAI desktop instance runs at a time."""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from typing import Literal

MUTEX_NAME = r"Local\CitiesAI.SingleInstance.v1"
FOCUS_TIMEOUT = 2.0
FOCUS_RETRIES = 20
FOCUS_RETRY_DELAY = 0.12

InstanceAction = Literal["start", "focused"]


class _WindowsMutex:
    def __init__(self) -> None:
        self._handle: int | None = None

    def try_acquire(self) -> bool:
        if sys.platform != "win32":
            return True
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.CreateMutexW(None, False, MUTEX_NAME)
        if not handle:
            return True
        already_exists = kernel32.GetLastError() == 183
        if already_exists:
            kernel32.CloseHandle(handle)
            return False
        self._handle = handle
        return True

    def release(self) -> None:
        if sys.platform != "win32" or self._handle is None:
            return
        kernel32 = ctypes.windll.kernel32
        kernel32.CloseHandle(self._handle)
        self._handle = None


if sys.platform == "win32":
    import ctypes

_mutex = _WindowsMutex()


def focus_running_instance(base_url: str) -> bool:
    url = f"{base_url.rstrip('/')}/api/focus"
    request = urllib.request.Request(url, headers={"User-Agent": "CitiesAI/single-instance"}, method="GET")
    for _ in range(FOCUS_RETRIES):
        try:
            with urllib.request.urlopen(request, timeout=FOCUS_TIMEOUT) as response:
                payload = json.loads(response.read().decode("utf-8"))
                return bool(payload.get("ok"))
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
            time.sleep(FOCUS_RETRY_DELAY)
    return False


def ensure_single_instance(base_url: str) -> InstanceAction:
    """Return ``focused`` when an existing instance was raised; else ``start``."""
    if _mutex.try_acquire():
        return "start"
    if focus_running_instance(base_url):
        return "focused"
    return "focused"
