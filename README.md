# Project Atlas

**Atlas is a personal AI operating framework** — not a chatbot, not a model
wrapper, not a demo. It is a long-term, Python-based, modular system that
orchestrates multiple AI models while owning its own memory, knowledge,
reasoning, planning, learning, and tooling. Atlas coordinates these subsystems
into a unified whole that grows more capable over time, while remaining under
human ownership and oversight.

> *AI models are tools. Atlas is the intelligence. Models may change. Atlas remains.*

---

## Current Status

Atlas is in the **Capability Track Era — Atlas Core COMPLETE**. All four core
capability tracks (A–D) are implemented; Track D (Advanced Reasoning) is
**released as `v0.20`**. Track A's research coordinator (Phase 21) and Phase 22
(Toolchain Execution & Learned-Skill Progression: CONDITIONAL/PARALLEL
execution + learned-skill authoring/promotion + integration) are implemented
and bundled, and the post-core improvements (F1–F8) and two hardening fixes are
complete — release **v0.20.0** is available at tag `v0.20.0` (`b92c5d9`).
**Phase 22 is the FINAL numbered implementation phase for Atlas Core — there is
NO Phase 23.** Development has transitioned to **post-core guided
self-improvement** (see `docs/ATLAS_STATE.md` §22.4 and §23): Atlas improves
itself through the existing governed mechanisms (`Observe/record → analyze/plan
→ propose → approve → execute governed changes → verify → repeat`) with
`SELF_CONFIG`/`INFORMATION` as the enabled governed scopes. CODE mutation
remains locked and is not enabled; code changes may be produced as reviewable
artifacts/patches rather than autonomously applied. **Autonomous code mutation
remains disabled.**

**Latest verified test run (v0.20.0 + Foundation Strengthening Batches 1–2):** `3260 passed`, `57 subtests passed`, `0 failed`, `2 warnings` — the 2 warnings are non-blocking `asyncio.iscoroutinefunction` deprecation warnings in a Phase 21 test.
*Current test inventory (not a result):* 178+ test files, 766+ test classes, 2958+ test methods.

**Current schema version:** `10`.

## Major Capabilities & Track Status

| Track | Capability | Status |
|---|---|---|
| A | Research & Knowledge | **COMPLETE** (`v0.17.0`); coordinator + `research.coordinate` implemented (Phase 21, bundled with Phase 22) |
| B | Tool Ecosystem | **COMPLETE** (`v0.18.0`); CONDITIONAL/PARALLEL execution + learned-skill authoring/promotion added (Phase 22) |
| C | Long-Term Learning | **COMPLETE & runtime-integrated** (`v0.19.1`) |
| D | Advanced Reasoning | **RELEASED (`v0.20`)** — implemented & runtime-integrated |

### Advanced Reasoning (Track D)

- Deterministic **multi-step reasoning**, **causal/counterfactual** analysis,
  **hypothesis generation**, **self-verification**, and **meta-reasoning**.
- Reasoning is pure deterministic pipeline logic; large-model enhancement is
  optional and protocol-injected.
- Persistence via `reasoning_*` SQLite tables (schema migration **v10**).
- Governed ingestion through the Evolution Framework (**GOV-011**) — the
  kernel-owned governed sink is wired at runtime into the research, longterm,
  and advanced-reasoning bridges.
- Exposed as `reasoning.*` capability handlers and an `atlas reasoning` CLI.

### Post-Core Improvements

- **F1** — runtime observation coverage; **F2** — planner observation
  aggregation; **F7** — closed learning feedback loop; **F8** — evolution
  audit/proposal visibility (`atlas proposals list|show|audit`).
- **F3** subsumed by F8; **F4** deferred/monitored; **F5** scheduler fail-soft
  diagnostics; **F6** persistence degradation documented as expected behavior.
- **Hardening** — cognition runtime test correctly routes to Mock Provider
  (Ollama 404 eliminated) and SQLite understanding-counter INTEGER overflow is
  clamped deterministically at `2**63 - 1`.

## Architecture (high level)

Atlas is modular, AI-independent, and event-driven. The **kernel** is the only
place where the whole system is wired. A **ServiceContainer** registers public
shared services; a **RuntimeCoordinator** orchestrates the 15-stage cognitive
pipeline; track-specific private dependencies (e.g. `AdvancedReasoningService`)
are injected directly and **not** registered in the container.

Layers: `CLI → Services → Managers/Engines → Repositories → Storage`.
Pure logic layers are isolated from infrastructure; the Evolution Framework is
the only channel by which Atlas may change its own operational state.

## Development Environment

```bash
# Python 3.10+ recommended; create a virtual environment
python -m venv .venv

# Activate (Windows PowerShell)
.venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt
```

## Running the Test Suite

```bash
pytest -q
```

All subsystems are tested against the full suite; tests are order-independent
and mandatory before completing any feature.

## Basic CLI

```bash
python main.py                    # run Atlas (interactive)
atlas research                    # Track A — research & knowledge
atlas toolchain / atlas skill     # Track B — tool ecosystem
atlas memory                      # Track C — long-term learning
atlas reasoning                   # Track D — advanced reasoning
atlas evolution                   # governed self-evolution
atlas proposals                   # evolution proposal audit (read-only; post-core F8)
atlas goal                        # goal intelligence
```

## Repository Structure

```
atlas/                Core framework packages
  ├── kernel/         Service container + root application (composition)
  ├── runtime/        RuntimeCoordinator (15-stage cognitive pipeline)
  ├── cognition/      API, context, engine, decisions, pipeline
  ├── reasoning/      Core reasoning (controller, capabilities, planning)
  ├── advanced_reasoning/  Track D — advanced reasoning (reasoning.*)
  ├── research/       Track A — research & knowledge
  ├── toolchain/      Track B — tool ecosystem
  ├── longterm/       Track C — long-term learning
  ├── memory/ knowledge/ understanding/ world_model/ learning_engine/
  ├── evolution/      Evolution Framework (governance, autonomy, gateway)
  ├── storage/        All SQLite adapters + migration framework
  ├── cli/            Command-line interface
  └── ...             Additional modules (services, events, config, goals, etc.)
tests/                Test suite
atlas_data/ data/     Runtime data artifacts (gitignored database files)
docs/                 Documentation
```

## Documentation Hierarchy

- **`README.md`** — public entry point (this file)
- **`docs/ATLAS_STATE.md`** — authoritative current technical state
- **`docs/ROADMAP.md`** — authoritative forward direction
- **`CHANGELOG.md`** — release notes (active since v0.20.0)
- **`docs/archive/`** — historical documents (reference only)
- **Git history** — historical chronology and implementation record

> **Rule:** Future AI agents MUST NOT treat archived documents as current
> architecture. When a major milestone completes: update `ATLAS_STATE.md`,
> then `ROADMAP.md`, then `README.md` if the public status changed.

## Roadmap (summary)

- **COMPLETED:** Tracks A, B, C, Track D (v0.20), Track A research coordinator
  (Phase 21), Phase 22 — Toolchain Execution & Learned-Skill Progression — and
  post-core F1–F8 + hardening. **Atlas Core is complete at Phase 22.**
  Foundation Strengthening Batch 1 (kernel decomposition) and Batch 2
  (scaffold cleanup) are complete.
- **CURRENT:** Foundation Strengthening — post-release architectural hardening.
  `SELF_CONFIG`/`INFORMATION` are the enabled governed scopes;
  `CODE_ARTIFACT`/`SANDBOXED`/`AUTONOMOUS` remain locked.
- **DEFERRED:** Governed `ReasoningIngestSink` runtime wiring remains
  pending/deferred; `reasoning.ingest` stays fail-closed (sink not wired).
- **NEXT:** Governed ingest sink resolution, episodic context surfacing,
  remaining Track A/C follow-ups. None is required for core completion.
- **PROPOSED (not approved):** Tracks E, F, G from the Capability Track
  roadmap. See `docs/ROADMAP.md` for details.

---

## Author

AB AL Mamun
