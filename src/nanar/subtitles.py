"""Subtitles from OpenSubtitles, when the user gave a key (`online.py` says what is sent).

Asked from the phone for the video playing; what is downloaded stays in the data directory (never
next to the films), and plays again with that video, and with the next episodes when they were
picked for the series.
"""

import hashlib
import threading
from collections.abc import Callable
from pathlib import Path

from nanar.library import Video
from nanar.online import OnlineError, OpenSubtitles, Wanted, moviehash


class Subtitles:
    def __init__(self, directory: Path, make: Callable[[str], OpenSubtitles] = OpenSubtitles):
        self._directory = directory
        self._make = make
        self._client: OpenSubtitles | None = None
        self._lock = threading.Lock()  # one download at a time

    @property
    def enabled(self) -> bool:
        return self._client is not None

    def configure(self, key: str) -> None:
        self._client = self._make(key) if key.strip() else None

    def saved(self, root: str, video: Video) -> list[Path]:
        """What was downloaded before for this video."""
        path = self._file(root, video)
        return [path] if path.is_file() else []

    def find(self, root: str, video: Video, source: Path | None) -> Path:
        """Downloads French subtitles for a video (`source`: its file, for the hash). Raises
        OnlineError: "no_subtitles", "online_off", "bad_key", "quota_reached", "offline"."""
        client = self._client
        if client is None:
            raise OnlineError("online_off")
        target = self._file(root, video)
        with self._lock:
            if target.is_file():
                return target
            wanted = Wanted(
                title=video.title,
                year=video.year,
                season=video.season if video.kind == "episode" else None,
                episode=video.episode if video.kind == "episode" else None,
                hash=moviehash(source) if source is not None else None,
            )
            file_id = client.best(wanted)
            if file_id is None:
                raise OnlineError("no_subtitles")
            data = client.download(file_id)
            self._directory.mkdir(parents=True, exist_ok=True)
            tmp = target.with_suffix(".tmp")
            tmp.write_bytes(data)
            tmp.replace(target)
            return target

    def _file(self, root: str, video: Video) -> Path:
        name = hashlib.blake2s(f"{root}\n{video.path}".encode(), digest_size=10).hexdigest()
        return self._directory / f"{name}.fr.srt"
