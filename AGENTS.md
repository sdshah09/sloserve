# SLOServe — Agent Orientation

Read this file before writing any code. It is the source of truth for Claude Code, Codex, Cursor, and any other coding agent.

## What this project is

**SLOServe** measures whether a deadline-aware vLLM scheduler improves interactive P99 TTFT and deadline goodput under mixed traffic, and quantifies the throughput cost.

Hypothesis (numbers are targets, not claims):

> Under 80/20 mixed workload at 2× overload, SLOServe improves interactive deadline goodput and P99 TTFT vs tuned vLLM priority scheduling, at a measurable TPS cost.

## Hard constraints (do not violate)

1. **Do not rent a GPU** until Week 1 harness works against a mock server.
2. **Do not build a custom scheduler** until Gate 1 passes (interference proven).
3. **Do not build** a gateway, Kubernetes deployment, Grafana dashboard, or CUDA kernels until the interference graph exists.
4. Compare against **existing vLLM capabilities**, not naive FCFS alone:
   - Default FCFS
   - Built-in priority scheduling
   - Chunked prefill (already in vLLM)
5. Custom scheduler loads only via `--scheduler-cls` when Week 4 starts.
6. Change **one variable at a time** in Week 5 ablations.

## Current phase

| Week | Focus | Status |
|------|--------|--------|
| 1 | Benchmark harness + mock server | **ACTIVE** |
| 2 | GPU baseline + interference graph | Blocked on Week 1 |
| 3 | Strongest built-in baseline | Blocked on Gate 1 |
| 4 | Scheduler V1 + instrumentation | Blocked on Week 3 |
| 5 | Ablations (A/B/C) | Blocked on Week 4 |
| 6 | Final benchmarks + write-up | Blocked on Week 5 |

**Right now:** build only the streaming benchmark client and harness. See [SKILLS.md](SKILLS.md) → Week 1.

## Fixed experimental setup

| Component | Choice |
|-----------|--------|
| GPU | One NVIDIA L4 24 GB |
| Model | Qwen3-8B |
| Runtime | Pin one vLLM release/commit (record in configs) |
| Interactive | 256–1,000 in; 32–128 out |
| Background | 4,000–8,000 in; 256–512 out |
| Mix | 80% interactive / 20% background |
| Initial SLO | Interactive TTFT ≤ 500 ms (revise once if unrealistic; document why) |
| Primary metric | Deadline goodput |
| Repetitions | ≥ 3 runs after warm-up |

**Deadline goodput** = interactive requests with TTFT ≤ 500 ms / total interactive requests.

## Target repository layout

```text
sloserve/
├── AGENTS.md          # this file
├── SKILLS.md          # how-to workflows for each week
├── README.md
├── harness/
│   ├── client.py      # streaming OpenAI-compatible client
│   ├── workloads.py   # interactive / background / mix generators
│   ├── metrics.py     # TTFT, ITL/TPOT, e2e, goodput
│   └── run.py         # CLI entrypoint
├── configs/           # pinned vLLM + workload YAML/JSON
├── analysis/          # plots, tables, write-ups
├── scheduler/         # Week 4+ only
├── tests/
└── mocks/             # mock streaming server for Week 1
```

## Week 1 must record (per request)

Every streaming request must capture:

- `request_id`, `request_class` (`interactive` | `background`)
- `arrival_time`
- `first_token_time` (TTFT = first_token − arrival)
- `token_times[]` (timestamp of every subsequent token)
- `completion_time`
- Derived: TTFT, ITL/TPOT, e2e latency, goodput flag vs SLO

Output: JSONL or CSV. Percentile graphs from analysis scripts.

## Gates

### Gate 1 (end of Week 2) — required before any scheduler work

Proceed only if mixed traffic **materially worsens** interactive P99 TTFT or goodput vs interactive-only. If not, investigate chunked-prefill / existing scheduling first — do not invent a scheduler for a non-problem.

### Gate 2 (end of Week 4)

Streaming works, cancellation works, background eventually completes, deterministic outputs match, unit tests pass.

## What "done" looks like

- Reproducible mixed-workload harness
- Interference graph (prove or disprove)
- Default / priority / tuned built-in baselines
- Custom scheduler + decision logs + tests
- Ablation table
- Workloads where the scheduler wins **and** loses
- Honest write-up with measured numbers (not the hypothesis)

## Agent behavior rules

- Prefer the smallest change that advances the **current week**.
- Do not expand scope into later weeks "while you're here."
- Keep harness GPU-free until Week 2.
- Pin versions; never leave "latest" undocumented.
- Prefer `--scheduler-cls` over forking vLLM internals when scheduler work begins.
- Raw results always land under a dated `results/` or `analysis/runs/` path.

## Quick links

- [vLLM scheduler config](https://docs.vllm.ai/en/latest/api/vllm/config/scheduler/)
- [vLLM optimization guide](https://docs.vllm.ai/en/stable/configuration/optimization/)
- [vLLM bench serve CLI](https://docs.vllm.ai/en/stable/cli/bench/serve/)
- Workflow details: [SKILLS.md](SKILLS.md)
