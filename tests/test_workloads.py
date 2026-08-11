"""Tests for workload generation."""

from harness.workloads import WorkloadConfig, iter_arrivals, make_spec
import random


def test_mixed_fraction_approximately_80_20() -> None:
    cfg = WorkloadConfig(
        mix="mixed",
        interactive_fraction=0.8,
        rate_rps=100.0,
        num_requests=1000,
        seed=7,
    )
    specs = list(iter_arrivals(cfg))
    assert len(specs) == 1000
    interactive = sum(1 for s in specs if s.request_class == "interactive")
    assert 750 <= interactive <= 850


def test_interactive_only_lengths() -> None:
    cfg = WorkloadConfig(mix="interactive", seed=1)
    rng = random.Random(1)
    spec = make_spec("interactive", cfg, rng)
    assert 256 <= spec.prompt_tokens <= 1000
    assert 32 <= spec.max_tokens <= 128


def test_background_only_lengths() -> None:
    cfg = WorkloadConfig(mix="background", seed=1)
    rng = random.Random(1)
    spec = make_spec("background", cfg, rng)
    assert 4000 <= spec.prompt_tokens <= 8000
    assert 256 <= spec.max_tokens <= 512
