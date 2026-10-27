import threading
from pathlib import Path

import pytest

from nanar import demo
from nanar.library import Library, scan
from nanar.thumbnails import Thumbnails, grab_frame

from .test_player import libmpv_available


def make_library(root: Path) -> Library:
    for name in (
        "Seul 2001.mkv",
        "Seul 2001.jpg",  # the user's own poster
        "Saga/Saga 1990.mkv",
        "Saga/Saga 2 1992.mkv",
        "Saga/folder.png",
        "Autre/Autre 2010.mkv",
    ):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"")
    return scan(root)


def by_title(library: Library, title: str) -> str:
    return next(v.id for v in library.videos.values() if v.title == title)


def test_a_poster_next_to_the_video_wins(tmp_path: Path) -> None:
    library = make_library(tmp_path / "films")
    thumbs = Thumbnails(tmp_path / "thumbs", on_ready=lambda: None)
    video = library.videos[by_title(library, "Seul")]
    assert thumbs.of_video(library, video) == tmp_path / "films" / "Seul 2001.jpg"


def test_a_saga_takes_its_folder_s_poster(tmp_path: Path) -> None:
    library = make_library(tmp_path / "films")
    thumbs = Thumbnails(tmp_path / "thumbs", on_ready=lambda: None)
    (group_id,) = library.groups
    assert thumbs.of_group(library, group_id) == tmp_path / "films" / "Saga" / "folder.png"


def test_makes_the_missing_ones_in_the_background_and_says_so(tmp_path: Path) -> None:
    library = make_library(tmp_path / "films")
    asked: list[str] = []

    def grab(source: str, destination: Path) -> bool:
        asked.append(Path(source).name)
        destination.write_bytes(b"jpeg")
        return True

    ready = threading.Event()
    thumbs = Thumbnails(tmp_path / "thumbs", on_ready=ready.set, grab=grab)
    thumbs.schedule(library)
    assert ready.wait(5)
    thumbs.stop()
    # Not the ones with a poster of their own; a saga's films do get theirs.
    assert sorted(asked) == ["Autre 2010.mkv", "Saga 1990.mkv", "Saga 2 1992.mkv"]
    autre = library.videos[by_title(library, "Autre")]
    made = thumbs.of_video(library, autre)
    assert made is not None
    assert made.parent == tmp_path / "thumbs"


def test_a_file_that_fails_is_not_tried_again_and_others_go_on(tmp_path: Path) -> None:
    library = make_library(tmp_path / "films")
    asked: list[str] = []

    def grab(source: str, destination: Path) -> bool:
        asked.append(Path(source).name)
        if "Autre" in source:
            raise RuntimeError("broken file")
        destination.write_bytes(b"jpeg")
        return True

    ready = threading.Event()
    thumbs = Thumbnails(tmp_path / "thumbs", on_ready=ready.set, grab=grab)
    thumbs.schedule(library)
    assert ready.wait(5)
    ready.clear()
    asked.clear()
    thumbs.schedule(library)  # again, as after a rescan
    thumbs.stop()
    assert "Autre 2010.mkv" not in asked


@pytest.mark.skipif(not libmpv_available(), reason="libmpv is not installed")
def test_takes_a_real_frame(tmp_path: Path) -> None:
    destination = tmp_path / "frame.jpg"
    assert grab_frame(demo.source(0, 20), destination)
    assert destination.read_bytes()[:2] == b"\xff\xd8"  # a JPEG
