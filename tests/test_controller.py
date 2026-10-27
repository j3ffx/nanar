import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

from nanar.config import Settings
from nanar.controller import CommandError, Controller
from nanar.library import Library, build
from nanar.player import Rect

from .fakes import FakeSessions, FakeWindow

PATHS = [
    "Seul 2001.mkv",
    "Saga/Saga 1990.mkv",
    "Saga/Saga 2 1992.mkv",
]


@pytest.fixture
def library() -> Library:
    return build("/films", PATHS)


@pytest.fixture
def sessions() -> FakeSessions:
    return FakeSessions()


@pytest.fixture
def window() -> FakeWindow:
    return FakeWindow()


@pytest.fixture
def controller(
    library: Library, sessions: FakeSessions, window: FakeWindow, tmp_path: Path
) -> Iterator[Controller]:
    c = Controller(library, Settings(), tmp_path / "settings.json", sessions, window)
    yield c
    c.shutdown()


def wait_for(condition: Callable[[], Any]) -> None:
    """Callbacks from mpv run on the controller's worker thread: wait until they have."""
    deadline = time.monotonic() + 2
    while not condition():
        if time.monotonic() > deadline:
            raise AssertionError("condition not met in time")
        time.sleep(0.01)


def video_id(library: Library, title: str) -> str:
    return next(v.id for v in library.videos.values() if v.title == title)


def test_playing_opens_mpv_over_the_window_and_hides_it(
    controller: Controller, library: Library, sessions: FakeSessions, window: FakeWindow
) -> None:
    controller.play(video_id(library, "Seul"), start=12)
    start = sessions.last.start
    assert start.source == str(Path("/films") / "Seul 2001.mkv")
    assert start.rect == Rect(100, 100, 1280, 720)
    assert start.start == 12
    assert not window.visible
    assert controller.state()["playing"]["video"]["title"] == "Seul"


def test_stopping_brings_the_window_back_where_mpv_was(
    controller: Controller, library: Library, sessions: FakeSessions, window: FakeWindow
) -> None:
    controller.play(video_id(library, "Seul"))
    sessions.last.window = Rect(5, 6, 700, 400)
    controller.command("stop")
    assert sessions.last.closed
    assert window.visible
    assert window.at == Rect(5, 6, 700, 400)
    assert controller.state()["playing"] is None


def test_the_end_of_the_video_brings_the_window_back(
    controller: Controller, library: Library, sessions: FakeSessions, window: FakeWindow
) -> None:
    controller.play(video_id(library, "Seul"))
    sessions.last.finish()
    wait_for(lambda: window.visible)
    assert sessions.last.closed
    assert controller.state()["playing"] is None


def test_player_commands_go_to_mpv(
    controller: Controller, library: Library, sessions: FakeSessions
) -> None:
    controller.play(video_id(library, "Seul"))
    controller.command("pause")
    controller.command("seek", -10)
    controller.command("audio", 2)
    assert sessions.last.commands == [("pause", None), ("seek", -10), ("audio", 2)]


def test_commands_fail_clearly(controller: Controller, library: Library) -> None:
    with pytest.raises(CommandError, match="nothing_playing"):
        controller.command("pause")
    with pytest.raises(CommandError, match="unknown_video"):
        controller.play("nope")
    controller.play(video_id(library, "Seul"))
    with pytest.raises(CommandError, match="unknown_action"):
        controller.command("explode")
    with pytest.raises(CommandError, match="bad_value"):
        controller.command("volume", "loud")
    with pytest.raises(CommandError, match="no_neighbour"):
        controller.command("next")


def test_next_and_previous_move_inside_a_saga(
    controller: Controller, library: Library, sessions: FakeSessions
) -> None:
    controller.play(video_id(library, "Saga"))
    assert controller.state()["playing"]["hasNext"] is True
    controller.command("next")
    assert sessions.made[0].closed
    assert sessions.last.start.title == "Saga 2"
    assert controller.state()["playing"]["hasNext"] is False
    controller.command("previous")
    assert sessions.last.start.title == "Saga"


def test_fullscreen_goes_to_the_window_or_to_mpv_and_is_remembered(
    controller: Controller,
    library: Library,
    sessions: FakeSessions,
    window: FakeWindow,
    tmp_path: Path,
) -> None:
    controller.command("fullscreen")
    assert window.fullscreen
    assert Settings.load(tmp_path / "settings.json").fullscreen
    controller.play(video_id(library, "Seul"))
    assert sessions.last.start.fullscreen
    controller.command("fullscreen", False)
    assert sessions.last.commands == [("fullscreen", False)]
    controller.command("stop")
    assert window.fullscreen is False


def test_fullscreen_toggled_in_mpv_is_followed(
    controller: Controller, library: Library, sessions: FakeSessions
) -> None:
    controller.play(video_id(library, "Seul"))
    sessions.last.report(fullscreen=True, position=3.0)
    wait_for(lambda: controller.state()["fullscreen"])
    assert controller.state()["playing"]["position"] == 3.0


def test_a_finished_session_is_ignored_once_another_plays(
    controller: Controller, library: Library, sessions: FakeSessions, window: FakeWindow
) -> None:
    controller.play(video_id(library, "Seul"))
    first = sessions.last
    controller.play(video_id(library, "Saga"))
    first.finish()  # late news from the first mpv
    first.report(position=99.0)
    time.sleep(0.1)
    assert controller.state()["playing"]["video"]["title"] == "Saga"
    assert not window.visible


def test_keys_pressed_in_mpv_act_like_commands(
    controller: Controller, library: Library, sessions: FakeSessions, window: FakeWindow
) -> None:
    controller.play(video_id(library, "Saga"))
    sessions.last.callbacks.action("next")
    wait_for(lambda: sessions.last.start.title == "Saga 2")
    sessions.last.callbacks.action("next")  # the last one: nothing happens
    sessions.last.callbacks.action("stop")
    wait_for(lambda: window.visible)


def test_listeners_hear_every_change(controller: Controller, library: Library) -> None:
    heard: list[dict[str, Any]] = []
    unsubscribe = controller.subscribe(heard.append)
    controller.play(video_id(library, "Seul"))
    controller.command("stop")
    unsubscribe()
    controller.command("fullscreen")
    assert [bool(s["playing"]) for s in heard] == [True, False]
