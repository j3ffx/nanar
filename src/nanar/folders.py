"""The folder Nanar shows: opened at start, from the TV page, or by a second launch.

Opening another folder reads it, swaps the library (what plays keeps playing), remembers it for
next time, and watches it instead of the previous one.
"""

from pathlib import Path

from nanar.config import Settings
from nanar.controller import CommandError, Controller
from nanar.library import scan
from nanar.watcher import FolderWatcher


class Folders:
    def __init__(
        self, controller: Controller, settings: Settings, settings_path: Path | None
    ) -> None:
        self._controller = controller
        self._settings = settings
        self._settings_path = settings_path
        self._watcher: FolderWatcher | None = None

    def open(self, folder: str | Path) -> None:
        path = Path(folder).expanduser()
        try:
            path = path.resolve()
            if not path.is_dir():
                raise CommandError("not_a_folder")
        except OSError as error:  # a disk that is gone, a path Windows refuses
            raise CommandError("not_a_folder") from error
        library = scan(path)
        self._settings.last_folder = str(path)
        if self._settings_path is not None:
            self._settings.save(self._settings_path)
        self._controller.set_library(library)
        self.stop()
        self._watcher = FolderWatcher(path, self._controller.set_library)
        self._watcher.start()

    def stop(self) -> None:
        if self._watcher is not None:
            self._watcher.stop()
            self._watcher = None
