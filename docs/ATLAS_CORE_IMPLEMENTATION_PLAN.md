# ATLAS CORE IMPLEMENTATION PLAN

**TEMPORARY CORE IMPLEMENTATION PLAN**

**Status:** ACTIVE implementation roadmap for the current core-building period ONLY.
This document is temporary. It is NOT a permanent architectural specification.
Once the core milestone is completed, it should be archived or removed after
owner review (see ROADMAP LIFECYCLE below).

---

## 1. PURPOSE

This document records the agreed Atlas core development plan so future
development sessions do NOT need to reconstruct the roadmap or repeat the
vision discussion. It prevents planning drift and repeated context during
the limited implementation window.

It was derived from the owner-approved long-term vision plus a read-only
repository audit performed at commit `bd783c9`.

---

## 2. MASTER ATLAS VISION

Atlas is intended to become an **independent AI companion and development
framework** rather than merely a chatbot or model wrapper.

The long-term Atlas should:

- understand natural/casual human conversation;
- understand what a user is trying to accomplish rather than requiring
  technical instructions;
- plan and perform useful work;
- use existing knowledge, procedures, skills, tools and capabilities;
- learn from interactions and corrections;
- understand individual users and their preferences;
- maintain an explicit single owner with highest authority;
- support other users with proper identity and isolation;
- learn from broader usage in a governed manner;
- research and acquire information from the internet;
- improve its own knowledge, procedures and capabilities;
- safely develop non-core portions of itself;
- use its existing governed self-development pipeline;
- progressively reduce dependence on paid external AI inference;
- eventually operate as independently as practical.

**IMPORTANT:** This month's objective is NOT to implement all of those
features. The objective is to establish the **CORE FOUNDATION** that allows
Atlas itself to develop the remaining non-core capabilities later, using its
existing governed self-development machinery.

---

## 3. CURRENT BASELINE (verified by repository audit)

Baseline commit: `bd783c9` — B1+B2+B3+B4 complete.

### 3.1 ALREADY IMPLEMENTED / SUFFICIENT — MUST NOT BE REBUILT

- Kernel/composition root (`atlas/kernel/atlas.py`)
- AI provider abstraction and model routing (`atlas/ai/**`)
- Runtime coordination (`atlas/runtime/runtime_coordinator.py`, 15-stage order)
- Memory systems (`atlas/memory/`, `atlas/longterm/` — episodic, procedural,
  semantic recall, consolidation, forgetting policy)
- Knowledge engine (`atlas/knowledge/`)
- Research and internet acquisition (`atlas/research/`, web adapter with
  deny-by-default allowlist)
- Research/evidence verification (`ClaimVerifier`, coordinator)
- Skills and tools (`atlas/toolchain/`, `atlas/tools/`)
- Workspace/files (`atlas/workspace/`)
- Governance and approval spine (`atlas/evolution/` — ApprovalManager, six
  gates, execution gateway, dispatcher, autonomy appliers)
- Self-development pipeline (`DevelopmentCycleController`,
  `DevelopmentPlanner`, `SelfDevelopmentLoop`)
- Sandbox/testing/verification (`CodeSandbox`, `CodeApplier`,
  `SandboxVerifier`, `VerificationService`)
- Rollback/promotion review (`RollbackManager`, `PromotionGate`)
- Deterministic intent classification (B2 `TaskIntake`/`TaskSpec`)
- Development-need bridge (B3 `development_intake.py`)
- Events and configuration (`atlas/events/`, `atlas/config/`)
- Extensive test infrastructure (246 modules / 4,413 tests)
- **B4 model-assisted authoring** (`atlas/evolution/model_assisted_supplier.py`)

### 3.2 B4 STATEMENT

B4 already provides the model-assisted authoring adapter and must NOT be
rebuilt. It safely produces bounded, unverified-draft `SuppliedChanges` that
stop at the existing approval boundary (`PENDING_APPROVAL`). It is OFF by
default (`[development] model_assisted_authoring = false`) and is injectable
through the existing `change_supplier` seam without modifying
`DevelopmentCycleController`.

### 3.3 PROTECTED INFRASTRUCTURE

Schema **v11**, `RuntimeCoordinator` stage ordering, and `Atlas.tick()` are
protected infrastructure (see LOCKED SURFACES, §9).

### 3.4 VERIFIED GAPS (what the audit found missing)

1. No agent/workflow layer.
2. No general conversational task orchestration.
3. No robust task-execution path from casual user request to multi-step work.
4. No explicit owner/user authority model.
5. No multi-user identity/session/isolation model.
6. No longitudinal user model / preference learning.
7. No human-behavior learning.
8. No governed collective learning.
9. No proactive assistance model.
10. No multimodal/voice foundation.
11. Model independence incomplete (interactive path still requires external
    inference).
12. User-facing interface is essentially a raw REPL.
13. Planning/decision-intelligence/cognitive loop remain limited.
14. Self-development exists as a governed pipeline but not yet as a
    continuous, conversationally-accessible development intelligence.

---

## 4. CORE DEFINITION

**"Core complete" = the minimum closed loop that makes the rest of Atlas
buildable by Atlas itself.**

The core consists of:

1. **Identity / Owner / Sessions** — explicit owner authority, user
   identity, attributable sessions, scoped context.
2. **Conversational Orchestration** — casual intent → deterministic plan →
   governed execution → real work → natural report.
3. **Interaction Learning Foundation** — per-user preferences, corrections,
   interaction patterns feeding existing learning machinery.
4. **Conversational Self-Development access** — development needs detectable
   and triggerable in conversation, routed into the existing governed cycle.
5. **Deterministic-first / model-degraded operation** — orchestration prefers
   stored knowledge, procedures, tools and deterministic capabilities; model
   inference is a fallback; graceful no-model degradation.

### 4.1 EXPLICITLY NOT CORE FOR THIS PERIOD

The following are future work that Atlas should eventually be capable of
developing itself through its governed self-development machinery. They are
deliberately out of scope now:

- Web UI
- API server
- Voice
- Multimodal interaction
- Large-scale collective learning
- Domain-specific workflows (media/footage, calendars, etc.)
- Calendar/media/integration systems
- Convenience features
- UI design modules
- Full autonomous proactive execution (advisory only is in scope)
- Every possible skill
- Every possible user-facing feature

---

## 5. MASTER PHASE PLAN

Seven phases. Batches are implemented one at a time, validated before the
next begins. Phase numbering below is internal to THIS document; it does not
reuse or conflict with historical Atlas phase numbering (Atlas Core is
complete at Phase 22; there is no Phase 23).

---

### PHASE 1 — IDENTITY, OWNER & SESSIONS (2 batches)

Prerequisite for safe conversational orchestration.

#### P1/B1.1 — Owner/User foundation
- Explicit single **Owner** entity.
- Owner is the **highest authority**; owner instructions take priority.
- User identity foundation (users are distinct from the owner).
- Authority semantics: who may approve what; owner can authorize deeper/core
  changes through explicit governance, not accidental privilege.
- Auditable authority decisions (reuse `EvolutionRecord` audit patterns).
- Minimal additive configuration (follow `Configuration`/typed-settings
  conventions).
- Reuse workspace member/permission patterns as the starting shape.
- **No authentication yet.**

#### P1/B1.2 — Session-scoped context
- Bind interactions to user/session.
- Scope conversation, context and memory operations per session/user.
- Preserve the existing context architecture
  (`ContextManager` / `ContextEngine`).
- No unnecessary schema redesign (in-memory session scoping first; storage
  namespacing deferred until justified by an owner-approved batch).

**Dependency:** P1 is prerequisite for safe conversational orchestration (P2).

---

### PHASE 2 — CONVERSATIONAL ORCHESTRATION (4 batches)

P2 is the largest and most important phase. It converts every existing
deterministic subsystem into conversational capability.

#### P2/B2.1 — Orchestrator skeleton
- Casual request → intent → deterministic plan → step graph.
- Reuse existing `TaskIntake`, reasoning/toolchain planners, capability
  registry/router/dispatcher, and toolchain catalog.
- Additive architecture (new package; no RuntimeCoordinator changes).
- Fail-closed on malformed/ambiguous input.

#### P2/B2.2 — Governed step execution
- Execute bounded steps through the existing `ToolEngine`,
  `CapabilityDispatcher`, `WorkspaceService`, research services and
  governance boundaries.
- Every action attributable to identity (P1).
- No governance bypass; existing approval/execution boundaries remain intact.

#### P2/B2.3 — Conversation integration
- Route `ACTION_REQUEST` and `INFORMATION_REQUEST` into orchestration.
- Preserve `DEVELOPMENT_REQUEST` / B3 / B4 behavior exactly.
- Clarification for ambiguous requests (never fabricated action).
- Natural-language result reporting.

#### P2/B2.4 — Experience capture
- Record completed orchestrated interactions.
- Reuse/extend the existing `ExperienceAccumulator` pattern.
- Provide the raw material for interaction learning (Phase 3).

---

### PHASE 3 — INTERACTION & HUMAN UNDERSTANDING (2 batches)

Human-behavior understanding begins as a foundation here.

#### P3/B3.1 — User preferences and corrections
- Per-user preference records.
- Correction capture (user fixes an Atlas mistake → recorded).
- Provenance on every record.
- Safe persistence/scoping.

#### P3/B3.2 — Interaction pattern learning
- Extract interaction patterns.
- Feed learned information into planning context (reuse the existing
  `planning_context_provider` seam — Stage D pattern).
- Reuse existing `LearningMemory`.
- Acceptance: demonstrate that at least one learned preference influences
  later behavior.

---

### PHASE 4 — GOVERNED COLLECTIVE LEARNING (1–2 batches)

- Aggregate appropriate/anonymized interaction patterns.
- Convert candidates into governed knowledge.
- Reuse existing governed ingest mechanisms (GOV-008/009/010/011 pattern).
- **Owner review required.**
- Strict privacy boundary: user-specific/private information must not
  automatically become global knowledge.
- Must NOT precede P1 + P3.

This is lower priority for the current core milestone.

---

### PHASE 5 — PROACTIVE ADVISORY (1 batch)

- Use the existing Scheduler / EvolutionScheduler tick and cooldown patterns.
- Use existing F1 (environment observer), F10 (availability), F11
  (self-management review) signals.
- Generate bounded user-facing observations/suggestions.
- **Advisory only — never autonomous execution.**
- Suggested actions use existing governed paths only.

May be implemented after P2 and can interleave with later phases.

---

### PHASE 6 — DETERMINISTIC-FIRST / MODEL-INDEPENDENCE (1–2 batches)

- Prefer stored knowledge.
- Prefer learned procedures.
- Prefer deterministic capabilities.
- Prefer tools.
- Use model inference as fallback.
- Graceful no-model operation for deterministic tasks.
- Preserve Ollama/LM Studio/local-provider capability.
- Reduce paid model dependence.
- **Do NOT claim complete zero-inference autonomy.**

Important: provider abstraction is already implemented, but **true model
independence is not**. The practical target is *minimized paid inference* and
*graceful degradation*, not the elimination of inference.

---

### PHASE 7 — CONVERSATIONAL SELF-DEVELOPMENT (1 batch)

- Detect development needs from real operation/experience (incl. F11).
- Allow conversational development requests (no hand-written JSON need files).
- Feed development needs into the existing governed development cycle.
- Reuse B4 model-assisted authoring (opt-in, unchanged).
- Preserve owner approval.
- Preserve sandbox verification.
- Preserve rollback.
- Preserve promotion review.

**This phase closes the current month's core objective.**

---

## 6. DEPENDENCY ORDER

```
P1 ──► P2 ──► P7

P3 depends on P1 and P2.
P4 depends on P1 + P3.
P5 depends on P2.
P6 depends on P2.
```

**Priority order:**

1. P1
2. P2
3. P7
4. P3
5. P6
6. P4
7. P5 (interleavable advisory phase)

Do not interpret this as permission to implement phases out of order without
owner approval.

---

## 7. ONE-MONTH CORE ACCEPTANCE CRITERIA

The core milestone is complete **only** when these behaviors are demonstrable:

1. A session exists with an explicit Owner and attributable user identity.
2. A casual user request can become intent → deterministic plan → governed
   execution → real work → natural report → stored experience.
3. Ambiguous requests produce clarification rather than fabricated actions.
4. Code-affecting changes still require Owner approval.
5. Existing sandbox/verification/rollback/promotion boundaries remain intact.
6. Preferences and corrections are captured per user and influence later work.
7. Atlas can conversationally identify/propose a development need for itself
   and route it into the existing governed cycle.
8. With an external model unavailable, deterministic classification, planning,
   memory/knowledge recall and deterministic execution still function in a
   degraded but useful way.
9. Existing evolution/governance and B1–B4 regression suites remain green.

---

## 8. ARCHITECTURAL RULES (non-negotiable)

- Do not rebuild already-sufficient infrastructure.
- Do not invent new phases without owner approval.
- Do not implement future features preemptively.
- One batch at a time.
- Validate each batch before starting the next.
- Preserve existing DI/composition-root patterns.
- Preserve existing governance choke points.
- Preserve fail-closed behavior.
- Preserve owner approval for code-affecting work.
- Do not casually modify schema.
- Do not modify RuntimeCoordinator ordering.
- Do not modify `Atlas.tick()` unless a future owner-approved phase
  explicitly requires it.
- Do not bypass the existing evolution gateway/approval/sandbox/promotion
  system.
- Reuse existing seams before introducing new infrastructure.
- Keep the core minimal so Atlas can build the non-core features later.

---

## 9. LOCKED SURFACES

The following are protected during this core implementation roadmap. They are
not permanently immutable, but touching them requires an owner-approved batch
with strong architectural justification:

- `atlas/runtime/**`
- `atlas/ai/**`
- `atlas/storage/**` and schema/migrations (currently schema v11)
- RuntimeCoordinator (15-stage ordering)
- `Atlas.tick()`
- `atlas/evolution/development_cycle.py`
- `atlas/evolution/self_development_loop.py`
- `atlas/evolution/approval_manager.py`
- `atlas/evolution/promotion_gate.py`
- `atlas/evolution/autonomy/**`
- B4 model-assisted supplier (`atlas/evolution/model_assisted_supplier.py`)
- The existing governance/execution/sandbox pipeline

---

## 10. COMMANDCODE / MODEL COST DISCIPLINE

The remaining development period uses a limited CommandCode subscription
budget. Therefore:

- Use **stronger models** for architecture/design/audits/critical
  implementation (notably Phase 2).
- Use **cost-optimized models** for mechanical work and documentation.
- Batch related work when safe.
- Avoid unnecessary repeated context.
- Do not spend inference budget implementing features outside the approved
  core.
- Every CommandCode task should have a clearly bounded scope.

---

## 11. ROADMAP LIFECYCLE

This file is **temporary implementation documentation**.

It exists to prevent repeated planning discussions and accidental roadmap
drift.

**During implementation:**

- Update only the status of roadmap items when necessary.
- Do not turn this document into a detailed permanent architecture manual.

**After the core milestone is successfully completed:**

- Owner reviews the document.
- Archive it (to `docs/archive/`) or remove it.
- The implemented Atlas architecture — as recorded in `docs/ATLAS_STATE.md`,
  `docs/ROADMAP.md` and the source code — becomes the source of truth.

---

## 12. CURRENT STATUS

> **HISTORICAL / STALE — this table is retained for reference only.**
> It was last updated at commit `bd783c9` before P1–P7 were implemented. The
> authoritative current state is now recorded in `docs/ROADMAP.md` (Post-Core
> Development: M0–M7) and `docs/ATLAS_STATE.md`. This table no longer reflects
> the actual repository state and must not be read as current.

| Item | State (historical) |
|---|---|
| Current baseline | B1–B4 complete |
| Current commit | `bd783c9` |
| Next approved candidate | **P1/B1.1** (Owner/User foundation) |
| P1/B1.2 | NOT started |
| Phase 2 (all batches) | NOT started |
| Phase 3 (all batches) | NOT started |
| Phase 4 | NOT started |
| Phase 5 | NOT started |
| Phase 6 | NOT started |
| Phase 7 | NOT started |
| B5 | NOT started / not defined |

No roadmap item beyond B4 is currently implemented unless explicitly stated
by the repository audit.

---

*Document created: 2026-08-29 · Temporary core implementation plan derived
from the owner-approved vision and the read-only repository audit at commit
`bd783c9` · Project Atlas — docs/ATLAS_CORE_IMPLEMENTATION_PLAN.md*
