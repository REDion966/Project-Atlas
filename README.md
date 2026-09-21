# Project Atlas

**Atlas is a personal AI operating framework** — not a chatbot, not a model
wrapper, not a demo. It is a long-term, Python-based, modular system that
orchestrates multiple AI models while owning its own memory, knowledge,
reasoning, planning, learning, and tooling. Atlas coordinates these subsystems
into a unified whole that grows more capable over time, while remaining under
human ownership and oversight.

> *AI models are tools. Atlas is the intelligence. Models may change. Atlas remains.*

> **Project Started (GitHub): July 10, 2026**

---

## Atlas Timeline

- **July 10, 2026** — Project Atlas GitHub repository created
- **July 2026** — Core foundation and workspace architecture
- **August 2026** — Intelligence, reasoning, self-development, and conversational architecture
- **September 2026** — Memory evolution, capability productionization, and conversational state
- **September 2026** — Phase C evidence-driven evolution (C0 → C9) reached the
  established evidence boundary; reference resolution completed the
  conversational state layer (C7)

---

## Current Status

Atlas is in the **Post-Roadmap Operational Era — Atlas Core COMPLETE** (this
supersedes the earlier Capability Track Era; see `docs/ATLAS_STATE.md` §2 and
§31). All four core capability tracks (A–D) are implemented; Track D (Advanced
Reasoning) is **released as `v0.20`**. Track A's research coordinator (Phase 21)
and Phase 22
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

**Phase C — evidence-driven evolution (C0 → C9):** the frozen roadmap reached
its established evidence boundary. **C8 is CLOSED — no evidence-backed gap.
C9 readiness is COMPLETE — no evidence-backed gap. C5.2 was NOT AUTHORIZED.**
No C10 exists or is planned. Current status and deliveries are owned by
`docs/ATLAS_STATE.md` §31; authorized forward direction by `docs/ROADMAP.md`.

**Phase 1–5 direct-evolution program (additive; deterministic; model-independent):**
Phase 3 — knowledge acquisition & research (deterministic authorized source
selection; validated knowledge retrieval); Phase 4 — governed self-development
(development cycle → sandbox execution → verification, with deterministic
relevant-test selection and bounded correction); Phase 5 — direct Atlas evolution
(capability/knowledge-gap adjudication, bounded deterministic scaffold authoring,
a bounded Development Driver, an opt-in Development Envelope for sandbox-only
execution, and OWNER-only transactional promotion with CODE versioning and
capability activation). **Phase 5.2 is implemented and Phase 5.3 is validated
(G1 — capability activation — closed).** See `docs/ATLAS_STATE.md` §32. This
`README.md` remains a public entry point, not an authority.

**Latest verified full-suite run (historical baseline):** full suite **5,945 test
items executed: 5,876 test cases passed (plus 67 subtests passed), 0 failed,
0 errors, 2 skipped** (pytest exit 0). This is the last recorded full-suite
baseline and was **not** re-run for the Phase 3–5 reconciliation, which verified
focused suites only (see `docs/ATLAS_STATE.md` §32).

**Current schema version:** `11`.

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
- **Post-core memory thread** — Persistent Learning (reusable
  `LearningInsight` persistence, migration v11), deterministic semantic
  recall (`memory.semantic_query` capability + `atlas memory search`), and
  long-term forgetting-policy operationalization (advisory, governed). All
  additive; schema remains `v11`.
- **Conversational development intake (B1+B2+B3)** — a casual conversational
  development request is classified deterministically (`TaskIntake`/`TaskSpec`),
  converted into a governed `DevelopmentNeed`, and routed through the existing
  development-cycle preparation flow, stopping at the human approval boundary
  (`PENDING_APPROVAL`). Additive; schema remains `v11`; no governance bypass.

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
# Python 3.11+ required; create a virtual environment
python -m venv .venv

# Activate (Windows PowerShell)
.venv\Scripts\Activate.ps1

# Install runtime dependencies
pip install -r requirements.txt

# Install runtime + development/test dependencies
pip install -e ".[test]"
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

The single authority model is defined in `docs/ATLAS_STATE.md` §0. In short:

1. **`docs/ATLAS_STATE.md`** — authoritative current state
2. **`docs/ROADMAP.md`** — authoritative future direction
3. **`docs/ATLAS_CORE.md`** — permanent architectural principles
4. **`docs/ATLAS_VISION.md`** — identity and purpose
5. **`docs/DEVELOPMENT_WORKFLOW.md`** — development process
6. **`CHANGELOG.md`**, **`docs/archive/`**, evidence reports — historical record
   (reference only)

This `README.md` is a public entry point, not an authority; it must not be read
as a second source of truth.

> **Rule:** Future AI agents MUST NOT treat archived documents or evidence
> reports as current architecture. When a major milestone completes: update
> `ATLAS_STATE.md`, then `ROADMAP.md`, then `README.md` if the public status
> changed.

## Roadmap (summary)

- **COMPLETED:** Tracks A, B, C, Track D (v0.20), Track A research coordinator
  (Phase 21), Phase 22 — Toolchain Execution & Learned-Skill Progression — and
  post-core F1–F8 + hardening. **Atlas Core is complete at Phase 22.**
  Foundation Strengthening Batch 1 (kernel decomposition), Batch 2 (scaffold
  cleanup), the Stage A1→H guided self-improvement thread, and the Track C
  post-core follow-ups (Persistent Learning, deterministic semantic recall,
  forgetting-policy operationalization) are complete.
- **CURRENT:** Post-roadmap operational state — governed, evidence-driven
  self-improvement. `SELF_CONFIG`/`INFORMATION` are the enabled governed
  scopes; `CODE_ARTIFACT`/`SANDBOXED`/`AUTONOMOUS` remain locked (see
  `docs/ATLAS_STATE.md` §31).
- **DEFERRED:** Episodic-context surfacing (pending a RuntimeCoordinator
  review).
- **NEXT:** No implementation NEXT is currently defined; any future work
  requires an explicitly written, owner-approved scope (see
  `docs/ROADMAP.md`).
- **PROPOSED (not approved):** Tracks E, F, G from the Capability Track
  roadmap. See `docs/ROADMAP.md` for details.

---

## Author

AB AL Mamun
