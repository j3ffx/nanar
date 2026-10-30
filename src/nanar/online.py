"""The two services Nanar may ask, when the user gave it their key (off otherwise).

- TMDb (themoviedb.org): a poster and a summary for each film and series. Nanar sends the title
  and the year read from the file name, nothing else.
- OpenSubtitles (opensubtitles.com): French subtitles for the video playing, when asked from the
  phone. Nanar sends the title, the year, the season and episode, and the video's "hash" (a
  checksum of its first and last 64 KiB, which finds subtitles timed for that very release).

Nothing else ever leaves the PC: no account, no list of the library, no address.
"""

import json
import os
import struct
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from nanar import __version__

TIMEOUT = 15.0
USER_AGENT = f"Nanar v{__version__}"
TMDB = "https://api.themoviedb.org/3"
TMDB_IMAGES = "https://image.tmdb.org/t/p/w500"
OPENSUBTITLES = "https://api.opensubtitles.com/api/v1"


class OnlineError(Exception):
    """`code`: "bad_key", "quota_reached", "offline" (or the service failed)."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class Request:
    url: str
    headers: dict[str, str]
    body: bytes | None = None


Fetch = Callable[[Request], bytes]  # tests give their own: no network there


def fetch(request: Request) -> bytes:
    """One request, tried a second time when the connection drops (OpenSubtitles' servers close
    one now and then)."""
    try:
        return _fetch_once(request)
    except OnlineError as error:
        if error.code != "dropped":
            raise
    try:
        return _fetch_once(request)
    except OnlineError as error:
        raise OnlineError("offline" if error.code == "dropped" else error.code) from None


def _fetch_once(request: Request) -> bytes:
    method = "POST" if request.body is not None else "GET"
    raw = urllib.request.Request(
        request.url,
        data=request.body,
        headers={"User-Agent": USER_AGENT, **request.headers},
        method=method,
    )
    try:
        with urllib.request.urlopen(raw, timeout=TIMEOUT) as response:
            data: bytes = response.read()
            return data
    except urllib.error.HTTPError as error:
        if error.code in (401, 403):
            raise OnlineError("bad_key") from None
        if error.code in (406, 429):
            raise OnlineError("quota_reached") from None
        raise OnlineError("offline") from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise OnlineError("dropped") from None


@dataclass(frozen=True)
class Info:
    """What TMDb knows of a film or a series."""

    tmdb_id: int
    overview: str
    poster: str | None  # its path at TMDb ("/abc.jpg")


class Tmdb:
    def __init__(self, key: str, get: Fetch = fetch) -> None:
        self._key = key.strip()
        self._get = get

    def _request(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        headers = {"Accept": "application/json"}
        query = {k: v for k, v in params.items() if v is not None}
        if self._key.startswith("eyJ"):  # a read access token (v4)
            headers["Authorization"] = f"Bearer {self._key}"
        else:  # an API key (v3)
            query["api_key"] = self._key
        url = f"{TMDB}{path}?{urllib.parse.urlencode(query)}"
        data: dict[str, Any] = json.loads(self._get(Request(url, headers)))
        return data

    def check(self) -> None:
        """Raises OnlineError("bad_key") when TMDb refuses the key."""
        self._request("/configuration", {})

    def search(self, kind: str, title: str, year: int | None) -> Info | None:
        """A film ("movie") or a series ("tv"), in French when TMDb has it."""
        params: dict[str, Any] = {"query": title, "language": "fr-FR", "include_adult": "false"}
        params["year" if kind == "movie" else "first_air_date_year"] = year
        results = self._request(f"/search/{kind}", params).get("results") or []
        if not results and year is not None:  # the year in a file name is not always right
            params.pop("year", None)
            params.pop("first_air_date_year", None)
            results = self._request(f"/search/{kind}", params).get("results") or []
        if not results:
            return None
        best = results[0]
        return Info(int(best["id"]), str(best.get("overview") or ""), best.get("poster_path"))

    def poster(self, path: str) -> bytes:
        return self._get(Request(TMDB_IMAGES + path, {}))


def moviehash(path: Path) -> str | None:
    """OpenSubtitles' hash: the size plus the 64-bit little-endian words of the first and last
    64 KiB, kept to 64 bits."""
    chunk = 65536
    try:
        size = os.path.getsize(path)
        if size < chunk * 2:
            return None
        total = size
        with path.open("rb") as file:
            for offset in (0, size - chunk):
                file.seek(offset)
                for (word,) in struct.iter_unpack("<Q", file.read(chunk)):
                    total = (total + word) & 0xFFFFFFFFFFFFFFFF
    except OSError:
        return None
    return f"{total:016x}"


@dataclass(frozen=True)
class Wanted:
    """What the subtitles are for."""

    title: str
    year: int | None = None
    season: int | None = None
    episode: int | None = None
    hash: str | None = None
    language: str = "fr"


class OpenSubtitles:
    def __init__(self, key: str, get: Fetch = fetch) -> None:
        self._key = key.strip()
        self._get = get

    def _headers(self) -> dict[str, str]:
        return {"Api-Key": self._key, "Accept": "application/json"}

    def check(self) -> None:
        """Raises OnlineError("bad_key") when OpenSubtitles refuses the key (a search does: its
        lists of formats and languages answer anyone)."""
        self._get(Request(f"{OPENSUBTITLES}/discover/popular?language=fr", self._headers()))

    def best(self, wanted: Wanted) -> int | None:
        """The file to download: one timed for this very video when there is, else the most
        downloaded."""
        params: dict[str, Any] = {"languages": wanted.language, "query": wanted.title.lower()}
        if wanted.season is not None and wanted.episode is not None:
            params |= {"season_number": wanted.season, "episode_number": wanted.episode}
            params["type"] = "episode"
        else:
            params["type"] = "movie"
            if wanted.year is not None:
                params["year"] = wanted.year
        if wanted.hash:
            params["moviehash"] = wanted.hash
        url = f"{OPENSUBTITLES}/subtitles?{urllib.parse.urlencode(sorted(params.items()))}"
        found = json.loads(self._get(Request(url, self._headers()))).get("data") or []
        candidates = []
        for item in found:
            attributes = item.get("attributes") or {}
            files = attributes.get("files") or []
            if not files:
                continue
            score = (bool(attributes.get("moviehash_match")), attributes.get("download_count", 0))
            candidates.append((score, int(files[0]["file_id"])))
        return max(candidates)[1] if candidates else None

    def download(self, file_id: int) -> bytes:
        headers = self._headers() | {"Content-Type": "application/json"}
        body = json.dumps({"file_id": file_id}).encode()
        answer = json.loads(self._get(Request(f"{OPENSUBTITLES}/download", headers, body)))
        link = answer.get("link")
        if not link:
            raise OnlineError("quota_reached")
        return self._get(Request(str(link), {}))
