"""Windows calls for placing windows: Nanar's and mpv's must cover the same rectangle.

Only imported on Windows. Both rectangles are outer ones, in physical pixels (the process is
DPI-aware: WebView2 and mpv both declare it).
"""

import ctypes
import sys
from ctypes import wintypes

from nanar.player import Rect

assert sys.platform == "win32"  # also tells mypy to check this module for Windows only

user32 = ctypes.WinDLL("user32", use_last_error=True)

_EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
user32.EnumWindows.argtypes = [_EnumWindowsProc, wintypes.LPARAM]
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.IsZoomed.argtypes = [wintypes.HWND]
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.SetWindowPos.argtypes = [
    wintypes.HWND,
    wintypes.HWND,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    wintypes.UINT,
]
_SWP_NOZORDER = 0x0004


def find_window(pid: int, class_name: str) -> int | None:
    """The first visible top-level window of this process with this window class."""
    found: list[int] = []

    def visit(hwnd: int, _: int) -> bool:
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value != pid or not user32.IsWindowVisible(hwnd):
            return True
        buffer = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, buffer, 256)
        if buffer.value == class_name:
            found.append(hwnd)
            return False
        return True

    user32.EnumWindows(_EnumWindowsProc(visit), 0)
    return found[0] if found else None


def window_rect(hwnd: int) -> Rect | None:
    rect = wintypes.RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return None
    return Rect(rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top)


def window_rect_of_process(pid: int, class_name: str) -> Rect | None:
    hwnd = find_window(pid, class_name)
    return window_rect(hwnd) if hwnd else None


def declare_dpi_aware() -> None:
    """Draws at the screen's real resolution. Without it, on a display scaled to 125 % or more,
    Windows renders mpv's video at a lower resolution and stretches it: a blurry film."""
    per_monitor_v2 = ctypes.c_void_p(-4)
    user32.SetProcessDpiAwarenessContext.argtypes = [ctypes.c_void_p]
    user32.SetProcessDpiAwarenessContext(per_monitor_v2)


def place_window(hwnd: int, rect: Rect) -> None:
    user32.SetWindowPos(hwnd, None, rect.x, rect.y, rect.width, rect.height, _SWP_NOZORDER)


def bring_to_front(hwnd: int) -> None:
    user32.SetForegroundWindow(hwnd)
