"""Where each video was left, and which ones were watched (SQLite, in the user's data directory).

Videos are known by their library folder and their path inside it: a rescan, or the same disk
mounted on another letter with the folder opened again, keeps their history. The audio and the
subtitles picked are kept the same way, for a whole saga or series (or a film on its own).
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
class Pick:
    """A track chosen by hand: found again in the next episode by its language and title, or by
    its rank when it has neither (the demo's). `off`: no subtitles at all."""

    lang: str | None = None
    title: str | None = None
    index: int = 0
    off: bool = False


@dataclass(frozen=True)
class Entry:
    position: float
    duration: float | None
    watched: bool
    updated: float
    hidden: bool = False  # taken out of "À suivre" (until it is played again)

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
            columns = {row[1] for row in self._db.execute("PRAGMA table_info(progress)")}
            if "hidden" not in columns:  # databases of 0.2
                self._db.execute(
                    "ALTER TABLE progress ADD COLUMN hidden INTEGER NOT NULL DEFAULT 0"
                )
            self._db.execute(
                "CREATE TABLE IF NOT EXISTS picks ("
                " root TEXT NOT NULL, owner TEXT NOT NULL, kind TEXT NOT NULL,"
                " lang TEXT, title TEXT, idx INTEGER NOT NULL, off INTEGER NOT NULL,"
                " PRIMARY KEY (root, owner, kind))"
            )

    def get(self, root: str, path: str) -> Entry | None:
        with self._lock:
            row = self._db.execute(
                "SELECT position, duration, watched, updated, hidden FROM progress"
                " WHERE root = ? AND path = ?",
                (root, path),
            ).fetchone()
        return Entry(row[0], row[1], bool(row[2]), row[3], bool(row[4])) if row else None

    def of_root(self, root: str) -> dict[str, Entry]:
        with self._lock:
            rows = self._db.execute(
                "SELECT path, position, duration, watched, updated, hidden FROM progress"
                " WHERE root = ?",
                (root,),
            ).fetchall()
        return {r[0]: Entry(r[1], r[2], bool(r[3]), r[4], bool(r[5])) for r in rows}

    def save(
        self, root: str, path: str, position: float, duration: float | None, *, finished: bool
    ) -> Entry:
        """Records where a video is. Past 90 % (or at its end) it is watched and starts over next
        time; watched stays watched when it is seen again."""
        done = finished or bool(duration and position >= duration * WATCHED_RATIO)
        previous = self.get(root, path)
        watched = done or bool(previous and previous.watched)
        entry = Entry(0.0 if done else position, duration, watched, time.time())
        self._write(root, path, entry)
        return entry

    def mark(self, root: str, path: str, *, watched: bool) -> None:
        """Watched by hand (seen elsewhere), or not watched any more: from the start either way."""
        if not watched:
            with self._lock, self._db:
                self._db.execute("DELETE FROM progress WHERE root = ? AND path = ?", (root, path))
            return
        previous = self.get(root, path)
        duration = previous.duration if previous else None
        self._write(root, path, Entry(0.0, duration, True, time.time()))

    def hide(self, root: str, path: str) -> None:
        """Takes a video out of "À suivre"; playing it again brings it back."""
        with self._lock, self._db:
            self._db.execute(
                "UPDATE progress SET hidden = 1 WHERE root = ? AND path = ?", (root, path)
            )

    def _write(self, root: str, path: str, entry: Entry) -> None:
        with self._lock, self._db:
            self._db.execute(
                "INSERT INTO progress (root, path, position, duration, watched, updated, hidden)"
                " VALUES (?, ?, ?, ?, ?, ?, 0)"
                " ON CONFLICT (root, path) DO UPDATE SET position = excluded.position,"
                " duration = excluded.duration, watched = excluded.watched,"
                " updated = excluded.updated, hidden = 0",
                (root, path, entry.position, entry.duration, int(entry.watched), entry.updated),
            )

    def pick(self, root: str, owner: str, kind: str, pick: Pick) -> None:
        """Remembers the audio ("audio") or subtitles ("sub") chosen for `owner`: a saga or a
        series, or a film on its own."""
        with self._lock, self._db:
            self._db.execute(
                "INSERT OR REPLACE INTO picks (root, owner, kind, lang, title, idx, off)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (root, owner, kind, pick.lang, pick.title, pick.index, int(pick.off)),
            )

    def picks(self, root: str, owner: str) -> dict[str, Pick]:
        with self._lock:
            rows = self._db.execute(
                "SELECT kind, lang, title, idx, off FROM picks WHERE root = ? AND owner = ?",
                (root, owner),
            ).fetchall()
        return {r[0]: Pick(r[1], r[2], r[3], bool(r[4])) for r in rows}

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
        if video.group is None and entry is not None and entry.in_progress and not entry.hidden:
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
        if last.hidden:
            continue
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
