# SLOServe

Deadline-aware scheduling for LLM inference under mixed interactive and background traffic.

## Purpose

Interactive LLM requests (chat, tools, agents) share GPUs with long background jobs (batch generation, offline eval, RAG indexing). Default serving policies optimize for throughput or FCFS fairness, so background prefills can inflate interactive time-to-first-token (TTFT) and miss latency SLOs.

**SLOServe** asks a precise question:

> Does a deadline-aware scheduler on top of vLLM improve interactive P99 TTFT and deadline goodput under mixed traffic—and at what throughput cost?

The work compares against what vLLM already provides (FCFS, priority scheduling, chunked prefill), not against a strawman baseline. The primary metric is **deadline goodput**: the fraction of interactive requests whose TTFT meets a fixed SLO (initially ≤ 500 ms). Secondary metrics include P99 TTFT, ITL/TPOT, throughput, queue time, KV-cache utilization, and preemptions.

## Fixed setup

| Component | Choice |
|-----------|--------|
| GPU | NVIDIA L4 24 GB |
| Model | Qwen3-8B |
| Traffic | 80% interactive / 20% background |
| Interactive | 256–1,000 input; 32–128 output tokens |
| Background | 4,000–8,000 input; 256–512 output tokens |

## Status

Week 1 harness is in place: streaming client, mixed workloads, metrics, and a mock server. No GPU required yet.

## Quick start (no GPU)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# terminal 1
python -m mocks.streaming_server --port 8000

# terminal 2
python -m harness.run \
  --base-url http://127.0.0.1:8000 \
  --mix mixed \
  --rate 4 \
  --num-requests 20 \
  --quick \
  --out results/local.jsonl \
  --plot results/local_latency_cdf.png
```

This writes raw per-request JSONL (class, arrival, first-token, every token time, completion), a summary JSON, and a latency CDF plot.

```bash
pytest
```
