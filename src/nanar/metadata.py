"""Posters and summaries from TMDb, when the user gave a key (`online.py` says what is sent).

Each film and each series is looked up once, in the background, one after the other; what was
found (or not) is kept in the data directory, with the posters, and asked again only after a
month when nothing was found. Without a key, nothing is asked and nothing found is shown.
"""

import json
import logging
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from nanar.library import Library, Video, _fold
from nanar.online import OnlineError, Tmdb

RETRY_MISSES_AFTER = 30 * 86400
PAUSE = 0.25  # seconds between two lookups: TMDb is free, be kind to it
ANNOUNCE_EVERY = 5  # lookups between two announcements to the pages

log = logging.getLogger(__name__)


def _key(kind: str, title: str, year: int | None) -> str:
    return f"{kind}|{_fold(title).strip()}|{year or ''}"


class Metadata:
    def __init__(
        self,
        directory: Path,
        *,
        on_ready: Callable[[], None],
        make: Callable[[str], Tmdb] = Tmdb,
    ) -> None:
        self._directory = directory
        self._posters = directory / "posters"
        self._file = directory / "tmdb.json"
        self._on_ready = on_ready
        self._make = make
        self._lock = threading.Lock()
        self._tmdb: Tmdb | None = None
        self._cache: dict[str, dict[str, Any]] = self._load()
        self._pending: list[tuple[str, str, int | None]] = []
        self._wake = threading.Event()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self.error: str | None = None  # why the last lookups stopped ("bad_key", "offline")

    @property
    def enabled(self) -> bool:
        return self._tmdb is not None

    def configure(self, key: str) -> None:
        """Starts (a key) or stops (none) asking TMDb."""
        with self._lock:
            self._tmdb = self._make(key) if key.strip() else None
            self.error = None

    # What the pages show ------------------------------------------------------------------------

    def of_video(self, library: Library, video: Video) -> dict[str, Any] | None:
        """A film's poster and summary (an episode's come with its series)."""
        if video.kind == "episode":
            return None
        return self._found(_key("movie", video.title, video.year))

    def of_group(self, library: Library, group_id: str) -> dict[str, Any] | None:
        """A series' poster and summary; a saga's poster is its first film's."""
        group = library.groups.get(group_id)
        if group is None:
            return None
        if group.kind == "series":
            return self._found(_key("tv", group.title, None))
        first = self.of_video(library, library.videos[group.videos[0]])
        return {"poster": first.get("poster"), "overview": ""} if first else None

    def poster(self, info: dict[str, Any] | None) -> Path | None:
        name = info.get("poster") if info else None
        path = self._posters / str(name) if name else None
        return path if path is not None and path.is_file() else None

    def _found(self, key: str) -> dict[str, Any] | None:
        if self._tmdb is None:
            return None
        entry = self._cache.get(key)
        return entry if entry and not entry.get("miss") else None

    # Looking them up ---------------------------------------------------------------------------

    def schedule(self, library: Library) -> None:
        """Looks up, in the background, what this library lacks."""
        if self._tmdb is None:
            return
        wanted: dict[str, tuple[str, str, int | None]] = {}
        for video in library.videos.values():
            if video.kind == "movie":
                wanted[_key("movie", video.title, video.year)] = ("movie", video.title, video.year)
        for group in library.groups.values():
            if group.kind == "series":
                wanted[_key("tv", group.title, None)] = ("tv", group.title, None)
        now = time.time()
        with self._lock:
            self._pending = [
                lookup
                for key, lookup in wanted.items()
                if key not in self._cache
                or (
                    self._cache[key].get("miss")
                    and now - self._cache[key]["at"] > RETRY_MISSES_AFTER
                )
            ]
        self._wake.set()
        if self._thread is None:
            self._thread = threading.Thread(target=self._work, name="nanar-tmdb", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()

    def _work(self) -> None:
        done = 0
        while not self._stop.is_set():
            with self._lock:
                lookup = self._pending.pop(0) if self._pending else None
                tmdb = self._tmdb
            if lookup is None or tmdb is None:
                if done:
                    self._save()
                    self._on_ready()
                    done = 0
                self._wake.wait()
                self._wake.clear()
                continue
            try:
                self._look_up(tmdb, *lookup)
            except OnlineError as error:
                log.warning("TMDb: %s", error.code)
                with self._lock:
                    self.error = error.code
                    self._pending.clear()  # until the next reading of the folder, or a new key
                continue
            except Exception:  # one odd answer is no reason to stop the others
                log.exception("TMDb lookup failed")
            done += 1
            if done % ANNOUNCE_EVERY == 0:
                self._save()
                self._on_ready()
            self._stop.wait(PAUSE)

    def _look_up(self, tmdb: Tmdb, kind: str, title: str, year: int | None) -> None:
        info = tmdb.search(kind, title, year)
        entry: dict[str, Any] = {"at": time.time()}
        if info is None:
            entry["miss"] = True
        else:
            entry |= {"id": info.tmdb_id, "overview": info.overview, "poster": None}
            if info.poster:
                name = f"{kind}-{info.tmdb_id}.jpg"
                self._posters.mkdir(parents=True, exist_ok=True)
                target = self._posters / name
                if not target.is_file():
                    target.with_suffix(".tmp").write_bytes(tmdb.poster(info.poster))
                    target.with_suffix(".tmp").replace(target)
                entry["poster"] = name
        with self._lock:
            self._cache[_key(kind, title, year)] = entry

    def _load(self) -> dict[str, dict[str, Any]]:
        try:
            data = json.loads(self._file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def _save(self) -> None:
        with self._lock:
            text = json.dumps(self._cache, ensure_ascii=False)
        self._directory.mkdir(parents=True, exist_ok=True)
        tmp = self._file.with_suffix(".tmp")
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(self._file)
