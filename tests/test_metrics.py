"""Unit tests for metrics helpers."""

from harness.client import RequestRecord
from harness.metrics import aggregate_metrics, deadline_goodput, percentile, summarize


def test_percentile_basic() -> None:
    values = [1.0, 2.0, 3.0, 4.0, 5.0]
    assert percentile(values, 50) == 3.0
    assert percentile(values, 100) == 5.0
    assert percentile([], 50) is None


def test_deadline_goodput() -> None:
    records = [
        RequestRecord(
            request_id="1",
            request_class="interactive",
            arrival_time=0.0,
            first_token_time=0.2,
            completion_time=1.0,
            status="ok",
        ),
        RequestRecord(
            request_id="2",
            request_class="interactive",
            arrival_time=0.0,
            first_token_time=0.8,
            completion_time=1.0,
            status="ok",
        ),
        RequestRecord(
            request_id="3",
            request_class="background",
            arrival_time=0.0,
            first_token_time=0.1,
            completion_time=1.0,
            status="ok",
        ),
    ]
    assert deadline_goodput(records, slo_s=0.5) == 0.5
    summary = aggregate_metrics(records, slo_s=0.5)
    assert summary["deadline_goodput"] == 0.5
    assert summary["interactive_ttft"]["p50"] == 0.5


def test_summarize_empty() -> None:
    stats = summarize([])
    assert stats.count == 0
    assert stats.p99 is None
