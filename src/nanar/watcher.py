"""Watches the library's folder: a film that finishes downloading shows up by itself.

Downloads in progress (`film.mkv.!qB`, `.part`…) are not videos to `library.scan`: the film joins
the library when its file gets its real name. A burst of changes leads to one new reading.
"""

import logging
import threading
from collections.abc import Callable
from pathlib import Path

from watchfiles import watch

from nanar.library import Library, scan

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
            for _changes in watch(self._root, stop_event=self._stop, raise_interrupt=False):
                self._on_change(scan(self._root))
        except Exception:  # a folder that vanished (a disk unplugged): stop watching, keep going
            log.exception("watching %s", self._root)
