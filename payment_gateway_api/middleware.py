import re
import time
import uuid

import structlog
from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

REQUEST_ID_HEADER = "X-Request-ID"
# Client-supplied IDs end up in logs, so only accept a safe, bounded format.
_VALID_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
_QUIET_PATHS = frozenset({"/health", "/liveness"})

logger = structlog.get_logger(__name__)


class RequestLoggingMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = _request_id(scope)
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id, method=scope["method"], path=scope["path"]
        )
        status_code = 500
        start = time.perf_counter()

        async def send_with_request_id(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                MutableHeaders(scope=message).append(REQUEST_ID_HEADER, request_id)
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            log = logger.debug if scope["path"] in _QUIET_PATHS else logger.info
            log(
                "request_completed",
                status_code=status_code,
                duration_ms=round((time.perf_counter() - start) * 1000, 2),
            )


def _request_id(scope: Scope) -> str:
    incoming = Headers(scope=scope).get(REQUEST_ID_HEADER)
    if incoming and _VALID_REQUEST_ID.match(incoming):
        return incoming
    return str(uuid.uuid4())
