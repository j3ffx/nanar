"""Stand-ins for mpv and Nanar's window, whose every call the tests can see."""

from typing import Any

from nanar.config import Settings
from nanar.player import Callbacks, Playback, Rect, Start


class FakeSession:
    instances: list["FakeSession"]

    def __init__(self, start: Start, settings: Settings, callbacks: Callbacks) -> None:
        self.start = start
        self.callbacks = callbacks
        self.commands: list[tuple[str, Any]] = []
        self.closed = False
        self.window = Rect(10, 20, 800, 450)

    def command(self, action: str, value: Any = None) -> None:
        if action == "volume" and not isinstance(value, int | float):
            raise ValueError("volume")
        self.commands.append((action, value))

    def rect(self) -> Rect | None:
        return self.window

    def close(self) -> None:
        self.closed = True

    # What mpv's event thread would report.

    def report(self, **changes: Any) -> None:
        self.callbacks.changed(Playback(**changes))

    def finish(self) -> None:
        self.callbacks.ended(True, self.window)


class FakeSessions:
    """The session factory: keeps every session it made."""

    def __init__(self) -> None:
        self.made: list[FakeSession] = []

    def __call__(self, start: Start, settings: Settings, callbacks: Callbacks) -> FakeSession:
        session = FakeSession(start, settings, callbacks)
        self.made.append(session)
        return session

    @property
    def last(self) -> FakeSession:
        return self.made[-1]


class FakeWindow:
    def __init__(self) -> None:
        self.visible = True
        self.fullscreen = False
        self.at = Rect(100, 100, 1280, 720)
        self.calls: list[str] = []

    def rect(self) -> Rect | None:
        return self.at

    def hide(self) -> None:
        self.visible = False
        self.calls.append("hide")

    def show(self, rect: Rect | None, fullscreen: bool) -> None:
        self.visible = True
        self.fullscreen = fullscreen
        if rect is not None:
            self.at = rect
        self.calls.append("show")

    def set_fullscreen(self, fullscreen: bool) -> None:
        self.fullscreen = fullscreen
        self.calls.append(f"fullscreen={fullscreen}")
