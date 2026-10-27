"""The single place where Nanar's state changes: what is playing, the window, the library.

The API (phones, the TV page) and mpv's window (keys, end of file) both act through here. Every
change is announced to the listeners with the new state, which they forward to the pages.
mpv calls back from its own event thread, and closing mpv waits for that thread to finish: a
callback that waited for the controller's lock while the lock's holder closed mpv would never
return. So callbacks never wait: what they report runs on the controller's worker thread.
"""

import contextlib
import copy
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Protocol

from nanar.config import Settings
from nanar.library import Library, Video
from nanar.player import Playback, Rect, Session, SessionFactory, Start

Listener = Callable[[dict[str, Any]], None]

PLAYER_ACTIONS = frozenset(
    {"pause", "seek", "seek_to", "volume", "mute", "audio", "sub", "sub_delay", "sub_scale"}
)


class WindowHost(Protocol):
    """Nanar's own window (the TV page), which hides while mpv plays."""

    def rect(self) -> Rect | None: ...

    def hide(self) -> None: ...

    def show(self, rect: Rect | None, fullscreen: bool) -> None: ...

    def set_fullscreen(self, fullscreen: bool) -> None: ...


class NoWindow:
    """No window at all (tests, or `nanar --headless` to drive mpv from the API alone)."""

    def rect(self) -> Rect | None:
        return None

    def hide(self) -> None:
        pass

    def show(self, rect: Rect | None, fullscreen: bool) -> None:
        pass

    def set_fullscreen(self, fullscreen: bool) -> None:
        pass


class CommandError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class Controller:
    def __init__(
        self,
        library: Library,
        settings: Settings,
        settings_path: Path | None,
        sessions: SessionFactory,
        window: WindowHost | None = None,
        *,
        demo: bool = False,
    ) -> None:
        self.library = library
        self.settings = settings
        self.window: WindowHost = window or NoWindow()
        self._settings_path = settings_path
        self._sessions = sessions
        self._demo = demo
        self._lock = threading.RLock()
        self._worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix="nanar-controller")
        self._listeners: list[Listener] = []
        self._session: Session | None = None
        self._video: Video | None = None
        self._playback: Playback | None = None
        self._generation = 0  # tells a finished session's late callbacks from the current one's
        self._phones = 0

    # Listeners ---------------------------------------------------------------------------------

    def subscribe(self, listener: Listener) -> Callable[[], None]:
        with self._lock:
            self._listeners.append(listener)
        return lambda: self._unsubscribe(listener)

    def _unsubscribe(self, listener: Listener) -> None:
        with self._lock:
            if listener in self._listeners:
                self._listeners.remove(listener)

    def _announce(self) -> None:
        state = self.state()
        for listener in list(self._listeners):
            listener(state)

    # State -------------------------------------------------------------------------------------

    def state(self) -> dict[str, Any]:
        with self._lock:
            playing = None
            if self._video is not None:
                p = self._playback or Playback()
                playing = {
                    "video": self._video.to_json(),
                    "position": p.position,
                    "duration": p.duration,
                    "paused": p.paused,
                    "volume": p.volume,
                    "muted": p.muted,
                    "subDelay": p.sub_delay,
                    "subScale": p.sub_scale,
                    "audio": [t.to_json() for t in p.audio],
                    "subs": [t.to_json() for t in p.subs],
                    "hasNext": self.library.neighbour(self._video.id, 1) is not None,
                    "hasPrevious": self.library.neighbour(self._video.id, -1) is not None,
                }
            return {
                "folder": self.library.root,
                "demo": self._demo,
                "fullscreen": self.settings.fullscreen,
                "phones": self._phones,
                "playing": playing,
            }

    def set_phones(self, count: int) -> None:
        """How many phones are connected (the TV page shows it)."""
        with self._lock:
            if count == self._phones:
                return
            self._phones = count
        self._announce()

    # Actions -----------------------------------------------------------------------------------

    def play(self, video_id: str, start: float = 0.0) -> None:
        with self._lock:
            video = self.library.videos.get(video_id)
            if video is None:
                raise CommandError("unknown_video")
            rect = self._close_session() or self.window.rect()
            self._generation += 1
            generation = self._generation
            self._video = video
            self._playback = Playback(fullscreen=self.settings.fullscreen)
            source = self._source_of(video)
            self._session = self._sessions(
                Start(
                    source=source,
                    title=video.title,
                    start=start,
                    rect=rect,
                    fullscreen=self.settings.fullscreen,
                ),
                self.settings,
                _SessionCallbacks(self, generation),
            )
            self.window.hide()
        self._announce()

    def command(self, action: str, value: Any = None, *, osd: bool = False) -> None:
        """Runs an action. `osd`: say on screen what happened (the phone's actions, as nobody
        sees the phone from the sofa); mpv already does for its own keys."""
        if action == "stop":
            self.stop()
        elif action in ("next", "previous"):
            self.skip(1 if action == "next" else -1)
        elif action == "fullscreen":
            self.set_fullscreen(None if value is None else bool(value))
        elif action in PLAYER_ACTIONS:
            with self._lock:
                if self._session is None:
                    raise CommandError("nothing_playing")
                try:
                    self._session.command(action, value, osd=osd)
                except (TypeError, ValueError) as error:
                    raise CommandError("bad_value") from error
        else:
            raise CommandError("unknown_action")

    def stop(self) -> None:
        with self._lock:
            if self._session is None:
                return
            rect = self._close_session()
            self._back_to_nanar(rect)
        self._announce()

    def skip(self, step: int) -> None:
        with self._lock:
            if self._video is None:
                raise CommandError("nothing_playing")
            target = self.library.neighbour(self._video.id, step)
            if target is None:
                raise CommandError("no_neighbour")
        self.play(target.id)

    def set_fullscreen(self, fullscreen: bool | None) -> None:
        with self._lock:
            value = not self.settings.fullscreen if fullscreen is None else fullscreen
            self.settings.fullscreen = value
            self._save_settings()
            if self._session is not None:
                self._session.command("fullscreen", value)
            else:
                self.window.set_fullscreen(value)
        self._announce()

    def shutdown(self) -> None:
        with self._lock:
            self._close_session()
        self._worker.shutdown(wait=False)

    # From the session (mpv's threads) ----------------------------------------------------------

    def _session_changed(self, generation: int, playback: Playback) -> None:
        def run() -> None:
            with self._lock:
                if generation != self._generation or self._session is None:
                    return
                self._playback = playback
                if playback.fullscreen != self.settings.fullscreen:
                    self.settings.fullscreen = playback.fullscreen
                    self._save_settings()
            self._announce()

        self._worker.submit(run)

    def _session_action(self, generation: int, name: str) -> None:
        def run() -> None:
            if generation != self._generation:
                return
            with contextlib.suppress(CommandError):  # "next" on the last episode: nothing to do
                self.command(name)

        self._worker.submit(run)

    def _session_ended(self, generation: int, finished: bool, rect: Rect | None) -> None:
        def run() -> None:
            with self._lock:
                if generation != self._generation or self._session is None:
                    return
                self._close_session()
                self._back_to_nanar(rect)
            self._announce()

        self._worker.submit(run)

    # Helpers -----------------------------------------------------------------------------------

    def _close_session(self) -> Rect | None:
        """Closes mpv if it runs, and says where its window was."""
        session, self._session = self._session, None
        self._generation += 1
        if session is None:
            return None
        rect = session.rect()
        session.close()
        return rect

    def _back_to_nanar(self, rect: Rect | None) -> None:
        self._video = None
        self._playback = None
        self.window.show(rect, self.settings.fullscreen)

    def _source_of(self, video: Video) -> str:
        if "://" in video.path:
            return video.path  # the demo's generated videos
        return str(Path(self.library.root) / video.path)

    def _save_settings(self) -> None:
        if self._settings_path is not None:
            self.settings.save(self._settings_path)


class _SessionCallbacks:
    def __init__(self, controller: Controller, generation: int) -> None:
        self._controller = controller
        self._generation = generation

    def changed(self, playback: Playback) -> None:
        # A copy: mpv's thread keeps updating its own while the pages read this one.
        self._controller._session_changed(self._generation, copy.deepcopy(playback))

    def action(self, name: str) -> None:
        self._controller._session_action(self._generation, name)

    def ended(self, finished: bool, rect: Rect | None) -> None:
        self._controller._session_ended(self._generation, finished, rect)
