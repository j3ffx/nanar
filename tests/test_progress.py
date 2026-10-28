from pathlib import Path

from nanar.library import build
from nanar.progress import Entry, Progress, to_continue


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


# "À suivre" ------------------------------------------------------------------------------------

SHELF = build(
    "/films",
    [
        "Seul 2001.mkv",
        "Autre 2003.mkv",
        "Saga/Saga 1990.mkv",
        "Saga/Saga 2 1992.mkv",
        "Saga/Saga 3 1995.mkv",
        "Serie/Serie.S01E01.mkv",
        "Serie/Serie.S01E02.mkv",
    ],
)


def ident(path: str) -> str:
    return next(v.id for v in SHELF.videos.values() if v.path == path)


def left(position: float, updated: float) -> Entry:
    return Entry(position, 6000.0, False, updated)


def done(updated: float) -> Entry:
    return Entry(0.0, 6000.0, True, updated)


def test_continue_lists_what_was_left_in_the_middle_most_recent_first() -> None:
    saved = {"Seul 2001.mkv": left(1200.0, 1.0), "Autre 2003.mkv": left(300.0, 2.0)}
    assert to_continue(SHELF, saved) == [ident("Autre 2003.mkv"), ident("Seul 2001.mkv")]


def test_continue_leaves_out_what_was_barely_started_or_finished() -> None:
    saved = {"Seul 2001.mkv": left(30.0, 1.0), "Autre 2003.mkv": done(2.0)}
    assert to_continue(SHELF, saved) == []


def test_continue_offers_the_next_episode_once_one_is_watched() -> None:
    saved = {"Serie/Serie.S01E01.mkv": done(1.0)}
    assert to_continue(SHELF, saved) == [ident("Serie/Serie.S01E02.mkv")]


def test_continue_gives_one_video_per_saga_from_where_it_was_last_left() -> None:
    saved = {
        "Saga/Saga 1990.mkv": left(900.0, 1.0),
        "Saga/Saga 2 1992.mkv": done(2.0),
    }
    # The second film was watched after the first was left: the third comes next.
    assert to_continue(SHELF, saved) == [ident("Saga/Saga 3 1995.mkv")]
    saved["Saga/Saga 1990.mkv"] = left(900.0, 3.0)
    assert to_continue(SHELF, saved) == [ident("Saga/Saga 1990.mkv")]


def test_continue_skips_what_was_already_watched_and_ends_with_the_saga() -> None:
    saved = {"Saga/Saga 1990.mkv": done(2.0), "Saga/Saga 2 1992.mkv": done(1.0)}
    assert to_continue(SHELF, saved) == [ident("Saga/Saga 3 1995.mkv")]
    saved["Saga/Saga 3 1995.mkv"] = done(3.0)
    assert to_continue(SHELF, saved) == []
