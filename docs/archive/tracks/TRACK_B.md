# Atlas Capability Track B — Tool Ecosystem

> HISTORICAL DOCUMENT — This track record is preserved for historical/design reference. The current implementation status is maintained in `docs/ATLAS_STATE.md` and `docs/ROADMAP.md`.

**Status:** Phase 18.1–18.10 (Batch 1–4) **· Integration:** Additive, no locked-component redesign

---

## 1. Overview

Track B delivers the tool-ecosystem layer: skill registration, deterministic tool-chain planning, safe chain execution, tool-effectiveness tracking, tool learning, SQLite persistence, capability-handler registration, governed skill-activation ingestion (GOV-009), and CLI presentation.

Skill activation **never** mutates the skill registry directly from Track B code — all activation intents flow through the Phase 16 Evolution Framework as INFORMATION-scope KNOWLEDGE `EvolutionRequest`s.

```
goal / skill
    ↓ ToolChainPlanner (18.4)
ToolChainPlan (steps, strategy, depth)
    ↓ ToolChainExecutor (18.5)
ToolChainResult
    ├─ ToolEffectivenessTracker (18.5)   — per-tool evidence
    ├─ ToolLearner (18.6)                — deterministic recommendations
    ├─ ToolchainSQLiteStorage (18.8)     — toolchain_* persistence
    └─ skill activate intent (18.10)
        → ToolchainEvolutionTracker → EvolutionRequest (KNOWLEDGE) → governed sink (18.9)
Capability handlers toolchain.execute_chain|run_skill|effectiveness|skills (18.7)
Component metadata + CLI `atlas toolchain ...` / `atlas skill ...` (18.10)
```

---

## 2. Architecture

### 2.1 Dependency direction (pure → infrastructure)

```
atlas/toolchain/models.py                — frozen dataclasses + enums (18.1)
atlas/toolchain/catalog.py               — skill categories, strategy names, defaults (18.2)
atlas/toolchain/registry.py              — SkillRegistry (18.3)
atlas/toolchain/planner.py               — ToolChainPlanner + ToolProvider protocol (18.4)
atlas/toolchain/executor.py              — Safe execution + RiskPolicy + ToolInvoker (18.5)
atlas/toolchain/effectiveness.py         — ToolEffectivenessTracker (18.5)
atlas/toolchain/learner.py               — ToolLearner (18.6)
        │ (pure)
atlas/toolchain/storage_protocol.py      — ToolchainStorage protocol (18.8)
atlas/toolchain/capability_handlers.py   — toolchain.* capability handlers (18.7)
atlas/toolchain/evolution_integration.py — governed activation bridge + GOV-009 (18.9)
atlas/toolchain/wiring.py                — ComponentMetadata + GOV-009 registration (18.10)
atlas/toolchain/cli_commands.py          — presentation wrappers (18.10)
        │ (infrastructure / presentation)
atlas/storage/toolchain_storage.py       — ToolchainSQLiteStorage (18.8)
atlas/cli/main.py                        — `atlas toolchain ...` / `atlas skill ...` (18.10)
```

### 2.2 Pure-logic isolation

- Models / registry / planner / executor / effectiveness / learner import **no** kernel, runtime, dispatcher, scheduler, gateway, storage, events, or AI providers.
- `ToolProvider` and `ToolInvoker` are protocol-injected; no concrete `atlas.tools` registry/executor class is ever imported.
- `ToolchainSQLiteStorage` is the only module importing `sqlite3` for Track B persistence.
- The evolution bridge never calls `EvolutionExecutionGateway.execute_request()` or `EvolutionAutonomyDispatcher` — the injected `ToolchainIngestSink` is the sole hand-off point.

---

## 3. Pipeline

| Phase | Component | Responsibility | Deterministic |
|---|---|---|---|
| 18.1 | `Skill`, `ToolChain`, `ToolStep`, `ToolChainPlan`, `ToolChainResult`, effectiveness models | Pure data containers + enums (`SkillKind`, `SkillStatus`, `ChainStrategy`) | Yes |
| 18.2 | `SKILL_CATEGORIES`, strategy names, goal→category keywords, planning/effectiveness defaults | Shared constants for registry + planner | Yes |
| 18.3 | `SkillRegistry` | Additive skill lifecycle: register, lookup, list, filter, activate/deactivate (frozen-copy transitions) | Yes |
| 18.4 | `ToolChainPlanner` | Goal → ranked `ToolChainPlan` (keywords, markers, depth) | Yes (timestamps aside) |
| 18.5 | `ToolChainExecutor` + `RiskPolicy` | Sequential/fallback execution; fail-closed deny/allow lists; never raises | Yes |
| 18.5 | `ToolEffectivenessTracker` | Per-tool success/speed aggregation → `ToolEffectivenessScore` | Yes |
| 18.6 | `ToolLearner` | Result + tracker → deterministic `record`/`promote`/`learn_skill`/`learn_failure` recommendations | Yes |
| 18.7 | `toolchain.execute_chain` / `run_skill` / `effectiveness` / `skills` | Capability-registry-compatible handlers (pure bridges) | Yes |
| 18.8 | `ToolchainSQLiteStorage` | `toolchain_skills`/`toolchain_chains`/`toolchain_effectiveness_records`/`toolchain_plans`/`toolchain_reports` (migration v8) | — |
| 18.9 | `ToolchainEvolutionTracker` + `ToolchainIngestBridge` | Builds INFORMATION-scope KNOWLEDGE `EvolutionRequest` for skill activation; hands to governed sink; fail-closed | Yes |
| 18.10 | Component metadata + GOV-009 registration + CLI | Observational registration; `atlas toolchain plan/execute`, `atlas skill list/lookup/activate` | — |

---

## 4. Modules (files)

| File | Responsibility |
|---|---|
| `atlas/toolchain/models.py` | 10 frozen dataclasses + 3 enums |
| `atlas/toolchain/catalog.py` | Shared constants + goal→category keywords |
| `atlas/toolchain/registry.py` | `SkillRegistry` |
| `atlas/toolchain/planner.py` | `ToolChainPlanner`, `ToolProvider` protocol |
| `atlas/toolchain/executor.py` | `ToolChainExecutor`, `RiskPolicy`, `ToolInvoker` protocol |
| `atlas/toolchain/effectiveness.py` | `ToolEffectivenessTracker` |
| `atlas/toolchain/learner.py` | `ToolLearner`, `ToolLearningRecommendation` |
| `atlas/toolchain/storage_protocol.py` | `ToolchainStorage` protocol |
| `atlas/toolchain/capability_handlers.py` | `ToolchainCapabilityFactory` + 4 handlers |
| `atlas/toolchain/evolution_integration.py` | `ToolchainEvolutionTracker`, `ToolchainIngestBridge`, `build_ingest_payload`, `register_gov_009` |
| `atlas/toolchain/wiring.py` | `toolchain_component()`, `toolchain_evolution_component()`, `register_toolchain_governance()` |
| `atlas/toolchain/cli_commands.py` | `run_plan`/`run_execute`/`run_skill_list`/`run_skill_lookup`/`run_skill_activate` + entry points |
| `atlas/storage/toolchain_storage.py` | `ToolchainSQLiteStorage` (migration v8) |
| `atlas/cli/main.py` | `atlas toolchain ...` / `atlas skill ...` subcommands |

---

## 5. Governance

GOV-009 (**TOOLCHAIN_INGEST / SKILL_ACTIVATE**) — additive rule, no constitutional change:

| Rule | Scope | Min level | Meaning |
|---|---|---|---|
| GOV-009 | KNOWLEDGE | INFORMATION (2) | Skill activation / toolchain ingest writes into Atlas state only through the governed evolution path |

Activation discipline: `Skill → ToolchainEvolutionTracker → EvolutionRequestFactory.from_cli(KNOWLEDGE, "activate") → ToolchainIngestSink → (Phase 16 validator / risk / authorization / dispatcher → gateway → applier)`. Track B never calls `execute_request()` directly; the sink is the sole hand-off point and is wired by the kernel to the Phase 16 schedule-store/dispatcher queue. Missing or refusing sink ⇒ fail closed; the registry is never mutated by Track B.

---

## 6. Storage (migration v8 — Phase 18.8)

| Table | Purpose | Write semantics |
|---|---|---|
| `toolchain_skills` | Registered skills (nested chain JSON) | Idempotent upsert by skill_id |
| `toolchain_chains` | Tool chains | Idempotent upsert by chain_id |
| `toolchain_effectiveness_records` | Effectiveness observations | Append-only (INSERT OR IGNORE by record_id) |
| `toolchain_plans` | Planned chains | Idempotent upsert by plan_id |
| `toolchain_reports` | Executed chain results | Append-only log |

Phase 18.9–18.10 add **no** new tables — the governed activation path persists via the existing Phase 16 `evolution_requests` table.

---

## 7. Capabilities & CLI

Registered capabilities: `toolchain.execute_chain`, `toolchain.run_skill`, `toolchain.effectiveness`, `toolchain.skills` (via `ToolchainCapabilityFactory.register(registry)`).

CLI (Phase 18.10, presentation-only):

```
atlas toolchain plan GOAL [--category C] [--max-steps N]
atlas toolchain execute GOAL [--parameter KEY=VALUE ...]
atlas skill list [--active-only] [--category C] [--tag T]
atlas skill lookup --id ID | --name NAME
atlas skill activate --id ID | --name NAME     # GOVERNED — via evolution bridge
```

`skill activate` is the only mutating-intent command and is governed: it builds an INFORMATION-scope KNOWLEDGE `EvolutionRequest` and passes it through `ToolchainIngestBridge`; without a sink it fails closed and never touches the registry.

---

## 8. Tests

- `tests/test_toolchain_models.py`
- `tests/test_toolchain_catalog.py`
- `tests/test_toolchain_registry.py`
- `tests/test_toolchain_planner.py`
- `tests/test_toolchain_executor.py`
- `tests/test_toolchain_effectiveness.py`
- `tests/test_toolchain_learner.py`
- `tests/test_toolchain_capability_handlers.py`
- `tests/test_toolchain_storage.py`
- `tests/test_toolchain_evolution_integration.py`
- `tests/test_toolchain_cli.py`
- `tests/test_toolchain_wiring.py`

---

## 9. Future extensions

- Skill authoring (create/update skills via governed CAPABILITY scope once `ScopeType.SKILLS` + GOV-006 are added).
- Chain-strategy execution for PARALLEL / CONDITIONAL (planning hints exist; executor supports sequential/fallback).
- Learned-skill promotion: applying `ToolLearner` recommendations through the governed evolution path.
- Effectiveness-driven re-planning: feeding `ToolEffectivenessScore` evidence back into the planner provider.
- Tool-chain chaining (composed chains) and constrained execution profiles per skill.
- Autonomous toolchains / tool agents — explicitly out of scope per track boundaries.
