# PROJECT ATLAS — C7 BOUNDED EXPOSURE (REFERENCE/CONTEXT RESOLUTION) — SCOPE & CONTRACT INVESTIGATION

Mode: READ-ONLY investigation (no code/test/config/schema/governance/CLI/conversation/roadmap changes)
Permitted artifact: this file only.

---

## 1. STATUS

**GAP-C31-02 remains a Category-B exposure gap, but the exposure is NOT yet ready
for implementation.** The resolver is deterministic, model-independent, and
side-effect-free, and the integration point is clear; however three precise
contract decisions are unresolved (detection false-positives; referent scope;
post-resolution semantics), and the resolver's phrase set does **not** cover part of
the validated real-world evidence. Recommendation **C — ARCHITECTURAL DECISION STILL
UNRESOLVED**.

---

## 2. BASELINE

- Branch `main`; HEAD `f85de896e338e4fa6cdd83b03a61d7e43dfe1ff2` (`f85de89`) — verified.
- Working tree: pre-existing modified/untracked files (C3–C6 artifacts + C4.2/C5.1/C6.1
  source+tests); no staged/deleted/renamed files.
- Relevant verification (this investigation): **125 passed, 0 failed, 0 errors** (§20).

---

## 3. C7 EVIDENCE BASIS

`C7_READINESS_INVESTIGATION.md`: Category-B exposure gap (GAP-C31-02); the resolver is
implemented (`reference_resolution.py:152`), instantiated
(`conversation_service.py:267`), exposed (`resolve_reference:307-314`), tested
(`tests/test_reference_resolution.py`, `tests/test_p15_2_conversation_continuity.py`),
with a rich `ConversationState` — but **no call in `send()`**. Candidate behavior:
bounded deterministic resolution; RESOLVED→use referent; AMBIGUOUS→clarification;
UNRESOLVED→fail closed; never guess; no model. Nothing contradicts this.

---

## 4. EXISTING RESOLVER CONTRACT

Verified from `atlas/conversation/reference_resolution.py`:

- `ConversationReferenceResolver.resolve(query, state) -> ReferenceResolutionResult`
  (`:158`). `normalized = query.strip().lower()` (`:172`); **first** pattern whose any
  phrase is a **substring** (`phrase in normalized`) wins (`:177-181`).
- Patterns (`_REFERENCE_PATTERNS`, `:76-149`), longest-phrase-first ordering:
  1. `what you just found|what did you find|what you found` → `(current_investigation, latest_result)`
  2. `continue with that|continue` → `(current_task, current_investigation, development_intent)`
  3. `do that again|run it again|repeat that|again` → `(current_task, relevant_prior_action)`
  4. `this investigation|that investigation|the investigation` → `(current_investigation,)`
  5. `this topic|that topic|this issue|that issue|the problem` → `(current_subject,)`
  6. `this task|that task|the task` → `(current_task,)`
  7. `that result|the result|the findings` → `(latest_result,)`
  8. `that improvement|the development` → `(development_intent,)`
  9. `the question|my question` → `(pending_question,)`
  10. `that confirmation|the confirmation` → `(pending_confirmation,)`
  11. `it` → `(current_task,)`
  12. `this|that` → `(current_subject,)`
- Candidates = matched fields whose state value is non-None (`:191-193`);
  0→`UNRESOLVED` (`:195`), 1→`RESOLVED` (`:202`, value = the state value), >1→`AMBIGUOUS`
  (`:213`, candidates listed; never guesses). Statuses
  `RESOLVED|UNRESOLVED|AMBIGUOUS` (`:32`).
- Explicit support check: pronouns `it` (→`current_task`); words `this`/`that`
  (→`current_subject`); `those`/`them` are **NOT** in the resolver pattern set;
  `the component(s)` is **NOT** a pattern; `the investigation`/`that investigation`
  **are**; `the previous result` is **NOT** (only `that result`/`the result`); `the
  findings` **is** (→`latest_result`).
- Deterministic; side-effect free; **no LLM** ("NEVER uses an LLM", `:11-12`);
  no authorization/execution (`:19-20`).

---

## 5. CONVERSATION STATE CONTRACT

`ConversationState` (`conversation_state.py:32-121`, frozen/immutable) fields usable as
referents: `current_subject`, `current_task`, `current_investigation`,
`active_proposal_id`, `active_proposal_fingerprint`, `pending_approval_id`,
`evolution_proposal_id`, `recovery_proposal_id`, `recovery_approval_id`,
`development_intent`, `pending_question`, `pending_confirmation`, `latest_result`,
`relevant_prior_action`, `turn_id`, autonomy counters. `ConversationStateManager`
mutates immutably via `update` (`:190`), `begin_turn` (`:208`), `replace_topic` (`:217`),
`reset_field` (`:198`), `clear` (`:193`); `to_dict`/`from_dict` serialize (metadata
round-trips). **No persistence beyond conversation storage; no stale/invalidation
concept.**

Referents **not** present in state: the investigation **report/components** (C3.3 keeps
`ConversationService._last_investigation_report` as a conversation-scoped attribute,
not state), repository targets, capability results. So the resolver can operate
**entirely on existing state** — but only for the state-backed referents above.

---

## 6. TASK INTAKE CONTRACT

`task_intake.py`: cue-based `_classify` (`:871`); `_AMBIGUOUS_PRONOUN_RE =
\b(it|that|this|them|those)\b` (`:422`) is **word-boundary** and feeds ambiguity
scoring/clarification, not resolution; `_CLARIFY_CUES["reference"] =
"What does the ambiguous reference refer to?"` (`:428`); `needs_clarification` is set
only for ACTION/DEVELOPMENT with ambiguity ≥ 0.5 (`:1102-1105`). TaskIntake does **not**
read `ConversationState` (it receives `history_length` only). Therefore TaskIntake cannot
resolve references against state without a bounded modification.

---

## 7. ConversationService.send() FLOW

Order (verified): add user `Message` (`:359-366`) → `ContextManager.build` (`:368`) →
`self._intake(text, len(messages))` (`:383`) → attach session to spec (`:385`) → routing
cascade (`:388-506`): INVESTIGATION → APPROVAL/REJECTION → PLANNING → EXECUTION →
RECOVERY → VERIFICATION → REPORT → REPOSITORY_IMPACT → AUTONOMY L1–L5 → DEVELOPMENT →
development-need confirmation → orchestration (`:499`) → cognition+AI (`:508-570`) →
deterministic fallback → `add_message` → return.

**Safest insertion point:** in `ConversationService.send`, **after** intake and session
attach, **before** the routing cascade (`:386`), consulting the resolver once and using
its result only when `RESOLVED`/`AMBIGUOUS` — so non-reference turns are untouched
(no pattern / `UNRESOLVED` ⇒ routing unchanged).

---

## 8. REFERENCE DETECTION

Options: (A) every turn; (B) only when TaskIntake signals a reference; (C) only
explicitly recognized reference-bearing forms; (D) other.

Evidence: the resolver's single-word triggers (`it`, `this`, `that`) are **substring**
matches, not word-boundary — e.g. `"priority"` contains `it`, `"rather"` contains
`"that"`? (no) — so invoking the resolver universally risks **false positives** that
could re-target non-reference turns (violating "non-reference turns unchanged"). The
existing tests do not cover this (e.g. `test_reference_resolution.py` uses clean
sentences). Therefore detection must be **bounded**: prefer multi-word patterns only,
or word-boundary matched single-word triggers, before acting. This is **unresolved**
(decision D1) and is a bounded detection/refinement requirement.

---

## 9. RESOLUTION SEMANTICS

- **RESOLVED:** resolver yields exactly one referent (a state value, e.g. the
  investigation target string). *Passing it into routing* is the unresolved part
  (decision D3): option (i) use the referent as the effective target/context and let
  existing routing proceed (e.g. re-investigate the same target); option (ii) route to
  an existing *answering* surface (C3.3 investigation synthesis via the report path).
  The validated C3.1 failures wanted an **answer** ("which component should I review
  first"), which option (i) does not provide.
- **AMBIGUOUS:** → existing clarification (intake `_CLARIFY_CUES["reference"]`), never
  guess (`reference_resolution.py:9`). Governed and unchanged.
- **UNRESOLVED:** fail closed → **routing unchanged** (no new behavior invented).
- **NO REFERENCE:** unchanged (this is mandatory).

---

## 10. MULTI-REFERENCE ANALYSIS

The resolver returns a **single** first-match result; it cannot handle multiple
references in one turn ("Which of those components depend on it?", "Compare those two
reports"). These are **explicitly unsupported / out of the first bounded scope**
(they would require multi-referent resolution — not evidenced as required and not
bounded).

---

## 11. PHRASE/PATTERN SUFFICIENCY

Validated real-world examples vs the resolver's pattern set:

| Example (source) | Classification |
|---|---|
| "Based on that investigation, which component should I review first?" (C3.1 t3) | **SUPPORTED** — `"that investigation"` → `current_investigation` (but see D3 for what it causes) |
| "What did you find?" (C3.1/C5 docs) | **AMBIGUOUS by contract** (`current_investigation` + `latest_result`) → clarification |
| "That result" / "the findings" | **SUPPORTED** — → `latest_result` |
| "What tests did you find for it?" (C3.1 t4) | **PARTIALLY/UNSUPPORTED** — `"what did you find"` is not a substring; `"it"` → `current_task` (usually None in investigation flows) ⇒ UNRESOLVED |
| "Which of those components should I review first?" (C3.1 t2) | **UNSUPPORTED** — `those` is not in the resolver set; `those components` has no pattern |
| "What about that investigation and its tests?" | **UNSUPPORTED** (multi-reference) |

**Conclusion:** the phrase set covers some validated examples (investigation/result
references) but **not** the plural-demonstrative and pronoun-to-investigation cases.
Exposure alone would therefore fix only part of the evidence. Whether a bounded
extension is justified is one of the unresolved decisions (D2).

---

## 12. CONTEXT BOUNDARY

Resolvable today (state-backed): previous investigation **target**
(`current_investigation`), latest result (`latest_result`), current task
(`current_task`), subject (`current_subject`), development intent
(`development_intent`), pending question/confirmation, relevant prior action.
**Not resolvable:** investigation **components/report**, repository targets, capability
results (not in `ConversationState`). The first exposure must use only existing reliable
context — no new state/persistence.

---

## 13. STALENESS / INVALID CONTEXT

`ConversationState` has no stale/invalidation concept; it is a per-turn immutable
snapshot; `begin_turn` regenerates `turn_id`; `replace_topic` demotes `current_task` →
`relevant_prior_action` and clears/replaces subject/investigation. The resolver simply
reads current values, so a referent is valid iff its field is non-None. **No new
invalidation system should be introduced**; absence of a stale-context concept is
documented as a boundary (a referent that is None ⇒ `UNRESOLVED` ⇒ fail closed).

---

## 14. GOVERNANCE ANALYSIS

Reference resolution is **interpretation only**: it does not authorize, mutate,
approve, execute, bypass sandbox verification, promote plans, or create autonomous
behavior (`reference_resolution.py:19-20`; it is side-effect free). Wiring it before
routing does not alter any governance/authorization boundary — it only changes which
text/target routing sees.

---

## 15. MODEL-INDEPENDENCE

**PASS.** Resolver is pure/deterministic; no network, API key, endpoint, model call,
embeddings, or semantic model; no LLM fallback. The exposure operates with the AI/model
layer fully unavailable.

---

## 16. ARCHITECTURAL OPTIONS

| Option | Affected | Blast radius | Deterministic | Routing compat | Test cost | Regression risk | Governance | Model-indep. | Non-ref turns |
|---|---|---|---|---|---|---|---|---|---|
| **A** ConversationService invokes resolver before routing | `conversation_service.py` | reference-bearing turns only | yes | preserved | low | low | none | yes | unchanged |
| **B** TaskIntake resolves and returns a resolved TaskSpec | `task_intake.py` (+ state access) | classification layer + all callers | yes | **changes intake contract** | high | high | none | yes | could change |
| **C** TaskIntake exposes a bounded reference signal; service resolves | `task_intake.py` + service | classification+service | yes | moderate | medium | medium | none | yes | mostly unchanged |
| **D** New routing subsystem | new module | large | yes | **new routing system (forbidden)** | high | high | risk | yes | risk |

**Only Option A** keeps the change minimal, in the conversation layer, with non-reference
behavior preserved and no second routing system. **Recommended structurally:** A.

---

## 17. RECOMMENDED CONTRACT

**Option A (recommended architecture)**, conditioned on resolving D1–D3:

- In `ConversationService.send`, after intake/session attach and **before** the routing
  cascade, invoke the existing resolver **only when a bounded reference-bearing form is
  present** (word-boundary multi-word patterns; single-word triggers only if
  word-boundary-guarded).
- Act on `RESOLVED`/`AMBIGUOUS`; leave `UNRESOLVED`/no-reference turns **unchanged**.
- `AMBIGUOUS` → existing clarification; never guess.
- No NLP/NLU; no model; read-only; no new persistence; no governance change.

**Not ready to authorize:** D1 (detection contract to avoid substring false positives),
D2 (whether a bounded resolver pattern extension is justified for the unsupported
examples), D3 (what a `RESOLVED` reference *causes* — re-target routing vs an existing
answering surface such as the C3.3 investigation synthesis/report path).

---

## 18. NON-GOALS

General NLP/NLU; semantic reference resolution; embeddings; external model; plural/
multi-reference resolution; component-level referents not in state; new persistence/
schema; profiling/emotion/personality; C5/C6/C8/C9 work; a second routing system;
legacy behavior changes for non-reference turns.

---

## 19. ACCEPTANCE CRITERIA

1. Non-reference turns remain behaviourally unchanged.
2. Valid reference-bearing turns resolve deterministically.
3. Exactly-one-candidate → correct referent selected.
4. Ambiguous → never guess (clarification).
5. Unresolved → fail closed (routing unchanged).
6. Existing clarification behavior remains governed.
7. Existing routing remains intact.
8. No external AI calls.
9. No mutation.
10. No governance bypass.
11. Repeated identical inputs → identical results.
12. Existing reference-resolution tests remain passing.
13. Real-world failed follow-ups become successful **only where the resolver contract
    supports them** (explicitly not the unsupported examples).
14. Unsupported references remain explicitly unsupported rather than silently guessed.

---

## 20. TEST STRATEGY

Reuse/extend (do not modify now): `tests/test_reference_resolution.py` (direct
resolved/ambiguous/unresolved + determinism), `tests/test_p15_2_conversation_continuity.py`
(multi-turn context), `tests/test_conversation_service.py` (routing/no-reference
regression), `tests/test_conversation_task_intake.py`, `tests/test_conversation_state.py`,
`tests/test_model_independence_p6.py` (model independence). New focused tests would cover
only: resolved reference through `send()`, ambiguous → clarification, unresolved →
unchanged, no-reference regression, repeat determinism, no AI calls. Command run now:
`python -m pytest tests/test_reference_resolution.py tests/test_p15_2_conversation_continuity.py tests/test_conversation_service.py tests/test_conversation_task_intake.py tests/test_conversation_state.py -q` → **125 passed**.

---

## 21. REAL-WORLD VALIDATION PLAN

Future production validation (real kernel, real `send()`, real state, real resolver,
isolated temp storage, failing-AI double), **only for contract-supported scenarios**:

- A. Turn1 "Investigate the conversation subsystem." → Turn2 "Based on **that
  investigation**, what should I do next?" → expect `RESOLVED` (current_investigation);
  routing/response class per resolved decision D3; AI calls 0; deterministic repeat.
- B. "What did you find?" → expect `AMBIGUOUS` → clarification (never guess).
- C. "Which of those components depend on it?" → expect **UNSUPPORTED → unchanged**
  (documented, not guessed).
- Ambiguous + unresolved cases → fail closed; determinism check; AI calls 0.

*(Recorded as a plan only; not executed.)*

---

## 22. C7/C8/C9 BOUNDARY

This bounded exposure is human-understanding of **references/continuity only**. It is not
C5 (capability model), C6 (knowledge/learning), C8 (autonomy), or C9 (evolution), and it
does not include personality/emotion/profiling/implicit human-state inference/general
NLP/semantic understanding.

---

## 23. GAP STATUS

GAP-C31-02 **remains a Category-B exposure gap**. It does **not** become a bounded C7
implementation candidate yet: (a) a bounded **detection/resolver refinement** is required
(D1, and possibly D2), and (b) the **referent-scope** and **post-resolution semantics**
must be decided (D3). It is **not** already satisfied and **not** blocked by a defect.

---

## 24. REMAINING QUESTIONS

- **D1 — Detection contract:** act only on word-boundary multi-word patterns, or also
  word-boundary-guarded single-word triggers? (Avoids substring false positives such as
  `it` inside `priority`.)
- **D2 — Pattern sufficiency:** is a bounded, evidence-backed extension required for the
  unsupported validated examples ("those components", pronoun→investigation), or are they
  explicitly out of scope?
- **D3 — Post-resolution semantics:** what should a `RESOLVED` reference *cause* — use the
  referent as the routing target, or route to an existing answering surface (C3.3
  investigation synthesis/report)? The validated failures wanted an answer, which
  re-targeting alone does not provide.
- Should the intake pronoun-ambiguity path be coordinated with the resolver (it currently
  only clarifies)?

---

## 25. RECOMMENDATION

**C. ARCHITECTURAL DECISION STILL UNRESOLVED.**

The capability exists and Option A is the recommended, minimal architecture, but the
exposure cannot be safely authorized until **D1** (bounded detection to prevent substring
false positives on non-reference turns), **D2** (whether a bounded resolver pattern
extension is required for the validated-but-unsupported examples), and **D3** (what a
resolved reference causes — re-target vs an answering surface) are decided. This report
does not implement anything, does not create "C7.1", and does not modify the roadmap.
