"""CLI entrypoint: generate workload, stream requests, write metrics."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

from harness.client import RequestRecord, StreamingClient
from harness.metrics import (
    aggregate_metrics,
    plot_latency_percentiles,
    write_csv,
    write_jsonl,
    write_summary,
)
from harness.workloads import (
    BACKGROUND_INPUT,
    BACKGROUND_OUTPUT,
    INTERACTIVE_INPUT,
    INTERACTIVE_OUTPUT,
    LengthRange,
    WorkloadConfig,
    iter_arrivals,
)


def _load_dotenv(path: Path | None = None) -> None:
    env_path = path or Path.cwd() / ".env"
    if not env_path.is_file():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        os.environ.setdefault(key, value)


def _resolve_api_key(cli_value: str | None) -> str | None:
    return (
        cli_value
        or os.environ.get("OPENAI_API_KEY")
        or os.environ.get("SLOSERVE_API_KEY")
    )


async def _run_async(args: argparse.Namespace) -> int:
    if args.quick:
        interactive_input = LengthRange(16, 64)
        interactive_output = LengthRange(4, 12)
        background_input = LengthRange(64, 128)
        background_output = LengthRange(8, 24)
    else:
        interactive_input = INTERACTIVE_INPUT
        interactive_output = INTERACTIVE_OUTPUT
        background_input = BACKGROUND_INPUT
        background_output = BACKGROUND_OUTPUT

    cfg = WorkloadConfig(
        mix=args.mix,
        interactive_fraction=args.interactive_fraction,
        rate_rps=args.rate,
        duration_s=args.duration,
        num_requests=args.num_requests,
        model=args.model,
        seed=args.seed,
        interactive_input=interactive_input,
        interactive_output=interactive_output,
        background_input=background_input,
        background_output=background_output,
    )
    api_key = _resolve_api_key(args.api_key)
    client = StreamingClient(args.base_url, api_key=api_key, timeout=args.timeout)

    specs = list(iter_arrivals(cfg))
    if not specs:
        print("No requests generated.", file=sys.stderr)
        return 1

    # Align schedule to "now" so arrival_time is absolute wall clock.
    offset = time.time() - specs[0].arrival_time
    for spec in specs:
        assert spec.arrival_time is not None
        spec.arrival_time += offset

    semaphore = asyncio.Semaphore(args.max_concurrency)
    cancel_event = asyncio.Event()
    records: list[RequestRecord] = []
    records_lock = asyncio.Lock()

    async def _one(spec) -> None:
        assert spec.arrival_time is not None
        delay = spec.arrival_time - time.time()
        if delay > 0:
            try:
                await asyncio.sleep(delay)
            except asyncio.CancelledError:
                return
        if cancel_event.is_set():
            return
        async with semaphore:
            record = await client.chat_completion_stream(
                spec, cancel_event=cancel_event
            )
        async with records_lock:
            records.append(record)

    tasks = [asyncio.create_task(_one(spec)) for spec in specs]
    try:
        await asyncio.gather(*tasks)
    except asyncio.CancelledError:
        cancel_event.set()
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise

    out = Path(args.out)
    write_jsonl(records, out)
    if args.csv:
        write_csv(records, Path(args.csv))

    summary = aggregate_metrics(records, slo_s=args.slo)
    summary_path = Path(args.summary) if args.summary else out.with_suffix(".summary.json")
    write_summary(summary, summary_path)

    plot_path = None
    if args.plot:
        plot_path = plot_latency_percentiles(
            records, Path(args.plot), slo_s=args.slo
        )

    print(json.dumps(summary, indent=2))
    print(f"wrote raw metrics: {out}")
    print(f"wrote summary: {summary_path}")
    if plot_path:
        print(f"wrote plot: {plot_path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="SLOServe mixed-workload streaming benchmark harness"
    )
    p.add_argument("--base-url", default="http://127.0.0.1:8000")
    p.add_argument("--api-key", default=None)
    p.add_argument(
        "--mix",
        choices=["interactive", "background", "mixed"],
        default="mixed",
        help="interactive-only, background-only, or 80/20 mixed (default)",
    )
    p.add_argument(
        "--interactive-fraction",
        type=float,
        default=0.8,
        help="Fraction of interactive requests when --mix mixed",
    )
    p.add_argument("--rate", type=float, default=4.0, help="Arrival rate (req/s)")
    p.add_argument("--duration", type=float, default=30.0, help="Duration seconds")
    p.add_argument(
        "--num-requests",
        type=int,
        default=None,
        help="If set, ignore duration and send exactly N requests",
    )
    p.add_argument("--model", default="mock-model")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument(
        "--quick",
        action="store_true",
        help="Use short prompts/outputs for local mock smoke tests",
    )
    p.add_argument("--slo", type=float, default=0.5, help="Interactive TTFT SLO seconds")
    p.add_argument("--max-concurrency", type=int, default=64)
    p.add_argument("--timeout", type=float, default=600.0)
    p.add_argument("--out", default="results/local.jsonl")
    p.add_argument("--csv", default=None)
    p.add_argument("--summary", default=None)
    p.add_argument("--plot", default="results/local_latency_cdf.png")
    return p


def main(argv: list[str] | None = None) -> None:
    _load_dotenv()
    args = build_parser().parse_args(argv)
    try:
        raise SystemExit(asyncio.run(_run_async(args)))
    except KeyboardInterrupt:
        print("interrupted; cancelling in-flight requests", file=sys.stderr)
        raise SystemExit(130) from None


if __name__ == "__main__":
    main()
