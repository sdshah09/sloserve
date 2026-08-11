---
name: sloserve-week1-harness
description: >-
  Builds the SLOServe Week 1 streaming benchmark harness (client, workloads,
  metrics, mock server). Use when scaffolding the repo, implementing the
  OpenAI-compatible streaming client, recording TTFT/token timestamps/goodput,
  or testing against a mock server without a GPU.
---

# SLOServe Week 1 Harness

## Before you start

1. Read [AGENTS.md](../../../AGENTS.md) and [SKILLS.md](../../../SKILLS.md) → skill `week1-harness`.
2. Do **not** implement `scheduler/`, rent a GPU, or deploy vLLM.

## Implement

```text
harness/client.py      # streaming OpenAI-compatible client
harness/workloads.py   # interactive / background / 80-20 mix
harness/metrics.py     # TTFT, ITL/TPOT, e2e, deadline goodput
harness/run.py         # CLI entrypoint
mocks/streaming_server.py
tests/
```

## Per-request record

`request_id`, `request_class`, `arrival_time`, `first_token_time`, `token_times[]`, `completion_time`, `status`.

## Done when

One command hits the mock server and writes JSONL/CSV metrics (+ optional percentile plot) with no GPU.
