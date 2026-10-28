"""Windows calls for placing windows: Nanar's and mpv's must cover the same rectangle.

Only imported on Windows. Both rectangles are outer ones, in physical pixels (the process is
DPI-aware: WebView2 and mpv both declare it).
"""

import ctypes
import os
import sys
from ctypes import wintypes
from pathlib import Path

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
user32.LoadImageW.argtypes = [
    wintypes.HINSTANCE,
    wintypes.LPCWSTR,
    wintypes.UINT,
    ctypes.c_int,
    ctypes.c_int,
    wintypes.UINT,
]
user32.LoadImageW.restype = wintypes.HANDLE
user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.SendMessageW.restype = wintypes.LPARAM
user32.IsIconic.argtypes = [wintypes.HWND]
user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
user32.AllowSetForegroundWindow.argtypes = [wintypes.DWORD]
_SW_RESTORE = 9
_ASFW_ANY = 0xFFFFFFFF
_MB_ICONINFORMATION = 0x40
_IMAGE_ICON = 1
_LR_LOADFROMFILE = 0x0010
_WM_SETICON = 0x0080
_ICON_SMALL = 0
_ICON_BIG = 1


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


ICON = Path(__file__).resolve().parent.parent / "assets" / "nanar.ico"


def unblock_bundle(folder: Path) -> int:
    """Removes the "downloaded from the Internet" mark from the DLLs shipped with Nanar.

    Unzipping a downloaded zip marks every file it holds (Mark of the Web, an alternate data
    stream named Zone.Identifier). .NET then refuses to load a marked assembly, and the window,
    which goes through .NET (pythonnet, WebView2), fails to open. These DLLs came with the
    executable the user chose to run: unmarking them is what Properties → Unblock does on the
    zip. Says how many were unmarked.
    """
    unmarked = 0
    for dll in folder.rglob("*.dll"):
        try:
            os.remove(f"{dll}:Zone.Identifier")
            unmarked += 1
        except OSError:  # not marked (the usual case), or a read-only folder
            pass
    return unmarked


def declare_app_id() -> None:
    """Groups Nanar's windows under its own taskbar button, not Python's."""
    shell32 = ctypes.WinDLL("shell32")
    shell32.SetCurrentProcessExplicitAppUserModelID.argtypes = [wintypes.LPCWSTR]
    shell32.SetCurrentProcessExplicitAppUserModelID("Nanar.Player")


def set_icon(hwnd: int) -> None:
    """Gives a window Nanar's icon (title bar, Alt+Tab, taskbar) instead of python.exe's."""
    for which, size in ((_ICON_SMALL, 16), (_ICON_BIG, 32)):
        icon = user32.LoadImageW(None, str(ICON), _IMAGE_ICON, size, size, _LR_LOADFROMFILE)
        if icon:
            user32.SendMessageW(hwnd, _WM_SETICON, which, icon)


def place_window(hwnd: int, rect: Rect) -> None:
    user32.SetWindowPos(hwnd, None, rect.x, rect.y, rect.width, rect.height, _SWP_NOZORDER)


def bring_to_front(hwnd: int) -> None:
    user32.SetForegroundWindow(hwnd)


def restore(hwnd: int) -> None:
    """Un-minimises a window (and leaves a visible one as it is)."""
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, _SW_RESTORE)


def allow_any_foreground() -> None:
    """Lets another process (the Nanar already open) come to the front: Windows only allows it
    to the process the user just started, which is this one."""
    user32.AllowSetForegroundWindow(_ASFW_ANY)


def message_box(title: str, text: str) -> None:
    """A plain message with an OK button: what the build, which has no console, prints."""
    user32.MessageBoxW(None, text, title, _MB_ICONINFORMATION)
