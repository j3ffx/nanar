import sqlite3
from pathlib import Path

from nanar.library import build
from nanar.progress import Entry, Pick, Progress, to_continue


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


def test_marks_by_hand_and_unmarks() -> None:
    progress = Progress(None)
    progress.save("/films", "A.mkv", 1200.0, 6000.0, finished=False)
    progress.mark("/films", "A.mkv", watched=True)
    entry = progress.get("/films", "A.mkv")
    assert entry is not None
    assert entry.watched
    assert entry.position == 0.0
    assert entry.duration == 6000.0
    progress.mark("/films", "A.mkv", watched=False)
    assert progress.get("/films", "A.mkv") is None  # as if never played


def test_a_hidden_video_leaves_continue_until_played_again() -> None:
    library = build("/films", ["A 2001.mkv", "Saga/Saga 1990.mkv", "Saga/Saga 2 1992.mkv"])
    progress = Progress(None)
    progress.save("/films", "A 2001.mkv", 1200.0, 6000.0, finished=False)
    progress.save("/films", "Saga/Saga 1990.mkv", 0.0, 6000.0, finished=True)
    assert len(to_continue(library, progress.of_root("/films"))) == 2
    progress.hide("/films", "A 2001.mkv")
    progress.hide("/films", "Saga/Saga 1990.mkv")
    assert to_continue(library, progress.of_root("/films")) == []
    progress.save("/films", "A 2001.mkv", 1300.0, 6000.0, finished=False)
    assert len(to_continue(library, progress.of_root("/films"))) == 1


def test_remembers_the_tracks_picked_for_a_series(tmp_path: Path) -> None:
    db = tmp_path / "progress.db"
    Progress(db).pick("/films", "series1", "audio", Pick("en", "VO", 1))
    Progress(db).pick("/films", "series1", "sub", Pick(off=True))
    assert Progress(db).picks("/films", "series1") == {
        "audio": Pick("en", "VO", 1),
        "sub": Pick(off=True),
    }
    assert Progress(db).picks("/films", "other") == {}


def test_opens_a_database_of_an_earlier_version(tmp_path: Path) -> None:
    db = tmp_path / "progress.db"
    with sqlite3.connect(db) as old:
        old.execute(
            "CREATE TABLE progress (root TEXT NOT NULL, path TEXT NOT NULL,"
            " position REAL NOT NULL, duration REAL, watched INTEGER NOT NULL,"
            " updated REAL NOT NULL, PRIMARY KEY (root, path))"
        )
        old.execute("INSERT INTO progress VALUES ('/films', 'A.mkv', 1200, 6000, 0, 1)")
    old.close()
    entry = Progress(db).get("/films", "A.mkv")
    assert entry == Entry(1200.0, 6000.0, False, 1.0, hidden=False)
