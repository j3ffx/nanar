from pathlib import Path

import pytest

from nanar import demo
from nanar.previews import Previews

from .test_player import libmpv_available


def test_grabs_each_frame_once_at_rounded_times(tmp_path: Path) -> None:
    asked: list[tuple[str, float]] = []

    def grab(source: str, at: float, destination: Path) -> bool:
        asked.append((source, at))
        destination.write_bytes(b"jpeg")
        return True

    previews = Previews(tmp_path / "previews", grab=grab)
    first = previews.frame("film.mkv", 61.0)
    assert first is not None
    assert first.read_bytes() == b"jpeg"
    assert previews.frame("film.mkv", 59.0) == first  # the same five seconds
    assert previews.frame("film.mkv", -3.0) is not None
    assert asked == [("film.mkv", 60), ("film.mkv", 0)]


def test_a_failed_grab_gives_no_picture_and_old_frames_go(tmp_path: Path) -> None:
    folder = tmp_path / "previews"
    folder.mkdir()
    (folder / "old.jpg").write_bytes(b"from the last run")
    previews = Previews(folder, grab=lambda source, at, destination: False)
    assert not (folder / "old.jpg").exists()
    assert previews.frame("film.mkv", 10.0) is None


@pytest.mark.skipif(not libmpv_available(), reason="libmpv is not installed")
def test_grabs_real_frames_at_their_time_even_from_the_demo(tmp_path: Path) -> None:
    previews = Previews(tmp_path / "previews")
    early = previews.frame(demo.source(0, 30), 5.0)
    late = previews.frame(demo.source(0, 30), 25.0)
    assert early is not None
    assert late is not None
    assert early.read_bytes()[:2] == b"\xff\xd8"  # a JPEG
    assert early.read_bytes() != late.read_bytes()  # the test pattern moved
