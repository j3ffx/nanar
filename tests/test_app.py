import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from nanar.app import Network, create_app
from nanar.config import Settings
from nanar.controller import Controller
from nanar.hotspot import HotspotError, Status
from nanar.library import build
from nanar.previews import Previews

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
    assert pairing.pop("instance")
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
    pairing = client.get("/api/pairing").json()
    assert not pairing["lan"]
    assert pairing["url"] is None
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
    assert view == {
        "path": "/g/abc",
        "focus": "v1",
        "filter": {"query": "", "kind": "all", "unwatched": False},
        "seq": before + 1,
    }
    assert phone.post("/api/view", json={"path": "http://evil"}).status_code == 422


def test_the_tv_shows_what_a_phone_searches(client: TestClient, phone: TestClient) -> None:
    pair(phone)
    searched = {"query": "requin", "kind": "films", "unwatched": True}
    assert phone.post("/api/view", json={"path": "/", "filter": searched}).status_code == 204
    assert client.get("/api/state").json()["view"]["filter"] == searched
    wrong = {"path": "/", "filter": {"kind": "everything"}}
    assert phone.post("/api/view", json=wrong).status_code == 422
    too_long = {"path": "/", "filter": {"query": "x" * 101}}
    assert phone.post("/api/view", json=too_long).status_code == 422


def test_serves_the_pictures_it_has(client: TestClient) -> None:
    assert client.get("/api/thumb/v/nope").status_code == 404
    assert client.get("/api/thumb/x/nope").status_code == 404


def test_previews_frames_of_the_video_playing_only(
    client: TestClient, controller: Controller, tmp_path: Path
) -> None:
    def grab(source: str, at: float, destination: Path) -> bool:
        destination.write_bytes(f"{at}".encode())
        return True

    controller.previews = Previews(tmp_path / "previews", grab=grab)
    film = first_film(client)
    nothing = client.get(f"/api/preview/{film}?at=60")
    assert nothing.status_code == 409
    assert nothing.json() == {"code": "nothing_playing"}
    controller.play(film)
    assert client.get(f"/api/preview/{film}?at=62").content == b"60"
    assert client.get("/api/preview/other?at=62").status_code == 409


class FakeDesktop:
    def __init__(self) -> None:
        self.opened: list[str] = []
        self.fronted = 0
        self.integrated: list[bool] = []
        self.picked: str | None = "/picked"

    def open(self, folder: str) -> None:
        self.opened.append(folder)

    def choose(self) -> str | None:
        return self.picked

    def bring_to_front(self) -> None:
        self.fronted += 1

    def integrate(self, install: bool) -> None:
        self.integrated.append(install)

    def update(self) -> None:
        self.updated = True


def desktop_app(controller: Controller, desktop: FakeDesktop) -> tuple[TestClient, TestClient]:
    app = create_app(controller, key=KEY, network=Network(port=8642), desktop=desktop)
    tv = TestClient(app, base_url="http://127.0.0.1:8642", client=TV)
    phone = TestClient(app, base_url="http://192.168.1.10:8642", client=PHONE)
    return tv, phone


def test_a_second_launch_hands_its_folder_over(controller: Controller) -> None:
    desktop = FakeDesktop()
    tv, _ = desktop_app(controller, desktop)
    assert tv.post("/api/open", json={"path": "D:/Films"}).status_code == 204
    assert desktop.opened == ["D:/Films"]
    assert desktop.fronted == 1
    assert tv.post("/api/open", json={}).status_code == 204  # no folder: just to the front
    assert desktop.opened == ["D:/Films"]


def test_the_tv_page_asks_for_a_folder_with_the_system_picker(controller: Controller) -> None:
    desktop = FakeDesktop()
    tv, _ = desktop_app(controller, desktop)
    tv.post("/api/open", json={"choose": True})
    assert desktop.opened == ["/picked"]
    desktop.picked = None  # cancelled
    tv.post("/api/open", json={"choose": True})
    assert desktop.opened == ["/picked"]


def test_only_this_machine_opens_folders_or_touches_menus(controller: Controller) -> None:
    desktop = FakeDesktop()
    _, phone = desktop_app(controller, desktop)
    pair(phone)
    assert phone.post("/api/open", json={"path": "C:/"}).json() == {"code": "this_machine_only"}
    assert phone.post("/api/integration", json={"install": True}).status_code == 403
    assert desktop.opened == []
    assert desktop.integrated == []


def test_answering_the_menus_offer_hides_it(controller: Controller) -> None:
    desktop = FakeDesktop()
    tv, _ = desktop_app(controller, desktop)
    controller.set_integration_offer(True)
    assert tv.get("/api/state").json()["offerIntegration"] is True
    assert tv.post("/api/integration", json={"install": False}).status_code == 204
    assert desktop.integrated == [False]
    assert tv.get("/api/state").json()["offerIntegration"] is False


def test_marks_a_video_from_a_phone(client: TestClient) -> None:
    film = first_film(client)
    assert client.post("/api/mark", json={"videoId": film, "action": "watched"}).status_code == 204
    assert client.get("/api/library").json()["videos"][film]["progress"]["watched"]
    bad = client.post("/api/mark", json={"videoId": film, "action": "burn"})
    assert bad.status_code == 422


class FakeHotspot:
    def __init__(self) -> None:
        self.last = Status(available=True, ssid="Nanar", passphrase="secret12")

    def status(self) -> Status:
        return self.last

    def turn(self, on: bool) -> Status:
        if not self.last.available:
            raise HotspotError("no_internet")
        self.last = Status(available=True, on=on, ssid="Nanar", passphrase="secret12")
        return self.last

    def close(self) -> None:
        pass


def test_only_this_machine_opens_the_hotspot_and_sees_its_password(
    controller: Controller,
) -> None:
    wifi = FakeHotspot()
    network = Network(port=8642, addresses=lambda: ["192.168.1.10"])
    app = create_app(controller, key=KEY, network=network, hotspot=wifi)  # type: ignore[arg-type]
    tv = TestClient(app, base_url="http://127.0.0.1:8642", client=TV)
    phone = TestClient(app, base_url="http://192.168.1.10:8642", client=PHONE)
    pair(phone)
    assert tv.get("/api/hotspot/qr.svg").status_code == 404  # closed
    assert phone.post("/api/hotspot", json={"on": True}).status_code == 403
    assert tv.post("/api/hotspot", json={"on": True}).status_code == 204
    assert controller.state()["hotspot"]["on"]
    assert controller.state()["hotspot"]["ssid"] == "Nanar"
    assert tv.get("/api/hotspot").json()["on"]
    assert phone.get("/api/hotspot").status_code == 403
    assert tv.get("/api/hotspot/qr.svg").headers["content-type"] == "image/svg+xml"
    assert phone.get("/api/hotspot/qr.svg").status_code == 404
    assert "secret12" not in phone.get("/api/state").text
    wifi.last = Status(available=False)
    refused = tv.post("/api/hotspot", json={"on": True})
    assert refused.status_code == 409
    assert refused.json() == {"code": "no_internet"}


def test_online_keys_are_set_from_this_machine_only_and_never_shown(
    client: TestClient, phone: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nanar.online import Tmdb

    monkeypatch.setattr(Tmdb, "check", lambda self: None)  # no network in tests
    pair(phone)
    assert phone.post("/api/online", json={"tmdb": "abcdef123456"}).status_code == 403
    assert phone.get("/api/online").status_code == 403
    assert client.post("/api/online", json={"tmdb": "abcdef123456"}).status_code == 204
    shown = client.get("/api/online").json()
    assert shown["tmdb"]["set"]
    assert shown["tmdb"]["hint"] == "…3456"
    assert "abcdef123456" not in client.get("/api/online").text
    assert client.post("/api/online", json={"tmdb": ""}).status_code == 204
    assert not client.get("/api/online").json()["tmdb"]["set"]


def test_a_refused_key_is_not_kept(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from nanar.online import OnlineError, Tmdb

    def refuse(self: Tmdb) -> None:
        raise OnlineError("bad_key")

    monkeypatch.setattr(Tmdb, "check", refuse)
    answer = client.post("/api/online", json={"tmdb": "wrongwrong"})
    assert answer.json() == {"code": "bad_key"}
    assert not client.get("/api/online").json()["tmdb"]["set"]


def test_only_this_machine_installs_an_update(controller: Controller) -> None:
    desktop = FakeDesktop()
    tv, phone = desktop_app(controller, desktop)
    pair(phone)
    assert phone.post("/api/update", json={}).status_code == 403
    assert phone.post("/api/updates", json={"enabled": True}).status_code == 403
    assert tv.post("/api/updates", json={"enabled": True}).status_code == 204
    assert controller.settings.check_updates
    assert tv.post("/api/update", json={}).status_code == 204
    assert desktop.updated


def test_a_network_path_in_the_address_never_reaches_the_file_system(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    touched: list[str] = []
    real = Path.resolve

    def resolve(self: Path, strict: bool = False) -> Path:
        touched.append(str(self))
        return real(self, strict)

    monkeypatch.setattr(Path, "resolve", resolve)
    client.get("/%5C%5C192.0.2.1%5Cshare%5Cx.txt")
    assert not [p for p in touched if "192.0.2.1" in p]


def test_pages_refuse_another_sites_frame(client: TestClient) -> None:
    headers = client.get("/api/health").headers
    assert headers["content-security-policy"] == "frame-ancestors 'none'"
    assert headers["x-content-type-options"] == "nosniff"


def test_a_websocket_must_come_from_the_same_port(client: TestClient) -> None:
    with (
        pytest.raises(WebSocketDisconnect),
        client.websocket_connect(
            "ws://127.0.0.1:8642/api/live", headers={"origin": "http://127.0.0.1:9999"}
        ),
    ):
        pass


def test_commands_go_over_the_live_connection_and_get_an_answer(
    client: TestClient, sessions: FakeSessions
) -> None:
    with client.websocket_connect("ws://127.0.0.1:8642/api/live") as socket:
        assert socket.receive_json()["type"] == "state"
        socket.send_json({"type": "command", "id": 1, "action": "pause"})
        while (message := socket.receive_json())["type"] != "result":
            pass
        assert message == {"type": "result", "id": 1, "code": "nothing_playing"}
        assert client.post("/api/play", json={"videoId": first_film(client)}).status_code == 204
        socket.send_json({"type": "command", "id": 2, "action": "pause"})
        while (message := socket.receive_json())["type"] != "result":
            pass
        assert message == {"type": "result", "id": 2, "code": None}
    assert sessions.last.commands == [("pause", None)]


def test_a_phone_leaving_is_noticed_at_once(app: FastAPI, phone: TestClient) -> None:
    pair(phone)
    controller = app.state.controller
    with phone.websocket_connect("ws://192.168.1.10:8642/api/live") as socket:
        socket.receive_json()
        assert controller.state()["phones"] == 1
    deadline = time.monotonic() + 2
    while controller.state()["phones"] and time.monotonic() < deadline:
        time.sleep(0.01)
    assert controller.state()["phones"] == 0


def test_only_this_machine_opens_where_to_get_a_key(
    client: TestClient, phone: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    opened: list[str] = []

    def browser(url: str) -> bool:
        opened.append(url)
        return True

    monkeypatch.setattr("webbrowser.open", browser)
    pair(phone)
    assert phone.post("/api/link", json={"target": "tmdb"}).status_code == 403
    assert client.post("/api/link", json={"target": "https://evil.test"}).status_code == 422
    assert client.post("/api/link", json={"target": "tmdb"}).status_code == 204
    assert opened == ["https://www.themoviedb.org/settings/api"]


def test_another_sites_picture_cannot_probe_the_api(client: TestClient) -> None:
    cross = {"Sec-Fetch-Site": "cross-site"}
    assert client.get("/api/library", headers=cross).status_code == 403
    assert client.get("/api/thumb/v/abc", headers=cross).status_code == 403
    assert client.get("/api/health", headers=cross).status_code == 200  # the page's own probe
    assert client.get("/api/library", headers={"Sec-Fetch-Site": "same-origin"}).status_code == 200


def test_a_huge_request_is_refused_before_it_fills_the_memory(phone: TestClient) -> None:
    body = b'{"key":"' + b"x" * 100_000 + b'"}'
    answer = phone.post("/api/pair", content=body, headers={"Content-Type": "application/json"})
    assert answer.status_code == 413


def test_an_odd_key_is_just_a_wrong_key(phone: TestClient) -> None:
    body = b'{"key":"\\ud800"}'
    headers = {"Content-Type": "application/json"}
    assert phone.post("/api/pair", content=body, headers=headers).status_code == 403


def test_vite_is_only_a_page_of_nanar_in_development(controller: Controller) -> None:
    network = Network(port=8642, addresses=list)
    origin = {"origin": "http://localhost:5173"}
    client = TestClient(create_app(controller, key=KEY, network=network), client=TV)
    with (
        pytest.raises(WebSocketDisconnect),
        client.websocket_connect("ws://127.0.0.1:8642/api/live", headers=origin),
    ):
        pass
    dev = TestClient(create_app(controller, key=KEY, network=network, dev=True), client=TV)
    with dev.websocket_connect("ws://127.0.0.1:8642/api/live", headers=origin) as socket:
        assert socket.receive_json()["type"] == "state"
