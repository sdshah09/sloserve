"""Streaming OpenAI-compatible client with per-token timestamps."""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

import httpx

RequestClass = Literal["interactive", "background"]
RequestStatus = Literal["ok", "cancelled", "error"]


@dataclass
class RequestSpec:
    request_class: RequestClass
    prompt_tokens: int
    max_tokens: int
    model: str = "mock-model"
    request_id: str | None = None
    arrival_time: float | None = None


@dataclass
class RequestRecord:
    request_id: str
    request_class: RequestClass
    arrival_time: float
    first_token_time: float | None = None
    token_times: list[float] = field(default_factory=list)
    completion_time: float | None = None
    status: RequestStatus = "ok"
    prompt_tokens: int = 0
    max_tokens: int = 0
    output_token_count: int = 0
    error: str | None = None

    @property
    def ttft(self) -> float | None:
        if self.first_token_time is None:
            return None
        return self.first_token_time - self.arrival_time

    @property
    def e2e(self) -> float | None:
        if self.completion_time is None:
            return None
        return self.completion_time - self.arrival_time

    @property
    def itls(self) -> list[float]:
        times = []
        if self.first_token_time is not None:
            times.append(self.first_token_time)
        times.extend(self.token_times)
        if len(times) < 2:
            return []
        return [times[i] - times[i - 1] for i in range(1, len(times))]

    @property
    def tpot(self) -> float | None:
        itls = self.itls
        if not itls:
            return None
        return sum(itls) / len(itls)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["ttft"] = self.ttft
        payload["e2e"] = self.e2e
        payload["tpot"] = self.tpot
        payload["itls"] = self.itls
        return payload


def _synthetic_prompt(num_tokens: int) -> str:
    # Approximate ~1 token/word for mock/vLLM tokenization.
    words = [f"w{i}" for i in range(max(1, num_tokens))]
    return " ".join(words)


class StreamingClient:
    """OpenAI-compatible chat completions streaming client."""

    def __init__(
        self,
        base_url: str,
        *,
        api_key: str | None = None,
        timeout: float = 600.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.transport = transport

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    async def chat_completion_stream(
        self,
        spec: RequestSpec,
        *,
        cancel_event: asyncio.Event | None = None,
    ) -> RequestRecord:
        request_id = spec.request_id or str(uuid.uuid4())
        arrival = spec.arrival_time if spec.arrival_time is not None else time.time()
        record = RequestRecord(
            request_id=request_id,
            request_class=spec.request_class,
            arrival_time=arrival,
            prompt_tokens=spec.prompt_tokens,
            max_tokens=spec.max_tokens,
        )

        body = {
            "model": spec.model,
            "messages": [
                {
                    "role": "user",
                    "content": _synthetic_prompt(spec.prompt_tokens),
                }
            ],
            "max_tokens": spec.max_tokens,
            "stream": True,
            "temperature": 0.0,
        }

        url = f"{self.base_url}/v1/chat/completions"
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout,
                transport=self.transport,
            ) as client:
                async with client.stream(
                    "POST",
                    url,
                    headers=self._headers(),
                    json=body,
                ) as response:
                    if response.status_code >= 400:
                        text = (await response.aread()).decode("utf-8", errors="replace")
                        record.status = "error"
                        record.error = f"HTTP {response.status_code}: {text}"
                        record.completion_time = time.time()
                        return record

                    async for line in response.aiter_lines():
                        if cancel_event is not None and cancel_event.is_set():
                            record.status = "cancelled"
                            record.completion_time = time.time()
                            await response.aclose()
                            return record

                        if not line or not line.startswith("data:"):
                            continue
                        data = line[len("data:") :].strip()
                        if data == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data)
                        except json.JSONDecodeError:
                            continue

                        now = time.time()
                        delta = ""
                        choices = chunk.get("choices") or []
                        if choices:
                            delta = (
                                choices[0].get("delta", {}).get("content")
                                or choices[0].get("text")
                                or ""
                            )
                        if not delta:
                            continue

                        # Count whitespace-separated pieces as tokens for mock parity.
                        pieces = delta.split()
                        if not pieces:
                            pieces = [delta]
                        for _ in pieces:
                            if record.first_token_time is None:
                                record.first_token_time = now
                            else:
                                record.token_times.append(now)
                            record.output_token_count += 1

                    if record.status != "cancelled":
                        record.status = "ok"
                        record.completion_time = time.time()
        except asyncio.CancelledError:
            record.status = "cancelled"
            record.completion_time = time.time()
            raise
        except Exception as exc:  # noqa: BLE001 - record and continue run
            record.status = "error"
            record.error = str(exc)
            record.completion_time = time.time()

        return record
