# PROJECT ATLAS — C8 REAL-WORLD CONTROLLED-AUTONOMY CAPABILITY EVIDENCE PILOT

Mode: READ-ONLY / evidence-acquisition. No production, test, config, schema, governance,
persistence, CLI, or roadmap modifications. Sole new artifact: this file.

Distinction key used throughout: **VERIFIED FACT** (observed through an actual production
path) · **OBSERVED BEHAVIOR** · **INTERPRETATION** · **INTENTIONAL SAFETY BOUNDARY** ·
**NON-C8 LIMITATION** · **GENUINE C8 CANDIDATE** · **SPECULATION (not used as evidence)**.

---

## 1. STATUS

**NO C8 GAP FOUND.**

Real-world use of the current Atlas architecture did **not** reveal a genuine, bounded,
governed capability gap that must be filled by C8. Atlas already performs controlled
autonomy: after an explicit human approval, a single bounded continuation request
("proceed autonomously" — L1) executes the already-approved, already-governed action
inside the disposable sandbox, with verification, fail-closed behavior, OWNER-only
authorization, and **zero** external-AI calls. All other stops observed are
intentional governance/safety boundaries.

**C8 remains not justified for implementation at the current evidence boundary.**

---

## 2. BASELINE

- Branch: `main` (VERIFIED FACT).
- HEAD: `f85de896e338e4fa6cdd83b03a61d7e43dfe1ff2` / `f85de89` (VERIFIED FACT — unchanged
  before and after the pilot).
- Working tree: pre-existing modified/untracked files only; none created, modified, deleted,
  renamed, staged, or committed by this pilot (VERIFIED FACT — `git status --short` identical
  before/after).
- Authoritative roadmap source: the frozen Phase C C0→C9 series supplied in the command
  (C7 COMPLETE AT CURRENT EVIDENCE BOUNDARY; C8 NEXT, not justified; C9 not started).
- Current C8 readiness report: `C8_READINESS_INVESTIGATION.md` → verdict
  **C8 NOT YET JUSTIFIED**.
- Autonomy implementation locations: `atlas/evolution/autonomy/*` (controller, policy,
  authorization, dispatcher, sandbox tools, appliers), `atlas/kernel/atlas.py`
  (`_autonomy_check`, `_require_development_authority`, `run_development_execution`,
  `_development_execution_bridge`), `atlas/conversation/conversation_service.py`
  (L1–L5 handlers, approval/execution/recovery/verification/report handlers),
  `atlas/conversation/task_intake.py` (autonomy + execution/approval/planning cues).
- Relevant tests: `test_autonomy_controller.py`, `test_l1..l5_integration.py`,
  `test_level1..level5_*.py`, `test_evolution_autonomy_dispatcher.py`,
  `test_evolution_autonomy_adapters.py`, `test_self_development_p7_authority.py`,
  `test_authority.py`.

---

## 3. C8 QUESTION

"Does real-world use of the current Atlas architecture reveal a useful task where Atlas is
unnecessarily unable to continue or coordinate a bounded, already-governed action after the
user has explicitly approved it?"

Answer from the pilot: **No.** Atlas **can** continue a bounded, already-governed action
after explicit approval (L1), and every point where it stops was verified to be an
intentional approval/authorization/sandbox/fail-closed boundary — not a missing capability.

---

## 4. CURRENT AUTONOMY BOUNDARY

| Level | Meaning (from implementation) | Production status |
|---|---|---|
| L1 | Execute **already-approved** work autonomously; cannot approve, expand scope, or promote | **Executes** (VERIFIED FACT in this pilot) |
| L2 | Chain approved workflows / bounded plan adjustment | Policy + state acknowledgement only |
| L3 | Autonomous recovery execution / sub-plans / HIGH risk | Policy + state acknowledgement only |
| L4 | Capability acquisition / INFORMATION level | Policy + state acknowledgement only |
| L5 | Cross-objective coordination | Policy + state acknowledgement only |

**VERIFIED FACT:** L1 is production-reachable and performs real governed execution.
L2–L5 do not autonomously execute work (consistent with `C8_READINESS_INVESTIGATION.md`).

---

## 5. PRODUCTION PATH VERIFIED

Pilot harness (read-only): real `Atlas()` kernel, real `atlas.chat → ConversationService.send`,
real `ApprovalManager`, real kernel `_autonomy_check`, real `_development_execution_bridge`,
real `SelfDevelopmentLoop` + `CodeSandbox`, isolated temp `SQLiteEvolutionStorage`
(the same `_storage_class` shim used by the project's own tests), and a deterministic
bounded `ChangeSupplier`. A failing-AI double was installed so that **no external AI is
required**. This mirrors the project's own `TestConversationalAuthoringJoin` wiring.

Observed chain across scenarios (VERIFIED FACT):

```
USER MESSAGE
 → ConversationService.send → TaskIntake classify → routing cascade
 → INVESTIGATION  (read-only; modification_status=NONE)
 → PLANNING        (PENDING_APPROVAL; approval request created)
 → APPROVAL        (ProposalStatus.APPROVED per ApprovalManager)
 → EXECUTION / L1  (OWNER only; fingerprint validated; sandbox; verify; report)
```

---

## 6. SCENARIO A — multi-step governed development, L1 continuation

Sequence and observed results (VERIFIED FACT; all turns 0 AI calls):

1. "Investigate the memory architecture" → investigation, `modification_status=NONE`,
   `findings_count=9`, investigation proposal created.
2. "Plan this improvement" → `planning.status="prepared"`, evolution proposal
   `PENDING_APPROVAL`, approval request `PENDING`.
3. "proceed autonomously" **before approval** → `autonomy.status="request_not_found"`
   (fail closed — no execution).
4. "Approve this proposal" → `approval.status="approved"`,
   `modification_status=NONE` ("No changes have been made. Implementation will require a
   separate explicit …").
5. "proceed autonomously" **after approval** → `autonomy.status="executed"`,
   `reason="L1 autonomous execution permitted"`, evidence
   `{proposal_status: APPROVED, authority: owner, scope: CODE, risk_level: LOW,
   execution_level: SANDBOXED}`, content: "Development Execution: SUCCESS … completed
   inside sandbox".

**Finding:** Atlas **can** continue the bounded, already-governed action after explicit
approval, via one bounded continuation phrase, with the approval/authorization/sandbox
boundary fully intact. This directly answers the C8 question — and the capability already
exists.

---

## 7. SCENARIO B — investigate → proposal → explicit execution

(V1) "Execute the approved proposal." with no active proposal → `no_active_proposal` (fail closed).
(V2) … before approval → `request_not_found` (fail closed).
(V3) "Approve this proposal" → `approved`.
(V4) "Execute the approved proposal" → `execution.status="succeeded"`, `result_status="SUCCESS"`,
persisted `metadata["execution"].status="succeeded"`, sandbox-only, 0 AI.
(V5) repeat "Execute the approved proposal" → `succeeded` again (see §11 — observation).

**Finding:** The explicit execution transition works end-to-end through the governed bridge.
Execution is deliberately **not** implied by approval ("approval alone does not execute") —
this is an **INTENTIONAL SAFETY BOUNDARY**, per the command's rule that ordinary human
approval is not a gap.

---

## 8. SCENARIO C — failure / recovery

A bounded author whose sandbox test fails was used.

- "Execute the approved proposal" → `execution.status="iterations_exhausted"`,
  `result_status="ITERATIONS_EXHAUSTED"`, 3 iterations; diagnostic present:
  `failure_class="verification"`, `confidence="probable"`,
  `cause="The bounded iteration budget was exhausted because verification did not pass."`,
  `evidence="status=ITERATIONS_EXHAUSTED; last.test_outcome='failed'; last.verification_passed=False"`.
- "recover from the failure" → `recovery.status="decided"`, `recoverable=false`,
  `strategy="no_recovery"` (read-only decision; never auto-executes).
- "proceed autonomously" after failure → L1 re-executes the same **approved** proposal in
  sandbox; fails again (`iterations_exhausted`). No silent recovery, no scope expansion,
  no real mutation.

**Finding:** Atlas detects, stops, preserves governance, reports the failure, diagnoses it,
rolls back via the disposable sandbox, and awaits human direction. Human intervention after
failure is required — an **INTENTIONAL SAFETY BOUNDARY**, not a gap. No bounded continuation
was observed that could be safely and explicitly governed but is unavailable.

---

## 9. SCENARIO D — multi-step coordination

- Completing investigate→plan→approve→execute required **4 user messages** — each an
  intentional governance transition (investigation, planning, approval, execution).
- Final execution `succeeded`; "continue the development" (L1) re-executes within the
  approved boundary.

**Finding:** The number of manual transitions equals the number of governance decisions;
no transition observed was a redundant or mechanical step that Atlas could safely take
without weakening a boundary. This is governed coordination, not a missing-orchestration gap.

---

## 10. SCENARIO E — read-only / non-mutating autonomy

- `Atlas.capability_model()` → 101 entries (read-only projection; VERIFIED FACT).
- `Atlas.validated_knowledge("anything")` → `status=empty` (read-only, fail-closed; VERIFIED FACT).
- Compound read-only request ("Investigate the memory architecture and summarize the
  repository structure") → handled deterministically as a single investigation,
  `modification_status=NONE`, 0 AI.
- Repository impact queries ("What depends on atlas.conversation.conversation_service?",
  "What is the impact of changing atlas.kernel.atlas?") → `repository_impact.status="resolved"`
  with dependents/dependencies/impact sets, 0 AI.

**Finding:** Atlas already autonomously performs multiple deterministic, non-mutating
read-only operations with no approval, no authorization, and no external side effect — PASS.

---

## 11. OBSERVED LIMITATIONS

**OL-1 — Execution replay has no explicit already-executed guard (OBSERVED BEHAVIOR).**
Re-issuing "Execute the approved proposal" for a still-`APPROVED` proposal re-invokes the
governed bridge and returns `SUCCESS` again. `_maybe_handle_execution_request` validates
status/decision/identity/fingerprint but contains no "already executed" guard, although its
docstring states execution does *not* "Allow replay of already-executed proposals".
Impact: re-execution happens **inside the disposable `CodeSandbox`** and never mutates the
real repository and produces no external side effect. Classification: **E — not a real C8
gap**; a documentation/implementation divergence in the non-C8 execution path. It does not
block the C8 verdict and is flagged for separate (non-C8) review. It was not fixed here.

**OL-2 — Approvals and execution are intentionally separate steps.** Classification:
**C — intentional governance boundary working correctly.**

No other limitations were observed. No Category-A candidate was found.

---

## 12. CLASSIFICATION MATRIX

| Observation | Category |
|---|---|
| L1 executes pre-approved work (Scenario A/B) | C (boundary working; and evidence that controlled autonomy exists) |
| Execution requires explicit request after approval | C (intentional boundary) |
| Premature autonomy/execute refused (`request_not_found`/`no_active_proposal`) | C (fail-closed) |
| Non-owner autonomy/execute refused (`unauthorized`) | C (authorization) |
| Failure → stop/diagnose/rollback, no auto-recovery | C (fail-closed) |
| Read-only multi-op coordination | C (already supported) |
| Replay without explicit guard (OL-1) | E (not a real C8 gap) |
| L2–L5 acknowledgement-only (not exercised as autonomous execution) | E (not promoted; no evidence of need) |

**Category A count: 0. Category B count: 0** (no autonomy capability tested was unreachable
through an exposure gap). Categories C and E account for every observation.

---

## 13. SAFETY / GOVERNANCE ANALYSIS

| Property | Status in pilot | Evidence |
|---|---|---|
| Approval preserved | PASS | Execution refused before approval (`request_not_found`) |
| Authorization preserved | PASS | Non-owner autonomy/execute → `unauthorized` |
| Sandbox preserved | PASS | Execution level `SANDBOXED`; rollback on failure |
| Verification preserved | PASS | `ITERATIONS_EXHAUSTED` after failing pytest in sandbox |
| Fail-closed preserved | PASS | Premature/no-proposal requests refused |
| Fingerprint/identity binding | PASS | Validated before bridge |
| No autonomous external side effect | PASS | No network/AI; sandbox-only |
| No autonomous Git operation | PASS | `git status` unchanged; no commits |
| No governance/permission change | PASS | No governance code touched |
| No autonomous continuation past failure | PASS | Failure requires human direction; L1 re-exercise stays in-boundary |
| Autonomous mutation of real repo | NONE observed | Sandbox is disposable; real repo untouched |

No candidate in this pilot would require bypassing approval/authorization, removing sandbox
verification, autonomous mutation, Git operations, external side effects, governance/permission
changes, or external-AI dependence. Nothing was promoted to an implementation candidate.

---

## 14. MODEL-INDEPENDENCE ANALYSIS

- External AI required: **NO**.
- AI calls recorded across all scenarios (A–F) and all repeatability runs: **0**.
- All exercised capabilities are deterministic. A failing-AI double was installed for the
  entire pilot and never affected any outcome.
- No Ollama/Qwen/OpenAI/Anthropic/llama.cpp/embeddings/network was used.

**PASS.**

---

## 15. REPEATABILITY RESULTS

A dedicated probe ran the core autonomy sequence (investigate → plan → premature-autonomy →
approve → L1-autonomy → read-only impact) **3 times** on fresh isolated storage.

- All stable fields identical across all 3 runs: `identical=true`.
- Per run: `inv=NONE`, `plan=prepared`, `late_autonomy=request_not_found`,
  `approve=approved`, `autonomy_status=executed`,
  `autonomy_reason="L1 autonomous execution permitted"`, `sandbox_success=true`,
  `ro=resolved`, `ai_calls=0`.

**Finding:** The observed behavior is deterministic and stable; no environmental noise.

---

## 16. TEST RESULTS

- Targeted autonomy/governance (16 files):
  `python -m pytest tests/test_autonomy_controller.py tests/test_autonomy_requests_cli.py tests/test_l1_integration.py tests/test_l2_integration.py tests/test_l3_integration.py tests/test_l4_integration.py tests/test_l5_integration.py tests/test_level1_analysis_contract.py tests/test_level2_proposal_approval.py tests/test_level3_execution.py tests/test_level4_execution.py tests/test_level5_execution.py tests/test_evolution_autonomy_dispatcher.py tests/test_evolution_autonomy_adapters.py tests/test_self_development_p7_authority.py tests/test_authority.py -q`
  → **458 passed, 0 failed, 0 errors** (exit 0).
- Relevant conversation/planning/investigation/execution coverage is included in the full suite below.
- Full suite:
  `python -m pytest tests -q --junitxml=junit_c8pilot.xml`
  → **5945 tests, 0 failures, 0 errors, 2 skipped** (exit 0). Matches the C7 baseline exactly
  (unchanged tree).

No test failed; nothing was classified as a readiness blocker.

---

## 17. GIT INTEGRITY

- Branch unchanged: `main` (PASS).
- HEAD unchanged: `f85de89` (PASS).
- No commits created (PASS).
- No tracked-file modifications by this pilot (PASS).
- No unintended untracked files (PASS); only this report is added.
- All pre-existing modifications preserved (PASS).

---

## 18. C8 GAP DECISION

**OUTCOME 1 — NO C8 GAP FOUND.**

Current Atlas provides sufficient controlled autonomy for the tested real-world scenarios:
after explicit approval, a bounded L1 continuation executes the already-governed action
deterministically, sandboxed, verified, OWNER-gated, and with zero external-AI calls. Every
other stop is an intentional approval/authorization/sandbox/fail-closed boundary, and
read-only multi-operation coordination is already supported. The one observed divergence
(OL-1, replay) is sandboxed, non-mutating, and outside C8.

No Category-A gap satisfied the evidence standard (real, reproducible, bounded, controlled,
already-supported or clearly missing, non-speculative, roadmap-fit, safety-preserving).

---

## 19. EVIDENCE SUMMARY

**VERIFIED FACT**
- L1 autonomous execution of an approved proposal succeeds in sandbox with
  `{proposal_status: APPROVED, authority: owner, scope: CODE, risk_level: LOW,
  execution_level: SANDBOXED}` and 0 AI calls.
- Premature autonomy/execute and non-owner autonomy/execute are refused (fail-closed).
- Failure produces `ITERATIONS_EXHAUSTED` + verification diagnostic + `no_recovery` decision,
  with rollback in the disposable sandbox.
- Read-only capability-model, validated-knowledge, and repository-impact operations complete
  with 0 AI calls.
- Full suite 5945/0/0/2; targeted 458/0/0; 3/3 repeatability identical; git unchanged.

**INTERPRETATION**
- The C8 question is already answered affirmatively by existing L1: Atlas *can* continue a
  bounded, already-governed action after approval; the "unnecessarily unable" condition is
  not met.

**INTENTIONAL SAFETY BOUNDARY**
- Approval ≠ execution; OWNER-only execution; sandbox-only mutation; no auto-recovery after
  failure; L2–L5 do not autonomously execute.

**NON-C8 LIMITATION**
- OL-1 replay without an explicit guard (sandboxed; no real mutation; documentation/
  implementation divergence).

**GENUINE C8 CANDIDATE**
- None identified.

---

## 20. RECOMMENDATION

Do not begin C8 implementation. Do not invent C8.1. Do not activate L2–L5 execution or
expand autonomy for convenience.

C8 remains not justified for implementation at the current evidence boundary.

If C8 is ever pursued, the only non-blocking follow-up surfaced by this pilot is the
**non-C8** OL-1 observation (an explicit already-executed guard on the conversational
execution path, or correction of its docstring) — which belongs to the existing governed
execution surface, not to a new autonomy capability. No decision on it is made here.
