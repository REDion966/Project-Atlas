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

Atlas is in the **Capability Track Era**. All four core capability tracks
(A–D) are implemented; Track D (Advanced Reasoning) is **released as `v0.20`**.

**Latest verified test run (Track D release gate):** `2973 passed`, `57 subtests passed`, `0 failed`, `0 errors` (~10 min).
*Current test inventory (not a result):* 178 test files, 766 test classes, 2958 test methods.

**Current schema version:** `10`.

## Major Capabilities & Track Status

| Track | Capability | Status |
|---|---|---|
| A | Research & Knowledge | **COMPLETE** (`v0.17.0`) |
| B | Tool Ecosystem | **COMPLETE** (`v0.18.0`) |
| C | Long-Term Learning | **COMPLETE & runtime-integrated** (`v0.19.1`) |
| D | Advanced Reasoning | **RELEASED (`v0.20`)** — implemented & runtime-integrated |

### Advanced Reasoning (Track D)

- Deterministic **multi-step reasoning**, **causal/counterfactual** analysis,
  **hypothesis generation**, **self-verification**, and **meta-reasoning**.
- Reasoning is pure deterministic pipeline logic; large-model enhancement is
  optional and protocol-injected.
- Persistence via `reasoning_*` SQLite tables (schema migration **v10**).
- Governed ingestion through the Evolution Framework (**GOV-011**) — the ingest
  sink is not yet wired at runtime, so `reasoning.ingest` intentionally fails
  closed.
- Exposed as `reasoning.*` capability handlers and an `atlas reasoning` CLI.

## Architecture (high level)

Atlas is modular, AI-independent, and event-driven. The **kernel** is the only
place where the whole system is wired. A **ServiceContainer** registers public
shared services; a **RuntimeCoordinator** orchestrates the 14-stage cognitive
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
atlas goal                        # goal intelligence
```

## Repository Structure

```
atlas/                Core framework packages
  ├── kernel/         Service container + root application (composition)
  ├── runtime/        RuntimeCoordinator (14-stage cognitive pipeline)
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
- **`docs/archive/`** — historical documents (reference only)
- **Git history** — historical chronology and implementation record

> **Rule:** Future AI agents MUST NOT treat archived documents as current
> architecture. When a major milestone completes: update `ATLAS_STATE.md`,
> then `ROADMAP.md`, then `README.md` if the public status changed.

## Roadmap (summary)

- **COMPLETED:** Tracks A, B, C, and the Track D foundation/implementation.
- **CURRENT:** Post-Track-D — Track D is released (`v0.20`); the first
  already-recorded NEXT implementation item (Track A research coordinator)
  is the primed next task.
- **DEFERRED:** Governed `ReasoningIngestSink` runtime wiring remains
  pending/deferred; it depends on the Phase 16 schedule-store/dispatcher
  hand-off being finalized, so `reasoning.ingest` stays fail-closed (sink not
  wired).
- **NEXT/PLANNED:** Per existing repository plans and track designs.
- **PROPOSED (not approved):** Tracks E, F, G from the Capability Track
  roadmap. See `docs/ROADMAP.md` for details.

---

## Author

AB AL Mamun
