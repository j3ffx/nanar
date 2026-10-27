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
from typing import TYPE_CHECKING, Any, Protocol

from nanar import demo
from nanar.config import Settings
from nanar.library import Library, Video
from nanar.player import Playback, Rect, Session, SessionFactory, Start
from nanar.progress import Progress

if TYPE_CHECKING:
    from nanar.thumbnails import Thumbnails

Listener = Callable[[dict[str, Any]], None]

PLAYER_ACTIONS = frozenset(
    {"pause", "seek", "seek_to", "volume", "mute", "audio", "sub", "sub_delay", "sub_scale"}
)
UP_NEXT_SECONDS = 10  # the countdown before the next episode
TICK = 1.0  # one second of that countdown (shorter in tests)
SAVE_EVERY = 10.0  # seconds of playback between two saves of where a video is


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
        progress: Progress | None = None,
        thumbnails: "Thumbnails | None" = None,
        demo: bool = False,
    ) -> None:
        self.library = library
        self.settings = settings
        self.window: WindowHost = window or NoWindow()
        self.progress = progress or Progress(None)
        self.thumbnails = thumbnails
        self._settings_path = settings_path
        self._sessions = sessions
        self._demo = demo
        self._lock = threading.RLock()
        self._worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix="nanar-controller")
        self._listeners: list[Listener] = []
        self._session: Session | None = None
        self._video: Video | None = None
        self._playback: Playback | None = None
        self._saved_at = 0.0  # the position last saved for the current video
        self._generation = 0  # tells a finished session's late callbacks from the current one's
        self._phones = 0
        self._library_version = 0
        self._up_next: Video | None = None
        self._up_next_seconds = 0
        self._countdown: threading.Timer | None = None
        self._view: dict[str, Any] = {"path": "/", "focus": None, "seq": 0}
        self._offer_integration = False

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
            up_next = None
            if self._up_next is not None:
                up_next = {"video": self._up_next.to_json(), "seconds": self._up_next_seconds}
            return {
                "folder": self.library.root,
                "demo": self._demo,
                "fullscreen": self.settings.fullscreen,
                "phones": self._phones,
                "libraryVersion": self._library_version,
                "playing": playing,
                "upNext": up_next,
                "view": dict(self._view),
                "offerIntegration": self._offer_integration,
            }

    def library_json(self) -> dict[str, Any]:
        """The library for the pages, with where each video was left."""
        with self._lock:
            data = self.library.to_json()
            saved = self.progress.of_root(self.library.root)
            for group_id in self.library.groups:
                data["groups"][group_id]["thumb"] = self._thumb_url("g", group_id)
            for video in self.library.videos.values():
                data["videos"][video.id]["thumb"] = self._thumb_url("v", video.id)
                entry = saved.get(video.path)
                data["videos"][video.id]["progress"] = (
                    {
                        "position": entry.position,
                        "duration": entry.duration,
                        "watched": entry.watched,
                    }
                    if entry
                    else None
                )
            return data

    def thumbnail(self, kind: str, ident: str) -> Path | None:
        """The picture of a video ("v") or of a saga or series ("g"), if there is one."""
        if self.thumbnails is None:
            return None
        if kind == "g":
            return self.thumbnails.of_group(self.library, ident)
        video = self.library.videos.get(ident)
        return self.thumbnails.of_video(self.library, video) if video else None

    def _thumb_url(self, kind: str, ident: str) -> str | None:
        path = self.thumbnail(kind, ident)
        if path is None:
            return None
        # The file's age in the URL: a new picture is a new address, and caches stay right.
        return f"/api/thumb/{kind}/{ident}?v={int(path.stat().st_mtime)}"

    def set_view(self, path: str, focus: str | None) -> None:
        """What a phone is looking at in the library: the TV page follows it, so that the
        whole room sees the choice being made."""
        if not path.startswith("/") or len(path) > 200:
            raise CommandError("bad_value")
        with self._lock:
            self._view = {"path": path, "focus": focus, "seq": self._view["seq"] + 1}
        self._announce()

    def set_integration_offer(self, offer: bool) -> None:
        """Whether the TV page asks to add Nanar to the Start menu and the right-click menu."""
        with self._lock:
            self._offer_integration = offer
        self._announce()

    def set_phones(self, count: int) -> None:
        """How many phones are connected (the TV page shows it)."""
        with self._lock:
            if count == self._phones:
                return
            self._phones = count
        self._announce()

    def set_library(self, library: Library) -> None:
        """A new reading of the folder (files added or removed); what plays keeps playing."""
        with self._lock:
            self.library = library
            self._library_version += 1
        if self.thumbnails is not None:
            self.thumbnails.schedule(library)
        self._announce()

    def library_changed(self) -> None:
        """Something the library shows changed (thumbnails): the pages fetch it again."""
        with self._lock:
            self._library_version += 1
        self._announce()

    # Actions -----------------------------------------------------------------------------------

    def play(self, video_id: str, start: float | None = None) -> None:
        """Plays a video, from `start`, or where it was left when `start` is None."""
        with self._lock:
            video = self.library.videos.get(video_id)
            if video is None:
                raise CommandError("unknown_video")
            self._cancel_up_next()
            self._save_current(finished=False)
            if start is None:
                entry = self.progress.get(self.library.root, video.path)
                start = entry.resume_at() if entry else 0.0
            self._video = video
            self._saved_at = start
            begin = Start(
                source=self._source_of(video),
                title=video.title,
                start=start,
                rect=None,
                fullscreen=self.settings.fullscreen,
                length=float(demo.SECONDS) if "://" in video.path else None,
            )
            if self._session is not None:
                # The same window: no flicker between two episodes.
                self._playback = Playback(fullscreen=self.settings.fullscreen)
                self._session.load(begin)
            else:
                rect = self.window.rect()
                self._generation += 1
                self._playback = Playback(fullscreen=self.settings.fullscreen)
                self._session = self._sessions(
                    Start(
                        begin.source,
                        begin.title,
                        begin.start,
                        rect,
                        begin.fullscreen,
                        begin.length,
                    ),
                    self.settings,
                    _SessionCallbacks(self, self._generation),
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
                if self._up_next is not None and action == "pause":
                    self._cancel_up_next()  # "pause" during the countdown: stay here
                    self._announce_later()
                    return
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
            self._cancel_up_next()
            self._save_current(finished=False)
            rect = self._close_session()
            self._back_to_nanar(rect)
        self._announce()

    def skip(self, step: int) -> None:
        with self._lock:
            if self._video is None:
                raise CommandError("nothing_playing")
            target = self._up_next if step > 0 and self._up_next else None
            target = target or self.library.neighbour(self._video.id, step)
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
            self._cancel_up_next()
            self._save_current(finished=False)
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
                if abs(playback.position - self._saved_at) >= SAVE_EVERY:
                    self._save_current(finished=False)
            self._announce()

        self._worker.submit(run)

    def _session_action(self, generation: int, name: str) -> None:
        def run() -> None:
            if generation != self._generation:
                return
            with contextlib.suppress(CommandError):  # "next" on the last episode: nothing to do
                self.command(name)

        self._worker.submit(run)

    def _session_finished(self, generation: int) -> None:
        def run() -> None:
            with self._lock:
                if generation != self._generation or self._video is None:
                    return
                self._save_current(finished=True)
                self._library_version += 1
                following = self.library.neighbour(self._video.id, 1)
                if following is None:
                    rect = self._close_session()
                    self._back_to_nanar(rect)
                else:
                    self._up_next = following
                    self._up_next_seconds = UP_NEXT_SECONDS
                    self._tick(generation)
            self._announce()

        self._worker.submit(run)

    def _session_ended(self, generation: int, rect: Rect | None) -> None:
        def run() -> None:
            with self._lock:
                if generation != self._generation or self._session is None:
                    return
                self._cancel_up_next()
                self._save_current(finished=False)
                self._close_session()
                self._back_to_nanar(rect)
            self._announce()

        self._worker.submit(run)

    # The countdown before the next episode -----------------------------------------------------

    def _tick(self, generation: int) -> None:
        """Shows the countdown, then plays the next video when it reaches zero."""
        following = self._up_next
        if following is None or self._session is None:
            return
        if self._up_next_seconds <= 0:
            self._worker.submit(self._play_up_next, generation, following)
            return
        with contextlib.suppress(Exception):  # a message that can't show is no reason to stop
            self._session.message(
                f"À suivre : {_label(following)} — dans {self._up_next_seconds} s\n"
                "N : tout de suite · S : arrêter",
                1.2,
            )
        timer = threading.Timer(TICK, lambda: self._worker.submit(self._step, generation))
        timer.daemon = True
        self._countdown = timer
        timer.start()

    def _step(self, generation: int) -> None:
        with self._lock:
            if generation != self._generation or self._up_next is None:
                return
            self._up_next_seconds -= 1
            self._tick(generation)
        self._announce()

    def _play_up_next(self, generation: int, following: Video) -> None:
        with self._lock:
            if generation != self._generation or self._up_next is not following:
                return
        with contextlib.suppress(CommandError):
            self.play(following.id, start=0.0)

    def _cancel_up_next(self) -> None:
        if self._countdown is not None:
            self._countdown.cancel()
            self._countdown = None
        self._up_next = None
        self._up_next_seconds = 0

    def _announce_later(self) -> None:
        self._worker.submit(self._announce)

    # Helpers -----------------------------------------------------------------------------------

    def _save_current(self, *, finished: bool) -> None:
        if self._video is None or self._playback is None:
            return
        p = self._playback
        if not finished and p.position <= 0 and p.duration is None:
            return  # nothing played yet: keep what was saved before
        self.progress.save(
            self.library.root, self._video.path, p.position, p.duration, finished=finished
        )
        self._saved_at = p.position

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
        self._library_version += 1  # what was watched shows in the library
        self.window.show(rect, self.settings.fullscreen)

    def _source_of(self, video: Video) -> str:
        if "://" in video.path:
            return video.path  # the demo's generated videos
        return str(Path(self.library.root) / video.path)

    def _save_settings(self) -> None:
        if self._settings_path is not None:
            self.settings.save(self._settings_path)


def _label(video: Video) -> str:
    if video.kind == "episode" and video.episode is not None:
        code = f"S{video.season or 0:02d}E{video.episode:02d}"
        return f"{code} {video.episode_title}" if video.episode_title else code
    return video.title


class _SessionCallbacks:
    def __init__(self, controller: Controller, generation: int) -> None:
        self._controller = controller
        self._generation = generation

    def changed(self, playback: Playback) -> None:
        # A copy: mpv's thread keeps updating its own while the pages read this one.
        self._controller._session_changed(self._generation, copy.deepcopy(playback))

    def action(self, name: str) -> None:
        self._controller._session_action(self._generation, name)

    def finished(self) -> None:
        self._controller._session_finished(self._generation)

    def ended(self, finished: bool, rect: Rect | None) -> None:
        self._controller._session_ended(self._generation, rect)
