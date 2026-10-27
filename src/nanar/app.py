"""The HTTP API and the pages: the TV page (/tv) and the remote (/), live over a WebSocket.

Who may call what is decided in `security.py`; phones pair with the key the TV shows as a QR code.
"""

import asyncio
import io
from collections.abc import Callable
from dataclasses import dataclass, field
from importlib.resources import files
from pathlib import Path
from typing import Any, Protocol

import segno
from fastapi import FastAPI, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from nanar import __version__
from nanar.controller import CommandError, Controller
from nanar.pairing import lan_addresses, remote_url
from nanar.security import COOKIE, AccessMiddleware, Caller, key_matches

TEN_YEARS = 10 * 365 * 24 * 3600


class PlayBody(BaseModel):
    videoId: str  # the pages' camelCase
    start: float | None = None  # None: where it was left


class CommandBody(BaseModel):
    action: str
    value: Any = None


class ViewBody(BaseModel):
    path: str  # the TV page's path: "/" or "/g/<group>"
    focus: str | None = None  # the video or group to put forward


class OpenBody(BaseModel):
    path: str | None = None  # a folder to open
    choose: bool = False  # or ask for one with the system's folder picker


class IntegrationBody(BaseModel):
    install: bool


class Desktop(Protocol):
    """What only this machine may ask for: its folders, its window, its Start menu."""

    def open(self, folder: str) -> None: ...

    def choose(self) -> str | None:
        """The system's folder picker; None when cancelled."""

    def bring_to_front(self) -> None: ...

    def integrate(self, install: bool) -> None:
        """Adds (or not) Nanar to the Start menu and to the folders' right-click menu."""


class PairBody(BaseModel):
    key: str


@dataclass
class Network:
    """How phones reach this machine: `lan` is False with `nanar --local`."""

    port: int
    lan: bool = True
    addresses: Callable[[], list[str]] = field(default=lan_addresses)
    # "nanar.local" while it is announced on the network (discovery.py), else None.
    name: Callable[[], str | None] = field(default=lambda: None)


def static_dir() -> Path:
    return Path(str(files("nanar"))) / "web" / "static"


def create_app(
    controller: Controller, *, key: str, network: Network, desktop: Desktop | None = None
) -> FastAPI:
    app = FastAPI(title="Nanar", version=__version__, docs_url=None, redoc_url=None)
    app.add_middleware(AccessMiddleware, key=key)
    phones: set[WebSocket] = set()

    @app.exception_handler(CommandError)
    async def command_error(_: Any, error: CommandError) -> JSONResponse:
        return JSONResponse({"code": error.code}, status_code=409)

    @app.get("/api/health")
    async def health(response: Response) -> dict[str, str]:
        # Readable from any page: the remote, opened by its IP address, asks whether
        # nanar.local answers before moving there. It says nothing but the version.
        response.headers["Access-Control-Allow-Origin"] = "*"
        return {"version": __version__}

    @app.get("/api/state")
    async def state() -> dict[str, Any]:
        return controller.state()

    @app.get("/api/library")
    async def library() -> dict[str, Any]:
        return controller.library_json()

    @app.get("/api/thumb/{kind}/{ident}", response_model=None)
    async def thumb(kind: str, ident: str) -> FileResponse | JSONResponse:
        path = controller.thumbnail(kind, ident) if kind in ("v", "g") else None
        if path is None:
            return JSONResponse({"code": "no_thumbnail"}, status_code=404)
        # Its address changes with the picture (?v=…): it may be kept for long.
        return FileResponse(path, headers={"Cache-Control": "private, max-age=31536000"})

    @app.post("/api/play", status_code=204)
    async def play(body: PlayBody) -> None:
        await asyncio.to_thread(controller.play, body.videoId, body.start)

    @app.post("/api/command", status_code=204)
    async def command(body: CommandBody, request: Request) -> None:
        await asyncio.to_thread(
            controller.command, body.action, body.value, osd=not _caller(request).local
        )

    @app.post("/api/view", status_code=204)
    async def view(body: ViewBody) -> None:
        controller.set_view(body.path, body.focus)

    @app.post("/api/open", status_code=204, response_model=None)
    async def open_folder(body: OpenBody, request: Request) -> JSONResponse | None:
        """Opens a folder (a second launch hands its folder over this way, the TV page's
        button asks for one), and brings Nanar's window to the front."""
        if not _caller(request).local:
            return JSONResponse({"code": "this_machine_only"}, status_code=403)
        if desktop is None:
            raise CommandError("no_window")
        here = desktop

        def run() -> None:
            folder = here.choose() if body.choose else body.path
            if folder:
                here.open(folder)
            here.bring_to_front()

        await asyncio.to_thread(run)
        return None

    @app.post("/api/integration", status_code=204, response_model=None)
    async def integration(body: IntegrationBody, request: Request) -> JSONResponse | None:
        if not _caller(request).local:
            return JSONResponse({"code": "this_machine_only"}, status_code=403)
        if desktop is None:
            raise CommandError("no_window")
        await asyncio.to_thread(desktop.integrate, body.install)
        controller.set_integration_offer(False)
        return None

    @app.post("/api/pair", response_model=None)
    async def pair(body: PairBody) -> Response:
        if not key_matches(body.key, key):
            return JSONResponse({"code": "wrong_key"}, status_code=403)
        response = Response(status_code=204)
        response.set_cookie(
            COOKIE, key, max_age=TEN_YEARS, httponly=True, samesite="strict", path="/"
        )
        return response

    @app.get("/api/pairing")
    async def pairing() -> dict[str, Any]:
        """For the TV page: the addresses to show, and the URL its QR code holds."""
        addresses = network.addresses() if network.lan else []
        name = network.name() if network.lan else None
        return {
            "lan": network.lan,
            "name": f"{name}:{network.port}" if name else None,
            "addresses": [f"{a}:{network.port}" for a in addresses],
            "url": remote_url(addresses[0], network.port, key) if addresses else None,
        }

    @app.get("/api/pairing/qr.svg")
    async def pairing_qr() -> Response:
        addresses = network.addresses() if network.lan else []
        if not addresses:
            return JSONResponse({"code": "no_network"}, status_code=404)
        qr = segno.make(remote_url(addresses[0], network.port, key), error="m")
        # A whole SVG document (with its namespace): an <img> shows nothing without it.
        out = io.BytesIO()
        qr.save(out, kind="svg", scale=8, border=2, dark="#120d1a", light="#f6efe4")
        return Response(
            out.getvalue(), media_type="image/svg+xml", headers={"Cache-Control": "no-store"}
        )

    @app.websocket("/api/live")
    async def live(socket: WebSocket) -> None:
        await socket.accept()
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

        def push(state: dict[str, Any]) -> None:
            loop.call_soon_threadsafe(queue.put_nowait, state)

        unsubscribe = controller.subscribe(push)
        is_phone = not _caller(socket).local
        if is_phone:
            phones.add(socket)
            controller.set_phones(len(phones))
        try:
            await socket.send_json({"type": "state", "state": controller.state()})
            while True:
                state = await queue.get()
                while not queue.empty():  # only the latest state matters
                    state = queue.get_nowait()
                await socket.send_json({"type": "state", "state": state})
        except WebSocketDisconnect:
            pass
        finally:
            unsubscribe()
            if is_phone:
                phones.discard(socket)
                controller.set_phones(len(phones))

    @app.get("/manifest.webmanifest", include_in_schema=False)
    async def manifest(request: Request) -> JSONResponse:
        # Added to a phone's home screen, the remote opens on its start URL. On an iPhone the
        # icon has cookies of its own: a paired phone's start URL carries the key, so that the
        # icon is paired too.
        start = f"/#k={key}" if _caller(request).paired else "/"
        return JSONResponse(
            {
                "name": "Nanar",
                "short_name": "Nanar",
                "description": "La télécommande de Nanar.",
                "start_url": start,
                "scope": "/",
                "display": "standalone",
                "background_color": "#120d1a",
                "theme_color": "#120d1a",
                "icons": [
                    {"src": "/icon-192.png", "sizes": "192x192", "type": "image/png"},
                    {"src": "/icon-512.png", "sizes": "512x512", "type": "image/png"},
                    {"src": "/icon.svg", "sizes": "any", "type": "image/svg+xml"},
                ],
            },
            media_type="application/manifest+json",
            headers={"Cache-Control": "no-cache"},
        )

    pages = static_dir()

    @app.get("/{path:path}", include_in_schema=False, response_model=None)
    async def page(path: str) -> FileResponse | JSONResponse:
        if path.startswith("api/"):
            return JSONResponse({"code": "not_found"}, status_code=404)
        asset = (pages / path).resolve()
        if path and asset.is_file() and asset.is_relative_to(pages.resolve()):
            return FileResponse(asset)
        index = pages / "index.html"
        if not index.is_file():
            return JSONResponse({"code": "ui_not_built"}, status_code=503)
        return FileResponse(index, headers={"Cache-Control": "no-cache"})

    return app


def _caller(connection: Request | WebSocket) -> Caller:
    caller: Caller = connection.scope["state"]["caller"]
    return caller
