from starlette.types import ASGIApp, Scope, Receive, Send
from starlette.responses import JSONResponse

MAX_REQUEST_SIZE = 64 * 1024  # 64 KiB = 65,536 bytes


class RequestSizeLimitMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope["headers"])
        content_length = headers.get(b"content-length")

        if content_length:
            try:
                if int(content_length) > MAX_REQUEST_SIZE:
                    response = JSONResponse(
                        {"detail": "Request body too large"},
                        status_code=413,
                    )
                    await response(scope, receive, send)
                    return
            except ValueError:
                pass

        received = 0

        async def limited_receive():
            nonlocal received

            message = await receive()

            if message["type"] == "http.request":
                received += len(message.get("body", b""))

                if received > MAX_REQUEST_SIZE:
                    raise RequestTooLarge()

            return message

        try:
            await self.app(scope, limited_receive, send)
        except RequestTooLarge:
            response = JSONResponse(
                {"detail": "Request body too large"},
                status_code=413,
            )
            await response(scope, receive, send)


class RequestTooLarge(Exception):
    pass