"""TMDb and OpenSubtitles, answered by the tests: nothing goes to the network here."""

import json
import struct
import time
from pathlib import Path
from typing import Any

import pytest

from nanar.library import build
from nanar.metadata import Metadata
from nanar.online import OnlineError, OpenSubtitles, Request, Tmdb, Wanted, moviehash
from nanar.subtitles import Subtitles


class Answers:
    """A fake network: answers by the start of the URL, and keeps every request."""

    def __init__(self, answers: dict[str, Any]) -> None:
        self.answers = answers
        self.asked: list[Request] = []

    def __call__(self, request: Request) -> bytes:
        self.asked.append(request)
        for prefix, answer in self.answers.items():
            if request.url.startswith(prefix):
                if isinstance(answer, Exception):
                    raise answer
                return answer if isinstance(answer, bytes) else json.dumps(answer).encode()
        raise OnlineError("offline")


MOVIE = {"results": [{"id": 7, "overview": "Un yéti.", "poster_path": "/yeti.jpg"}]}


def test_tmdb_finds_a_film_by_title_and_year_with_an_api_key() -> None:
    net = Answers({"https://api.themoviedb.org/3/search/movie": MOVIE})
    info = Tmdb("abc123", net).search("movie", "Le Retour du Yeti Laser", 2001)
    assert info is not None
    assert (info.tmdb_id, info.overview, info.poster) == (7, "Un yéti.", "/yeti.jpg")
    url = net.asked[0].url
    assert "api_key=abc123" in url
    assert "year=2001" in url
    assert "language=fr-FR" in url


def test_tmdb_takes_a_read_token_as_a_bearer_and_tries_without_the_year() -> None:
    net = Answers(
        {
            "https://api.themoviedb.org/3/search/tv?query=Kaamelott&language=fr-FR&include_adult"
            "=false&first_air_date_year=2004": {"results": []},
            "https://api.themoviedb.org/3/search/tv": {"results": [{"id": 3}]},
        }
    )
    info = Tmdb("eyJtoken", net).search("tv", "Kaamelott", 2004)
    assert info is not None
    assert info.poster is None
    assert net.asked[0].headers["Authorization"] == "Bearer eyJtoken"
    assert "api_key" not in net.asked[0].url
    assert len(net.asked) == 2


def test_opensubtitles_prefers_the_release_timed_for_this_video() -> None:
    found = {
        "data": [
            {"attributes": {"download_count": 900, "files": [{"file_id": 1}]}},
            {
                "attributes": {
                    "download_count": 10,
                    "moviehash_match": True,
                    "files": [{"file_id": 2}],
                }
            },
        ]
    }
    net = Answers({"https://api.opensubtitles.com/api/v1/subtitles": found})
    client = OpenSubtitles("key", net)
    assert client.best(Wanted("Série", season=1, episode=2, hash="00ff")) == 2
    asked = net.asked[0]
    assert asked.headers["Api-Key"] == "key"
    assert "episode_number=2" in asked.url
    assert "moviehash=00ff" in asked.url
    assert "type=episode" in asked.url


def test_opensubtitles_downloads_through_the_link_it_gives() -> None:
    net = Answers(
        {
            "https://api.opensubtitles.com/api/v1/download": {"link": "https://dl.example/1.srt"},
            "https://dl.example/1.srt": b"1\n00:00:01,000 --> 00:00:02,000\nBonjour\n",
        }
    )
    assert OpenSubtitles("key", net).download(5).startswith(b"1\n")
    assert json.loads(net.asked[0].body or b"") == {"file_id": 5}


def test_the_hash_of_a_video_follows_opensubtitles_rule(tmp_path: Path) -> None:
    video = tmp_path / "v.mkv"
    words = [1] * (65536 * 2 // 8)
    video.write_bytes(struct.pack(f"<{len(words)}Q", *words))
    size = video.stat().st_size
    assert moviehash(video) == f"{size + len(words):016x}"
    tiny = tmp_path / "tiny.mkv"
    tiny.write_bytes(b"x")
    assert moviehash(tiny) is None


def test_metadata_looks_each_title_up_once_and_keeps_it(tmp_path: Path) -> None:
    library = build("/films", ["Yeti 2001.mkv", "Show/Show.S01E01.mkv", "Show/Show.S01E02.mkv"])
    net = Answers(
        {
            "https://api.themoviedb.org/3/search/movie": MOVIE,
            "https://api.themoviedb.org/3/search/tv": {"results": []},
            "https://image.tmdb.org/t/p/w500/yeti.jpg": b"jpeg",
        }
    )
    ready: list[bool] = []
    metadata = Metadata(tmp_path, on_ready=lambda: ready.append(True), make=lambda k: Tmdb(k, net))
    yeti = next(v for v in library.videos.values() if v.title == "Yeti")
    metadata.schedule(library)  # no key: nothing asked
    assert metadata.of_video(library, yeti) is None
    metadata.configure("abc123")
    metadata.schedule(library)
    deadline = time.monotonic() + 5
    while not ready and time.monotonic() < deadline:
        time.sleep(0.02)
    metadata.stop()
    info = metadata.of_video(library, yeti)
    assert info is not None
    assert info["overview"] == "Un yéti."
    poster = metadata.poster(info)
    assert poster is not None
    assert poster.read_bytes() == b"jpeg"
    series = next(iter(library.groups))
    assert metadata.of_group(library, series) is None  # TMDb knew nothing

    again = Metadata(tmp_path, on_ready=lambda: None, make=lambda k: Tmdb(k, net))
    again.configure("abc123")
    asked = len(net.asked)
    again.schedule(library)  # all known: nothing asked again
    again.stop()
    assert len(net.asked) == asked
    assert again.of_video(library, yeti) is not None
    again.configure("")  # the key taken away: nothing shown any more
    assert again.of_video(library, yeti) is None


def test_subtitles_are_downloaded_once_into_the_data_directory(tmp_path: Path) -> None:
    library = build("/films", ["Yeti 2001.mkv"])
    (video,) = library.videos.values()
    net = Answers(
        {
            "https://api.opensubtitles.com/api/v1/subtitles": {
                "data": [{"attributes": {"files": [{"file_id": 9}]}}]
            },
            "https://api.opensubtitles.com/api/v1/download": {"link": "https://dl.example/9"},
            "https://dl.example/9": b"srt",
        }
    )
    subtitles = Subtitles(tmp_path, make=lambda k: OpenSubtitles(k, net))
    with pytest.raises(OnlineError, match="online_off"):
        subtitles.find("/films", video, None)
    subtitles.configure("key")
    found = subtitles.find("/films", video, None)
    assert found.read_bytes() == b"srt"
    assert found.parent == tmp_path
    assert subtitles.saved("/films", video) == [found]
    subtitles.find("/films", video, None)
    assert len(net.asked) == 3  # not asked again


def test_no_subtitles_found_says_so(tmp_path: Path) -> None:
    library = build("/films", ["Yeti 2001.mkv"])
    (video,) = library.videos.values()
    net = Answers({"https://api.opensubtitles.com/api/v1/subtitles": {"data": []}})
    subtitles = Subtitles(tmp_path, make=lambda k: OpenSubtitles(k, net))
    subtitles.configure("key")
    with pytest.raises(OnlineError, match="no_subtitles"):
        subtitles.find("/films", video, None)
