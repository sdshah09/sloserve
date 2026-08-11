"""Workload generators for interactive and background traffic."""

from __future__ import annotations

import random
import time
from dataclasses import dataclass
from typing import Iterator, Literal

from harness.client import RequestClass, RequestSpec

MixMode = Literal["interactive", "background", "mixed"]


@dataclass(frozen=True)
class LengthRange:
    low: int
    high: int

    def sample(self, rng: random.Random) -> int:
        return rng.randint(self.low, self.high)


# Fixed experimental defaults from AGENTS.md
INTERACTIVE_INPUT = LengthRange(256, 1000)
INTERACTIVE_OUTPUT = LengthRange(32, 128)
BACKGROUND_INPUT = LengthRange(4000, 8000)
BACKGROUND_OUTPUT = LengthRange(256, 512)


@dataclass
class WorkloadConfig:
    mix: MixMode = "mixed"
    interactive_fraction: float = 0.8
    rate_rps: float = 4.0
    duration_s: float = 30.0
    num_requests: int | None = None
    model: str = "mock-model"
    seed: int = 42
    interactive_input: LengthRange = INTERACTIVE_INPUT
    interactive_output: LengthRange = INTERACTIVE_OUTPUT
    background_input: LengthRange = BACKGROUND_INPUT
    background_output: LengthRange = BACKGROUND_OUTPUT


def _choose_class(cfg: WorkloadConfig, rng: random.Random) -> RequestClass:
    if cfg.mix == "interactive":
        return "interactive"
    if cfg.mix == "background":
        return "background"
    return "interactive" if rng.random() < cfg.interactive_fraction else "background"


def make_spec(request_class: RequestClass, cfg: WorkloadConfig, rng: random.Random) -> RequestSpec:
    if request_class == "interactive":
        prompt = cfg.interactive_input.sample(rng)
        out = cfg.interactive_output.sample(rng)
    else:
        prompt = cfg.background_input.sample(rng)
        out = cfg.background_output.sample(rng)
    return RequestSpec(
        request_class=request_class,
        prompt_tokens=prompt,
        max_tokens=out,
        model=cfg.model,
    )


def iter_arrivals(cfg: WorkloadConfig) -> Iterator[RequestSpec]:
    """Yield RequestSpecs with arrival_time set (Poisson process at rate_rps)."""
    rng = random.Random(cfg.seed)
    t0 = time.time()
    t = t0
    count = 0

    while True:
        if cfg.num_requests is not None and count >= cfg.num_requests:
            break
        if cfg.num_requests is None and (t - t0) >= cfg.duration_s:
            break

        request_class = _choose_class(cfg, rng)
        spec = make_spec(request_class, cfg, rng)
        spec.arrival_time = t
        yield spec

        count += 1
        # Exponential inter-arrival for Poisson arrivals.
        gap = rng.expovariate(cfg.rate_rps) if cfg.rate_rps > 0 else 0.0
        t += gap
