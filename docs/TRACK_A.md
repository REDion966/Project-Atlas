# Atlas Capability Track A — Research & Knowledge

**Status:** Complete (Phase 17.1–17.9) · **Version tag:** v0.17.0-track-a · **Integration:** Additive, no locked-component redesign

---

## 1. Overview

Track A delivers a self-contained research pipeline: deterministic query decomposition, local source normalization, knowledge-claim extraction, cross-source claim verification, persistence, capability-handler registration, and governed evolution ingestion. Research results **never** write into Atlas knowledge directly — all knowledge mutations flow through the Phase 16 Evolution Framework.

```
ResearchQuery
    ↓ ResearchPlanner (17.3)
ResearchPlan (sub_queries, target_sources, strategy, max_depth)
    ↓ Source adapters (17.2)
SourceProfile
    ↓ KnowledgeExtractor (17.4)
KnowledgeClaim[]
    ↓ ClaimVerifier (17.5)
ClaimVerification[]
    ↓ (aggregation)
ResearchReport
    ├─ ResearchSQLiteStorage (17.6) — append-only persistence
    └─ ResearchEvolutionTracker → EvolutionRequest (KNOWLEDGE) → governed sink (17.8)
Capability handlers research.query|verify|summarize (17.7)
Component metadata + CLI `atlas research ...` (17.9)
```

---

## 2. Architecture

### 2.1 Dependency direction (pure → infrastructure)

```
atlas/research/models.py            — frozen dataclasses + to_dict() (17.1)
atlas/research/source_catalog.py    — format/extension/scheme constants
atlas/research/_text.py             — SourceLike union + text helpers
atlas/research/_verification.py     — confidence + similarity helpers
atlas/research/_extraction.py       — chunking / normalization / dedupe / IDs / provisional confidence
        │ (pure)
atlas/research/planner.py           — deterministic query decomposition (17.3)
atlas/research/source_adapter.py    — SourceAdapter Protocol (17.2)
atlas/research/sources/*            — document / workspace / codebase adapters (17.2)
atlas/research/extractor.py         — KnowledgeExtractor + ExtractionModel protocol (17.4)
atlas/research/verifier.py          — ClaimVerifier + ClaimOutcome + VerificationModel protocol (17.5)
        │ (domain layer)
atlas/research/storage_protocol.py  — ResearchStorage + ResearchIngestDispatcher protocols (17.6)
atlas/research/capability_handlers.py — research.* capability handlers (17.7)
atlas/research/evolution_integration.py — governed ingest bridge + GOV-008 (17.8)
atlas/research/wiring.py            — ComponentMetadata (17.9)
        │ (infrastructure / presentation)
atlas/storage/research_storage.py   — ResearchSQLiteStorage (17.6)
atlas/cli/main.py                   — `atlas research ...` subcommands (17.9)
```

### 2.2 Pure-logic isolation

- Models / planner / extractor / verifier / tracker import **no** kernel, runtime, dispatcher, scheduler, gateway, storage, events, or AI providers.
- AI is optional and protocol-injected (`ExtractionModel`, `VerificationModel`); no provider SDK is ever imported.
- `ResearchSQLiteStorage` is the only new module importing `sqlite3` for Track A persistence.

---

## 3. Pipeline

| Phase | Component | Responsibility | Deterministic |
|---|---|---|---|
| 17.3 | `ResearchPlanner` | Decomposes `ResearchQuery` → sub-queries, target source kinds, verification strategy, max depth | Yes (model timestamps aside) |
| 17.2 | `DocumentSourceAdapter` / `WorkspaceSourceAdapter` / `CodebaseSourceAdapter` | Normalize local sources → `SourceProfile` (text, language, sizes) | Yes |
| 17.4 | `KnowledgeExtractor` | Chunk → normalize → dedupe → stable `claim:{sha256[:16]}` ids → provisional confidence (≤0.8) | Yes without model; model falls back on failure |
| 17.5 | `ClaimVerifier` | Cross-source evidence → `ClaimOutcome` VERIFIED/PLAUSIBLE/CONTESTED/UNKNOWN + score; LLM optional (`strict_llm`) | Yes without model |
| 17.6 | `ResearchSQLiteStorage` | Append-only `research_*` tables in `atlas_data/atlas_experience.db` | — |
| 17.7 | `research.query` / `research.verify` / `research.summarize` | Capability-registry-compatible handlers routing to the pipeline | Yes |
| 17.8 | `ResearchEvolutionTracker` + `ResearchIngestBridge` | Builds INFORMATION-scope `EvolutionRequest` (KNOWLEDGE) + observation + evidence; hands to governed sink; fail-closed | Yes |
| 17.9 | Component metadata + CLI | Observational registration; presentation-only commands | — |

### VerificationStatus mapping (17.1 enum is locked; 17.5 labels preserved in metadata)

| ClaimOutcome (17.5) | VerificationStatus (17.1) |
|---|---|
| VERIFIED | SUPPORTED (score ≥ 0.85) |
| PLAUSIBLE | SUPPORTED (score 0.75) |
| CONTESTED | CONTRADICTED |
| UNKNOWN | UNVERIFIED |

---

## 4. Modules (files)

| File | Responsibility |
|---|---|
| `atlas/research/models.py` | 7 frozen dataclasses + `SourceKind`/`VerificationStatus` enums |
| `atlas/research/source_catalog.py` | Shared extension/scheme/language constants |
| `atlas/research/source_adapter.py` | `SourceAdapter` Protocol |
| `atlas/research/sources/{document,workspace,codebase}.py` | Concrete adapters (+ `_read.py` helper) |
| `atlas/research/planner.py` | `ResearchPlanner` |
| `atlas/research/extractor.py` | `KnowledgeExtractor`, `ExtractionModel` |
| `atlas/research/verifier.py` | `ClaimVerifier`, `ClaimOutcome`, `VerificationModel` |
| `atlas/research/storage_protocol.py` | `ResearchStorage`, `ResearchIngestDispatcher` |
| `atlas/research/capability_handlers.py` | `ResearchCapabilityFactory` + `research.*` handlers |
| `atlas/research/evolution_integration.py` | `ResearchEvolutionTracker`, `ResearchIngestBridge`, GOV-008 |
| `atlas/research/wiring.py` | `research_component()` metadata |
| `atlas/research/cli_commands.py` | Presentation wrappers for the research CLI |
| `atlas/storage/research_storage.py` | `ResearchSQLiteStorage` (research_* tables, migration v7) |
| `atlas/storage/migration.py` | + migration 7 (additive research tables) |

---

## 5. Governance

GOV-008 (**RESEARCH_INGEST**) — additive rule, no constitutional change:

| Rule | Scope | Min level | Meaning |
|---|---|---|---|
| GOV-008 | KNOWLEDGE | INFORMATION (2) | Research results enter knowledge only through the governed evolution path |

Ingest discipline: `ResearchReport → EvolutionRequestFactory.from_cli(KNOWLEDGE) → ResearchIngestSink → (Phase 16 validator / risk / authorization / dispatcher → gateway → applier → knowledge)`. Track A never calls `execute_request()` directly; the sink is the sole hand-off point and is wired by the kernel to the Phase 16 schedule-store/dispatcher queue. Missing or refusing sink ⇒ fail closed.

---

## 6. Storage (migration v7)

| Table | Purpose | Write semantics |
|---|---|---|
| `research_sources` | Normalized source metadata | Append-only (INSERT OR IGNORE by uri) |
| `research_claims` | Extracted knowledge claims | Idempotent upsert by claim_id |
| `research_verifications` | Claim verification results | Append-only log |
| `research_citations` | Citation records | Idempotent upsert by record_id |
| `research_reports` | Final research deliverables | Append-only log |

---

## 7. Capabilities & CLI

Registered capabilities: `research.query`, `research.verify`, `research.summarize` (via `ResearchCapabilityFactory.register(registry)`).

CLI (presentation-only; delegates to the same handlers):

```
atlas research query "question" [--query-id ID] [--source URI ...]
atlas research verify --claim "statement" [--source URI ...]
atlas research summarize --report-id ID | --report-file PATH
```

---

## 8. Tests

- `tests/test_research_models.py`
- `tests/test_research_source_adapters.py`
- `tests/test_research_planner.py`
- `tests/test_research_extractor.py`
- `tests/test_research_verifier.py`
- `tests/test_research_storage.py`
- `tests/test_research_capability_handlers.py`
- `tests/test_research_evolution_integration.py`

---

## 9. Future extensions

- `ResearchCoordinator` implementation (the abstract interface already exists in `atlas/evolution/research_coordinator.py`) — orchestrates the pipeline end-to-end and wires storage/reporting.
- Web adapter (deferred by design; third-party fetching out of scope for the local adapter layer).
- PDF / DOCX / binary parsers (deferred).
- Knowledge-graph expansion from verified claims (Track A follow-ons).
- Research report aggregation into `ResearchReport` (fields exist in the 17.1 model).
- Deeper semantic contradiction detection (hooks into `VerificationModel` without touching the deterministic path).
- Autonomous background research / research agents / multi-agent research — explicitly out of scope per track boundaries.
