"""Playback, in mpv's own window: one mpv instance per video, closed when the video stops.

The `Session` protocol is what the controller drives; `MpvSession` is the real one (libmpv
through python-mpv), and tests use a fake. mpv calls back from its own threads: the callbacks
given to a session must be thread-safe.
"""

import os
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar, Protocol

from nanar.config import Settings


@dataclass(frozen=True)
class Rect:
    """A window's outer rectangle on the desktop, in physical pixels."""

    x: int
    y: int
    width: int
    height: int


@dataclass
class Track:
    id: int
    kind: str  # "audio" or "sub"
    lang: str | None
    title: str | None
    selected: bool
    external: bool = False

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "lang": self.lang,
            "title": self.title,
            "selected": self.selected,
            "external": self.external,
        }


@dataclass
class Playback:
    """What the phone and the TV show about the video being played."""

    position: float = 0.0
    duration: float | None = None
    paused: bool = False
    volume: float = 100.0
    muted: bool = False
    fullscreen: bool = False
    sub_delay: float = 0.0
    sub_scale: float = 1.0
    audio: list[Track] = field(default_factory=list)
    subs: list[Track] = field(default_factory=list)


@dataclass(frozen=True)
class Start:
    source: str
    title: str
    start: float = 0.0
    rect: Rect | None = None
    fullscreen: bool = False


class Callbacks(Protocol):
    def changed(self, playback: Playback) -> None: ...

    def action(self, name: str) -> None:
        """A key pressed in mpv's window that Nanar handles (next, previous)."""

    def ended(self, finished: bool, rect: Rect | None) -> None:
        """The video finished, failed, or its window was closed. Called once; the controller
        then closes the session."""


class Session(Protocol):
    def command(self, action: str, value: Any = None) -> None: ...

    def rect(self) -> Rect | None:
        """Where mpv's window is now (None when unknown)."""

    def close(self) -> None: ...


SessionFactory = Callable[[Start, Settings, Callbacks], Session]

# VLC's habits on top of mpv's own keys (mpv keeps the rest: [ ] speed, z/Z subtitle delay…).
KEY_BINDINGS = {
    "SPACE": "cycle pause",
    "f": "cycle fullscreen",
    "MBTN_LEFT_DBL": "cycle fullscreen",
    "ESC": "set fullscreen no",
    "RIGHT": "seek 10",
    "LEFT": "seek -10",
    "Ctrl+RIGHT": "seek 60",
    "Ctrl+LEFT": "seek -60",
    "UP": "add volume 5",
    "DOWN": "add volume -5",
    "WHEEL_UP": "add volume 5",
    "WHEEL_DOWN": "add volume -5",
    "m": "cycle mute",
    "b": "cycle audio",
    "v": "cycle sub",
    "g": "add sub-delay -0.1",
    "h": "add sub-delay 0.1",
    "n": "script-message nanar next",
    "p": "script-message nanar previous",
    "s": "script-message nanar stop",
    "q": "script-message nanar stop",
}


def libmpv_dirs() -> list[Path]:
    """Where libmpv-2.dll may be, besides the system's PATH: next to the frozen executable,
    or in the repository's vendor/ folder (scripts/get-libmpv.py)."""
    dirs = []
    if bundle := getattr(sys, "_MEIPASS", None):
        dirs.append(Path(bundle))
    dirs.append(Path(__file__).resolve().parents[2] / "vendor")
    return [d for d in dirs if d.is_dir()]


def _load_mpv() -> Any:
    for directory in libmpv_dirs():
        os.environ["PATH"] = f"{directory}{os.pathsep}{os.environ.get('PATH', '')}"
    import mpv  # type: ignore[import-untyped]  # python-mpv ships no type information

    return mpv


class MpvSession:
    """One video in one mpv window."""

    # Options laid over the others: tests play without a window or a sound card.
    overrides: ClassVar[dict[str, Any]] = {}

    def __init__(self, start: Start, settings: Settings, callbacks: Callbacks) -> None:
        mpv = _load_mpv()
        self._ids = mpv.MpvEventID
        self._end_file = mpv.MpvEventEndFile
        self._callbacks = callbacks
        self._playback = Playback(fullscreen=start.fullscreen)
        self._start = start
        self._placed = False
        self._ended = False  # `ended` was called (it is called once)
        self._terminated = False
        self._last_rect: Rect | None = start.rect
        options: dict[str, Any] = {
            "title": f"{start.title} — Nanar",
            "force_window": "immediate",
            "keep_open": "no",
            "idle": "yes",  # with "no", libmpv quits before the file is even loaded
            "fullscreen": start.fullscreen,
            "input_default_bindings": True,
            "input_vo_keyboard": True,
            "osc": True,
            "alang": ",".join(settings.audio_languages),
            "slang": ",".join(settings.subtitle_languages),
            "sub_auto": "fuzzy",
            "audio_file_auto": "no",
            "hwdec": "auto-safe",
            "stop_screensaver": "yes",
            "start": f"{start.start:.3f}",
        }
        if start.rect is not None:
            r = start.rect
            options["geometry"] = f"{r.width}x{r.height}+{r.x}+{r.y}"
        self._mpv = mpv.MPV(**(options | self.overrides))
        # No subtitles in the audio's language, but the forced ones (signs, a foreign line).
        # libmpv before 0.38 only knows yes/no: there, none at all.
        try:
            self._mpv["subs-with-matching-audio"] = "forced"
        except (ValueError, TypeError, RuntimeError):  # python-mpv's errors for a refused value
            self._mpv["subs-with-matching-audio"] = "no"
        for key, command in KEY_BINDINGS.items():
            self._mpv.command("keybind", key, command)
        self._mpv.register_message_handler("nanar", self._on_message)
        for name in (
            "time-pos",
            "duration",
            "pause",
            "volume",
            "mute",
            "fullscreen",
            "sub-delay",
            "sub-scale",
            "track-list",
        ):
            self._mpv.observe_property(name, self._on_property)
        self._mpv.register_event_callback(self._on_event)
        self._mpv.play(start.source)

    def command(self, action: str, value: Any = None) -> None:
        m = self._mpv
        match action:
            case "pause":
                m.pause = bool(value) if value is not None else not m.pause
            case "seek":
                m.command("seek", float(value), "relative")
            case "seek_to":
                m.command("seek", float(value), "absolute")
            case "volume":
                m.volume = max(0.0, min(130.0, float(value)))
            case "mute":
                m.mute = bool(value) if value is not None else not m.mute
            case "fullscreen":
                m.fullscreen = bool(value) if value is not None else not m.fullscreen
            case "audio":
                m.aid = int(value) if value is not None else "no"
            case "sub":
                m.sid = int(value) if value is not None else "no"
            case "sub_delay":
                m.sub_delay = float(value)
            case "sub_scale":
                m.sub_scale = max(0.3, min(3.0, float(value)))
            case _:
                raise ValueError(f"unknown player action {action!r}")

    def rect(self) -> Rect | None:
        if sys.platform != "win32":
            return None
        from nanar.desktop import win32

        return win32.window_rect_of_process(os.getpid(), "mpv")

    def _place(self) -> None:
        """Lays mpv's window exactly over Nanar's. `geometry` only comes close: mpv reads its
        size as the inside of the window, and Windows adds the frame around it."""
        self._placed = True
        target = self._start.rect
        if sys.platform != "win32" or target is None or self._start.fullscreen:
            return
        from nanar.desktop import win32

        hwnd = win32.find_window(os.getpid(), "mpv")
        if hwnd is not None:
            win32.place_window(hwnd, target)

    def close(self) -> None:
        """Closes mpv. The controller asked for it: `ended` is not called."""
        if self._terminated:
            return
        self._terminated = True
        self._mpv.terminate()

    def _on_message(self, *args: bytes | str) -> None:
        words = [a.decode() if isinstance(a, bytes) else a for a in args]
        if words and words[0] in ("stop", "next", "previous"):
            self._callbacks.action(words[0])

    def _on_property(self, name: str, value: Any) -> None:
        p = self._playback
        match name:
            case "time-pos":
                if value is None:
                    return
                if not self._placed:
                    self._place()
                # Seconds are enough for the phone: skip the many updates in between.
                if int(value) == int(p.position):
                    p.position = float(value)
                    return
                p.position = float(value)
                # Where the window is, once a second: once it is closed, it is too late to ask.
                self._last_rect = self.rect() or self._last_rect
            case "duration":
                p.duration = float(value) if value is not None else None
            case "pause":
                p.paused = bool(value)
            case "volume":
                p.volume = float(value or 0)
            case "mute":
                p.muted = bool(value)
            case "fullscreen":
                p.fullscreen = bool(value)
            case "sub-delay":
                p.sub_delay = float(value or 0)
            case "sub-scale":
                p.sub_scale = float(value or 1)
            case "track-list":
                tracks = value or []
                p.audio = [_track(t) for t in tracks if t.get("type") == "audio"]
                p.subs = [_track(t) for t in tracks if t.get("type") == "sub"]
        self._callbacks.changed(p)

    def _on_event(self, event: Any) -> None:
        if self._ended or self._terminated:
            return
        kind = event.event_id.value
        if kind == self._ids.END_FILE:
            reason = event.data.reason
            if reason in (self._end_file.EOF, self._end_file.ERROR):
                # The video is over (or could not play): the controller closes mpv.
                self._ended = True
                self._callbacks.ended(reason == self._end_file.EOF, self.rect())
        elif kind == self._ids.SHUTDOWN:
            # mpv's window was closed (its close button, Alt+F4).
            self._ended = True
            self._callbacks.ended(False, self._last_rect)


def _track(raw: dict[str, Any]) -> Track:
    return Track(
        id=int(raw.get("id", 0)),
        kind=str(raw.get("type")),
        lang=raw.get("lang"),
        title=raw.get("title"),
        selected=bool(raw.get("selected")),
        external=bool(raw.get("external")),
    )
