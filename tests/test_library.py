from pathlib import Path

from nanar import demo
from nanar.library import build, scan

# Names as downloaded films come, with made-up titles.
PATHS = [
    "Le.Requin.Volant.1987.MULTi.VFF.1080p.BluRay.x264-NANAR.mkv",
    "Karaté Cowboy 1984 - La Ruée vers l'Or.mkv",
    "[ www.Exemple.test ] Robo.Facteur.L.Integrale.Des.3.Films.MULTI.1080p/"
    "Robo.Facteur.3.1995.MULTI.1080p.BluRay.x264-NANAR.mkv",
    "[ www.Exemple.test ] Robo.Facteur.L.Integrale.Des.3.Films.MULTI.1080p/"
    "Robo.Facteur.1990.MULTI.1080p.BluRay.x264-NANAR.mkv",
    "[ www.Exemple.test ] Robo.Facteur.L.Integrale.Des.3.Films.MULTI.1080p/"
    "Robo.Facteur.2.1992.MULTI.1080p.BluRay.x264-NANAR.mkv",
    "Ninja Express - integrale - HEVC/Ninja Express - 2 - Le Retour - 1080p.mkv",
    "Ninja Express - integrale - HEVC/Ninja Express - 1 - Le Départ - 1080p.mkv",
    "Les Brigades/Saison 2/Les.Brigades.S02E01.Panique.720p.mkv",
    "Les Brigades/Saison 1/Les.Brigades.S01E02.Fausse.Piste.720p.mkv",
    "Les Brigades/Saison 1/Les.Brigades.S01E01.Le.Commissaire.720p.mkv",
]


def ids_by_path(paths: list[str]) -> dict[str, str]:
    lib = build("/films", paths)
    return {v.path: v.id for v in lib.videos.values()} | {
        g.title: g.id for g in lib.groups.values()
    }


def test_reads_titles_and_years_from_release_names() -> None:
    lib = build("/films", PATHS)
    films = {v.title: v.year for v in lib.videos.values() if v.kind == "movie"}
    assert films["Le Requin Volant"] == 1987
    assert films["Karaté Cowboy - La Ruée vers l'Or"] == 1984
    assert films["Ninja Express - 2 - Le Retour"] is None


def test_groups_a_folder_of_films_into_a_saga_in_year_order() -> None:
    lib = build("/films", PATHS)
    saga = next(g for g in lib.groups.values() if g.title == "Robo Facteur")
    assert saga.kind == "saga"
    assert [lib.videos[v].year for v in saga.videos] == [1990, 1992, 1995]


def test_orders_a_saga_without_years_by_name() -> None:
    lib = build("/films", PATHS)
    saga = next(g for g in lib.groups.values() if g.title == "Ninja Express")
    assert [lib.videos[v].title for v in saga.videos] == [
        "Ninja Express - 1 - Le Départ",
        "Ninja Express - 2 - Le Retour",
    ]


def test_groups_episodes_into_a_series_across_season_folders() -> None:
    lib = build("/films", PATHS)
    series = next(g for g in lib.groups.values() if g.kind == "series")
    assert series.title == "Les Brigades"
    episodes = [(lib.videos[v].season, lib.videos[v].episode) for v in series.videos]
    assert episodes == [(1, 1), (1, 2), (2, 1)]
    assert lib.videos[series.videos[0]].episode_title == "Le Commissaire"


def test_lists_groups_and_lone_films_by_title_ignoring_articles() -> None:
    lib = build("/films", PATHS)
    titles = [
        (lib.groups[i].title if kind == "group" else lib.videos[i].title)
        for kind, i in lib.entries()
    ]
    assert titles == [
        "Les Brigades",
        "Karaté Cowboy - La Ruée vers l'Or",
        "Ninja Express",
        "Le Requin Volant",
        "Robo Facteur",
    ]


def test_finds_the_neighbours_inside_a_group() -> None:
    lib = build("/films", PATHS)
    series = next(g for g in lib.groups.values() if g.kind == "series")
    first, second, third = series.videos
    assert lib.neighbour(first, 1) == lib.videos[second]
    assert lib.neighbour(third, 1) is None
    assert lib.neighbour(first, -1) is None
    lone = next(v for v in lib.videos.values() if v.group is None)
    assert lib.neighbour(lone.id, 1) is None


def test_ids_stay_the_same_from_one_scan_to_the_next() -> None:
    assert ids_by_path(PATHS) == ids_by_path(list(reversed(PATHS)))


def test_scans_video_files_and_skips_the_rest(tmp_path: Path) -> None:
    (tmp_path / "Saga").mkdir()
    (tmp_path / ".cache").mkdir()
    for name in ("Saga/A 1990.mkv", "Saga/B 1991.MP4", "Seul 2001.avi", ".cache/X 2000.mkv"):
        (tmp_path / name).write_bytes(b"")
    (tmp_path / "notes.nfo").write_text("not a video")
    lib = scan(tmp_path)
    assert sorted(v.path for v in lib.videos.values()) == [
        "Saga/A 1990.mkv",
        "Saga/B 1991.MP4",
        "Seul 2001.avi",
    ]
    assert len(lib.groups) == 1


def test_the_demo_library_has_sagas_series_and_films() -> None:
    lib = demo.library()
    assert {g.kind for g in lib.groups.values()} == {"saga", "series"}
    assert all(v.path.startswith("av://lavfi:") for v in lib.videos.values())
