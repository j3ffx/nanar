"""Who may drive Nanar.

- **This machine** (the TV page, scripts): a request from a loopback address with a loopback
  `Host`. The `Host` check defeats DNS rebinding (a hostile name resolving to 127.0.0.1).
- **A paired phone**: any address, carrying the pairing key in the `nanar_key` cookie (set by
  `POST /api/pair`) or in an `Authorization: Bearer` header.
- **Anyone else** only gets the pages themselves (to show "scan the QR code"), the manifest,
  `GET /api/health` and `POST /api/pair`.

Whoever they are, a request that changes state must carry a JSON body: another website open in a
browser can't send one without a CORS preflight, and only `/api/health` grants a CORS header. The
cookie is `SameSite=Strict`, a WebSocket must come from the page's own origin, and no page shows
in another site's frame.
"""

import hmac
import ipaddress
import json
from dataclasses import dataclass

from starlette.datastructures import Headers
from starlette.types import ASGIApp, Message, Receive, Scope, Send

COOKIE = "nanar_key"
LOOPBACK_NAMES = frozenset({"127.0.0.1", "localhost", "::1"})
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
OPEN_API = frozenset({("GET", "/api/health"), ("POST", "/api/pair")})
DEV_ORIGINS = frozenset({"localhost:5173", "127.0.0.1:5173"})
HARDENING = (
    (b"content-security-policy", b"frame-ancestors 'none'"),
    (b"x-content-type-options", b"nosniff"),
)


@dataclass(frozen=True)
class Caller:
    local: bool  # this machine
    paired: bool  # carries the key


def hostname_of(host: str) -> str:
    if host.startswith("["):  # [::1]:8642
        return host[1 : host.find("]")]
    return host.rsplit(":", 1)[0] if host.count(":") == 1 else host


def _is_loopback_address(address: str) -> bool:
    try:
        return ipaddress.ip_address(address).is_loopback
    except ValueError:
        return False


def caller_of(scope: Scope, key: str) -> Caller:
    headers = Headers(scope=scope)
    client = scope.get("client")
    host = hostname_of(headers.get("host", "")).lower()
    local = (
        client is not None
        and _is_loopback_address(client[0])
        and (host in LOOPBACK_NAMES or host.endswith(".localhost"))
    )
    return Caller(local=local, paired=key_matches(_presented_key(headers), key))


def key_matches(presented: str | None, key: str) -> bool:
    return presented is not None and hmac.compare_digest(presented.encode(), key.encode())


def _presented_key(headers: Headers) -> str | None:
    authorization = headers.get("authorization", "")
    if authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    for part in headers.get("cookie", "").split(";"):
        name, _, value = part.strip().partition("=")
        if name == COOKIE:
            return value
    return None


class AccessMiddleware:
    def __init__(self, app: ASGIApp, *, key: str) -> None:
        self.app = app
        self.key = key

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return
        caller = caller_of(scope, self.key)
        scope.setdefault("state", {})["caller"] = caller
        problem = _problem(scope, Headers(scope=scope), caller)
        if problem is None:

            async def hardened(message: Message) -> None:
                if message["type"] == "http.response.start":
                    # No page of Nanar in another site's frame: there, its clicks would count
                    # as this machine's.
                    message["headers"] = [*message.get("headers", []), *HARDENING]
                await send(message)

            await self.app(scope, receive, hardened)
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


def _same_origin(origin: str, host: str) -> bool:
    """A page's own origin, port included; or the pages served by Vite, in development."""
    there = origin.split("://")[-1]
    return there == host or there in DEV_ORIGINS


def _problem(scope: Scope, headers: Headers, caller: Caller) -> tuple[int, str] | None:
    path: str = scope["path"]
    if scope["type"] == "websocket":
        if not (caller.local or caller.paired):
            return 401, "pairing_required"
        origin = headers.get("origin")
        if origin is not None and not _same_origin(origin, headers.get("host", "")):
            return 403, "forbidden_origin"
        return None
    method: str = scope["method"]
    if method not in SAFE_METHODS and not headers.get("content-type", "").startswith(
        "application/json"
    ):
        return 415, "json_required"
    if caller.local or caller.paired:
        return None
    if not path.startswith("/api/") or (method, path) in OPEN_API:
        return None
    return 401, "pairing_required"
