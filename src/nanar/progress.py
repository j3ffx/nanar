"""Where each video was left, and which ones were watched (SQLite, in the user's data directory).

Videos are known by their library folder and their path inside it: a rescan, or the same disk
mounted on another letter with the folder opened again, keeps their history.
"""

import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from nanar.library import Library

WATCHED_RATIO = 0.9  # past this, a video counts as watched (the credits are not worth waiting for)
RESUME_MIN = 60.0  # less than a minute in: start over rather than resume
RESUME_REWIND = 5.0  # resume a few seconds earlier, to find the thread again
CONTINUE_MAX = 12  # videos in "À suivre"


@dataclass(frozen=True)
class Entry:
    position: float
    duration: float | None
    watched: bool
    updated: float

    @property
    def in_progress(self) -> bool:
        """Left in the middle: worth resuming."""
        return self.position >= RESUME_MIN

    def resume_at(self) -> float:
        """Where to start this video: where it was left, or from the start."""
        if not self.in_progress:
            return 0.0
        return max(0.0, self.position - RESUME_REWIND)


class Progress:
    def __init__(self, path: Path | None) -> None:
        """`path` None keeps everything in memory (tests)."""
        self._db = sqlite3.connect(str(path) if path else ":memory:", check_same_thread=False)
        self._lock = threading.Lock()
        with self._lock, self._db:
            self._db.execute(
                "CREATE TABLE IF NOT EXISTS progress ("
                " root TEXT NOT NULL, path TEXT NOT NULL,"
                " position REAL NOT NULL, duration REAL, watched INTEGER NOT NULL,"
                " updated REAL NOT NULL, PRIMARY KEY (root, path))"
            )

    def get(self, root: str, path: str) -> Entry | None:
        with self._lock:
            row = self._db.execute(
                "SELECT position, duration, watched, updated FROM progress"
                " WHERE root = ? AND path = ?",
                (root, path),
            ).fetchone()
        return Entry(row[0], row[1], bool(row[2]), row[3]) if row else None

    def of_root(self, root: str) -> dict[str, Entry]:
        with self._lock:
            rows = self._db.execute(
                "SELECT path, position, duration, watched, updated FROM progress WHERE root = ?",
                (root,),
            ).fetchall()
        return {r[0]: Entry(r[1], r[2], bool(r[3]), r[4]) for r in rows}

    def save(
        self, root: str, path: str, position: float, duration: float | None, *, finished: bool
    ) -> Entry:
        """Records where a video is. Past 90 % (or at its end) it is watched and starts over next
        time; watched stays watched when it is seen again."""
        done = finished or bool(duration and position >= duration * WATCHED_RATIO)
        previous = self.get(root, path)
        watched = done or bool(previous and previous.watched)
        entry = Entry(0.0 if done else position, duration, watched, time.time())
        with self._lock, self._db:
            self._db.execute(
                "INSERT INTO progress (root, path, position, duration, watched, updated)"
                " VALUES (?, ?, ?, ?, ?, ?)"
                " ON CONFLICT (root, path) DO UPDATE SET position = excluded.position,"
                " duration = excluded.duration, watched = excluded.watched,"
                " updated = excluded.updated",
                (root, path, entry.position, duration, int(watched), entry.updated),
            )
        return entry

    def close(self) -> None:
        with self._lock:
            self._db.close()


def to_continue(library: Library, saved: dict[str, Entry]) -> list[str]:
    """The "À suivre" row: the videos left in the middle and, in a saga or a series, the one
    after the last watched; the most recent first. A saga or a series gives one video only, from
    where it was last left: the next episode once one ends, the episode itself while under way."""
    found: list[tuple[float, str]] = []
    for video in library.videos.values():
        entry = saved.get(video.path)
        if video.group is None and entry is not None and entry.in_progress:
            found.append((entry.updated, video.id))
    for group in library.groups.values():
        seen = [
            (entry.updated, index)
            for index, ident in enumerate(group.videos)
            if (entry := saved.get(library.videos[ident].path)) is not None
        ]
        if not seen:
            continue
        updated, index = max(seen)
        last = saved[library.videos[group.videos[index]].path]
        if last.in_progress:
            found.append((updated, group.videos[index]))
            continue
        if not last.watched:
            continue  # barely started: nothing to resume, nothing finished
        for following in group.videos[index + 1 :]:
            entry = saved.get(library.videos[following].path)
            if entry is None or not entry.watched:
                found.append((updated, following))
                break
    return [ident for _, ident in sorted(found, reverse=True)[:CONTINUE_MAX]]
