"""
IntelliClaim AI - ASGI middleware

Plain ASGI middleware (rather than BaseHTTPMiddleware) so responses are not
buffered and exceptions keep their tracebacks.
"""

import json
import logging

from starlette.datastructures import MutableHeaders
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from config import settings

logger = logging.getLogger("intelliclaim.errors")

_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "X-XSS-Protection": "1; mode=block",
    "Referrer-Policy": "strict-origin-when-cross-origin",
}


class SecurityHeadersMiddleware:
    """Adds standard security headers to every HTTP response."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                for name, value in _SECURITY_HEADERS.items():
                    headers[name] = value
            await send(message)

        await self.app(scope, receive, send_with_headers)


class UnhandledErrorMiddleware:
    """Turns unexpected exceptions into a JSON 500 without internal details.

    Starlette's own fallback runs outside every user middleware, so its plain
    text 500 would reach browsers without CORS headers and the frontend could
    not read it. This middleware is installed inside CORSMiddleware instead.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        response_started = False

        async def tracking_send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, receive, tracking_send)
        except Exception:
            logger.exception("Unhandled error on %s %s", scope.get("method"), scope.get("path"))
            if response_started:
                raise
            response = JSONResponse({"detail": "Internal server error"}, status_code=500)
            await response(scope, receive, send)


class _BodyTooLarge(Exception):
    pass


class BodySizeLimitMiddleware:
    """Caps request bodies: MAX_UPLOAD_MB (plus multipart overhead) for uploads, 1 MB elsewhere.

    A declared Content-Length over the limit is rejected before the body is read.
    Bodies without one (chunked uploads) are counted as they stream in and cut
    off at the limit, so the multipart parser never spools more than that to disk.
    """

    UPLOAD_PATH = "/api/documents/upload"
    MULTIPART_OVERHEAD = 64 * 1024
    DEFAULT_LIMIT = 1024 * 1024

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    def _limit_for(self, path: str) -> tuple[int, str]:
        if path == self.UPLOAD_PATH:
            limit = settings.max_upload_bytes + self.MULTIPART_OVERHEAD
            return limit, f"File too large (max {settings.MAX_UPLOAD_MB} MB)"
        return self.DEFAULT_LIMIT, "Request body too large"

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        limit, detail = self._limit_for(scope["path"])
        for name, value in scope["headers"]:
            if name == b"content-length":
                if value.isdigit() and int(value) > limit:
                    await JSONResponse({"detail": detail}, status_code=413)(scope, receive, send)
                    return
                break

        received = 0
        exceeded = False
        response_started = False

        async def limited_receive() -> Message:
            nonlocal received, exceeded
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    exceeded = True
                    raise _BodyTooLarge()
            return message

        async def guarded_send(message: Message) -> None:
            nonlocal response_started
            if exceeded:
                # The app turned the aborted read into its own error (FastAPI answers
                # 400 "error parsing the body"); send the 413 instead.
                if message["type"] == "http.response.start" and not response_started:
                    response_started = True
                    await _send_json(send, 413, detail)
                return
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, guarded_send)
        except _BodyTooLarge:
            if not response_started:
                await _send_json(send, 413, detail)


async def _send_json(send: Send, status_code: int, detail: str) -> None:
    body = json.dumps({"detail": detail}).encode()
    await send({
        "type": "http.response.start",
        "status": status_code,
        "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())],
    })
    await send({"type": "http.response.body", "body": body})
