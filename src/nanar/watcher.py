"""Watches the library's folder: a film that finishes downloading shows up by itself.

Downloads in progress (`film.mkv.!qB`, `.part`…) are not videos to `library.scan`: the film joins
the library when its file gets its real name. A file growing is no news; a file arriving or leaving
leads to a new reading, and the pages hear of it only if the videos did change, or a poster.
"""

import logging
import threading
from collections.abc import Callable
from pathlib import Path

from watchfiles import Change, watch

from nanar.library import Library, scan
from nanar.thumbnails import POSTER_EXTENSIONS

log = logging.getLogger(__name__)


class FolderWatcher:
    def __init__(self, root: Path, on_change: Callable[[Library], None]) -> None:
        self._root = root
        self._on_change = on_change
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="nanar-watch", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        try:
            # watchfiles gathers the changes of about two seconds into one batch.
            known: set[str] | None = None
            for changes in watch(self._root, stop_event=self._stop, raise_interrupt=False):
                posters = any(Path(path).suffix.lower() in POSTER_EXTENSIONS for _, path in changes)
                if not posters and all(kind == Change.modified for kind, _ in changes):
                    continue
                library = scan(self._root)
                if self._stop.is_set():  # another folder was opened during that reading
                    return
                videos = {video.path for video in library.videos.values()}
                if videos != known or posters:
                    known = videos
                    self._on_change(library)
        except Exception:  # a folder that vanished (a disk unplugged): stop watching, keep going
            log.exception("watching %s", self._root)
