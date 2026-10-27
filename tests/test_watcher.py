import threading
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
