import threading
import time
from pathlib import Path

from nanar.library import Library
from nanar.watcher import FolderWatcher


def test_a_finished_download_joins_the_library(tmp_path: Path) -> None:
    (tmp_path / "Vieux 1990.mkv").write_bytes(b"")
    seen: list[Library] = []
    changed = threading.Event()

    def on_change(library: Library) -> None:
        seen.append(library)
        if any(v.title == "Nouveau" for v in library.videos.values()):
            changed.set()

    watcher = FolderWatcher(tmp_path, on_change)
    watcher.start()
    try:
        partial = tmp_path / "Nouveau 2024.mkv.!qB"
        partial.write_bytes(b"downloading")
        partial.rename(tmp_path / "Nouveau 2024.mkv")
        assert changed.wait(10)
    finally:
        watcher.stop()
    assert all("!qB" not in v.path for lib in seen for v in lib.videos.values())


def test_a_download_growing_does_not_read_the_folder_over_and_over(tmp_path: Path) -> None:
    (tmp_path / "Vieux 1990.mkv").write_bytes(b"")
    seen: list[Library] = []
    partial = tmp_path / "Nouveau 2024.mkv.part"
    partial.write_bytes(b"")
    watcher = FolderWatcher(tmp_path, seen.append)
    watcher.start()
    try:
        time.sleep(0.5)
        for _ in range(10):
            with partial.open("ab") as file:
                file.write(b"x" * 1000)
            time.sleep(0.2)
        time.sleep(2)
    finally:
        watcher.stop()
    assert len(seen) == 0  # nothing the pages would show has changed
