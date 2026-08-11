# SLOServe — Agent Skills & Workflows

How Claude Code, Codex, and Cursor should execute work on this repo. Always read [AGENTS.md](AGENTS.md) first for constraints and current phase.

---

## Skill: discover-project-state

**When:** Starting any session, or after unclear user intent.

1. Read `AGENTS.md` → note **Current phase**.
2. List existing dirs: `harness/`, `mocks/`, `scheduler/`, `analysis/`, `results/`.
3. If `scheduler/` has real policy code but Gate 1 evidence is missing → **stop and warn**.
4. Report: phase, what’s built, next deliverable, what is out of scope.

---

## Skill: week1-harness (ACTIVE)

**When:** User asks to scaffold the repo, build the client, metrics, workloads, or mock server. Default until Week 1 deliverable exists.

### Goal

One command generates a workload and writes a metrics file **without a GPU**.

### Build checklist

- [ ] `harness/client.py` — streaming OpenAI-compatible HTTP client
- [ ] `harness/workloads.py` — interactive, background, interactive-only, 80/20 mix; rate + length controls
- [ ] `harness/metrics.py` — TTFT, ITL/TPOT, e2e, deadline goodput; percentiles
- [ ] `harness/run.py` — CLI: target URL, rate, mix, duration, output path
- [ ] `mocks/streaming_server.py` — fake token stream with controllable delays
- [ ] `tests/` — client records timestamps; cancel is safe; metrics formulas
- [ ] `README.md` — exact Week 1 command

### Required per-request fields

```text
request_id, request_class, arrival_time, first_token_time,
token_times[], completion_time, status (ok|cancelled|error)
```

### Acceptance

```bash
# Example — adjust to actual CLI once implemented
python -m harness.run --base-url http://127.0.0.1:8000 --mix 80/20 --rate 4 --duration 30 --out results/local.jsonl
```

Produces metrics file + optional percentile plot. No GPU, no vLLM required.

### Do not do in Week 1

Scheduler, vLLM deploy, K8s, Grafana, CUDA, real model calls.

---

## Skill: week2-baseline-interference

**When:** Week 1 harness works; user starts GPU baseline. Rent L4 only then.

### Steps

1. Deploy **unmodified** vLLM (pin commit/release in `configs/`).
2. Interactive-only sweep: `1 → 2 → 4 → 8 → 16 → 32` rps → find `λ_sat`.
3. At `0.5×`, `1.0×`, `1.5×`, `2.0×` λ_sat, run:
   - Interactive-only
   - 80/20 mixed
4. Graph: X = offered load, Y = interactive P99 TTFT; two lines.
5. One-page write-up under `analysis/`.

### Gate 1

Mixed traffic must materially hurt interactive P99 TTFT or goodput. If not → investigate chunked prefill / existing schedulers; **do not start Week 4**.

---

## Skill: week3-builtin-baselines

**When:** Gate 1 passed.

Compare and freeze one config each:

1. Default FCFS
2. Built-in priority
3. Priority + varied `max_num_batched_tokens`

Record: interactive P50/P90/P99 TTFT, deadline goodput, P99 ITL, output TPS, background completion rate, queue time, KV util, preemptions.

**Deliverable:** comparison table + one fixed config per policy (the best built-in becomes the real baseline).

Custom harness remains required for classes, deadlines, goodput (vLLM bench CLI alone is not enough).

---

## Skill: week4-scheduler-v1

**When:** Week 3 baseline frozen. **Not before Gate 1.**

1. Instrument decision logs: token budget, prefill/decode scheduled, interactive vs background allocation, queue time, remaining deadline, KV usage, preemptions, select/skip reason.
2. Implement simplest policy via `--scheduler-cls`:
   - Prefer waiting interactive near deadline
   - Reserve part of iteration token budget for interactive
   - Give remainder to background
3. Gate 2: streaming, cancel, background completion, deterministic parity, unit tests.

No dynamic prediction formulas yet.

---

## Skill: week5-ablations

**When:** Scheduler V1 + Gate 2 pass.

Add **one** feature per experiment; re-benchmark vs previous:

| Exp | Change |
|-----|--------|
| A | Background prefill chunk limit |
| B | Dynamic interactive reservation (queue depth / deadline pressure) |
| C | Background starvation prevention (aging priority) |

**Deliverable:** ablation table — what each feature changed.

---

## Skill: week6-final-writeup

**When:** Ablations done.

Policies: Default FCFS | Best built-in priority | SLOServe.

Workloads: interactive-only | 80/20 | 80/20 @ 2× overload | 50/50.

≥ 3 runs after warm-up; report median + variability.

Final table columns: Policy | P99 TTFT | Goodput | P99 ITL | TPS | TPS cost.

Write-up must include a win workload and a lose workload, with honest measured numbers.

---

## Skill: metrics-definitions

Use consistently across harness and analysis:

| Metric | Definition |
|--------|------------|
| TTFT | `first_token_time - arrival_time` |
| ITL | Inter-token latency between consecutive tokens |
| TPOT | Mean ITL over generated tokens (exclude first) |
| E2E | `completion_time - arrival_time` |
| Deadline goodput | `# interactive with TTFT ≤ SLO` / `# interactive` |
| SLO | 500 ms TTFT initially; one documented revision allowed |

Secondary: TPS, queue time, KV utilization, preemptions.

---

## Skill: stop-and-check-scope

**When:** User asks for infra, dashboards, custom CUDA, gateway, or scheduler early.

Reply with current week from `AGENTS.md`, what is blocked, and the single next deliverable. Offer to do that instead.

---

## Cursor / Claude / Codex wiring

| Tool | Where this guidance lives |
|------|---------------------------|
| All | `AGENTS.md`, `SKILLS.md` (repo root) |
| Cursor | Also `.cursor/rules/sloserve.mdc` (always apply) |
| Claude Code | Reads `AGENTS.md` / `CLAUDE.md` if present |
| Codex | Reads `AGENTS.md` |

If you add a `CLAUDE.md`, keep it to a short pointer: “Follow AGENTS.md and SKILLS.md.”
