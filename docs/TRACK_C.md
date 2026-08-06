# Atlas Capability Track C — Long-Term Learning

**Status:** Approved for implementation · **Integration:** Additive, no locked-component redesign

---

## 0. Convention

This document distinguishes two kinds of content:

- **[FACT]** — confirmed by `docs/ATLAS_STATE.md`, `docs/ATLAS_CORE.md`, `docs/ATLAS_VISION.md`, `docs/ARCHITECTURE.md`, or existing source code.
- **[DESIGN]** — a proposal by this document. **Design** entries are not project facts. They require approval before implementation and must not be confused with confirmed architecture.

If any **[DESIGN]** entry conflicts with a future authoritative document, the future documented architecture wins and this document must be revised.

---

## 1. Overview

Track C delivers the long-term learning layer: **episodic memory** (event-sequence recollection of what Atlas did and observed), **procedural memory** (reusable task/method patterns distilled from repeated execution), **cross-session loading** (restoring episodic/procedural state across restarts), and **consolidation + principled forgetting** (preventing unbounded accumulation while preserving understanding).

### 1.0 Explicitly out of scope for Track C

- **No changes to `atlas/memory/` or its `MemoryType` enum.** Episodic/procedural types live in the new track package; the existing memory system is untouched.
- **No changes to `atlas/learning_engine/`.** Track C consolidation is standalone pure logic; it does not modify or import existing learning modules.
- **No RuntimeCoordinator pipeline change.** The 14-stage pipeline and its execution order are locked; Track C is an additive consumer of existing `ExperienceAccumulator` output, not a pipeline modification.
- **No autonomous forgetting.** Forgetting (principled) is governed through the Evolution Framework; no component may delete memory state directly.
- **No working-memory or `ContextEngine` integration in this track.** Feeding episodic context into working memory is a deferred future extension.
- **No changes to existing public APIs, service keys, models, or protocols.** Only new additive APIs/surfaces are introduced.
- **No web/binary source adapters** (outside Track C scope; remains a Track A follow-on).

[FACT] ATLAS_STATE.md §8 states: "Episodic/Procedural | **Not yet implemented** | Future Track C adds explicit episodic and procedural memory layers." [FACT]

[FACT] ATLAS_STATE.md §13 lists Track C as: "*Long-Term Learning* — Episodic memory, procedural memory, cross-session loading, consolidation + principled forgetting." [FACT]

[DESIGN] This document is the design proposal. It does not modify any source file.

### 1.1 Intended data flow

```
RuntimeCoordinator pipeline (unchanged)
        ↓ (post-pipeline outcome, via ExperienceAccumulator)
StructuredExperience (existing)
        ↓ EpisodicRecorder [DESIGN]
EpisodicEpisode (event sequence)
        ↓ ProcedureExtractor [DESIGN]   (repeated-episode pattern distillation)
ProceduralProcedure (reusable method)
        ↓ Consolidator [DESIGN]         (dedup, merge, principled forgetting)
ConsolidationRecord
        ├─ LongTermSQLiteStorage [DESIGN] — episodic_* / procedural_* tables (migration v9)
        └─ LongTermEvolutionTracker [DESIGN] → EvolutionRequest (MEMORY) → governed sink
Capability handlers memory.episodic_query|procedure_query|consolidate [DESIGN]
Component metadata + CLI `atlas memory ...` [DESIGN]
```

---

## 2. Confirmed Facts vs. Design Decisions

### 2.1 Confirmed facts [FACT]

| # | Fact | Source |
|---|------|--------|
| 1 | Memory architecture layers: working, long-term (MemoryManagerService), knowledge, understanding, experience, evolution memory | ATLAS_STATE.md §8 |
| 2 | Episodic/Procedural is **Not yet implemented** | ATLAS_STATE.md §8 |
| 3 | Storage is additive-only; SQLite shared DB `atlas_data/atlas_experience.db`; migration framework in `atlas/storage/migration.py` | ATLAS_STATE.md §7 |
| 4 | All state mutation flows through `EvolutionExecutionGateway.execute_request()`; MEMORY scope → INFORMATION level (GOV-004) | ATLAS_STATE.md §1.4, §10 |
| 5 | RuntimeCoordinator executes a fixed 14-stage pipeline; execution order is locked | ATLAS_STATE.md §1.4; `.clinerules/` |
| 6 | Pure logic layers must never import kernel, runtime, dispatcher, gateway, AI providers, EventBus, scheduler | ATLAS_STATE.md §12 |
| 7 | `ExperienceRepository` already persists structured experiences and restores them at boot | Source: `atlas/experience/experience_repository.py` |
| 8 | Migration framework currently at schema v8 | Source: `atlas/storage/migration.py` |
| 9 | Track A/B established module pattern: models → catalog → planner → executor → storage protocol → capability handlers → evolution bridge → wiring → CLI | `docs/TRACK_A.md`, `docs/TRACK_B.md` |
| 10 | New capability handlers register in `CapabilityRegistry` via `DEFAULT_HANDLERS` factory pattern | ATLAS_STATE.md §6.1 |

### 2.2 Design decisions [DESIGN]

| # | Decision | Rationale |
|---|----------|-----------|
| D1 | New package `atlas/longterm/` | Mirrors Track A/B self-contained track packages; keeps `atlas/memory/` untouched |
| D2 | No changes to `atlas/memory/` or its `MemoryType` enum | Avoids touching any locked/stable module; episodic/procedural types live in the new package |
| D3 | No changes to `atlas/learning_engine/` | Track C implements its own standalone consolidation pure-logic, protocol-injected |
| D4 | Reuse existing MEMORY scope (GOV-004, INFORMATION level) for governed writes | No new GOV rule required |
| D5 | No RuntimeCoordinator pipeline change | Meets locked-component rule; Track C exposed via capabilities only |
| D6 | Additive migration v9 for new tables | Adheres to additive-only storage policy |
| D7 | Storage adapter is the only new module importing `sqlite3` | Matches Track A/B |
| D8 | Capability names `memory.episodic_query`, `memory.procedure_query`, `memory.consolidate` | Naming convention consistent with `research.*`, `toolchain.*` |
| D9 | CLI `atlas memory ...` presentation-only commands | Matches Track A/B CLI pattern |
| D10 | Cross-session loading mirrors `ExperienceRepository.restore()` | Proven pattern |

---

## 3. Architecture

### 3.1 Dependency direction (pure → infrastructure)

```
atlas/longterm/models.py            — frozen dataclasses + enums [DESIGN]
atlas/longterm/catalog.py           — constants, defaults, forgetting policy defaults [DESIGN]
atlas/longterm/episode_recorder.py  — EpisodicRecorder (pure) [DESIGN]
atlas/longterm/procedure_extractor.py — ProcedureExtractor (pure) [DESIGN]
atlas/longterm/consolidator.py      — Consolidator (pure) [DESIGN]
atlas/longterm/episode_repository.py — EpisodicRepository (pure) [DESIGN]
atlas/longterm/procedure_repository.py — ProceduralRepository (pure) [DESIGN]
        │ (pure)
atlas/longterm/storage_protocol.py  — LongTermStorage protocol [DESIGN]
atlas/longterm/capability_handlers.py — memory.* capability handlers (pure bridges) [DESIGN]
atlas/longterm/evolution_integration.py — governed ingest bridge (MEMORY scope) [DESIGN]
atlas/longterm/wiring.py            — ComponentMetadata + GOV-004 reuse [DESIGN]
atlas/longterm/cli_commands.py      — presentation wrappers [DESIGN]
        │ (infrastructure / presentation)
atlas/storage/longterm_storage.py   — LongTermSQLiteStorage (migration v9) [DESIGN]
atlas/cli/main.py                   — `atlas memory ...` subcommands [DESIGN]
```

### 3.2 Pure-logic isolation

[FACT] Pure logic layers must not import kernel, runtime, dispatcher, scheduler, gateway, storage, events, or AI providers (ATLAS_STATE.md §12). [FACT]

[DESIGN] All pure modules in `atlas/longterm/` follow this rule. `LongTermSQLiteStorage` is the only new module importing `sqlite3`. The evolution bridge never calls `EvolutionExecutionGateway.execute_request()` directly; an injected governed sink is the sole hand-off point (same discipline as Track A `ResearchIngestSink` and Track B `ToolchainIngestSink`). [DESIGN]

---

## 4. Pipeline

| Phase | Component | Responsibility | Deterministic |
|---|---|---|---|
| C.1 | `Episode`, `Procedure`, `ConsolidationRecord`, enums | Pure data containers + serialization | Yes |
| C.2 | `EpisodicRecorder` | Builds `Episode` from `StructuredExperience` (with optional session context) | Yes |
| C.3 | `ProcedureExtractor` | Distills repeated episode patterns → `Procedure` (deterministic similarity/exactness-based) | Yes |
| C.4 | `Consolidator` | Dedup/merge episodes & procedures; principled forgetting (age/importance/recurrence scores); produces `ConsolidationRecord` | Yes |
| C.5 | `EpisodicRepository` / `ProceduralRepository` | Pure in-memory stores with bounded size; dual-write to injected storage (best-effort) | Yes |
| C.6 | `LongTermSQLiteStorage` | Additive `episodic_*`/`procedural_*` tables in shared DB (migration v9) | — |
| C.7 | `memory.episodic_query` / `memory.procedure_query` / `memory.consolidate` | Capability-registry-compatible handlers routing to repositories/consolidator | Yes (times aside) |
| C.8 | `LongTermEvolutionTracker` + `LongTermIngestBridge` | Builds INFORMATION-scope MEMORY `EvolutionRequest` for consolidation writes; hands to governed sink; fail-closed | Yes |
| C.9 | Component metadata + CLI | Observational registration; presentation-only commands | — |

---

## 5. Modules (files)

All paths under `atlas/longterm/` unless noted. All **[DESIGN]**.

| File | Responsibility |
|---|---|
| `models.py` | Frozen dataclasses: `Episode`, `Procedure`, `ConsolidationRecord`, `MemoryDecayPolicy`; enums: `EpisodeKind`, `ProcedureKind`, `ConsolidationStatus` |
| `catalog.py` | Shared constants: default decay thresholds, forgetting policy defaults, episode/procedure category keywords |
| `episode_recorder.py` | `EpisodicRecorder` — maps `StructuredExperience` → `Episode` |
| `procedure_extractor.py` | `ProcedureExtractor` — deterministic repeated-pattern detection |
| `consolidator.py` | `Consolidator` — dedup, merge, principled forgetting |
| `episode_repository.py` | `EpisodicRepository` — bounded in-memory store + dual-write |
| `procedure_repository.py` | `ProceduralRepository` — bounded in-memory store + dual-write |
| `storage_protocol.py` | `LongTermStorage` protocol (lifecycle + episode/procedure/consolidation methods) |
| `capability_handlers.py` | `LongTermCapabilityFactory` + `memory.*` handlers |
| `evolution_integration.py` | `LongTermEvolutionTracker`, `LongTermIngestBridge`, `build_ingest_payload` |
| `wiring.py` | `longterm_component()`, `longterm_evolution_component()` metadata |
| `cli_commands.py` | Presentation wrappers for the track CLI |
| `atlas/storage/longterm_storage.py` | `LongTermSQLiteStorage` (migration v9) |
| `atlas/storage/migration.py` | Additive migration v9 (existing file, new entry only) |
| `atlas/cli/main.py` | `atlas memory ...` subcommands (existing file, additive) |
| `atlas/lifecycle/component_definitions.py` | Additive `ComponentMetadata` entries (existing file, additive) |

---

## 6. Governance

[FACT] MEMORY scope → INFORMATION level via GOV-004 (ATLAS_STATE.md §10.5). [FACT]

[DESIGN] Track C reuses the existing MEMORY scope. No new GOV rule is proposed. Writes to Atlas state (consolidation application, procedure registration) flow as INFORMATION-scope MEMORY `EvolutionRequest`s through the governed sink:

```
ConsolidationRecord
    → LongTermEvolutionTracker [DESIGN]
    → EvolutionRequestFactory.from_cli(MEMORY, "consolidate") [DESIGN]
    → LongTermIngestSink [DESIGN]  (sole hand-off; wired by kernel to Phase 16 schedule-store/dispatcher)
    → (Phase 16 validator / risk / authorization / dispatcher → gateway → applier → memory)
```

Missing or refusing sink ⇒ fail closed; the repositories are never mutated by Track C directly.

---

## 7. Storage (migration v9 — conceptual)

[FACT] Additive-only policy; shared DB `atlas_data/atlas_experience.db` (ATLAS_STATE.md §7). [FACT]

[DESIGN] Proposed tables (all additive, none modifying existing tables):

| Table | Purpose | Write semantics |
|---|---|---|
| `episodic_episodes` | Event-sequence episodes | Idempotent upsert by episode_id |
| `episodic_episode_events` | Individual events within an episode | Append-only (INSERT OR IGNORE by event_id) |
| `procedural_procedures` | Distilled reusable methods | Idempotent upsert by procedure_id |
| `memory_consolidation_records` | Consolidation/forgetting audit log | Append-only |

Nested fields JSON-serialized. Datetimes ISO strings. All columns additive.

---

## 8. Capabilities & CLI

[DESIGN] Registered capabilities (via `LongTermCapabilityFactory.register(registry)`):

- `memory.episodic_query` — query recent episodes by time/outcome
- `memory.procedure_query` — query distilled procedures by category/tool
- `memory.consolidate` — trigger consolidation (governed)

[DESIGN] CLI (presentation-only):

```
atlas memory episodes [--limit N] [--outcome X]
atlas memory procedures [--category C] [--tool T]
atlas memory consolidate            # GOVERNED — via evolution bridge
```

`consolidate` is the only mutating-intent command and is governed: it builds an INFORMATION-scope MEMORY `EvolutionRequest` and passes it through `LongTermIngestBridge`; without a sink it fails closed and never mutates repositories.

---

## 9. Dependency Injection strategy

[FACT] All cross-module edges are constructor-injected; `Atlas.start()` constructs services; shared services register in `ServiceContainer`; private Atlas-owned dependencies inject directly (ATLAS_STATE.md §11.1, §4.2). [FACT]

[DESIGN] Proposed wiring in `Atlas.start()`:

- `EpisodicRecorder`, `ProcedureExtractor`, `Consolidator`, `EpisodicRepository`, `ProceduralRepository` are **private Atlas-owned** dependencies (injected into a `LongTermService`).
- `LongTermService` is registered in `ServiceContainer` under key `longterm` (shared surface) **OR** kept private — **decision pending approval (Q2)**.
- `LongTermSQLiteStorage` is constructed and injected; repositories dual-write best-effort (same degradation as `ExperienceRepository`).
- The governed sink (`LongTermIngestSink`) is injected into the evolution bridge; never imported.

---

## 10. RuntimeCoordinator interaction

[FACT] RuntimeCoordinator executes a fixed 14-stage pipeline; order is locked (`.clinerules/`, ATLAS_STATE.md). [FACT]

[DESIGN] **No pipeline change.** Track C does not modify the RuntimeCoordinator, its stages, or its order. Track C is exposed as capability handlers + CLI on top of the existing system, consistent with Track A/B (`research.*`, `toolchain.*`). The only entry point is `ExperienceAccumulator` output (existing) being consumed by `EpisodicRecorder` in the track layer — this is an additive consumer, not a pipeline modification.

---

## 11. Public APIs

[FACT] Existing public APIs must not break (ATLAS_STATE.md §14.4). [FACT]

[DESIGN] Track C adds new public APIs only:

- New service key `longterm` (if approved, Q2)
- New capability names `memory.*` (additive)
- New CLI `atlas memory ...` (additive)
- New dataclasses/protocols in `atlas/longterm/`

No existing API, service key, model, or protocol is modified.

---

## 12. Error handling

[FACT] Execution layer returns result objects; fail-closed; never silent success (ATLAS_STATE.md §11.1). [FACT]

[DESIGN]

- Repositories degrade gracefully on storage write failure (best-effort, never break in-memory path).
- Consolidator never raises; returns `ConsolidationResult` with error info.
- Evolutions bridge fails closed when sink missing/refusing.
- Storage adapter marks unavailable on failure; falls back to memory-only operation.

---

## 13. Testing strategy

[DESIGN] New test files (no code written yet):

- `tests/test_longterm_models.py`
- `tests/test_longterm_catalog.py`
- `tests/test_longterm_episode_recorder.py`
- `tests/test_longterm_procedure_extractor.py`
- `tests/test_longterm_consolidator.py`
- `tests/test_longterm_repositories.py`
- `tests/test_longterm_storage.py`
- `tests/test_longterm_capability_handlers.py`
- `tests/test_longterm_evolution_integration.py`
- `tests/test_longterm_cli.py`
- `tests/test_longterm_wiring.py`

Full existing suite (2000+ tests) must remain green after implementation.

---

## 14. Migration strategy

- `atlas/storage/migration.py`: bump `CURRENT_SCHEMA_VERSION` to 9; add migration v9 with only new `episodic_*`, `procedural_*`, `memory_consolidation_records` tables.
- No existing table is altered or dropped.
- `LongTermSQLiteStorage.initialize()` opens the shared DB, applies migrations, marks available.

---

## 15. Future extension points

[DESIGN]

- Feed episodic context into `ContextEngine` / working memory (requires explicit RuntimeCoordinator review; deferred).
- Semantic memory upgrades on top of `UnderstandingEngine` concepts.
- Forgetting-policy tuning via `MemoryDecayPolicy` (config-driven later).
- Autonomous procedure suggestion via `ProcedureExtractor` learning loop (requires Evolution approval).
- Full integration with `atlas/learning_engine/` (protocol-injected, not direct import).

---

## 16. Architecture consistency check

| Requirement | Status |
|---|---|
| Modular architecture | PASS — new self-contained `atlas/longterm/` package |
| Dependency Injection | PASS — constructor-injected; private + shared pattern; no global state |
| RuntimeCoordinator pipeline | PASS — no change; additive consumer only |
| Existing public APIs | PASS — additive-only; no existing API modified |
| Evolution governance | PASS — MEMORY scope reuse (GOV-004); governed sink; fail-closed |
| Storage migration policy | PASS — additive migration v9; no existing table touched |
| Pure-logic isolation | PASS — pure modules import no infrastructure; one sqlite3 adapter |
| Minimal changes | PASS — only additive edits to existing files (migration, CLI, lifecycle, kernel wiring) |

---

## 17. Potential conflicts

1. **`atlas/memory/` untouched** — Track C does not extend `MemoryType` or modify any `atlas/memory/` file. This avoids touching a stable package. **[DESIGN]**
2. **`atlas/learning_engine/` untouched** — Track C consolidation is standalone pure logic, not a modification or import of `atlas/learning_engine/`. **[DESIGN]**
3. **RuntimeCoordinator locked** — no pipeline change; only additive consumption of existing `ExperienceAccumulator` output. **[DESIGN]**

---

## 18. Questions requiring approval before implementation

1. **Package name** — is `atlas/longterm/` acceptable, or should the track use `atlas/memory_episodic/`, `atlas/learning_track/`, or another name? **[DESIGN — needs approval]**
2. **Service key** — should `LongTermService` be registered publicly in `ServiceContainer` (key `longterm`) or kept as a private Atlas-owned dependency (not in container)? **[DESIGN — needs approval]**
3. **Capability names** — are `memory.episodic_query`, `memory.procedure_query`, `memory.consolidate` acceptable, or should they be prefixed differently (e.g., `longterm.*`)? **[DESIGN — needs approval]**
4. **CLI surface** — is the `atlas memory ...` command set acceptable, or should it be `atlas longterm ...`? **[DESIGN — needs approval]**
5. **Storage table names** — are `episodic_episodes`, `episodic_episode_events`, `procedural_procedures`, `memory_consolidation_records` acceptable? **[DESIGN — needs approval]**
6. **Consolidation write path** — is routing consolidation application through the Evolution Framework as MEMORY-scope `EvolutionRequest`s correct, or should the ingestion use a different scope/level? **[DESIGN — needs approval]**

---

*Document created: 2026-08-06 · Project Atlas — docs/TRACK_C.md · Approved design baseline for Track C implementation.*
