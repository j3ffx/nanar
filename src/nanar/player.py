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
from nanar.progress import Pick

ONLINE_TITLE = "OpenSubtitles"  # the title of the subtitles Nanar downloaded

# Night mode: loud scenes brought down and quiet lines up, for late evenings and thin walls.
NIGHT_FILTER = "lavfi=[dynaudnorm=f=250:g=15:p=0.6:m=8]"


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

    @property
    def label(self) -> str:
        """'Français (VFF)', 'Anglais', 'Piste 3'."""
        language = LANGUAGES.get((self.lang or "").lower(), self.lang)
        if language and self.title and self.title.casefold() != language.casefold():
            return f"{language} ({self.title})"
        return language or self.title or f"Piste {self.id}"

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "lang": self.lang,
            "title": self.title,
            "selected": self.selected,
            "external": self.external,
        }


# The languages films come in most, by their ISO 639 codes.
LANGUAGES = {
    code: name
    for codes, name in [
        (("fr", "fre", "fra", "fre-fr", "fr-fr"), "Français"),
        (("fr-ca", "fre-ca"), "Français (Québec)"),
        (("en", "eng"), "Anglais"),
        (("es", "spa"), "Espagnol"),
        (("de", "ger", "deu"), "Allemand"),
        (("it", "ita"), "Italien"),
        (("pt", "por"), "Portugais"),
        (("nl", "dut", "nld"), "Néerlandais"),
        (("ja", "jpn"), "Japonais"),
        (("ko", "kor"), "Coréen"),
        (("zh", "chi", "zho"), "Chinois"),
        (("ru", "rus"), "Russe"),
        (("ar", "ara"), "Arabe"),
    ]
    for code in codes
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
    night: bool = False
    chapter: int | None = None  # from 0
    chapters: int = 0
    audio: list[Track] = field(default_factory=list)
    subs: list[Track] = field(default_factory=list)


@dataclass(frozen=True)
class Start:
    source: str
    title: str
    start: float = 0.0
    rect: Rect | None = None
    fullscreen: bool = False
    # The length of a generated video (the demo's): its stream never says, and mpv's guess
    # grows as it plays.
    length: float | None = None
    # The tracks picked by hand for its saga or series, found again in this video.
    audio: Pick | None = None
    sub: Pick | None = None
    night: bool = False
    sub_files: tuple[str, ...] = ()  # subtitles downloaded for this video before


class Callbacks(Protocol):
    def changed(self, playback: Playback) -> None: ...

    def action(self, name: str) -> None:
        """A key pressed in mpv's window that Nanar handles (next, previous)."""

    def finished(self) -> None:
        """The video played to its end. mpv's window stays open on the last picture, for the
        next video or until the controller closes the session."""

    def ended(self, finished: bool, rect: Rect | None) -> None:
        """The video failed, or mpv's window was closed. Called once; the controller then
        closes the session."""


class Session(Protocol):
    def command(self, action: str, value: Any = None, *, osd: bool = False) -> None:
        """Runs a player action; with `osd`, says on screen what changed."""

    def load(self, start: Start) -> None:
        """Plays another video in the same window (the next episode: no window opens or
        closes). `start.rect` and `start.fullscreen` are ignored: the window stays as it is."""

    def message(self, text: str, seconds: float) -> None:
        """Shows a line of text over the video."""

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
    "b": "script-message nanar cycle_audio",  # through Nanar, which remembers the choice
    "v": "script-message nanar cycle_sub",
    "g": "add sub-delay -0.1",
    "h": "add sub-delay 0.1",
    "n": "script-message nanar next",
    "p": "script-message nanar previous",
    "s": "script-message nanar stop",
    "q": "script-message nanar stop",
}


def choose(tracks: list[Track], pick: Pick | None) -> int | str | None:
    """The track to select for a pick made in another video: "no" for no subtitles, None to
    leave mpv's own choice (nothing alike in this video)."""
    if pick is None:
        return None
    if pick.off:
        return "no"
    if pick.lang is None and pick.title is None:
        return tracks[pick.index].id if 0 <= pick.index < len(tracks) else None
    lang = (pick.lang or "").casefold()
    same_lang = [t for t in tracks if (t.lang or "").casefold() == lang]
    for track in same_lang:
        if track.title == pick.title:
            return track.id
    return same_lang[0].id if same_lang else None


def pick_of(tracks: list[Track], track_id: int | None) -> Pick | None:
    """What to remember of a track chosen by hand (None: an unknown track)."""
    if track_id is None:
        return Pick(off=True)
    for index, track in enumerate(tracks):
        if track.id == track_id:
            return Pick(track.lang, track.title, index)
    return None


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
        self._at_end = False  # `finished` was called for the current video
        self._terminated = False
        self._picked = False  # the start's picks were applied to this video's tracks
        self._last_rect: Rect | None = start.rect
        options: dict[str, Any] = {
            "title": f"{start.title} — Nanar",
            "force_window": "immediate",
            "keep_open": "yes",  # stays on the last picture: the controller decides what's next
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
            "af": NIGHT_FILTER if start.night else "",
        }
        if start.length is not None:
            # A generated stream (the demo's) can't seek: mpv's cache can, about half a minute
            # back, and forward by generating faster.
            options |= {"cache": "yes", "force_seekable": "yes", "demuxer_max_back_bytes": "300MiB"}
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
            "af",
            "chapter",
            "chapters",
            "track-list",
            "eof-reached",
        ):
            self._mpv.observe_property(name, self._on_property)
        self._mpv.register_event_callback(self._on_event)
        self._mpv.play(start.source)

    def load(self, start: Start) -> None:
        self._start = start
        self._at_end = False
        self._picked = False
        self._playback = Playback(
            fullscreen=self._playback.fullscreen,
            volume=self._playback.volume,
            night=self._playback.night,
        )
        self._mpv["title"] = f"{start.title} — Nanar"
        # Options of this file only. At the end of the previous one, mpv paused on its last
        # picture (keep-open): unpausing before loading would only pause it again.
        self._mpv.loadfile(start.source, "replace", start=f"{start.start:.3f}", pause="no")

    def message(self, text: str, seconds: float) -> None:
        self._mpv.command("show-text", text, int(seconds * 1000))

    def command(self, action: str, value: Any = None, *, osd: bool = False) -> None:
        m = self._mpv
        message: str | None = None
        match action:
            case "pause":
                m.pause = bool(value) if value is not None else not m.pause
                message = "Pause" if m.pause else "Lecture"
            case "seek" | "seek_to":
                m.command("seek", float(value), "relative" if action == "seek" else "absolute")
                if osd:
                    m.command("show-progress")
            case "volume":
                m.volume = max(0.0, min(130.0, float(value)))
                message = f"Volume : {round(m.volume)} %"
            case "mute":
                m.mute = bool(value) if value is not None else not m.mute
                message = "Son coupé" if m.mute else "Son rétabli"
            case "fullscreen":
                m.fullscreen = bool(value) if value is not None else not m.fullscreen
                if m.fullscreen:
                    self._to_front()
            case "audio":
                m.aid = int(value) if value is not None else "no"
                message = f"Audio : {self._selected('audio') or 'aucun'}"
            case "sub":
                m.sid = int(value) if value is not None else "no"
                message = f"Sous-titres : {self._selected('sub') or 'aucun'}"
            case "sub_delay":
                m.sub_delay = float(value)
                message = f"Décalage des sous-titres : {m.sub_delay:+.1f} s".replace(".", ",")
            case "sub_scale":
                m.sub_scale = max(0.3, min(3.0, float(value)))
                message = f"Taille des sous-titres : {round(m.sub_scale * 100)} %"
            case "sub_add":
                m.command("sub-add", str(value), "select", ONLINE_TITLE, "fr")
                message = f"Sous-titres : {ONLINE_TITLE}"
            case "night":
                on = bool(value) if value is not None else not self._playback.night
                m.af = NIGHT_FILTER if on else ""
                message = "Mode nuit" if on else "Mode nuit désactivé"
            case "chapter":
                count = int(m.chapters or 0)
                if count == 0:
                    return
                current = int(m.chapter or 0)
                target = max(0, min(count - 1, current + int(value)))
                m.chapter = target
                message = f"Chapitre {target + 1} / {count}"
            case _:
                raise ValueError(f"unknown player action {action!r}")
        if osd and message:
            m.command("show-text", message, 2000)

    def _selected(self, kind: str) -> str | None:
        for raw in self._mpv.track_list or []:
            if raw.get("type") == kind and raw.get("selected"):
                return _track(raw).label
        return None

    def rect(self) -> Rect | None:
        if sys.platform != "win32":
            return None
        from nanar.desktop import win32

        return win32.window_rect_of_process(os.getpid(), "mpv")

    def _place(self) -> None:
        """Gives mpv's window Nanar's icon, and lays it exactly over Nanar's. `geometry` only
        comes close: mpv reads its size as the inside of the window, and Windows adds the frame
        around it."""
        self._placed = True
        if sys.platform != "win32":
            return
        from nanar.desktop import win32

        hwnd = win32.find_window(os.getpid(), "mpv")
        if hwnd is None:
            return
        win32.set_icon(hwnd)
        target = self._start.rect
        if target is not None and not self._start.fullscreen:
            win32.place_window(hwnd, target)
        win32.bring_to_front(hwnd)  # started from the phone, it would open behind the others

    def _to_front(self) -> None:
        if sys.platform != "win32":
            return
        from nanar.desktop import win32

        if (hwnd := win32.find_window(os.getpid(), "mpv")) is not None:
            win32.bring_to_front(hwnd)

    def close(self) -> None:
        """Closes mpv. The controller asked for it: `ended` is not called."""
        if self._terminated:
            return
        self._terminated = True
        self._mpv.terminate()

    def _on_message(self, *args: bytes | str) -> None:
        words = [a.decode() if isinstance(a, bytes) else a for a in args]
        if words and words[0] in ("stop", "next", "previous", "cycle_audio", "cycle_sub"):
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
                known = self._start.length
                p.duration = known or (float(value) if value is not None else None)
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
            case "af":
                p.night = bool(value)
            case "chapter":
                p.chapter = int(value) if value is not None and value >= 0 else None
            case "chapters":
                p.chapters = int(value or 0)
            case "track-list":
                tracks = value or []
                p.audio = [_track(t) for t in tracks if t.get("type") == "audio"]
                p.subs = [_track(t) for t in tracks if t.get("type") == "sub"]
                if not self._picked and p.audio:
                    self._picked = True
                    self._apply_picks(p)
            case "eof-reached":
                if value:
                    self._reached_end()
                return
        self._callbacks.changed(p)

    def _apply_picks(self, p: Playback) -> None:
        """Adds the subtitles downloaded before, and selects the tracks picked by hand in
        another video of the saga or series."""
        subs = p.subs
        if self._start.sub_files:
            for path in self._start.sub_files:
                self._mpv.command("sub-add", path, "auto", ONLINE_TITLE, "fr")
            fresh = self._mpv.track_list or []
            subs = [_track(t) for t in fresh if t.get("type") == "sub"]
        audio = choose(p.audio, self._start.audio)
        sub = choose(subs, self._start.sub)
        if audio is not None:
            self._mpv["aid"] = audio
        if sub is not None:
            self._mpv["sid"] = sub

    def _reached_end(self) -> None:
        if self._at_end or self._ended or self._terminated:
            return
        self._at_end = True
        self._callbacks.finished()

    def _on_event(self, event: Any) -> None:
        if self._ended or self._terminated:
            return
        kind = event.event_id.value
        if kind == self._ids.END_FILE:
            reason = event.data.reason
            if reason == self._end_file.EOF:
                # keep-open holds most videos on their last picture; streams end this way.
                self._reached_end()
            elif reason == self._end_file.ERROR:
                # The video could not play: the controller closes mpv.
                self._ended = True
                self._callbacks.ended(False, self.rect())
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
