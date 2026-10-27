"""The video library: what a folder holds, read from the names of its files.

Folders of downloaded films follow no rule. Nanar reads each file name with guessit (title, year,
season and episode), then groups what belongs together:
- the episodes of a series, whatever folders they sit in, in season and episode order;
- the films sharing a folder (a saga, a "complete collection"), in the order of their years, or of
  their names when the years are missing.
Everything else is a film on its own. Nothing is fetched from the Internet.
"""

import hashlib
import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Literal

from guessit import guessit

VIDEO_EXTENSIONS = frozenset(
    {
        ".mkv",
        ".mp4",
        ".m4v",
        ".avi",
        ".mov",
        ".wmv",
        ".webm",
        ".ts",
        ".m2ts",
        ".mpg",
        ".mpeg",
        ".ogv",
        ".flv",
        ".divx",
        ".3gp",
    }
)

# Release tags that start the technical tail of a folder name ("…MULTI.1080p.BluRay…").
_TECH = re.compile(
    r"\b(19\d\d|20\d\d|multi|vff|vfq|vfi|vf2|vostfr|french|truefrench|\d{3,4}p|4k|uhd|hdr|"
    r"hevc|x26[45]|h\.?26[45]|av1|ac3|dts|aac|bluray|bdrip|brrip|web(-?dl|rip)?|hdlight|"
    r"remux|(l[ '’])?int[ée]grale|complete|collection|coffret)\b",
    re.IGNORECASE,
)
_SITE = re.compile(r"[\[(][^\])]*(www\.|\.com|\.org|\.net|torrent)[^\])]*[\])]", re.IGNORECASE)

Kind = Literal["movie", "episode"]
GroupKind = Literal["saga", "series"]


@dataclass
class Video:
    id: str
    path: str  # relative to the library root, with "/" separators (or a URL, in the demo)
    title: str
    kind: Kind = "movie"
    year: int | None = None
    season: int | None = None
    episode: int | None = None
    episode_title: str | None = None
    group: str | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "kind": self.kind,
            "year": self.year,
            "season": self.season,
            "episode": self.episode,
            "episodeTitle": self.episode_title,
            "group": self.group,
        }


@dataclass
class Group:
    id: str
    kind: GroupKind
    title: str
    videos: list[str] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        return {"id": self.id, "kind": self.kind, "title": self.title, "videos": self.videos}


@dataclass
class Library:
    root: str
    videos: dict[str, Video] = field(default_factory=dict)
    groups: dict[str, Group] = field(default_factory=dict)

    def entries(self) -> list[tuple[Literal["video", "group"], str]]:
        """The top level, sorted by title: groups, and the videos that belong to none."""
        items: list[tuple[str, Literal["video", "group"], str]] = [
            (_sort_key(g.title), "group", g.id) for g in self.groups.values()
        ]
        items += [(_sort_key(v.title), "video", v.id) for v in self.videos.values() if not v.group]
        return [(kind, ident) for _, kind, ident in sorted(items)]

    def neighbour(self, video_id: str, step: int) -> Video | None:
        """The video before (-1) or after (+1) this one in its group, if any."""
        video = self.videos.get(video_id)
        if video is None or video.group is None:
            return None
        order = self.groups[video.group].videos
        index = order.index(video_id) + step
        return self.videos[order[index]] if 0 <= index < len(order) else None

    def to_json(self) -> dict[str, Any]:
        return {
            "root": self.root,
            "videos": {k: v.to_json() for k, v in self.videos.items()},
            "groups": {k: g.to_json() for k, g in self.groups.items()},
            "entries": [{"kind": kind, "id": ident} for kind, ident in self.entries()],
        }


def scan(root: Path) -> Library:
    """Reads every video under `root` (hidden folders skipped) into a library."""
    paths = sorted(
        p.relative_to(root).as_posix()
        for p in root.rglob("*")
        if p.suffix.lower() in VIDEO_EXTENSIONS
        and p.is_file()
        and not any(part.startswith(".") for part in p.relative_to(root).parts)
    )
    return build(str(root), paths)


def build(root: str, paths: Iterable[str]) -> Library:
    """Builds a library from relative paths (separate from `scan` so that tests need no files)."""
    library = Library(root=root)
    by_folder: dict[str, list[Video]] = {}
    series: dict[str, list[Video]] = {}
    for path in paths:
        video = _read(path)
        library.videos[video.id] = video
        if video.kind == "episode":
            series.setdefault(_fold(video.title), []).append(video)
        else:
            by_folder.setdefault(str(PurePosixPath(path).parent), []).append(video)

    for episodes in series.values():
        group = Group(id=_id("series:" + _fold(episodes[0].title)), kind="series", title="")
        group.title = episodes[0].title
        episodes.sort(key=lambda v: (v.season or 0, v.episode or 0, v.path))
        _attach(library, group, episodes)

    for folder, films in by_folder.items():
        if folder == "." or len(films) < 2:
            continue
        group = Group(id=_id("saga:" + folder), kind="saga", title=_folder_title(folder))
        dated = all(v.year for v in films)
        films.sort(key=lambda v: (v.year or 0, _natural(v.path)) if dated else _natural(v.path))
        _attach(library, group, films)
    return library


def _attach(library: Library, group: Group, videos: list[Video]) -> None:
    group.videos = [v.id for v in videos]
    for v in videos:
        v.group = group.id
    library.groups[group.id] = group


def _read(path: str) -> Video:
    pure = PurePosixPath(path)
    name = pure.name
    # The file name alone: a parent folder's release tags would mislead guessit. A season
    # folder ("Saison 1/Kaamelott - 03.avi") is the exception, as it holds the season number.
    guess: dict[str, Any] = dict(guessit(name))
    if guess.get("type") == "episode" and guess.get("season") is None and len(pure.parts) > 1:
        with_folder: dict[str, Any] = dict(guessit(f"{pure.parent.name}/{name}"))
        if with_folder.get("season") is not None:
            guess = with_folder
    title = _first_str(guess.get("title")) or _clean(pure.stem)
    year = guess.get("year") if isinstance(guess.get("year"), int) else None
    season, episode = _first_int(guess.get("season")), _first_int(guess.get("episode"))
    if guess.get("type") == "episode" and season is not None and episode is not None:
        return Video(
            id=_id(path),
            path=path,
            title=title,
            kind="episode",
            year=year,
            season=season,
            episode=episode,
            episode_title=_first_str(guess.get("episode_title")),
        )
    if guess.get("type") == "episode":
        # A film numbered inside a collection ("Le Hobbit - 1 - Un Voyage Inattendu") keeps its
        # whole name: guessit reads it as episode 1 of a series called "Le Hobbit".
        title = _clean(pure.stem)
    elif alternatives := guess.get("alternative_title"):
        # "Indiana Jones 1981 - Les Aventuriers…", "Le Hobbit - 1 - Un Voyage Inattendu"
        parts = alternatives if isinstance(alternatives, list) else [alternatives]
        title = " - ".join([title, *(str(p) for p in parts)])
    return Video(id=_id(path), path=path, title=title, year=year)


def _folder_title(folder: str) -> str:
    return _clean(PurePosixPath(folder).name) or PurePosixPath(folder).name


def _clean(name: str) -> str:
    """'[ Site.com ] Harry.Potter.L.Integrale.Des.8.Films.MULTI.1080p' → 'Harry Potter L'."""
    text = _SITE.sub(" ", name)
    if " " not in text.strip():
        text = text.replace(".", " ").replace("_", " ")
    tech = _TECH.search(text)
    if tech and tech.start() > 0:
        text = text[: tech.start()]
    return re.sub(r"\s+", " ", text).strip(" -–_.")


def _first_str(value: object) -> str | None:
    if isinstance(value, list):
        value = value[0] if value else None
    return value if isinstance(value, str) and value.strip() else None


def _first_int(value: object) -> int | None:
    if isinstance(value, list):
        value = value[0] if value else None
    return value if isinstance(value, int) else None


def _fold(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return re.sub(
        r"[^a-z0-9]+", " ", "".join(c for c in decomposed if not unicodedata.combining(c))
    )


def _sort_key(title: str) -> str:
    return re.sub(r"^(le|la|les|l|the|a|an) ", "", _fold(title).strip())


def _natural(text: str) -> list[int | str]:
    return [int(part) if part.isdigit() else part for part in re.split(r"(\d+)", _fold(text))]


def _id(text: str) -> str:
    return hashlib.blake2s(text.encode(), digest_size=6).hexdigest()
