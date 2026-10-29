"""Nanar's window: the TV page in a native window (pywebview, WebView2 on Windows).

When a video starts, mpv opens over the same rectangle and this window hides; when it stops, the
window comes back where mpv's was, windowed or full screen as mpv was left.
"""

import sys
import threading
from collections.abc import Callable
from typing import Any

from nanar.player import Rect

BACKGROUND = "#120d1a"  # the TV page's background, shown before it has loaded


class TvWindow:
    def __init__(self, url: str, *, fullscreen: bool) -> None:
        import webview

        self._webview = webview
        self._fullscreen = fullscreen
        self._hidden = False  # while mpv plays over it
        self._lock = threading.Lock()
        window = webview.create_window(
            "Nanar",
            url,
            width=1280,
            height=720,
            min_size=(640, 360),
            fullscreen=fullscreen,
            background_color=BACKGROUND,
            text_select=False,
        )
        assert window is not None
        window.events.shown += self._on_shown
        self.window: Any = window

    def _on_shown(self) -> None:
        if sys.platform == "win32" and (hwnd := self._hwnd()) is not None:
            from nanar.desktop import win32

            win32.set_icon(hwnd)

    def run(self, on_ready: Callable[[], None] | None = None) -> None:
        """Runs the GUI loop on this (main) thread until the window is closed."""
        self._webview.start(on_ready, private_mode=False)

    # WindowHost --------------------------------------------------------------------------------

    def rect(self) -> Rect | None:
        if self._fullscreen:
            return None  # mpv opens full screen on the same display on its own
        if sys.platform == "win32" and (hwnd := self._hwnd()) is not None:
            from nanar.desktop import win32

            return win32.window_rect(hwnd)
        return None

    def hide(self) -> None:
        self._hidden = True
        self.window.hide()

    def show(self, rect: Rect | None, fullscreen: bool) -> None:
        self._hidden = False
        self.set_fullscreen(fullscreen)
        if sys.platform == "win32" and (hwnd := self._hwnd()) is not None:
            from nanar.desktop import win32

            if rect is not None and not fullscreen:
                win32.place_window(hwnd, rect)
            self.window.show()
            win32.bring_to_front(hwnd)
        else:
            self.window.show()

    def set_fullscreen(self, fullscreen: bool) -> None:
        with self._lock:
            if fullscreen != self._fullscreen:
                self._fullscreen = fullscreen
                self.window.toggle_fullscreen()
        if fullscreen and not self._hidden:
            self.bring_to_front()  # asked from the phone: the taskbar stays over it otherwise

    # The desktop -------------------------------------------------------------------------------

    def choose_folder(self) -> str | None:
        """The system's folder picker, over Nanar's window; None when cancelled."""
        chosen = self.window.create_file_dialog(self._webview.FileDialog.FOLDER)
        return str(chosen[0]) if chosen else None

    def bring_to_front(self) -> None:
        """Back in front (from behind other windows, or minimised)."""
        if sys.platform == "win32" and (hwnd := self._hwnd()) is not None:
            from nanar.desktop import win32

            win32.restore(hwnd)
            win32.bring_to_front(hwnd)

    def _hwnd(self) -> int | None:
        native = getattr(self.window, "native", None)
        handle = getattr(native, "Handle", None)
        return int(handle.ToInt64()) if handle is not None else None
