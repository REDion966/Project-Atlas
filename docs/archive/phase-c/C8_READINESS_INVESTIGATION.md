# PROJECT ATLAS — C8 READINESS INVESTIGATION

Mode: READ-ONLY investigation (no code/test/config/schema/governance/CLI/conversation/roadmap changes)
Permitted artifact: this file only.

---

## 1. STATUS

**C8 NOT YET JUSTIFIED.**

C7 is verifiably complete. The autonomy architecture is comprehensive (L1–L5
production-reachable, governed, tested). No genuine, evidence-backed C8 capability gap
was identified. No C1–C7 evidence demonstrated a bounded autonomy expansion need. No
speculative C8 work should be invented.

---

## 2. BASELINE

- Branch `main`; HEAD `f85de896e338e4fa6cdd83b03a61d7e43dfe1ff2` (`f85de89`).
- Working tree: pre-existing modified/untracked files (C3–C7 artifacts, C4.2/C5.1/C6.1
  source+tests) — no staged/deleted/renamed files.
- Relevant tests (this investigation): **351 passed, 0 failed, 0 errors** (§17).

---

## 3. AUTHORITATIVE C8 SCOPE

C8 — **Controlled Autonomy Expansion** — from the frozen Phase C roadmap.

**Established from existing architecture:** controlled autonomy in Atlas is
implemented as a five-level system (L1–L5) where each level represents a bounded
expansion of what Atlas may do autonomously, always within a governance envelope
defined by `AutonomyPolicy`, always requiring a pre-approved proposal, always
subject to `AutonomyController` checks, `AuthorizationManager` scope validation,
sandbox execution, and fail-closed verification.

**C8's operational meaning (from evidence):** the expansion of what Atlas may do
autonomously while remaining governed. C8 does NOT mean unrestricted autonomy,
autonomous coding without approval, or autonomous deployment.

---

## 4. C7 CLOSURE BASELINE

C7 completed its bounded evidence/closure cycle: GAP-C31-02 (conversational
reference/context resolution exposure) was implemented and validated; real-world
validation passed with 0 AI calls on the resolution path; full suite 5945/0/0/2 at
C7 closure. No new C7 gap was identified. C6 closed before that (C6.1 validated
knowledge retrieval, full lifecycle complete; C6 consumption investigation concluded
"C6 OBJECTIVE SATISFIED — CLOSE C6").

---

## 5. CURRENT AUTONOMY ARCHITECTURE

### A. Planning
- `ResearchPlanner` (`research/planner.py:138`) — deterministic decomposition.
- `DevelopmentPlanner` (`evolution/development_planner.py:83`) — 7-step lifecycle.
- `ImprovementPlanner` (`evolution/improvement_planner.py:31`) — weakness detection.
- Production-reachable via `DevelopmentCycleController` (`development_cycle.py:355`).

### B. Investigation
- `InvestigationService` (`conversation/investigation.py:171`) — read-only.
- C6.1 synthesis (`investigation_synthesis.py`).
- Production-reachable via `ConversationService.send` (INVESTIGATION_REQUEST).

### C. Proposal generation
- `InvestigationProposalGenerator` (`investigation.py:622`) → `InvestigationProposalConverter`
  (`:707`) → `EvolutionProposal` (`evolution/models.py:266`).
- `DeterministicChangeSupplier` (`development_cycle.py:246`) — fail-closed without payload.
- `ModelAssistedChangeSupplier` (`model_assisted_supplier.py`) — optional, OFF by default.
- Production-reachable via planning handler.

### D. Approval
- `ApprovalManager` (`evolution/approval_manager.py`) — create/approve/reject/defer.
- Conversational approval (`conversation_service.py:1399-1563`).
- Kernel two-step confirm (`atlas.py:1508`) — OWNER-gated.
- Human approval required for all consequential actions.

### E. Authorization
- `Atlas._require_development_authority` (`atlas.py:1446`) — OWNER-only via
  SessionManager + AuthorityService.
- `AuthorizationManager` (`autonomy/authorization_manager.py`) — scope validation.
- `AutonomyPolicyEngine` (`autonomy_policy.py:50`) — envelope checks.

### F. Execution
- `Atlas.run_development_execution` (`atlas.py:1573`) — requires APPROVED.
- `SelfDevelopmentLoop.run` (`self_development_loop.py:349`) — bounded iterations.
- `SandboxImplementer.apply` (`:159`) — snapshot → apply → verify → restore.
- `SandboxVerifier.run` (`:201`) — real pytest in sandbox.

### G. Mutation
- `CodeApplier` (`autonomy/code_execution.py`) — applies changes only inside sandbox.
- `KnowledgeApplier`/`MemoryApplier` (`autonomy/information_applier.py`) — governed
  writers for KNOWLEDGE/MEMORY scopes only.
- `ApplicationEngine` (`autonomy/application_engine.py:75`) — writers include
  MEMORY/KNOWLEDGE only; **no CODE writer** (`autonomy_wiring.py:161-164`).
- Real-repo mutation: **production path does not exist** (`promotion_gate.py:73`
  reserves `PROMOTED` for operator tooling).

### H. Sandboxing
- `CodeSandbox` (`autonomy/code_sandbox.py:189`) — disposable, path-confined.
- `SandboxWorkspace` (`autonomy/sandbox_tools.py:232`) — identity token, never real repo.
- `SandboxTools._spawn` — `shell=False`, allow-listed env, no secrets.

### I. Verification
- `SandboxVerifier` (`self_development_loop.py:201`) — pytest in sandbox.
- `DevelopmentVerification` (`development_verification.py:86`) — read-only analysis.
- `SelfVerifier` (`advanced_reasoning/verify.py:45`) — circularity/premise/contradiction.

### J. Promotion
- `PromotionGate` (`promotion_gate.py:250`) — deterministic risk assessment +
  `PENDING_REVIEW → APPROVED/REJECTED` lifecycle.
- `PROMOTED` reserved for operator tooling (`:73`).
- **No apply path from promotion to real repository.**

### K. Failure/recovery
- `DevelopmentDiagnostic` (`development_diagnostic.py:90`) — evidence-based diagnosis.
- `DevelopmentRecovery` (`development_recovery.py:79`) — fail-closed recovery decision.
- Conversational recovery (`conversation_service.py:2111`) — read-only decision,
  requires explicit new approval for execution.

### L. Conversation-driven task initiation
- All 19 `TaskType` values in `task_intake.py:54-75` with handlers in
  `conversation_service.py`.
- L1-L5 autonomy handlers (`conversation_service.py:2992-3242`) — OWNER-gated.

### M. Capability discovery / self-knowledge
- `ComponentRegistry` (`lifecycle/component_registry.py:19`) — 35 components.
- `CapabilityModel` (`self_knowledge/capability_model.py`) — canonical projection.
- `Atlas.capability_model()` + `atlas capabilities` CLI.

### N. Evidence collection
- `EvolutionRecord` (`models.py:431`) — evolution history.
- `LearningInsight` (`learning_engine/models.py:36`) — persistent insights.
- Runtime observations (`evolution/runtime_observations.py:31`).

### O. Learning / validated knowledge
- `ValidatedKnowledgeRetriever` (`research/validated_retrieval.py`) — C6.1.
- `LearningMemory` (`learning_engine/learning_memory.py:107`) — persistent (v11).

### P. Audit / history
- `EvolutionMemory` (`evolution_memory.py:268`) — proposals, approvals, records.
- `promotion_gate.py` — promotion review audit.

---

## 6. PRODUCTION CALL-PATH ANALYSIS

```
USER INTENT
    ↓ Atlas.chat → ConversationService.send
    ↓ TaskIntake._classify → TaskSpec
    ↓ routing cascade
    ↓ [read-only handlers: investigation/impact/validated-knowledge/capability-model]
    ↓ [governed handlers: development/planning/approval/execution/recovery/verification]
    ↓ INVESTIGATION → InvestigationService (read-only)
    ↓ PLANNING → InvestigationProposalConverter → EvolutionProposal (DRAFT) → ApprovalManager
    ↓ APPROVAL → ApprovalManager.approve → ProposalStatus.APPROVED
    ↓ EXECUTION → Atlas.run_development_execution
        → _require_development_authority (OWNER)
        → DevelopmentPlanner.plan
        → SelfDevelopmentLoop.run
            → CodeSandbox (create) → SandboxImplementer.apply (snapshot/apply)
            → SandboxVerifier.run (pytest) → rollback on failure
    ↓ PROMOTION REVIEW → PromotionGate.assess → PENDING_REVIEW (no apply)
    ↓ AUTONOMY L1-L5 → AutonomyController.check_* → acknowledge/execute/deny
```

No production-reachable path bypasses the approval→authorization→execution chain.

---

## 7. GOVERNANCE / APPROVAL ANALYSIS

- `ApprovalManager` is the sole approval surface (`approval_manager.py:21`).
- `ProposalStatus.APPROVED` is the only state that permits execution.
- `ApprovalRequest.is_valid_for` binds proposal_id + fingerprint.
- Human approval is conversational (`_maybe_handle_approval`) or kernel two-step
  (`atlas.py:1508`).
- No path exists to bypass approval: execution requires APPROVED + OWNER.

---

## 8. EXECUTION / SANDBOX / VERIFICATION ANALYSIS

- Execution is exclusively via `SelfDevelopmentLoop` inside `CodeSandbox`.
- Sandbox is disposable; path-confined; `shell=False`; allow-listed env.
- Verification is real pytest inside the sandbox.
- Failure → rollback (`sandbox.restore`) → `FAILED` outcome → diagnostic.
- No real-repo mutation during execution.

---

## 9. CURRENT AUTONOMY BOUNDARY

| Level | What it means | Handler | Production status | Actually executes? |
|---|---|---|---|---|
| L1 | Execute pre-approved work | `_maybe_handle_autonomy_request` (`:2649`) | yes — requires APPROVED proposal + OWNER | yes — calls the governed execution bridge |
| L2 | Chain approved workflows, bounded plan adjustment | `_maybe_handle_l2_autonomy_request` (`:2866`) | acknowledgment only | no (decision-only) |
| L3 | Autonomous recovery, sub-plans, HIGH risk | `_maybe_handle_l3_autonomy_request` (`:2992`) | acknowledgment only | no |
| L4 | Capability acquisition, INFORMATION level | `_maybe_handle_l4_autonomy_request` (`:3117`) | acknowledgment only | no |
| L5 | Cross-objective coordination | `_maybe_handle_l5_autonomy_request` (`:3242`) | acknowledgment only | no |

**Key finding:** L1 actually executes pre-approved work through the governed
pipeline. L2–L5 are acknowledgment-only: they check autonomy policy, update state,
and return a message — but do **not** execute any autonomous action. They are
"acknowledgment handlers" that confirm the autonomy level was recognized.

---

## 10. C1–C7 EVIDENCE REVIEW

| Milestone | Evidence relevant to C8 | Does it justify C8 expansion? |
|---|---|---|
| C1 | Readiness verification; governance/model-independence confirmed | No — confirms existing governance is sufficient |
| C2 | Conversational development pilot; casual/self-understanding/investigation/development/failure-recovery | No — exercised existing pipeline, no autonomy expansion need |
| C3 | Real-world capability evidence; investigation; synthesis | No — read-only work; no autonomy need |
| C4 | Capability exposure (impact analysis); validated knowledge retrieval | No — read-only exposure; no autonomy need |
| C5 | Canonical capability model; self-knowledge | No — read-only self-knowledge; no autonomy need |
| C6 | Validated knowledge retrieval; knowledge maturity | No — read-only retrieval; no autonomy need |
| C7 | Reference/context resolution; bounded exposure | No — read-only conversation understanding; no autonomy need |

**No C1–C7 evidence demonstrates an autonomy expansion need.** All milestones
produced read-only or governance-preserving capabilities.

---

## 11. REAL-WORLD CAPABILITY-GAP ANALYSIS

No real-world scenario across C1–C7 demonstrated that Atlas lacks a controlled
autonomy capability it needs. The governed pipeline already handles:
- investigation → planning → proposal → approval → execution → verification
- failure/recovery with diagnostics
- L1 autonomous execution of pre-approved work
- L2–L5 acknowledgment with policy checks

**No bounded capability gap was identified.**

---

## 12. C8 CANDIDATE GAP CLASSIFICATION

| Candidate | Category | Justification |
|---|---|---|
| Expanding L1 to execute without OWNER re-check | Not evidenced | Already OWNER-gated; weakening = safety violation |
| Wiring L2–L5 to actually execute (vs acknowledge) | **Not evidenced** | No C1–C7 scenario demonstrated a need; activation without evidence = speculative |
| Activating `AutonomyController.check_recovery_autonomy` (defined but unreferenced) | **Not evidenced** | Recovery already works through the governed path |
| Applying F2 freshness to validated claims | Already classified C6/C7 boundary | Not an autonomy gap |
| Autonomous code writer (CODE scope) | **Explicitly locked** (`autonomy_wiring.py`: no CODE writer) | Would require new governance scope — not C8 without evidence |
| Autonomous promotion/apply | **Explicitly reserved** (`promotion_gate.py:73`) | Not C8 without evidence |

---

## 13. AUTONOMY SAFETY MATRIX

| Behavior | Existing? | Governed? | Approved? | Verified? | Safe to expand? | Requires new governance? | C8 scope? |
|---|---|---|---|---|---|---|---|
| Read-only investigation | yes | yes | n/a | n/a | yes | no | no (already done) |
| Information gathering | yes | yes | n/a | n/a | yes | no | no |
| Analysis | yes | yes | n/a | n/a | yes | no | no |
| Planning | yes | yes | n/a | n/a | yes | no | no |
| Proposal generation | yes | yes | yes | n/a | yes | no | no |
| Sandbox execution | yes | yes | yes | yes | yes | no | already exists |
| Verification | yes | yes | n/a | yes | yes | no | already exists |
| User-approved code change (sandbox) | yes | yes | yes | yes | yes | no | already exists |
| User-approved repo mutation | **no** | would need | yes | yes | **no** | **yes** | **not without evidence** |
| Promotion | yes (review) | yes | yes | n/a | yes | no | already exists |
| Promotion apply | **no** | would need | yes | yes | **no** | **yes** | **not without evidence** |
| Git commit | **no** | — | — | — | **no** | **yes** | **out of C8** |
| External side effect | **no** | — | — | — | **no** | **yes** | **out of C8** |
| Self-modification | **no** | — | — | — | **no** | **yes** | **out of C8** |
| Governance modification | **no** | — | — | — | **no** | **yes** | **out of C8** |
| Permission modification | **no** | — | — | — | **no** | **yes** | **out of C8** |
| Autonomous continuation after failure | partial (recovery decision) | yes | yes | yes | **no** | **yes** | **not without evidence** |

---

## 14. MODEL-INDEPENDENCE ANALYSIS

All autonomy-related components are deterministic:
- `AutonomyController` — pure logic, no AI.
- `AutonomyPolicyEngine` — pure logic.
- `AuthorizationManager` — pure logic.
- `DevelopmentPlanner` — deterministic-first, optional model.
- `SelfDevelopmentLoop` — deterministic sandbox execution.
- `PromotionGate` — deterministic risk assessment.

No hidden model dependency exists in planning/execution/governance. **PASS.**

---

## 15. GOVERNANCE PRESERVATION REQUIREMENTS

Existing mechanisms sufficient for any C8 capability:
- Human approval: `ApprovalManager` + conversational approval + kernel two-step confirm.
- Authorization: `Atlas._require_development_authority` (OWNER-only).
- Scope validation: `AutonomyPolicyEngine.is_scope_in_envelope`.
- Sandbox verification: `CodeSandbox` + `SandboxVerifier` (real pytest).
- Fail-closed: every failure path returns an explicit failure; no silent continuation.
- Immutable/auditable state: `EvolutionMemory` + `EvolutionRecord` + promotion audit.
- No silent mutation: all changes go through governed execution + sandbox.

**Existing governance is sufficient** for the current L1–L5 architecture. No new
governance mechanism is needed unless evidence justifies it.

---

## 16. ACCEPTED NON-GOALS

C8 is NOT: unrestricted autonomous agent behavior; autonomous coding without
approval; autonomous deployment; autonomous Git operations; autonomous permission
changes; autonomous governance changes; self-rewriting architecture; LLM as
identity; removing human approval; removing sandbox verification; removing
fail-closed; recursive uncontrolled self-improvement; arbitrary external action.

---

## 17. TEST / VERIFICATION RESULTS

- `python -m pytest tests/test_autonomy_controller.py tests/test_autonomy_requests_cli.py tests/test_l1_integration.py tests/test_l2_integration.py tests/test_l3_integration.py tests/test_l4_integration.py tests/test_l5_integration.py tests/test_level1_analysis_contract.py tests/test_level2_proposal_approval.py tests/test_level3_execution.py tests/test_level4_execution.py tests/test_level5_execution.py -q` → **351 passed, 0 failed, 0 errors (exit 0)**.
- Reference: full suite (unchanged tree) 5945/0/0/2.
- No failure; nothing to classify.

---

## 18. GIT / BASELINE INTEGRITY

- Branch `main`; HEAD `f85de89` — unchanged before/after.
- No source/test/config/schema/persistence/governance/CLI/conversation/roadmap
  modification; no staged files; no commit/reset/clean/stash; no deletion/rename.
- Only new artifact: this investigation report.

---

## 19. C8 READINESS CRITERIA

| # | Criterion | Result | Evidence |
|---|---|---|---|
| 1 | C7 verified complete | **PASS** | C7 closure report; no new gap |
| 2 | Genuine C8 capability gap OR authoritative scope established | **FAIL** | No C1–C7 evidence demonstrates autonomy expansion need; no authoritative C8 definition exists |
| 3 | Production-relevant | **UNCLEAR** | No demonstrated scenario requires expanded autonomy |
| 4 | Reproducible/authoritatively specified | **FAIL** | No authoritative C8 scope |
| 5 | Bounded | **UNCLEAR** | L1–L5 architecture is bounded; C8 expansion scope is not |
| 6 | Acceptance criteria testable | **UNCLEAR** | Without a defined gap, criteria cannot be objective |
| 7 | Governance boundaries definable | **PASS** | Existing governance is comprehensive |
| 8 | Human approval semantics clear | **PASS** | OWNER-only; conversational/kernel approval |
| 9 | Verification semantics clear | **PASS** | Sandbox pytest; read-only analysis |
| 10 | Fail-closed definable | **PASS** | All existing paths fail closed |
| 11 | Model independence preservable | **PASS** | All autonomy is deterministic |
| 12 | No speculative architecture | **PASS** | No speculative work performed |
| 13 | No C9 pull-forward | **PASS** | No C9 work proposed |
| 14 | No C5/C6/C7 boundary undo | **PASS** | All boundaries preserved |
| 15 | No safety weakening | **PASS** | No safety change proposed |

---

## 20. FINAL C8 READINESS VERDICT

**C8 NOT YET JUSTIFIED.**

No genuine, evidence-backed C8 capability gap exists at the current boundary. The
L1–L5 autonomy architecture is comprehensive, production-reachable, and tested; the
governance/approval/execution/sandbox/verification chain is complete; and no C1–C7
milestone produced evidence of an autonomy expansion need. Activating dormant
autonomy levels or expanding their scope without demonstrated real-world evidence
would be speculative.

**What would justify C8:** a demonstrated real-world scenario where Atlas's current
governed pipeline (investigation→planning→proposal→approval→execution→verification)
is insufficient and a bounded autonomy expansion would resolve it — supported by
reproduction, an objective acceptance criterion, and an explicit governance boundary
definition. None was found.

---

## 21. PRECISE NEXT ROADMAP POSITION

C8 remains **NEXT** on the frozen Phase C roadmap but is **not yet justified** for
implementation. C6 and C7 are closed at their evidence boundaries. No C6.2, C7.1,
C8.1, or other substep is authorized or invented. The next evidence-driven step
would be a C8 scope/contract investigation if real-world evidence emerges that
demonstrates a bounded autonomy expansion need.
