import asyncio

import httpx
import pytest
from fastapi import FastAPI

from app.api.middleware.request_size import (
    MAX_REQUEST_SIZE,
    RequestSizeLimitMiddleware,
)


@pytest.mark.parametrize(
    "size", [0, MAX_REQUEST_SIZE - 1, MAX_REQUEST_SIZE, MAX_REQUEST_SIZE + 1]
)
@pytest.mark.parametrize("length", ["actual", "missing", "understated"])
def test_body_limit(size, length):
    calls = []

    async def endpoint(scope, receive, send):
        message = await receive()
        calls.append(message["body"])
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    async def check():
        body = b"x" * size
        messages = iter(
            [
                {"type": "http.request", "body": body[:32000], "more_body": True},
                {"type": "http.request", "body": body[32000:], "more_body": False},
            ]
        )
        headers = (
            []
            if length == "missing"
            else [(b"content-length", str(size if length == "actual" else 0).encode())]
        )
        sent = []

        async def receive():
            return next(messages)

        async def send(message):
            sent.append(message)

        await RequestSizeLimitMiddleware(endpoint)(
            {"type": "http", "headers": headers}, receive, send
        )
        assert sent[0]["status"] == (413 if size > MAX_REQUEST_SIZE else 204)
        assert calls == ([] if size > MAX_REQUEST_SIZE else [body])

    asyncio.run(check())


def test_chunked_json_returns_413_through_fastapi():
    app = FastAPI()
    app.add_middleware(RequestSizeLimitMiddleware)

    @app.post("/")
    async def endpoint(body: dict):
        pytest.fail("Oversized body reached the endpoint")

    async def check():
        async def chunks():
            yield b'{"value":"'
            yield b"x" * MAX_REQUEST_SIZE
            yield b'"}'

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/", content=chunks(), headers={"Content-Type": "application/json"}
            )
        assert response.status_code == 413
        assert response.json() == {"detail": "Request body too large"}

    asyncio.run(check())


# import requests

# url = "https://accralife.app/api/login"

# payload = {
#     "handle": "user@example.com",
#     "password": "A" * 70000 #68kb
#     # "password": "A" * 1_073_741_824 #1Gib
# }

# response = requests.post(url, json=payload)

# print(response.status_code)
# print(response.text)







# import httpx

# url = "http://localhost:8000/auth/login"

# headers = {
#     "Content-Type": "application/json",
#     "Accept": "application/json",
#     "Origin": "https://accralife.app",
#     "Referer": "https://accralife.app/",
# }

# payload = {
#     "handle": "user@example.com",
#     "password": "A" * 70000 #68kb
# }

# timeout = httpx.Timeout(
#     30.0,
#     write=60.0
# )

# try:
#     response = httpx.post(
#         url,
#         json=payload,
#         headers=headers,
#         timeout=timeout
#     )
#     print(response.status_code, response.text)

# except httpx.WriteTimeout:
#     print("Timed out while sending the request body")

# print("Status:", response.status_code)
# print("Response:", response.text)