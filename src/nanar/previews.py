"""Pictures of the video playing, for the phone's progress bar: while the finger drags it, the
frame near the time it points at.

libmpv grabs each frame when asked (about a tenth of a second, from the keyframe before), and
the frames are kept for the rest of the run: dragging back and forth shows them again at once.
"""

import hashlib
import shutil
import threading
from collections.abc import Callable
from pathlib import Path

from nanar import demo
from nanar.thumbnails import grab_frame

STEP = 5  # seconds: times are rounded to this (web/src/remote/Controls.tsx rounds the same)
WIDTH = 320

Grabber = Callable[[str, float, Path], bool]  # source, time, destination → made it


def _grab(source: str, at: float, destination: Path) -> bool:
    if demo.is_generated(source):  # the demo's videos can't seek: generated from `at` on
        return grab_frame(demo.from_time(source, at), destination, start="0", width=WIDTH)
    return grab_frame(source, destination, start=f"{at:g}", width=WIDTH)


class Previews:
    def __init__(self, directory: Path, *, grab: Grabber = _grab) -> None:
        shutil.rmtree(directory, ignore_errors=True)  # last run's frames: never asked again
        directory.mkdir(parents=True, exist_ok=True)
        self._directory = directory
        self._grab = grab
        self._lock = threading.Lock()  # one libmpv at a time: a drag asks faster than it grabs

    def frame(self, source: str, at: float) -> Path | None:
        """The frame near `at` seconds into `source`, made if it isn't yet."""
        at = max(0, round(at / STEP) * STEP)
        digest = hashlib.blake2s(f"{source}|{at}".encode(), digest_size=10).hexdigest()
        path = self._directory / f"{digest}.jpg"
        with self._lock:
            if not path.is_file() and not self._grab(source, at, path):
                return None
        return path
