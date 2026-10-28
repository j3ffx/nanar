"""Pictures for the library: a poster found next to the video, or a frame taken from it.

A poster the user put there wins: `<video name>.jpg` (or -poster, .png…), or `poster.jpg` /
`folder.jpg` / `cover.jpg` in its folder. Otherwise libmpv takes one frame, a quarter into the
video, scaled down to 480 pixels wide, into the data directory, one video at a time in the
background. Nothing is ever fetched from the Internet.
"""

import hashlib
import logging
import shutil
import tempfile
import threading
from collections.abc import Callable
from pathlib import Path, PurePosixPath
from typing import Any

from nanar.library import Library, Video

POSTER_SUFFIXES = ("", "-poster", ".poster", "-cover")
POSTER_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp")
FOLDER_POSTERS = ("poster", "folder", "cover")
GRAB_TIMEOUT = 30.0
ANNOUNCE_EVERY = 4  # thumbnails made between two announcements to the pages

log = logging.getLogger(__name__)

Grabber = Callable[[str, Path], bool]  # source, destination → made it


class Thumbnails:
    def __init__(
        self, directory: Path, *, on_ready: Callable[[], None], grab: Grabber | None = None
    ) -> None:
        self._directory = directory
        self._directory.mkdir(parents=True, exist_ok=True)
        self._on_ready = on_ready
        self._grab = grab or grab_frame
        self._lock = threading.Lock()
        self._pending: list[tuple[str, Path]] = []
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._failed: set[Path] = set()

    # What the pages ask for --------------------------------------------------------------------

    def of_video(self, library: Library, video: Video) -> Path | None:
        """The picture of a video, if there is one yet."""
        poster = local_poster(library, video)
        if poster is not None:
            return poster
        made = self._made(library, video)
        return made if made.is_file() else None

    def of_group(self, library: Library, group_id: str) -> Path | None:
        """A saga's or a series' picture: its folder's poster, else its first video's."""
        group = library.groups.get(group_id)
        if group is None:
            return None
        first = library.videos[group.videos[0]]
        folder_poster = _folder_poster(library, PurePosixPath(first.path).parent)
        if folder_poster is None and first.kind == "episode":  # Série/Saison 1/… → Série/
            folder_poster = _folder_poster(library, PurePosixPath(first.path).parent.parent)
        return folder_poster or self.of_video(library, first)

    # Making them -------------------------------------------------------------------------------

    def schedule(self, library: Library) -> None:
        """Makes, in the background, the pictures this library lacks."""
        missing = [
            (_source_of(library, v), self._made(library, v))
            for v in library.videos.values()
            if local_poster(library, v) is None and not self._made(library, v).is_file()
        ]
        with self._lock:
            self._pending = [m for m in missing if m[1] not in self._failed]
        self._wake.set()
        if self._thread is None:
            self._thread = threading.Thread(target=self._work, name="nanar-thumbs", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()

    def _work(self) -> None:
        made = 0
        while not self._stop.is_set():
            with self._lock:
                job = self._pending.pop(0) if self._pending else None
            if job is None:
                if made:
                    self._on_ready()
                    made = 0
                self._wake.clear()
                self._wake.wait()
                continue
            source, destination = job
            try:
                ok = self._grab(source, destination)
            except Exception:  # one broken file must not stop the others
                log.exception("thumbnail of %s", source)
                ok = False
            if not ok:
                self._failed.add(destination)
                continue
            made += 1
            if made >= ANNOUNCE_EVERY:
                self._on_ready()
                made = 0

    def _made(self, library: Library, video: Video) -> Path:
        digest = hashlib.blake2s(f"{library.root}|{video.path}".encode(), digest_size=10)
        return self._directory / f"{digest.hexdigest()}.jpg"


def local_poster(library: Library, video: Video) -> Path | None:
    """A picture the user put next to the video, or in its folder when it is alone there."""
    if "://" in video.path:
        return None
    file = Path(library.root) / video.path
    for suffix in POSTER_SUFFIXES:
        for extension in POSTER_EXTENSIONS:
            candidate = file.with_name(file.stem + suffix + extension)
            if candidate.is_file():
                return candidate
    folder = PurePosixPath(video.path).parent
    alone = sum(1 for v in library.videos.values() if PurePosixPath(v.path).parent == folder) == 1
    return _folder_poster(library, folder) if alone and str(folder) != "." else None


def _folder_poster(library: Library, folder: PurePosixPath) -> Path | None:
    if str(folder) in (".", "") or "://" in str(folder):
        return None
    base = Path(library.root) / folder
    for name in FOLDER_POSTERS:
        for extension in POSTER_EXTENSIONS:
            candidate = base / (name + extension)
            if candidate.is_file():
                return candidate
    return None


def _source_of(library: Library, video: Video) -> str:
    return video.path if "://" in video.path else str(Path(library.root) / video.path)


def grab_frame(
    source: str, destination: Path, *, start: str | None = None, width: int = 480
) -> bool:
    """One frame, as a JPEG: at `start` (mpv's syntax), by default a quarter into the video
    (eight seconds into a generated one)."""
    from nanar.player import _load_mpv

    mpv = _load_mpv()
    done = threading.Event()
    with tempfile.TemporaryDirectory(prefix="nanar-thumb-") as tmp:
        player: Any = mpv.MPV(
            vo="image",
            vo_image_outdir=tmp,
            vo_image_format="jpg",
            vo_image_jpeg_quality=82,
            ao="null",
            aid="no",
            sid="no",
            frames=1,
            start=start or ("8" if "://" in source else "25%"),
            hr_seek="no",  # the keyframe before is close enough, and much faster
            vf=f"scale={width}:-2",
            hwdec="no",
            idle="yes",
            ytdl=False,
        )
        try:
            player.register_event_callback(
                lambda event: (
                    done.set() if event.event_id.value == mpv.MpvEventID.END_FILE else None
                )
            )
            player.play(source)
            done.wait(GRAB_TIMEOUT)
        finally:
            player.terminate()
        frames = sorted(Path(tmp).glob("*.jpg"))
        if not frames:
            return False
        shutil.move(str(frames[0]), destination)
    return True
