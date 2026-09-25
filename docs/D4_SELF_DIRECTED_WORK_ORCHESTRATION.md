# D4 — Self-Directed Work Orchestration

Authoritative description of the D4 orchestration boundary. It describes only
what D4 implements; it does not claim Atlas is fully autonomous (that is D5).

## 1. Orchestration boundary

D4 connects the existing subsystems into ONE governed, deterministic workflow
for a single user objective:

```
objective (D1 SemanticIntake)
  -> requirements          (knowledge / capabilities / subtasks)
  -> knowledge decision    (D3: local-first; D2 acquisition when justified)
  -> plan                  (bounded decomposition; no second planner)
  -> capability availability + dispatch (EXISTING CapabilityRegistry/Dispatcher)
  -> authorization gate    (EXISTING session/authority boundary ONLY)
  -> execution             (existing governed capability path)
  -> verification
  -> bounded report
```

Implementation: `atlas/orchestration/work_orchestrator.py`
(`WorkOrchestrator`, `OrchestrationRun`, `OrchestrationState`), exposed via
`Atlas.work_orchestrator` / `Atlas.run_work_objective(...)`.

It is **orchestration only**. Every authority/ownership concern is delegated:

| Concern | Authoritative owner (reused) |
|---|---|
| knowledge validity / provenance | D3 `KnowledgeDecisionService` + C6 pipeline |
| external acquisition | D2 `ExternalKnowledgeAcquirer` (only external path) |
| capability identity + dispatch | `CapabilityRegistry` / `CapabilityDispatcher` |
| authorization / approval | `SessionManager` / `AuthorityService` (read via injected check) |
| governed development execution | existing proposal → approval → sandbox → verification flow |
| verification | existing `ExecutionResult` success + existing verification infra |

No second reasoning engine, planner, dispatcher, research engine, knowledge
store, governance system, or execution engine is introduced.

## 2. Lifecycle and states

`RECEIVED → UNDERSTOOD → REQUIREMENTS_IDENTIFIED → KNOWLEDGE_CHECK →
(KNOWLEDGE_ACQUIRED) → PLANNED → [AUTHORIZATION_REQUIRED → AUTHORIZED] →
EXECUTING → VERIFYING → COMPLETED`.

Bounded terminal/intermediate states: `NEEDS_CLARIFICATION`,
`KNOWLEDGE_UNAVAILABLE`, `KNOWLEDGE_CONTRADICTED`, `BLOCKED_BY_AUTHORITY`,
`FAILED`, `VERIFICATION_FAILED`. Each run records an ordered `transitions`
trace, so the sequence is auditable.

## 3. Knowledge integration (D3/D2)

For a knowledge-bearing objective, D3's local-first decision runs first;
sufficient validated knowledge continues with **no network**. Insufficient
knowledge triggers the governed D2 acquisition (authorized hosts only);
`no_authorized_source` / `insufficient` → `KNOWLEDGE_UNAVAILABLE` (honest stop),
`CONTESTED` → `KNOWLEDGE_CONTRADICTED` (no winner). Evidence, provenance,
confidence, freshness, and uncertainty are the existing values. No direct HTTP;
D2 is the only external path.

## 4. Planning, capability, tool integration

Planning is a **bounded deterministic decomposition** from the D1 semantic
(subtasks + required capabilities) — no second planner. Capability identity and
availability come from the existing `CapabilityRegistry`; an unavailable
capability fails honestly (`FAILED`). Execution uses the existing
`CapabilityDispatcher` only (registered handlers; the default handlers are
effect-free). Tools remain governed by their existing contracts.

## 5. Authorization and governance

Authorization is **never inferred** from language, a plan, prior steps, or
external content. A governed objective (development/execution/autonomy task
types, or `require_authorization=True`) transitions to
`AUTHORIZATION_REQUIRED`; the injected check consults the EXISTING
session/authority boundary (OWNER only). Without valid authority the run is
`BLOCKED_BY_AUTHORITY` and nothing executes. With valid OWNER authority the run
reaches `AUTHORIZED` and **does not execute governed development** — that
remains the existing proposal → approval → sandbox → verification → promotion
flow (D5-owned). D4 creates no approval mechanism and no authority.

## 6. Execution and verification

Execution is through the existing dispatcher over registered capabilities.
Verification distinguishes executed vs verified vs failed: any non-success
result yields `VERIFICATION_FAILED` (never `COMPLETED`), so execution failure or
verification failure cannot become successful completion.

## 7. Persistence / lifetime

`OrchestrationRun` is a bounded, JSON-safe, deterministic value object; it is
**transient** (not persisted) and carries **no authority**. No new database and
no durable conversational memory are introduced. Conversation continuity uses
the existing bounded D1 `ConversationState`/`ConversationContext`.

## 8. Fail-closed behaviour

Empty objective → `FAILED`; ambiguous objective → `NEEDS_CLARIFICATION`;
missing/denied knowledge → `KNOWLEDGE_UNAVAILABLE`; contradiction →
`KNOWLEDGE_CONTRADICTED`; governed without authority → `BLOCKED_BY_AUTHORITY`;
unavailable capability → `FAILED`; execution/verification failure →
`VERIFICATION_FAILED`. A failed step never silently becomes overall success.

## 9. Model independence / security / parity

No `atlas.ai` import, no model call, no network except through D2's authorized
boundary. External content is untrusted data; the run envelope exposes no
authority field and cannot authorize, execute, promote, modify, or change
autonomy/configuration. The D4 API is deterministic and side-effect-free with
respect to governance; D1/D3 chat and stream paths (which D4 reuses) remain
parity-verified, and C4 capability-detail / C5 self-knowledge routing are
untouched.

## 10. Explicit D4 limitations / what remains for D5

D4 orchestrates bounded, deterministic work over existing capabilities; it does
not perform unrestricted autonomous planning, autonomous tool chaining beyond
registered capabilities, self-directed development, autonomous promotion, new
autonomy levels, or Atlas-directed software development. Conversational
invocation of D4 is via the kernel API plus the existing D1/D3 surfaces; a
general multi-intent conversational planner remains future work. Atlas is **not**
fully autonomous after D4 — D5 addresses development independence.
