"""Mock OpenAI-compatible streaming chat server for local harness tests."""

from __future__ import annotations

import argparse
import asyncio
import json
import time
import uuid
from typing import Any, AsyncIterator

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

app = FastAPI(title="SLOServe mock streaming server")


def _count_prompt_tokens(messages: list[dict[str, Any]]) -> int:
    text = " ".join(str(m.get("content", "")) for m in messages)
    return max(1, len(text.split()))


async def _token_stream(
    *,
    prompt_tokens: int,
    max_tokens: int,
    ttft_ms: float,
    itl_ms: float,
    request: Request,
) -> AsyncIterator[bytes]:
    # Prefill delay scales lightly with prompt size so mixed traffic is visible.
    prefill_delay = (ttft_ms / 1000.0) + (prompt_tokens / 50_000.0)
    await asyncio.sleep(prefill_delay)

    for i in range(max_tokens):
        if await request.is_disconnected():
            return
        chunk = {
            "id": f"chatcmpl-mock-{uuid.uuid4().hex[:8]}",
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": "mock-model",
            "choices": [
                {
                    "index": 0,
                    "delta": {"content": f"t{i} "},
                    "finish_reason": None,
                }
            ],
        }
        yield f"data: {json.dumps(chunk)}\n\n".encode("utf-8")
        if i + 1 < max_tokens:
            await asyncio.sleep(itl_ms / 1000.0)

    done = {
        "id": f"chatcmpl-mock-{uuid.uuid4().hex[:8]}",
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": "mock-model",
        "choices": [{"index": 0, "delta": {}, "finish_reason": "length"}],
    }
    yield f"data: {json.dumps(done)}\n\n".encode("utf-8")
    yield b"data: [DONE]\n\n"


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/v1/chat/completions")
async def chat_completions(request: Request) -> Any:
    body = await request.json()
    messages = body.get("messages") or []
    max_tokens = int(body.get("max_tokens") or 16)
    stream = bool(body.get("stream", False))
    prompt_tokens = _count_prompt_tokens(messages)

    ttft_ms = float(request.query_params.get("ttft_ms", app.state.ttft_ms))
    itl_ms = float(request.query_params.get("itl_ms", app.state.itl_ms))

    if not stream:
        await asyncio.sleep((ttft_ms / 1000.0) + (prompt_tokens / 50_000.0))
        text = " ".join(f"t{i}" for i in range(max_tokens))
        return JSONResponse(
            {
                "id": f"chatcmpl-mock-{uuid.uuid4().hex[:8]}",
                "object": "chat.completion",
                "created": int(time.time()),
                "model": body.get("model", "mock-model"),
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": text},
                        "finish_reason": "length",
                    }
                ],
                "usage": {
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": max_tokens,
                    "total_tokens": prompt_tokens + max_tokens,
                },
            }
        )

    generator = _token_stream(
        prompt_tokens=prompt_tokens,
        max_tokens=max_tokens,
        ttft_ms=ttft_ms,
        itl_ms=itl_ms,
        request=request,
    )
    return StreamingResponse(generator, media_type="text/event-stream")


def create_app(*, ttft_ms: float = 20.0, itl_ms: float = 5.0) -> FastAPI:
    app.state.ttft_ms = ttft_ms
    app.state.itl_ms = itl_ms
    return app


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="SLOServe mock streaming server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--ttft-ms", type=float, default=20.0)
    parser.add_argument("--itl-ms", type=float, default=5.0)
    args = parser.parse_args(argv)

    import uvicorn

    create_app(ttft_ms=args.ttft_ms, itl_ms=args.itl_ms)
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


app.state.ttft_ms = 20.0
app.state.itl_ms = 5.0


if __name__ == "__main__":
    main()
