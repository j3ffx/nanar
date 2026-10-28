"""The demo library: made-up films and episodes, played as videos mpv generates on the fly.

It needs no file at all, so development, tests and screenshots never touch anyone's films.
"""

import re

from nanar.library import Library, build

# Fictitious titles, laid out as downloaded files usually are.
NAMES = [
    "Le.Retour.du.Yeti.Laser.2001.MULTi.1080p.BluRay.x264-NANAR.mkv",
    "La Trilogie du Requin Volant/Le Requin Volant 2 - La Revanche 1989.mkv",
    "La Trilogie du Requin Volant/Le Requin Volant 3 - Requin Contre Requin 1991.mkv",
    "La Trilogie du Requin Volant/Le Requin Volant 1987.mkv",
    "Les Brigades du Nanar/Saison 1/Les.Brigades.du.Nanar.S01E01.Le.Commissaire.720p.mkv",
    "Les Brigades du Nanar/Saison 1/Les.Brigades.du.Nanar.S01E02.Fausse.Piste.720p.mkv",
    "Les Brigades du Nanar/Saison 1/Les.Brigades.du.Nanar.S01E03.Le.Retour.720p.mkv",
    "Les Brigades du Nanar/Saison 2/Les.Brigades.du.Nanar.S02E01.Panique.au.Port.720p.mkv",
    "Karaté Cowboy (1984).avi",
    "[ www.Exemple.test ] Zombies.Au.Ski.2003.FRENCH.DVDRip.XviD.avi",
    "Ninja Express 1985 VFF 720p.mkv",
    "Mission Galaxie Oméga 1979 MULTi 1080p x265.mkv",
    "Les.Vampires.du.Camping.1996.TRUEFRENCH.WEB-DL.1080p.mkv",
    "Robo-Facteur.2 (1992).mp4",
]

# Hues for the generated pictures, so that each video looks a little different.
_HUES = [0, 40, 80, 120, 160, 200, 240, 280, 320]


SECONDS = 300  # each made-up video lasts five minutes


def source(index: int, seconds: int = SECONDS) -> str:
    """A video mpv generates (test pattern and a tone), with a French and an English track."""
    hue = _HUES[index % len(_HUES)]
    # Small: its raw pictures fill the cache that lets the player jump back (player.py).
    video = f"testsrc2=size=640x360:rate=25:duration={seconds},hue=h={hue}"
    tone = 220 + 55 * (index % 5)
    return (
        f"av://lavfi:{video}[out0];"
        f"sine=frequency={tone}:duration={seconds}[out1];"
        f"sine=frequency={tone * 2}:duration={seconds}[out2]"
    )


def is_generated(source: str) -> bool:
    return source.startswith("av://lavfi:")


def from_time(source: str, at: float) -> str:
    """The picture of a generated video from `at` seconds on, small and silent. Its stream can't
    seek: the frames before are generated (quickly, at that size) and dropped."""
    picture = source.removeprefix("av://lavfi:").split(";")[0]
    picture = re.sub(r"size=\d+x\d+", "size=320x180", picture)
    picture = re.sub(r"duration=\d+", f"duration={at + 1:g}", picture)
    return "av://lavfi:" + picture.replace("[out0]", f",trim=start={at:g}[out0]")


def library() -> Library:
    lib = build("Démo", NAMES)
    for index, video in enumerate(lib.videos.values()):
        video.path = source(index)
    return lib
