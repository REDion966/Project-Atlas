# PROJECT ATLAS — C7 READINESS INVESTIGATION — HUMAN UNDERSTANDING

Mode: READ-ONLY investigation (no code/test/config/schema/governance/CLI/conversation/roadmap changes)
Permitted artifact: this file only.

---

## 1. STATUS

**C7 NOT YET JUSTIFIED AS A NEW CAPABILITY — ONE BOUNDED EXPOSURE GAP IDENTIFIED.**

C6 is verifiably closed. Evidence from C2–C6 establishes exactly **one**
human-understanding limitation that is deterministic, bounded, model-independent,
reproducible, and production-relevant: **conversational reference/context
resolution is implemented but never applied in the turn flow (GAP-C31-02)**. Because
the underlying capability already exists (pure, tested resolver + rich
`ConversationState` + an intake-level pronoun-ambiguity detector), this is a
**Category B (existing capability, exposure missing)** finding, not a missing
capability. Recommendation **C**.

---

## 2. BASELINE

- Branch `main`; HEAD `f85de896e338e4fa6cdd83b03a61d7e43dfe1ff2` (`f85de89`) — verified.
- Working tree: pre-existing modified/untracked files (C3–C6 artifacts, C4.2/C5.1/C6.1
  source+tests) — no staged/deleted/renamed files.
- Relevant verification (this investigation): **171 passed, 0 failed, 0 errors** (§17).

---

## 3. C6 CLOSURE VERIFICATION

Verified from the C6 artifacts:

- `C6_READINESS_INVESTIGATION.md` → GENUINE C6 GAP; recommended bounded C6.1.
- `C6_1_SCOPE_CONTRACT_INVESTIGATION.md` → REFINE (B1–B6).
- `C6_1_CONTRACT_RESOLUTION.md` → **CONTRACT VALIDATED**; ready for authorization.
- `C6_1_IMPLEMENTATION_REPORT.md` → **C6.1 IMPLEMENTATION COMPLETE — FULL LIFECYCLE COMPLETE** (focused 30, relevant 230, full 5906/0/0/2, real-world validation PASS, 0 AI calls).
- `C6_POST_C6_1_EVIDENCE_INVESTIGATION.md` → no Category-A gap; one exposure limitation.
- `C6_VALIDATED_KNOWLEDGE_CONSUMPTION_INVESTIGATION.md` → **C6 OBJECTIVE SATISFIED — CLOSE C6**; no actionable C6 consumption gap; no defect.

**C6 closed; no unresolved C6 defect; no C6.2 authorized.** Proceeding is valid.

---

## 4. C7 AUTHORITATIVE OBJECTIVE

C7 — **Human Understanding**: Atlas should better understand human communication,
**intent, context, goals, constraints, ambiguity, conversational continuity, and
problem structure** — transparently, deterministically-first, model-independently,
governed, fail-closed. It is NOT generic chatbot behavior, LLM dependency,
personality simulation, unrestricted NLU, hidden/profiling behavior, or manipulation.

---

## 5. HUMAN-UNDERSTANDING ARCHITECTURE INVENTORY

| Mechanism | Human-facing problem | Deterministic | Model-indep. | Prod-reachable | Tested | Boundary |
|---|---|---|---|---|---|---|
| `TaskIntake` (`task_intake.py`) task-type classification | Understand what the user asks for | yes | yes | yes (`send()`) | yes (`test_conversation_task_intake.py`) | cue-based; no semantic NLU |
| TaskSpec intent/goal/constraints/priorities/success_criteria | Structured request understanding | yes | yes | yes | yes | extracted, bounded |
| Ambiguity assessment + clarification cues (`_assess_ambiguity`, `_CLARIFY_CUES` `task_intake.py:424-430`) | Ask when a request is underspecified | yes | yes | yes | yes | only triggers for ACTION/DEVELOPMENT (`:1102-1105`) |
| Pronoun ambiguity detection (`_AMBIGUOUS_PRONOUN_RE` `task_intake.py:422`) | Detect unresolved references | yes | yes | yes | yes | **detects** `it/that/this/them/those`; does **not resolve** |
| `ConversationState` (`conversation_state.py:32-121`) | Carry context across turns | yes | yes | yes | yes | `current_subject`, `current_task`, `current_investigation`, `active_proposal_id`, `pending_question`, `latest_result`, `relevant_prior_action`, … |
| `ConversationReferenceResolver` (`reference_resolution.py:152`) | Resolve references to prior context | **yes** | **yes** | **NO — unwired in `send()`** | yes (`test_reference_resolution.py`) | AMBIGUITY→clarification, never guesses |
| `ConversationService.resolve_reference()` (`:307-314`) | Manual resolution helper | yes | yes | convenience only | yes (`test_p15_2`) | not called by the turn flow |
| Development-need dialogue/coordinator (`development_need_dialogue.py`, `development_need_coordinator.py`) | Confirm an inferred development need | yes | yes | yes | yes | session-bound, fail-closed |
| Deterministic fallback (`deterministic_fallback.py`) | Answer when no model | yes | yes | yes | yes | knowledge/tool/notice only |

---

## 6. CURRENT CONVERSATIONAL CAPABILITY

Production path (verified names):

```
USER
→ Atlas.chat                          (kernel/atlas.py:3457)
→ ConversationService.send            (conversation_service.py:340)
→ self._intake → TaskIntake.intake    (task_intake.py:780 → :871 _classify)
→ routing cascade                     (conversation_service.py:388-500)
   INVESTIGATION → APPROVAL/REJECTION → PLANNING → EXECUTION → RECOVERY →
   VERIFICATION → REPORT → REPOSITORY_IMPACT → AUTONOMY(L1–L5) → DEVELOPMENT →
   development-need confirmation → orchestration → cognition + AI chat
→ deterministic fallback on AI failure (conversation_service.py:549-570)
→ assistant Message appended to the conversation
```

**A. Deterministic understanding (Atlas-native):** cue-based task classification
(19 `TaskType`s), structured `TaskSpec`, stateful `ConversationState`, ambiguity
detection/clarification, development-need confirmation, read-only handlers
(investigation, impact analysis, validated knowledge, capability model), repository
inspection. **B. Optional external-model behavior:** cognition/AI chat and
model-assisted intent parsing (injected, OFF by default). **C. Unsupported/ambiguous:**
open-ended synthesis without a model; **references to prior turns are not resolved in
the turn flow**.

---

## 7. C2 EVIDENCE REVIEW

- **Casual conversation:** greeting/research/question classification; deterministic; general questions fall to cognition/AI (degraded notice offline). Limitation remains (open-ended answers need a model) — **not a C7 gap** (would require an LLM; rejected).
- **Self-understanding conversation:** there is no dedicated deterministic self-Q&A handler (the kernel exposes `component_registry`/`capability_model`/`validated_knowledge`; C5 delivered the capability model). Conversational self-Q&A is the C5→C7 boundary — **not reopened**.
- **Investigation conversation:** deterministic, read-only; works (C2/C3 pilots). **No regression.**
- **Development conversation:** deterministic governed lifecycle (investigate→plan→approve→execute→verify), fail-closed; works (C2/C4/C6.1). **No regression.**
- **Failure/recovery conversation:** deterministic, fail-closed; works (C2.5). **No regression.**
- **Observed limitation carried forward (C3.1/C4.1 pilots):** follow-ups that refer to
  prior context lose it — e.g. *"Based on that investigation, which component should
  I review first?"* was re-classified as a fresh `INVESTIGATION_REQUEST` on the literal
  text; *"What tests did you find for it?"* produced an ambiguity clarification;
  *"Which of those components…?"* fell through to the model. **This limitation persists**
  (§8).

---

## 8. REFERENCE / CONTEXT ANALYSIS

**GAP-C31-02 current status (verified):**

- The resolver is **implemented** (`ConversationReferenceResolver.resolve`,
  `reference_resolution.py:158-221`), **pure/deterministic/side-effect-free**, with the
  invariant **"AMBIGUITY → CLARIFICATION. NEVER GUESS."** and statuses
  RESOLVED/UNRESOLVED/AMBIGUOUS.
- It is **instantiated** (`conversation_service.py:267`) and **exposed**
  (`resolve_reference` `:307-314`), and **tested** (`tests/test_reference_resolution.py`;
  `tests/test_p15_2_conversation_continuity.py:96,106`).
- It is **not called anywhere in `send()`** (grep: the only references are the
  definition, the property, the convenience wrapper, and tests). **No later work wired
  it; no later work removed it.**
- Intake-level pronoun detection exists (`task_intake.py:422`) and can *ask* for
  clarification (`_CLARIFY_CUES["reference"]` `:428`) but **cannot resolve**.

**Conclusion:** the reference/context-understanding **capability exists**; the
**turn-flow exposure is missing**. Reproducible (C3.1/C4.1 pilots), production-relevant,
bounded (a fixed phrase→state mapping, no NLP), deterministic, model-independent.

---

## 9. INTENT / AMBIGUITY ANALYSIS

| Behavior | Current | Deterministic? | C7-relevant? |
|---|---|---|---|
| Explicit intent | cue classification → handler | yes | solved |
| Implicit but bounded intent | partial (compound/negation handling; development-need detection) | yes | partially solved |
| Context across turns | `ConversationState` carries fields | yes | **state exists; references not applied** |
| References to prior turns | **not resolved in `send()`** | (resolver exists, unwired) | **yes — the gap** |
| Ambiguous requests | clarification (ACTION/DEVELOPMENT; pronoun detection) | yes | partially solved |
| Corrections | not a distinct deterministic path | — | C7-relevant but unbounded (no evidence) |
| Follow-up questions | fall to question/model; no context carry | yes/— | **yes — same root (references)** |
| Pronouns ("it/that/those") | detected, not resolved | yes | **yes** |
| Omitted subjects | not reconstructed | — | would need inference → speculative |
| Conversational continuation | state persists; not exploited for references | — | **yes** |

The recurring root cause is **unapplied reference/context resolution**; the other
items are either already solved or would require speculative inference/NLP.

---

## 10. HUMAN PROBLEM-SOLVING UNDERSTANDING

Existing deterministic mechanisms: problem framing via `TaskSpec`
(intent/goal/constraints/priorities/success criteria), missing-information detection
via ambiguity + `needs_clarification` (`task_intake.py:1102-1105`), decomposition via
planning/investigation, distinguishing facts from assumptions via investigation
evidence + validated knowledge, constraints/outcomes captured in the spec, uncertainty
via diagnostic confidence / fail-closed responses, and response adaptation via
deterministic templates. **What is genuinely missing** is carrying the *problem's
context across turns* — i.e. reference/context resolution — which is the same gap.

No separate "generic human psychology engine" is evidenced or needed.

---

## 11. MODEL-INDEPENDENCE

**PASS.** Every mechanism in §5/§9 is deterministic; the resolver is explicitly
model-free ("NEVER uses an LLM", `reference_resolution.py:11-12`). The candidate
exposure requires no Ollama/Qwen/llama.cpp/OpenAI/Anthropic endpoint, API key, or
network. Optional models remain injected/OFF.

---

## 12. HUMAN-SAFETY / BOUNDARY ANALYSIS

Reference/context resolution operates only on Atlas's **own** `ConversationState`
fields and the user's current message; it performs **no** profiling, hidden inference,
sensitive-attribute inference, emotional inference, persuasion, or autonomous decisions
about the human. It is transparent (ambiguity → explicit clarification). No evidence in
the repository touches manipulation/personality/surveillance areas. The candidate is
**plainly in-scope for C7** and safely bounded.

---

## 13. REAL-WORLD CAPABILITY EVIDENCE

Reproduced (C3.1/C4.1, real `Atlas.chat`, failing AI, read-only):
- Turn 2 of a multi-turn session: *"Based on that investigation, which component should
  I review first?"* → classified `INVESTIGATION_REQUEST` and **re-investigated the
  literal question text** (context lost).
- *"What tests did you find for it?"* → `INFORMATION_REQUEST` → clarification question
  (the resolver's AMBIGUOUS contract, surfaced without state resolution).
- *"Which of those components…?"* → `QUESTION` → deterministic fallback.

**User-visible consequence:** a user who refers to their immediately preceding request
must restate context; Atlas can appear to "forget" the conversation within a session
even though `ConversationState` holds it.

---

## 14. GAP CLASSIFICATION

| Finding | Category |
|---|---|
| Conversational reference/context resolution not applied in the turn flow (GAP-C31-02) | **B — existing capability, bounded exposure missing** |
| Open-ended question answering without a model | **C — intentional (deterministic-first; would require an LLM)** |
| Conversational self-Q&A / capability conversation | **D — C5 boundary (not reopened)** |
| Implicit-subject reconstruction, corrections handling, personality/emotional inference | **F/E — speculative (no evidence; would need NLP/invention)** |
| Ranking/decision/scheduling of human goals | **E — C8/C9 territory** |
| Task intake, ambiguity/clarification, state carriage, problem framing, governed development | **G — no gap** |

---

## 15. CATEGORY-A GAPS

**NO CATEGORY-A GAP IDENTIFIED.** No missing *core* human-understanding capability is
evidenced. The material limitation is the **exposure** of an already-implemented
deterministic resolver (Category B).

---

## 16. C6/C8/C9 BOUNDARY

- **C6:** CLOSED — not reopened (no defect found; C6 consumption investigation closed it).
- **C8:** no autonomous action/implementation/authorization in C7.
- **C9:** no self-modification/continuous evolution in C7.
- The reference-resolution exposure is human-understanding (C7), not knowledge maturity,
  autonomy, or evolution.

---

## 17. TEST / REGRESSION EVIDENCE

`python -m pytest tests/test_conversation_service.py tests/test_conversation_task_intake.py tests/test_conversation_state.py tests/test_reference_resolution.py tests/test_p15_2_conversation_continuity.py tests/test_conversation_development_intake.py tests/test_conversation_orchestration.py tests/test_model_independence_p6.py -q`
→ **171 passed, 0 failed, 0 errors (exit 0)**.

Reference: C6.1 full suite 5906/0/0/2. No failure observed; nothing to classify.

---

## 18. DEFECT ANALYSIS

**No defect found.** C6 closed cleanly; the reference resolver behaves per its
documented contract; nothing regressed. GAP-C31-02 is a deferred exposure, not a
defect.

---

## 19. READ-ONLY INTEGRITY

- HEAD `f85de89` unchanged; no source/test/config/schema/persistence/governance/CLI/
  conversation/roadmap change; no staged files; no commit/reset/clean/stash; no
  deletion/rename. Only new artifact: this report.

---

## 20. RECOMMENDATION

**C. EXISTING CAPABILITY NEEDS BOUNDED EXPOSURE.**

**Proof the capability already exists (only exposure is missing):**
`ConversationReferenceResolver` (`reference_resolution.py:152-221`) is a deterministic,
side-effect-free, model-free resolver with a conservative contract; it is instantiated
(`conversation_service.py:267`) and exposed via `resolve_reference` (`:307-314`), and is
covered by `tests/test_reference_resolution.py` and `tests/test_p15_2_conversation_continuity.py`.
Rich context already exists in `ConversationState` (`conversation_state.py:32-121`), and
intake already detects ambiguous pronouns (`task_intake.py:422`). The **only** missing
piece is applying the resolver within the `send()` turn flow.

**Bounded exposure to be defined/authorized next (not implemented here):**
- Objective: let Atlas use its existing deterministic reference resolution so a bounded,
  reference-bearing user turn is understood against the current session's
  `ConversationState` instead of being treated as a fresh literal request.
- Exact production surface: the `ConversationService.send()` dispatch (conversation).
- Existing machinery to reuse: `ConversationReferenceResolver`, `ConversationState`,
  the intake ambiguity/clarification cues.
- Deterministic contract: resolve only when `RESOLVED` to exactly one referent;
  `AMBIGUOUS` → existing clarification behavior; `UNRESOLVED` → current routing
  unchanged (fail-closed; never guess).
- Non-goals: no NLP/NLU, no external model, no semantic search, no profiling/emotional/
  personality inference, no C6/C8/C9 work, no legacy-routing changes for non-reference
  inputs, no new persistence/schema.
- Model-independence: resolver is model-free.
- Acceptance direction (future): a bounded reference-bearing follow-up is resolved to the
  prior referent deterministically; ambiguous/unresolved inputs preserve today's behavior;
  provenance/state unchanged; focused conversation tests + a real `Atlas.chat` pilot.
- Safety: transparent, user-benefiting, operates only on Atlas's own state; ambiguity →
  explicit clarification.

This report **does not** authorize implementation and does **not** create "C7.1".

---

## 21. REMAINING QUESTIONS

- Should the bounded exposure include only resolver wiring, or also coordinating the
  intake pronoun-ambiguity path (which currently only clarifies)?
- The resolver's phrase set is fixed; is that sufficient for the demonstrated failures,
  or is a bounded extension required (and, if so, is it still evidence-backed)?
- Ownership/placement (conversation layer) and whether the exposure changes any existing
  routing contract for non-reference inputs.
- Whether to treat conversational self-Q&A (C5 boundary) as a separate later C7 concern
  rather than bundling it.
