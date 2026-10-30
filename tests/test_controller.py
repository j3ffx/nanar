import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

from nanar import controller as controller_module
from nanar.config import Settings
from nanar.controller import CommandError, Controller
from nanar.library import Library, build
from nanar.player import Rect, Track
from nanar.progress import Pick, Progress

from .fakes import FakeSessions, FakeWindow

PATHS = [
    "Seul 2001.mkv",
    "Saga/Saga 1990.mkv",
    "Saga/Saga 2 1992.mkv",
]


@pytest.fixture(autouse=True)
def quick_countdown(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(controller_module, "TICK", 0.01)


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
def progress() -> Progress:
    return Progress(None)


@pytest.fixture
def controller(
    library: Library,
    sessions: FakeSessions,
    window: FakeWindow,
    progress: Progress,
    tmp_path: Path,
) -> Iterator[Controller]:
    c = Controller(
        library, Settings(), tmp_path / "settings.json", sessions, window, progress=progress
    )
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


def test_a_failed_video_or_a_closed_window_brings_nanar_back(
    controller: Controller, library: Library, sessions: FakeSessions, window: FakeWindow
) -> None:
    controller.play(video_id(library, "Seul"))
    sessions.last.fail()
    wait_for(lambda: window.visible)
    assert sessions.last.closed
    assert controller.state()["playing"] is None


def test_the_end_of_a_lone_film_brings_nanar_back_and_marks_it_watched(
    controller: Controller,
    library: Library,
    sessions: FakeSessions,
    window: FakeWindow,
    progress: Progress,
) -> None:
    controller.play(video_id(library, "Seul"))
    sessions.last.report(position=5990.0, duration=6000.0)
    sessions.last.finish()
    wait_for(lambda: window.visible)
    entry = progress.get("/films", "Seul 2001.mkv")
    assert entry is not None
    assert entry.watched
    assert controller.library_json()["videos"][video_id(library, "Seul")]["progress"]["watched"]


def test_the_end_of_an_episode_counts_down_then_plays_the_next_in_the_same_window(
    controller: Controller, library: Library, sessions: FakeSessions, window: FakeWindow
) -> None:
    heard: list[dict[str, Any]] = []
    controller.subscribe(heard.append)
    controller.play(video_id(library, "Saga"))
    sessions.last.finish()
    wait_for(lambda: sessions.last.loaded)
    assert len(sessions.made) == 1  # no second window
    assert sessions.last.loaded[0].title == "Saga 2"
    assert sessions.last.loaded[0].start == 0.0
    assert not window.visible
    counts = [s["upNext"]["seconds"] for s in heard if s["upNext"]]
    assert counts[0] == controller_module.UP_NEXT_SECONDS
    assert counts == sorted(counts, reverse=True)
    assert any(m.startswith("À suivre : Saga 2") for m in sessions.last.messages)
    assert controller.state()["upNext"] is None


def test_stop_during_the_countdown_goes_back_to_the_library(
    controller: Controller,
    library: Library,
    sessions: FakeSessions,
    window: FakeWindow,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(controller_module, "TICK", 5)  # a countdown that stays put
    controller.play(video_id(library, "Saga"))
    sessions.last.finish()
    wait_for(lambda: controller.state()["upNext"])
    controller.command("stop")
    assert window.visible
    assert sessions.last.loaded == []


def test_next_during_the_countdown_plays_at_once(
    controller: Controller,
    library: Library,
    sessions: FakeSessions,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(controller_module, "TICK", 5)
    controller.play(video_id(library, "Saga"))
    sessions.last.finish()
    wait_for(lambda: controller.state()["upNext"])
    controller.command("next")
    assert sessions.last.loaded[-1].title == "Saga 2"
    assert controller.state()["upNext"] is None


def test_resumes_where_a_video_was_left(
    controller: Controller, library: Library, sessions: FakeSessions, progress: Progress
) -> None:
    progress.save("/films", "Seul 2001.mkv", 600.0, 6000.0, finished=False)
    controller.play(video_id(library, "Seul"))
    assert sessions.last.start.start == 595.0  # a few seconds earlier, to find the thread
    controller.command("stop")
    controller.play(video_id(library, "Seul"), start=0.0)
    assert sessions.last.start.start == 0.0  # "from the start" overrides


def test_the_library_says_what_to_continue(
    controller: Controller, library: Library, progress: Progress
) -> None:
    assert controller.library_json()["continue"] == []
    progress.save("/films", "Seul 2001.mkv", 600.0, 6000.0, finished=False)
    assert controller.library_json()["continue"] == [video_id(library, "Seul")]


def test_saves_where_a_video_is_while_it_plays_and_when_it_stops(
    controller: Controller, library: Library, sessions: FakeSessions, progress: Progress
) -> None:
    controller.play(video_id(library, "Seul"))
    sessions.last.report(position=30.0, duration=6000.0)
    wait_for(lambda: progress.get("/films", "Seul 2001.mkv"))
    sessions.last.report(position=42.0, duration=6000.0)
    wait_for(lambda: controller.state()["playing"]["position"] == 42.0)
    controller.command("stop")
    entry = progress.get("/films", "Seul 2001.mkv")
    assert entry is not None
    assert entry.position == 42.0
    assert not entry.watched


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


def test_next_and_previous_move_inside_a_saga_in_the_same_window(
    controller: Controller, library: Library, sessions: FakeSessions
) -> None:
    controller.play(video_id(library, "Saga"))
    assert controller.state()["playing"]["hasNext"] is True
    controller.command("next")
    assert len(sessions.made) == 1
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


def test_a_closed_session_is_ignored_once_another_plays(
    controller: Controller, library: Library, sessions: FakeSessions, window: FakeWindow
) -> None:
    controller.play(video_id(library, "Seul"))
    first = sessions.last
    controller.command("stop")
    controller.play(video_id(library, "Saga"))
    first.fail()  # late news from the first mpv
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


def test_a_new_reading_of_the_folder_reaches_the_pages(
    controller: Controller, library: Library
) -> None:
    before = controller.state()["libraryVersion"]
    controller.set_library(build("/films", [*PATHS, "Nouveau 2024.mkv"]))
    assert controller.state()["libraryVersion"] == before + 1
    titles = {v["title"] for v in controller.library_json()["videos"].values()}
    assert "Nouveau" in titles


TRACKS = {
    "audio": [Track(1, "audio", "fre", None, True), Track(2, "audio", "eng", None, False)],
    "subs": [Track(3, "sub", "fre", "Complets", False)],
}


def test_tracks_picked_by_hand_carry_on_through_the_saga(
    controller: Controller, library: Library, sessions: FakeSessions
) -> None:
    controller.play(video_id(library, "Saga"))
    assert sessions.last.start.audio is None
    sessions.last.report(position=5.0, **TRACKS)
    wait_for(lambda: controller.state()["playing"]["audio"])
    controller.command("audio", 2)
    controller.command("sub", 3)
    controller.command("next")
    loaded = sessions.last.loaded[-1]
    assert loaded.audio == Pick("eng", None, 1)
    assert loaded.sub == Pick("fre", "Complets", 0)
    controller.command("sub", None)
    controller.play(video_id(library, "Saga"))
    assert sessions.last.loaded[-1].sub == Pick(off=True)
    controller.play(video_id(library, "Seul"))  # a film of its own: its own tracks
    assert sessions.last.loaded[-1].audio is None


def test_mpv_keys_cycle_the_tracks_through_nanar(
    controller: Controller, library: Library, sessions: FakeSessions
) -> None:
    controller.play(video_id(library, "Seul"))
    sessions.last.report(position=5.0, **TRACKS)
    wait_for(lambda: controller.state()["playing"]["audio"])
    sessions.last.callbacks.action("cycle_audio")
    sessions.last.callbacks.action("cycle_sub")
    wait_for(lambda: len(sessions.last.commands) == 2)
    assert sessions.last.commands == [("audio", 2), ("sub", 3)]
    assert sessions.last.osd == [True, True]


def test_night_mode_stays_on_for_the_next_videos(
    controller: Controller, library: Library, sessions: FakeSessions
) -> None:
    controller.command("night")  # before any video: kept for the first one
    assert controller.state()["night"]
    controller.play(video_id(library, "Saga"))
    assert sessions.last.start.night
    controller.command("night", False, osd=True)
    assert sessions.last.commands[-1] == ("night", False)
    controller.command("next")
    assert not sessions.last.loaded[-1].night


def test_sleep_after_this_video_skips_the_countdown(
    controller: Controller, library: Library, sessions: FakeSessions, window: FakeWindow
) -> None:
    with pytest.raises(CommandError, match="nothing_playing"):
        controller.command("sleep", "end")
    controller.play(video_id(library, "Saga"))
    controller.command("sleep", "end")
    assert controller.state()["sleep"] == {"kind": "end"}
    sessions.last.finish()
    wait_for(lambda: window.visible)
    assert not sessions.last.loaded  # the next one did not start
    assert controller.state()["sleep"] is None


def test_sleep_timer_warns_then_stops(
    controller: Controller,
    library: Library,
    sessions: FakeSessions,
    window: FakeWindow,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(controller_module, "MINUTE", 0.2)
    monkeypatch.setattr(controller_module, "SLEEP_WARNING", 0.1)
    controller.play(video_id(library, "Seul"))
    with pytest.raises(CommandError, match="bad_value"):
        controller.command("sleep", 0)
    controller.command("sleep", 1)
    assert controller.state()["sleep"]["kind"] == "timer"
    wait_for(lambda: sessions.last.messages)
    wait_for(lambda: window.visible)
    assert "une minute" in sessions.last.messages[0]
    assert controller.state()["sleep"] is None


def test_a_cancelled_sleep_timer_does_nothing(
    controller: Controller, library: Library, window: FakeWindow
) -> None:
    controller.play(video_id(library, "Seul"))
    controller.command("sleep", 1)
    controller.command("sleep", None)
    assert controller.state()["sleep"] is None
    assert not window.visible


def test_phones_mark_videos_and_clear_continue(
    controller: Controller, library: Library, progress: Progress
) -> None:
    seul, saga2 = video_id(library, "Seul"), video_id(library, "Saga 2")
    progress.save("/films", "Seul 2001.mkv", 600.0, 6000.0, finished=False)
    progress.save("/films", "Saga/Saga 1990.mkv", 0.0, 6000.0, finished=True)
    assert controller.library_json()["continue"] == [saga2, seul]
    controller.mark(saga2, "dismiss")  # the next of the saga: hides the one watched before it
    assert controller.library_json()["continue"] == [seul]
    controller.mark(seul, "watched")
    assert controller.library_json()["videos"][seul]["progress"]["watched"]
    controller.mark(seul, "unwatched")
    assert controller.library_json()["videos"][seul]["progress"] is None
    with pytest.raises(CommandError, match="unknown_video"):
        controller.mark("nope", "watched")


class FakeSubtitles:
    enabled = True

    def __init__(self, folder: Path) -> None:
        self.folder = folder
        self.found: list[str] = []

    def saved(self, root: str, video: Any) -> list[Path]:
        path = self.folder / f"{video.id}.srt"
        return [path] if path.exists() else []

    def find(self, root: str, video: Any, source: Path | None) -> Path:
        self.found.append(video.title)
        path = self.folder / f"{video.id}.srt"
        path.write_text("srt")
        return path


def test_subtitles_found_online_play_now_and_with_the_next_episodes(
    controller: Controller, library: Library, sessions: FakeSessions, tmp_path: Path
) -> None:
    subtitles = FakeSubtitles(tmp_path)
    controller.subtitles = subtitles  # type: ignore[assignment]
    controller.play(video_id(library, "Saga"))
    controller.find_subtitles()
    action, path = sessions.last.commands[-1]
    assert action == "sub_add"
    assert path.endswith(".srt")
    controller.play(video_id(library, "Saga"))  # downloaded before: given to mpv at once
    assert sessions.last.loaded[-1].sub_files == (path,)
    controller.command("next")  # picked for the saga: found for this one too, in the background
    wait_for(lambda: subtitles.found == ["Saga", "Saga 2"])
    wait_for(lambda: sessions.last.commands[-1][0] == "sub_add")
