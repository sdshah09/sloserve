"""Latency metrics, goodput, JSONL/CSV export, and percentile plots."""

from __future__ import annotations

import csv
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

from harness.client import RequestRecord


@dataclass
class SummaryStats:
    count: int
    p50: float | None
    p90: float | None
    p99: float | None
    mean: float | None
    min: float | None
    max: float | None


def percentile(values: Sequence[float], p: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (p / 100.0) * (len(ordered) - 1)
    low = math.floor(rank)
    high = math.ceil(rank)
    if low == high:
        return ordered[low]
    weight = rank - low
    return ordered[low] * (1 - weight) + ordered[high] * weight


def summarize(values: Sequence[float]) -> SummaryStats:
    if not values:
        return SummaryStats(0, None, None, None, None, None, None)
    return SummaryStats(
        count=len(values),
        p50=percentile(values, 50),
        p90=percentile(values, 90),
        p99=percentile(values, 99),
        mean=sum(values) / len(values),
        min=min(values),
        max=max(values),
    )


def deadline_goodput(
    records: Iterable[RequestRecord],
    *,
    slo_s: float = 0.5,
    request_class: str = "interactive",
) -> float | None:
    relevant = [
        r
        for r in records
        if r.request_class == request_class and r.status == "ok" and r.ttft is not None
    ]
    if not relevant:
        return None
    met = sum(1 for r in relevant if r.ttft is not None and r.ttft <= slo_s)
    return met / len(relevant)


def aggregate_metrics(
    records: Sequence[RequestRecord],
    *,
    slo_s: float = 0.5,
) -> dict[str, Any]:
    ok = [r for r in records if r.status == "ok"]
    interactive = [r for r in ok if r.request_class == "interactive"]
    background = [r for r in ok if r.request_class == "background"]

    def ttfts(rs: Sequence[RequestRecord]) -> list[float]:
        return [r.ttft for r in rs if r.ttft is not None]

    def e2es(rs: Sequence[RequestRecord]) -> list[float]:
        return [r.e2e for r in rs if r.e2e is not None]

    def tpots(rs: Sequence[RequestRecord]) -> list[float]:
        return [r.tpot for r in rs if r.tpot is not None]

    all_itls = [itl for r in ok for itl in r.itls]
    output_tokens = sum(r.output_token_count for r in ok)
    if ok:
        start = min(r.arrival_time for r in ok)
        end = max(r.completion_time or r.arrival_time for r in ok)
        wall = max(end - start, 1e-9)
    else:
        wall = 0.0

    return {
        "num_requests": len(records),
        "num_ok": len(ok),
        "num_cancelled": sum(1 for r in records if r.status == "cancelled"),
        "num_error": sum(1 for r in records if r.status == "error"),
        "interactive_ok": len(interactive),
        "background_ok": len(background),
        "deadline_goodput": deadline_goodput(records, slo_s=slo_s),
        "slo_s": slo_s,
        "interactive_ttft": summarize(ttfts(interactive)).__dict__,
        "background_ttft": summarize(ttfts(background)).__dict__,
        "interactive_e2e": summarize(e2es(interactive)).__dict__,
        "interactive_tpot": summarize(tpots(interactive)).__dict__,
        "interactive_itl": summarize(
            [itl for r in interactive for itl in r.itls]
        ).__dict__,
        "all_itl": summarize(all_itls).__dict__,
        "output_tps": (output_tokens / wall) if wall > 0 else 0.0,
        "output_tokens": output_tokens,
    }


def write_jsonl(records: Sequence[RequestRecord], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record.to_dict()) + "\n")


def write_csv(records: Sequence[RequestRecord], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "request_id",
        "request_class",
        "arrival_time",
        "first_token_time",
        "completion_time",
        "status",
        "prompt_tokens",
        "max_tokens",
        "output_token_count",
        "ttft",
        "e2e",
        "tpot",
        "error",
    ]
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for record in records:
            row = {k: record.to_dict().get(k) for k in fieldnames}
            writer.writerow(row)


def write_summary(summary: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")


def plot_latency_percentiles(
    records: Sequence[RequestRecord],
    path: Path,
    *,
    slo_s: float = 0.5,
) -> Path | None:
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        return None

    interactive = [
        r for r in records if r.request_class == "interactive" and r.status == "ok"
    ]
    ttfts = [r.ttft for r in interactive if r.ttft is not None]
    e2es = [r.e2e for r in interactive if r.e2e is not None]
    itls = [itl for r in interactive for itl in r.itls]
    if not ttfts and not e2es and not itls:
        return None

    path.parent.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(1, 3, figsize=(12, 3.5))

    def _cdf(ax, values: list[float], title: str, vline: float | None = None) -> None:
        if not values:
            ax.set_title(f"{title} (empty)")
            return
        ordered = sorted(values)
        ys = [i / (len(ordered) - 1 or 1) for i in range(len(ordered))]
        ax.plot(ordered, ys, color="#1f4e5f")
        if vline is not None:
            ax.axvline(vline, color="#b85c38", linestyle="--", linewidth=1, label=f"SLO {vline}s")
            ax.legend(fontsize=8)
        ax.set_title(title)
        ax.set_xlabel("seconds")
        ax.set_ylabel("CDF")
        ax.grid(True, alpha=0.3)

    _cdf(axes[0], ttfts, "Interactive TTFT CDF", slo_s)
    _cdf(axes[1], itls, "Interactive ITL CDF")
    _cdf(axes[2], e2es, "Interactive E2E CDF")
    fig.tight_layout()
    fig.savefig(path, dpi=140)
    plt.close(fig)
    return path
