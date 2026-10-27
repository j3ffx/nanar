from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from nanar.config import Settings
from nanar.controller import Controller
from nanar.library import build

from .fakes import FakeSessions


@pytest.fixture
def sessions() -> FakeSessions:
    return FakeSessions()


@pytest.fixture
def controller(sessions: FakeSessions, tmp_path: Path) -> Iterator[Controller]:
    library = build("/films", ["Seul 2001.mkv", "Saga/Saga 1990.mkv", "Saga/Saga 2 1992.mkv"])
    c = Controller(library, Settings(), tmp_path / "settings.json", sessions)
    yield c
    c.shutdown()


@pytest.fixture
def client(controller: Controller) -> TestClient:
    from nanar.app import create_app

    return TestClient(create_app(controller), base_url="http://127.0.0.1:8642")


def first_film(client: TestClient) -> str:
    entries = client.get("/api/library").json()["entries"]
    return str(next(e["id"] for e in entries if e["kind"] == "video"))


def test_lists_the_library(client: TestClient) -> None:
    library = client.get("/api/library").json()
    assert library["root"] == "/films"
    assert [e["kind"] for e in library["entries"]] == ["group", "video"]
    assert len(library["videos"]) == 3


def test_plays_and_reports_the_state(client: TestClient, sessions: FakeSessions) -> None:
    assert client.post("/api/play", json={"videoId": first_film(client)}).status_code == 204
    assert sessions.last.start.title == "Seul"
    state = client.get("/api/state").json()
    assert state["playing"]["video"]["title"] == "Seul"
    assert client.post("/api/command", json={"action": "seek", "value": 10}).status_code == 204
    assert sessions.last.commands == [("seek", 10)]


def test_reports_errors_with_a_code(client: TestClient) -> None:
    response = client.post("/api/command", json={"action": "pause"})
    assert response.status_code == 409
    assert response.json() == {"code": "nothing_playing"}
    assert client.post("/api/play", json={"videoId": "nope"}).json() == {"code": "unknown_video"}


def test_streams_the_state_over_a_websocket(client: TestClient) -> None:
    with client.websocket_connect("ws://127.0.0.1:8642/api/live") as socket:
        assert socket.receive_json()["state"]["playing"] is None
        client.post("/api/play", json={"videoId": first_film(client)})
        assert socket.receive_json()["state"]["playing"]["video"]["title"] == "Seul"


def test_refuses_other_hosts(controller: Controller) -> None:
    from nanar.app import create_app

    rebinding = TestClient(create_app(controller), base_url="http://evil.example.com")
    response = rebinding.get("/api/state")
    assert response.status_code == 403
    assert response.json() == {"code": "forbidden_host"}


def test_refuses_state_changes_without_a_json_body(client: TestClient) -> None:
    response = client.post(
        "/api/command", content="action=stop", headers={"Content-Type": "text/plain"}
    )
    assert response.status_code == 415


def test_refuses_a_websocket_from_another_site(client: TestClient) -> None:
    from starlette.websockets import WebSocketDisconnect

    with (
        pytest.raises(WebSocketDisconnect),
        client.websocket_connect(
            "ws://127.0.0.1:8642/api/live", headers={"Origin": "http://evil.example.com"}
        ) as ws,
    ):
        ws.receive_json()


def test_unknown_api_paths_are_404(client: TestClient) -> None:
    assert client.get("/api/nope").status_code == 404
