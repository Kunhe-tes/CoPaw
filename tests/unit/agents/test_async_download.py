# -*- coding: utf-8 -*-
from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
import pytest

from swe.agents.utils import async_download


@pytest.fixture
async def mock_client(monkeypatch: pytest.MonkeyPatch):
    clients: list[httpx.AsyncClient] = []

    async def install(handler):
        client = httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            follow_redirects=False,
        )
        clients.append(client)

        async def get_client():
            return client

        monkeypatch.setattr(async_download, "_client_for_loop", get_client)
        return client

    yield install
    for client in clients:
        await client.aclose()


@pytest.mark.asyncio
async def test_streams_success_response_to_destination(
    tmp_path: Path,
    mock_client,
) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/plain"},
            content=b"hello",
        )

    await mock_client(handler)
    destination = tmp_path / ".download.part"
    content_type = await async_download.download_http_to_path(
        "https://example.test/file.txt",
        destination,
        deadline=async_download.time.monotonic() + 5,
        max_bytes=10,
    )

    assert destination.read_bytes() == b"hello"
    assert content_type == "text/plain"


@pytest.mark.asyncio
async def test_rejects_content_length_before_reading(
    tmp_path: Path,
    mock_client,
) -> None:
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            200,
            headers={"content-length": "11"},
            content=b"01234567890",
        )

    await mock_client(handler)
    with pytest.raises(ValueError, match="10 MiB"):
        await async_download.download_http_to_path(
            "https://example.test/large.bin",
            tmp_path / ".large.part",
            deadline=async_download.time.monotonic() + 5,
            max_bytes=10,
        )
    assert calls == 1


@pytest.mark.asyncio
async def test_rejects_chunked_response_after_limit(
    tmp_path: Path,
    mock_client,
) -> None:
    async def body():
        yield b"12345"
        yield b"67890"
        yield b"x"

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=body())

    await mock_client(handler)
    with pytest.raises(ValueError, match="10 MiB"):
        await async_download.download_http_to_path(
            "https://example.test/chunked.bin",
            tmp_path / ".chunked.part",
            deadline=async_download.time.monotonic() + 5,
            max_bytes=10,
        )


@pytest.mark.asyncio
async def test_limits_redirect_hops(tmp_path: Path, mock_client) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        hop = int(request.url.path.rsplit("/", 1)[-1])
        return httpx.Response(
            302,
            headers={"location": f"https://example.test/{hop + 1}"},
        )

    await mock_client(handler)
    with pytest.raises(async_download.AsyncDownloadError, match="redirects"):
        await async_download.download_http_to_path(
            "https://example.test/0",
            tmp_path / ".redirect.part",
            deadline=async_download.time.monotonic() + 5,
            max_bytes=10,
        )


@pytest.mark.asyncio
async def test_http_status_error_is_distinct_from_transport_error(
    tmp_path: Path,
    mock_client,
) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, content=b"missing")

    await mock_client(handler)
    with pytest.raises(
        async_download.AsyncDownloadHTTPError,
        match="404",
    ):
        await async_download.download_http_to_path(
            "https://example.test/missing",
            tmp_path / ".missing.part",
            deadline=async_download.time.monotonic() + 5,
            max_bytes=10,
        )


@pytest.mark.asyncio
async def test_slow_stream_keeps_heartbeat_running(
    tmp_path: Path,
    mock_client,
) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(0.06)
        return httpx.Response(200, content=b"hello")

    await mock_client(handler)
    ticks = 0

    async def heartbeat() -> None:
        nonlocal ticks
        for _ in range(3):
            ticks += 1
            await asyncio.sleep(0.02)

    await asyncio.gather(
        async_download.download_http_to_path(
            "https://example.test/slow",
            tmp_path / ".slow.part",
            deadline=async_download.time.monotonic() + 5,
            max_bytes=10,
        ),
        heartbeat(),
    )
    assert ticks == 3
