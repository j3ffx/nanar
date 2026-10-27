from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from nanar.app import Network, create_app
from nanar.config import Settings
from nanar.controller import Controller
from nanar.library import build

from .fakes import FakeSessions

KEY = "k3y-for-the-tests-only"
TV = ("127.0.0.1", 50000)  # this machine
PHONE = ("192.168.1.20", 50000)  # a phone on the same network (addresses reserved for docs)


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
def app(controller: Controller) -> FastAPI:
    network = Network(port=8642, addresses=lambda: ["192.168.1.10"])
    return create_app(controller, key=KEY, network=network)


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    """The TV page, in Nanar's window."""
    return TestClient(app, base_url="http://127.0.0.1:8642", client=TV)


@pytest.fixture
def phone(app: FastAPI) -> TestClient:
    """A phone that has not paired yet."""
    return TestClient(app, base_url="http://192.168.1.10:8642", client=PHONE)


def first_film(client: TestClient) -> str:
    entries = client.get("/api/library").json()["entries"]
    return str(next(e["id"] for e in entries if e["kind"] == "video"))


def pair(phone: TestClient) -> None:
    assert phone.post("/api/pair", json={"key": KEY}).status_code == 204


# This machine ----------------------------------------------------------------------------------


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
    assert sessions.last.osd == [False]  # mpv's own window: nothing more to say on screen


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


def test_gives_the_tv_the_qr_code_to_show(client: TestClient) -> None:
    pairing = client.get("/api/pairing").json()
    assert pairing == {
        "lan": True,
        "name": None,
        "addresses": ["192.168.1.10:8642"],
        "url": f"http://192.168.1.10:8642/#k={KEY}",
    }
    qr = client.get("/api/pairing/qr.svg")
    assert qr.headers["content-type"] == "image/svg+xml"
    assert 'xmlns="http://www.w3.org/2000/svg"' in qr.text  # or an <img> shows nothing


def test_gives_the_fixed_name_while_it_is_announced(controller: Controller) -> None:
    network = Network(port=8642, addresses=lambda: ["192.168.1.10"], name=lambda: "nanar.local")
    client = TestClient(create_app(controller, key=KEY, network=network), client=TV)
    assert client.get("http://127.0.0.1:8642/api/pairing").json()["name"] == "nanar.local:8642"


def test_any_page_may_ask_whether_nanar_answers(phone: TestClient) -> None:
    response = phone.get("/api/health", headers={"Origin": "http://192.168.1.10:8642"})
    assert response.headers["access-control-allow-origin"] == "*"


def test_says_when_phones_cannot_connect(controller: Controller) -> None:
    app = create_app(controller, key=KEY, network=Network(port=8642, lan=False))
    client = TestClient(app, base_url="http://127.0.0.1:8642", client=TV)
    assert client.get("/api/pairing").json() == {
        "lan": False,
        "name": None,
        "addresses": [],
        "url": None,
    }
    assert client.get("/api/pairing/qr.svg").status_code == 404


def test_refuses_a_rebinding_host_even_from_this_machine(app: FastAPI) -> None:
    rebinding = TestClient(app, base_url="http://evil.example.com", client=TV)
    response = rebinding.get("/api/state")
    assert response.status_code == 401
    assert response.json() == {"code": "pairing_required"}


def test_refuses_state_changes_without_a_json_body(client: TestClient) -> None:
    response = client.post(
        "/api/command", content="action=stop", headers={"Content-Type": "text/plain"}
    )
    assert response.status_code == 415


def test_refuses_a_websocket_from_another_site(client: TestClient) -> None:
    with (
        pytest.raises(WebSocketDisconnect),
        client.websocket_connect(
            "ws://127.0.0.1:8642/api/live", headers={"Origin": "http://evil.example.com"}
        ) as ws,
    ):
        ws.receive_json()


def test_unknown_api_paths_are_404(client: TestClient) -> None:
    assert client.get("/api/nope").status_code == 404


# Phones ----------------------------------------------------------------------------------------


def test_an_unpaired_phone_gets_nothing_but_the_page(phone: TestClient) -> None:
    assert phone.get("/api/state").json() == {"code": "pairing_required"}
    assert phone.get("/api/library").status_code == 401
    assert phone.post("/api/command", json={"action": "stop"}).status_code == 401
    assert phone.get("/api/pairing").status_code == 401
    assert phone.get("/api/health").status_code == 200
    with pytest.raises(WebSocketDisconnect), phone.websocket_connect("/api/live") as ws:
        ws.receive_json()


def test_a_wrong_key_does_not_pair(phone: TestClient) -> None:
    response = phone.post("/api/pair", json={"key": "guess"})
    assert response.status_code == 403
    assert response.json() == {"code": "wrong_key"}
    assert "set-cookie" not in response.headers
    assert phone.get("/api/state").status_code == 401


def test_a_paired_phone_drives_nanar_and_the_tv_says_so(
    phone: TestClient, sessions: FakeSessions
) -> None:
    pair(phone)
    cookie = phone.cookies.get("nanar_key")
    assert cookie == KEY
    assert phone.post("/api/play", json={"videoId": first_film(phone)}).status_code == 204
    assert phone.post("/api/command", json={"action": "pause"}).status_code == 204
    assert sessions.last.osd == [True]


def test_the_cookie_is_kept_from_other_sites(phone: TestClient) -> None:
    header = phone.post("/api/pair", json={"key": KEY}).headers["set-cookie"].lower()
    assert "httponly" in header
    assert "samesite=strict" in header


def test_a_bearer_key_works_too(app: FastAPI) -> None:
    script = TestClient(
        app,
        base_url="http://192.168.1.10:8642",
        client=PHONE,
        headers={"Authorization": f"Bearer {KEY}"},
    )
    assert script.get("/api/state").status_code == 200


def test_the_tv_counts_the_phones_connected(
    client: TestClient, phone: TestClient, controller: Controller
) -> None:
    pair(phone)
    with client.websocket_connect("ws://127.0.0.1:8642/api/live") as tv:
        assert tv.receive_json()["state"]["phones"] == 0
        with phone.websocket_connect("ws://192.168.1.10:8642/api/live") as remote:
            remote.receive_json()
            assert tv.receive_json()["state"]["phones"] == 1
        assert tv.receive_json()["state"]["phones"] == 0


def test_the_home_screen_icon_of_a_paired_phone_is_paired_too(phone: TestClient) -> None:
    assert phone.get("/manifest.webmanifest").json()["start_url"] == "/"
    pair(phone)
    manifest = phone.get("/manifest.webmanifest").json()
    assert manifest["start_url"] == f"/#k={KEY}"
    assert manifest["display"] == "standalone"


def test_the_tv_follows_what_a_phone_looks_at(client: TestClient, phone: TestClient) -> None:
    pair(phone)
    before = client.get("/api/state").json()["view"]["seq"]
    assert phone.post("/api/view", json={"path": "/g/abc", "focus": "v1"}).status_code == 204
    view = client.get("/api/state").json()["view"]
    assert view == {"path": "/g/abc", "focus": "v1", "seq": before + 1}
    assert phone.post("/api/view", json={"path": "http://evil"}).status_code == 409


def test_serves_the_pictures_it_has(client: TestClient) -> None:
    assert client.get("/api/thumb/v/nope").status_code == 404
    assert client.get("/api/thumb/x/nope").status_code == 404
