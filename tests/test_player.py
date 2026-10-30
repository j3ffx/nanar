"""The real libmpv, playing the demo's generated videos without a window or sound."""

import threading
from typing import Any

import pytest

from nanar import demo
from nanar.config import Settings
from nanar.player import MpvSession, Playback, Rect, Start, Track, choose, pick_of
from nanar.progress import Pick


def libmpv_available() -> bool:
    try:
        from nanar.player import _load_mpv

        _load_mpv()
    except OSError:
        return False
    return True


pytestmark = pytest.mark.skipif(not libmpv_available(), reason="libmpv is not installed")


class Recorder:
    def __init__(self) -> None:
        self.latest = Playback()
        self.actions: list[str] = []
        self.at_end = threading.Event()
        self.done = threading.Event()
        self.changed_event = threading.Event()

    def changed(self, playback: Playback) -> None:
        self.latest = playback
        self.changed_event.set()

    def action(self, name: str) -> None:
        self.actions.append(name)

    def finished(self) -> None:
        self.at_end.set()

    def ended(self, finished: bool, rect: Rect | None) -> None:
        self.done.set()

    def wait(self, check: Any, timeout: float = 10) -> None:
        deadline = threading.Event()
        timer = threading.Timer(timeout, deadline.set)
        timer.start()
        try:
            while not check(self.latest):
                if deadline.is_set():
                    raise AssertionError(f"mpv did not get there: {self.latest}")
                self.changed_event.wait(0.1)
                self.changed_event.clear()
        finally:
            timer.cancel()


@pytest.fixture(autouse=True)
def headless(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(MpvSession, "overrides", {"vo": "null", "ao": "null", "force_window": "no"})


def test_plays_and_obeys_commands() -> None:
    recorder = Recorder()
    session = MpvSession(Start(demo.source(0, 60), "Démo"), Settings(), recorder)
    try:
        recorder.wait(lambda p: p.position > 0.2 and len(p.audio) == 2)
        session.command("audio", 2)
        recorder.wait(lambda p: [t.selected for t in p.audio] == [False, True])
        session.command("pause", True)
        recorder.wait(lambda p: p.paused)
        session.command("volume", 40)
        recorder.wait(lambda p: p.volume == 40)
        with pytest.raises(ValueError, match="unknown player action"):
            session.command("explode")
    finally:
        session.close()
    assert not recorder.done.is_set()  # closed by Nanar: no "ended" report


def test_reports_the_end_and_plays_the_next_video_in_the_same_window() -> None:
    recorder = Recorder()
    session = MpvSession(Start(demo.source(1, 1), "Démo"), Settings(), recorder)
    try:
        assert recorder.at_end.wait(15)
        assert not recorder.done.is_set()  # mpv stays open on the last picture
        recorder.at_end.clear()
        session.load(Start(demo.source(2, 1), "Suite"))
        recorder.wait(lambda p: p.position > 0.2 and not p.paused)  # plays, not left paused
        assert recorder.at_end.wait(15)
    finally:
        session.close()


def test_the_demo_jumps_forward_and_back() -> None:
    recorder = Recorder()
    start = Start(demo.source(3, 60), "Démo", length=60.0)
    session = MpvSession(start, Settings(), recorder)
    try:
        recorder.wait(lambda p: p.position > 0.2)
        session.command("seek_to", 20)
        recorder.wait(lambda p: p.position >= 19.5)
        session.command("seek", -10)
        recorder.wait(lambda p: 9 <= p.position < 15)
    finally:
        session.close()


def test_picks_found_again_by_language_and_title_then_language_then_rank() -> None:
    tracks = [
        Track(1, "sub", "fre", "Forcés", False),
        Track(2, "sub", "fre", "Complets", False),
        Track(3, "sub", "eng", None, False),
    ]
    assert choose(tracks, Pick("fre", "Complets", 1)) == 2
    assert choose(tracks, Pick("FRE", "SDH", 0)) == 1  # same language, another title
    assert choose(tracks, Pick("spa", None, 0)) is None  # nothing alike: mpv's own choice
    assert choose(tracks, Pick(off=True)) == "no"
    assert choose(tracks, Pick(None, None, 2)) == 3  # no language, no title: its rank
    assert choose(tracks, None) is None
    assert pick_of(tracks, 2) == Pick("fre", "Complets", 1)
    assert pick_of(tracks, None) == Pick(off=True)
    assert pick_of(tracks, 9) is None


def test_plays_with_the_tracks_picked_before_and_night_mode() -> None:
    recorder = Recorder()
    start = Start(demo.source(0, 60), "Démo", audio=Pick(index=1), night=True)
    session = MpvSession(start, Settings(), recorder)
    try:
        recorder.wait(lambda p: [t.selected for t in p.audio] == [False, True])
        recorder.wait(lambda p: p.night)
        session.command("night", False)
        recorder.wait(lambda p: not p.night)
        session.command("chapter", 1)  # no chapters here: nothing happens
        assert recorder.latest.chapters == 0
    finally:
        session.close()
