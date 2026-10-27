from pathlib import Path

import pytest

from nanar.config import Settings
from nanar.controller import CommandError, Controller
from nanar.folders import Folders
from nanar.library import Library

from .fakes import FakeSessions


def test_opens_another_folder_and_remembers_it(tmp_path: Path) -> None:
    films = tmp_path / "Films"
    films.mkdir()
    (films / "Seul 2001.mkv").write_bytes(b"")
    settings = Settings()
    controller = Controller(Library(root=""), settings, None, FakeSessions())
    folders = Folders(controller, settings, tmp_path / "settings.json")
    try:
        folders.open(films)
        assert controller.library.root == str(films.resolve())
        assert [v.title for v in controller.library.videos.values()] == ["Seul"]
        assert Settings.load(tmp_path / "settings.json").last_folder == str(films.resolve())
        with pytest.raises(CommandError, match="not_a_folder"):
            folders.open(tmp_path / "nowhere")
        assert controller.library.root == str(films.resolve())  # unchanged
    finally:
        folders.stop()
        controller.shutdown()
