"""The HTTP API and the pages: the TV page (/tv) and the remote (/), live over a WebSocket.

Until phones can pair (a token shown as a QR code on the TV), the server listens on loopback only.
"""

import asyncio
import json
from importlib.resources import files
from pathlib import Path
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from starlette.datastructures import Headers
from starlette.types import ASGIApp, Receive, Scope, Send

from nanar import __version__
from nanar.controller import CommandError, Controller

LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


class PlayBody(BaseModel):
    videoId: str  # the pages' camelCase
    start: float = 0.0


class CommandBody(BaseModel):
    action: str
    value: Any = None


def static_dir() -> Path:
    return Path(str(files("nanar"))) / "web" / "static"


def create_app(controller: Controller) -> FastAPI:
    app = FastAPI(title="Nanar", version=__version__, docs_url=None, redoc_url=None)
    app.add_middleware(LocalOnlyMiddleware)

    @app.exception_handler(CommandError)
    async def command_error(_: Any, error: CommandError) -> JSONResponse:
        return JSONResponse({"code": error.code}, status_code=409)

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        return {"version": __version__}

    @app.get("/api/state")
    async def state() -> dict[str, Any]:
        return controller.state()

    @app.get("/api/library")
    async def library() -> dict[str, Any]:
        return controller.library.to_json()

    @app.post("/api/play", status_code=204)
    async def play(body: PlayBody) -> None:
        await asyncio.to_thread(controller.play, body.videoId, body.start)

    @app.post("/api/command", status_code=204)
    async def command(body: CommandBody) -> None:
        await asyncio.to_thread(controller.command, body.action, body.value)

    @app.websocket("/api/live")
    async def live(socket: WebSocket) -> None:
        await socket.accept()
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

        def push(state: dict[str, Any]) -> None:
            loop.call_soon_threadsafe(queue.put_nowait, state)

        unsubscribe = controller.subscribe(push)
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


class LocalOnlyMiddleware:
    """Keeps the server to this machine: a loopback `Host` (defeats DNS rebinding), and a JSON
    body for anything that changes state (another website open in the browser can't send one
    without a CORS preflight, and no CORS header is ever granted)."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return
        headers = Headers(scope=scope)
        problem = _problem(scope, headers)
        if problem is None:
            await self.app(scope, receive, send)
            return
        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 1008})
            return
        status, code = problem
        body = json.dumps({"code": code}).encode()
        await send(
            {
                "type": "http.response.start",
                "status": status,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})


def _problem(scope: Scope, headers: Headers) -> tuple[int, str] | None:
    hostname = _hostname(headers.get("host", "")).lower()
    if hostname not in LOOPBACK_HOSTS and not hostname.endswith(".localhost"):
        return 403, "forbidden_host"
    if scope["type"] == "websocket":
        origin = headers.get("origin")
        if origin is not None and _hostname(origin.split("://")[-1]) not in LOOPBACK_HOSTS:
            return 403, "forbidden_origin"
        return None
    if scope["method"] in ("GET", "HEAD", "OPTIONS"):
        return None
    if not headers.get("content-type", "").startswith("application/json"):
        return 415, "json_required"
    return None


def _hostname(host: str) -> str:
    if host.startswith("["):  # [::1]:8642
        return host[1 : host.find("]")]
    return host.rsplit(":", 1)[0] if host.count(":") == 1 else host
