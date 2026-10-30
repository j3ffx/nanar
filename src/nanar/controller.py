"""The single place where Nanar's state changes: what is playing, the window, the library.

The API (phones, the TV page) and mpv's window (keys, end of file) both act through here. Every
change is announced to the listeners with the new state, which they forward to the pages.
mpv calls back from its own event thread, and closing mpv waits for that thread to finish: a
callback that waited for the controller's lock while the lock's holder closed mpv would never
return. So callbacks never wait: what they report runs on the controller's worker thread.
"""

import contextlib
import copy
import dataclasses
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

from nanar import demo
from nanar.config import Settings
from nanar.library import Library, Video, recent
from nanar.online import OnlineError, OpenSubtitles, Tmdb
from nanar.player import ONLINE_TITLE, Playback, Rect, Session, SessionFactory, Start, pick_of
from nanar.progress import Pick, Progress, to_continue

if TYPE_CHECKING:
    from nanar.metadata import Metadata
    from nanar.previews import Previews
    from nanar.subtitles import Subtitles
    from nanar.thumbnails import Thumbnails
    from nanar.updates import Updates

Listener = Callable[[dict[str, Any]], None]

PLAYER_ACTIONS = frozenset(
    {
        "pause",
        "seek",
        "seek_to",
        "volume",
        "mute",
        "audio",
        "sub",
        "sub_delay",
        "sub_scale",
        "chapter",
    }
)
UP_NEXT_SECONDS = 10  # the countdown before the next episode
TICK = 1.0  # one second of that countdown (shorter in tests)
SAVE_EVERY = 10.0  # seconds of playback between two saves of where a video is
NO_FILTER: dict[str, Any] = {"query": "", "kind": "all", "unwatched": False}
MINUTE = 60.0  # one minute of the sleep timer (shorter in tests)
SLEEP_WARNING = 60.0  # seconds of notice on screen before the sleep timer stops the video
SLEEP_MAX_MINUTES = 240


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
        previews: "Previews | None" = None,
        demo: bool = False,
    ) -> None:
        self.library = library
        self.settings = settings
        self.window: WindowHost = window or NoWindow()
        self.progress = progress or Progress(None)
        self.thumbnails = thumbnails
        self.previews = previews
        self.metadata: Metadata | None = None
        self.subtitles: Subtitles | None = None
        self.updates: Updates | None = None
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
        self._view: dict[str, Any] = {"path": "/", "focus": None, "filter": NO_FILTER, "seq": 0}
        self._offer_integration = False
        self._night = False  # for this run: a quieter evening is not every evening
        self._sleep: str | None = None  # "end" (of this video) or "timer"
        self._sleep_at = 0.0  # when the timer stops the video (time.monotonic)
        self._sleep_timer: threading.Timer | None = None
        self._sleep_seq = 0  # tells a cancelled timer's late call from the current one
        self._hotspot: dict[str, Any] = {"available": False, "on": False, "ssid": None}

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
                    "chapter": p.chapter,
                    "chapters": p.chapters,
                    "audio": [t.to_json() for t in p.audio],
                    "subs": [t.to_json() for t in p.subs],
                    "hasNext": self.library.neighbour(self._video.id, 1) is not None,
                    "hasPrevious": self.library.neighbour(self._video.id, -1) is not None,
                }
            up_next = None
            if self._up_next is not None:
                up_next = {"video": self._up_next.to_json(), "seconds": self._up_next_seconds}
            sleep: dict[str, Any] | None = None
            if self._sleep == "end":
                sleep = {"kind": "end"}
            elif self._sleep == "timer":
                remaining = max(0, round(self._sleep_at - time.monotonic()))
                sleep = {"kind": "timer", "remaining": remaining}
            return {
                "folder": self.library.root,
                "demo": self._demo,
                "fullscreen": self.settings.fullscreen,
                "phones": self._phones,
                "libraryVersion": self._library_version,
                "playing": playing,
                "upNext": up_next,
                "night": self._night,
                "sleep": sleep,
                "hotspot": dict(self._hotspot),
                "updates": self.updates.state() if self.updates else None,
                "online": {
                    "posters": bool(self.metadata and self.metadata.enabled),
                    "subtitles": bool(self.subtitles and self.subtitles.enabled),
                },
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
                info = self.metadata.of_group(self.library, group_id) if self.metadata else None
                data["groups"][group_id]["overview"] = (info or {}).get("overview") or None
            for video in self.library.videos.values():
                data["videos"][video.id]["thumb"] = self._thumb_url("v", video.id)
                info = self.metadata.of_video(self.library, video) if self.metadata else None
                data["videos"][video.id]["overview"] = (info or {}).get("overview") or None
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
            data["continue"] = to_continue(self.library, saved)
            data["recent"] = [
                {"kind": kind, "id": ident}
                for kind, ident in recent(self.library, time.time())
                if kind == "group" or not _watched(saved, self.library.videos[ident].path)
            ]
            return data

    def thumbnail(self, kind: str, ident: str) -> Path | None:
        """The picture of a video ("v") or of a saga or series ("g"), if there is one."""
        if self.thumbnails is None:
            return None
        if kind == "g":
            return self.thumbnails.of_group(self.library, ident, self._online_poster)
        video = self.library.videos.get(ident)
        return self.thumbnails.of_video(self.library, video, self._online_poster) if video else None

    def _online_poster(self, kind: str, ident: str) -> Path | None:
        """TMDb's poster, when it is asked (after the user's own, before a frame)."""
        if self.metadata is None:
            return None
        if kind == "g":
            return self.metadata.poster(self.metadata.of_group(self.library, ident))
        video = self.library.videos.get(ident)
        return self.metadata.poster(self.metadata.of_video(self.library, video)) if video else None

    def preview(self, video_id: str, at: float) -> Path | None:
        """A frame of the video playing, near `at` seconds: the phone's progress bar shows it
        while the finger drags."""
        with self._lock:
            if self._video is None or self._video.id != video_id:
                raise CommandError("nothing_playing")
            source = self._source_of(self._video)
        # Out of the lock: grabbing takes a moment, and the state must not wait for it.
        return self.previews.frame(source, at) if self.previews else None

    def _thumb_url(self, kind: str, ident: str) -> str | None:
        path = self.thumbnail(kind, ident)
        if path is None:
            return None
        # The file's age in the URL: a new picture is a new address, and caches stay right.
        return f"/api/thumb/{kind}/{ident}?v={int(path.stat().st_mtime)}"

    def set_view(self, path: str, focus: str | None, filter: dict[str, Any] | None = None) -> None:
        """What a phone is looking at in the library (its page, the item picked, what it
        searches): the TV page follows it, so that the whole room sees the choice being made."""
        if not path.startswith("/") or len(path) > 200:
            raise CommandError("bad_value")
        with self._lock:
            self._view = {
                "path": path,
                "focus": focus,
                "filter": dict(filter or NO_FILTER),
                "seq": self._view["seq"] + 1,
            }
        self._announce()

    def set_integration_offer(self, offer: bool) -> None:
        """Whether the TV page asks to add Nanar to the Start menu and the right-click menu."""
        with self._lock:
            self._offer_integration = offer
        self._announce()

    def set_hotspot(self, public: dict[str, Any]) -> None:
        """Whether the PC's own Wi-Fi is open (mode hôtel), for the TV page."""
        with self._lock:
            if public == self._hotspot:
                return
            self._hotspot = dict(public)
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
        if self.metadata is not None:
            self.metadata.schedule(library)
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
            picks = self.progress.picks(self.library.root, _owner(video))
            begin = Start(
                source=self._source_of(video),
                title=video.title,
                start=start,
                rect=None,
                fullscreen=self.settings.fullscreen,
                length=float(demo.SECONDS) if "://" in video.path else None,
                audio=picks.get("audio"),
                sub=picks.get("sub"),
                night=self._night,
                sub_files=tuple(
                    str(p)
                    for p in (
                        self.subtitles.saved(self.library.root, video) if self.subtitles else []
                    )
                ),
            )
            wants_online = (
                (pick := picks.get("sub")) is not None
                and pick.title == ONLINE_TITLE
                and not begin.sub_files
                and self.subtitles is not None
                and self.subtitles.enabled
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
                    dataclasses.replace(begin, rect=rect),
                    self.settings,
                    _SessionCallbacks(self, self._generation),
                )
                self.window.hide()
        self._announce()
        if wants_online:  # the series plays with downloaded subtitles: this episode too
            threading.Thread(
                target=self._quietly_find_subtitles, args=(video.id,), daemon=True
            ).start()

    def find_subtitles(self) -> None:
        """Downloads French subtitles for the video playing, and shows them. Raises
        CommandError with OnlineError's codes (or "nothing_playing")."""
        with self._lock:
            if self._video is None or self.subtitles is None:
                raise CommandError("nothing_playing" if self._video is None else "online_off")
            video, root = self._video, self.library.root
            source = None if "://" in video.path else Path(self._source_of(video))
        try:
            found = self.subtitles.find(root, video, source)  # out of the lock: seconds
        except OnlineError as error:
            raise CommandError(error.code) from error
        with self._lock:
            if self._video is not video or self._session is None:
                return  # another video by now
            self._session.command("sub_add", str(found), osd=True)
            self.progress.pick(root, _owner(video), "sub", Pick("fr", ONLINE_TITLE))

    def _quietly_find_subtitles(self, video_id: str) -> None:
        with self._lock:
            if self._video is None or self._video.id != video_id:
                return
        with contextlib.suppress(CommandError):
            self.find_subtitles()

    def set_check_updates(self, enabled: bool) -> None:
        """Looks for new versions on GitHub (once a day), or stops."""
        with self._lock:
            self.settings.check_updates = enabled
            if not enabled and self.updates is not None:
                self.updates.available = None
            self._save_settings()
        if enabled and self.updates is not None:
            self.updates.poke()
        self._announce()

    def set_online(self, *, tmdb: str | None = None, opensubtitles: str | None = None) -> None:
        """New keys ("" takes one away): each is tried first. Raises CommandError("bad_key"),
        ("offline")."""
        try:
            if tmdb:
                Tmdb(tmdb).check()
            if opensubtitles:
                OpenSubtitles(opensubtitles).check()
        except OnlineError as error:
            raise CommandError(error.code) from error
        with self._lock:
            if tmdb is not None:
                self.settings.tmdb_key = tmdb.strip()
                if self.metadata is not None:
                    self.metadata.configure(self.settings.tmdb_key)
                    self.metadata.schedule(self.library)
            if opensubtitles is not None:
                self.settings.opensubtitles_key = opensubtitles.strip()
                if self.subtitles is not None:
                    self.subtitles.configure(self.settings.opensubtitles_key)
            self._save_settings()
            self._library_version += 1
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
        elif action == "night":
            self.set_night(None if value is None else bool(value), osd=osd)
        elif action == "sleep":
            self.set_sleep(value)
        elif action in ("cycle_audio", "cycle_sub"):
            self._cycle("audio" if action == "cycle_audio" else "sub")
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
                if action in ("audio", "sub"):
                    self._remember(action, value)
        else:
            raise CommandError("unknown_action")

    def _remember(self, kind: str, value: Any) -> None:
        """Keeps a track chosen by hand for the rest of the saga or series."""
        if self._video is None or self._playback is None:
            return
        tracks = self._playback.audio if kind == "audio" else self._playback.subs
        pick = pick_of(tracks, None if value is None else int(value))
        if pick is not None and not (kind == "audio" and pick.off):
            self.progress.pick(self.library.root, _owner(self._video), kind, pick)

    def _cycle(self, kind: str) -> None:
        """The next audio track, or subtitles (then none): mpv's B and V keys."""
        with self._lock:
            if self._playback is None:
                raise CommandError("nothing_playing")
            tracks = self._playback.audio if kind == "audio" else self._playback.subs
            choices: list[int | None] = [t.id for t in tracks]
            if kind == "sub":
                choices.append(None)
            if not choices:
                return
            current = next((t.id for t in tracks if t.selected), None)
            index = choices.index(current) if current in choices else -1
            self.command(kind, choices[(index + 1) % len(choices)], osd=True)

    def set_night(self, night: bool | None, *, osd: bool = False) -> None:
        """Night mode: loud scenes softer, quiet lines louder. It stays on for the next videos,
        until Nanar closes."""
        with self._lock:
            self._night = not self._night if night is None else night
            if self._session is not None:
                self._session.command("night", self._night, osd=osd)
        self._announce()

    def set_sleep(self, value: Any) -> None:
        """Stops the video later: at its end ("end"), or in `value` minutes; None cancels."""
        with self._lock:
            if value is not None and self._session is None:
                raise CommandError("nothing_playing")
            if value is not None and value != "end":
                if isinstance(value, bool) or not isinstance(value, int | float):
                    raise CommandError("bad_value")
                if not 1 <= value <= SLEEP_MAX_MINUTES:
                    raise CommandError("bad_value")
            self._cancel_sleep()
            if value == "end":
                self._sleep = "end"
            elif value is not None:
                seconds = float(value) * MINUTE
                self._sleep = "timer"
                self._sleep_at = time.monotonic() + seconds
                self._sleep_timer_in(max(0.0, seconds - SLEEP_WARNING), self._sleep_warn)
        self._announce()

    def _sleep_timer_in(self, seconds: float, then: Callable[[int], None]) -> None:
        seq = self._sleep_seq
        timer = threading.Timer(seconds, lambda: self._worker.submit(then, seq))
        timer.daemon = True
        self._sleep_timer = timer
        timer.start()

    def _sleep_warn(self, seq: int) -> None:
        with self._lock:
            if seq != self._sleep_seq or self._sleep != "timer":
                return
            if self._session is not None:
                with contextlib.suppress(Exception):
                    self._session.message("Nanar s’arrête dans une minute.", 5)
            self._sleep_timer_in(max(0.0, self._sleep_at - time.monotonic()), self._sleep_now)

    def _sleep_now(self, seq: int) -> None:
        with self._lock:
            if seq != self._sleep_seq or self._sleep != "timer":
                return
        self.stop()

    def _cancel_sleep(self) -> None:
        self._sleep_seq += 1
        if self._sleep_timer is not None:
            self._sleep_timer.cancel()
            self._sleep_timer = None
        self._sleep = None

    def mark(self, video_id: str, action: str) -> None:
        """From a phone: "watched" (seen elsewhere), "unwatched" (to see again), "dismiss" (out
        of "À suivre")."""
        with self._lock:
            video = self.library.videos.get(video_id)
            if video is None:
                raise CommandError("unknown_video")
            root = self.library.root
            if action == "dismiss":
                # A saga's or a series' place in the row comes from its latest video played.
                group = self.library.groups.get(video.group) if video.group else None
                paths = [self.library.videos[i].path for i in group.videos] if group else []
                saved = self.progress.of_root(root)
                played = [(saved[p].updated, p) for p in paths if p in saved]
                self.progress.hide(root, max(played)[1] if played else video.path)
            elif action in ("watched", "unwatched"):
                self.progress.mark(root, video.path, watched=action == "watched")
            else:
                raise CommandError("bad_value")
            self._library_version += 1
        self._announce()

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
            self._cancel_sleep()
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
                if following is None or self._sleep == "end":
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
        self._cancel_sleep()
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


def _owner(video: Video) -> str:
    """Whose tracks a video plays with: its saga or series, or the film itself."""
    return video.group or video.path


def _watched(saved: dict[str, Any], path: str) -> bool:
    entry = saved.get(path)
    return bool(entry and entry.watched)


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
