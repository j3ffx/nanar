from pathlib import Path

from nanar.progress import Progress


def test_keeps_where_a_video_was_left_across_runs(tmp_path: Path) -> None:
    db = tmp_path / "progress.db"
    Progress(db).save("/films", "A.mkv", 1200.0, 6000.0, finished=False)
    entry = Progress(db).get("/films", "A.mkv")
    assert entry is not None
    assert entry.position == 1200.0
    assert entry.resume_at() == 1195.0
    assert not entry.watched


def test_the_first_minute_is_not_worth_resuming() -> None:
    progress = Progress(None)
    entry = progress.save("/films", "A.mkv", 40.0, 6000.0, finished=False)
    assert entry.resume_at() == 0.0


def test_past_90_percent_a_video_is_watched_and_starts_over() -> None:
    progress = Progress(None)
    entry = progress.save("/films", "A.mkv", 5500.0, 6000.0, finished=False)
    assert entry.watched
    assert entry.resume_at() == 0.0


def test_watched_stays_watched_when_seen_again() -> None:
    progress = Progress(None)
    progress.save("/films", "A.mkv", 0.0, 6000.0, finished=True)
    entry = progress.save("/films", "A.mkv", 300.0, 6000.0, finished=False)
    assert entry.watched
    assert entry.resume_at() == 295.0


def test_each_library_keeps_its_own_history() -> None:
    progress = Progress(None)
    progress.save("/films", "A.mkv", 300.0, 6000.0, finished=False)
    progress.save("/autres", "A.mkv", 900.0, 6000.0, finished=False)
    assert set(progress.of_root("/films")) == {"A.mkv"}
    assert progress.of_root("/autres")["A.mkv"].position == 900.0
