"""Integration tests against the mock streaming server (ASGI, no GPU)."""

from __future__ import annotations

import asyncio

import pytest
from httpx import ASGITransport

from harness.client import RequestSpec, StreamingClient
from mocks.streaming_server import create_app


@pytest.fixture
def client() -> StreamingClient:
    app = create_app(ttft_ms=10.0, itl_ms=2.0)
    return StreamingClient(
        "http://test",
        transport=ASGITransport(app=app),
    )


@pytest.mark.asyncio
async def test_streaming_records_timestamps(client: StreamingClient) -> None:
    record = await client.chat_completion_stream(
        RequestSpec(
            request_class="interactive",
            prompt_tokens=32,
            max_tokens=8,
        )
    )
    assert record.status == "ok"
    assert record.first_token_time is not None
    assert record.ttft is not None and record.ttft >= 0
    assert record.output_token_count == 8
    assert len(record.token_times) == 7
    assert record.completion_time is not None
    assert record.e2e is not None and record.e2e >= record.ttft
    assert record.tpot is not None


@pytest.mark.asyncio
async def test_cancel_mid_stream(client: StreamingClient) -> None:
    cancel_event = asyncio.Event()

    async def _cancel_soon() -> None:
        await asyncio.sleep(0.05)
        cancel_event.set()

    cancel_task = asyncio.create_task(_cancel_soon())
    record = await client.chat_completion_stream(
        RequestSpec(
            request_class="interactive",
            prompt_tokens=16,
            max_tokens=80,
        ),
        cancel_event=cancel_event,
    )
    await cancel_task
    assert record.status == "cancelled"
    assert record.completion_time is not None
    assert record.output_token_count < 80
