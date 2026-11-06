import asyncio
import time
from uuid import uuid4

import structlog
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = structlog.get_logger()


class RequestLoggingMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        structlog.contextvars.clear_contextvars()
        request_id = str(uuid4())
        started = time.perf_counter()
        status_code = 500
        response_started = False
        response_complete = False
        failed = False
        structlog.contextvars.bind_contextvars(request_id=request_id)

        async def send_wrapper(message: Message):
            nonlocal status_code, response_started, response_complete
            if message["type"] == "http.response.start":
                headers = [
                    (key, value)
                    for key, value in message.get("headers", [])
                    if key.lower() != b"x-request-id"
                ]
                headers.append((b"x-request-id", request_id.encode()))
                message = {**message, "headers": headers}
            await send(message)
            if message["type"] == "http.response.start":
                status_code = message["status"]
                response_started = True
            elif message["type"] == "http.response.body":
                response_complete = not message.get("more_body", False)

        try:
            await self.app(scope, receive, send_wrapper)
        except asyncio.CancelledError:
            failed = True
            raise
        except Exception:
            failed = True
            if response_started:
                # Uvicorn logs the propagated exception once and closes the stream.
                raise
            logger.exception("unhandled_request_exception")
            await JSONResponse({"detail": "Internal server error"}, status_code=500)(
                scope, receive, send_wrapper
            )
        finally:
            try:
                outcome = (
                    "server_error"
                    if failed
                    else "incomplete"
                    if not response_complete
                    else "success"
                    if status_code < 400
                    else "client_error"
                    if status_code < 500
                    else "server_error"
                )
                logger.info(
                    "http_request_completed",
                    method=scope["method"],
                    route=getattr(scope.get("route"), "path", "unmatched"),
                    status=status_code,
                    response_complete=response_complete,
                    duration_ms=round((time.perf_counter() - started) * 1000, 2),
                    outcome=outcome,
                )
            finally:
                structlog.contextvars.clear_contextvars()
