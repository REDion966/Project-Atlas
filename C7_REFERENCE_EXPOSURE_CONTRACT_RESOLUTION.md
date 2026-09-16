# PROJECT ATLAS — C7 REFERENCE/CONTEXT RESOLUTION — CONTRACT RESOLUTION

Mode: READ-ONLY investigation (no code/test/config/schema/governance/CLI/conversation/roadmap changes)
Permitted artifact: this file only.

---

## 1. STATUS

**A bounded resolver refinement is REQUIRED before exposure.** D1/D2/D3 are resolved
from repository evidence: **(D1)** the existing resolver's **substring** matching
produces demonstrable false positives inside ordinary words, so a small word-boundary
matching refinement is required before it can be safely invoked in the turn flow;
**(D2)** no new patterns are needed — existing multi-word patterns suffice for a bounded
first scope, and the unsupported examples are out of scope; **(D3)** post-resolution
semantics can reuse the existing single routing cascade (structured TaskSpec/target
context), with AMBIGUOUS→clarification and UNRESOLVED/no-reference unchanged.
Recommendation **B — BOUNDED RESOLVER EXTENSION REQUIRED BEFORE EXPOSURE**.

---

## 2. BASELINE

- Branch `main`; HEAD `f85de896e338e4fa6cdd83b03a61d7e43dfe1ff2` (`f85de89`) — verified.
- Working tree: pre-existing modified/untracked files (C3–C6 artifacts + C4.2/C5.1/C6.1
  source+tests); no staged/deleted/renamed files.
- Verification (this investigation): 125 relevant tests passed (§22) + a read-only probe
  of the resolver (§5).

---

## 3. EVIDENCE BASIS

`C7_READINESS_INVESTIGATION.md` (GAP-C31-02 = Category B; resolver exists, unwired;
Option A minimal) and `C7_REFERENCE_EXPOSURE_SCOPE_INVESTIGATION.md` (D1–D3 unresolved;
non-reference turns must be unchanged; AMBIGUOUS never guesses; UNRESOLVED fails closed;
multi-reference out of scope). No contradiction found.

---

## 4. D1 DETECTION CONTRACT

**Resolution:** the resolver must be invoked **only when a bounded, explicitly
recognized reference form is present**, and — critically — the resolver's own matching
must be **word-boundary-correct** before it is invoked. A pre-detection guard alone is
insufficient because the resolver matches its **first** pattern by **substring**, which
can differ from the detected cue (e.g., a text whose cue is `"that investigation"` also
contains `"again"` inside `"against"`, and the resolver would match the *action* pattern
first). Therefore the smallest safe D1 is a **resolver matching refinement** (word
boundaries, order preserved), combined with an invocation guard restricted to the
resolver's **multi-word** reference phrases.

Options evaluated: (A) TaskIntake pronoun detection — **insufficient** (it only scores
ambiguity and is word-boundary, but does not gate the resolver's first-match/substring
problem); (B) a bounded word-boundary detector in ConversationService — **necessary but
not sufficient** alone (does not fix the resolver's internal substring first-match);
(C) safe post-detection resolver behavior — **requires the refinement**; (D) other
existing mechanism — none found. No new general-purpose NLP detector is proposed.

---

## 5. D1 FALSE-POSITIVE ANALYSIS

Empirical probe (`ConversationReferenceResolver().resolve(text, state)`), state with all
common fields set:

| Input | Resolver status | resolved_field / value | Expected | Verdict |
|---|---|---|---|---|
| "Based on that investigation, what should I do next?" | resolved | `current_investigation` = "Investigate the conversation subsystem" | RESOLVED(investigation) | ✅ correct |
| "What did you find for it?" | ambiguous | candidates `[current_investigation, latest_result]` | AMBIGUOUS | ✅ correct |
| "What is the priority of the release?" | **resolved** | `current_task` ("it" inside "prior**it**y") | UNRESOLVED | ❌ **false positive** |
| "Is the architecture documented?" | **resolved** | `current_task` ("it" inside "arch**it**ecture") | UNRESOLVED | ❌ false positive |
| "How is the quality of the output?" | **resolved** | `current_task` ("it" inside "qual**it**y") | UNRESOLVED | ❌ false positive |
| "Please summarise the repository structure." | **resolved** | `current_task` ("it" inside "repos**it**ory") | UNRESOLVED | ❌ false positive |
| "We voted against the rule." | **ambiguous** | `[current_task, relevant_prior_action]` ("again" inside "ag**ain**st") | UNRESOLVED | ❌ false positive |
| "Which of those components depend on it?" | **resolved** | `current_task` | UNRESOLVED/unsupported | ❌ wrong (out of scope) |
| "What about this result?" | resolved | `current_subject` (not `latest_result`) | RESOLVED(result) | ⚠ semantic mismatch |
| "Which result was that?" | resolved | `current_subject` | RESOLVED(result) | ⚠ semantic mismatch |
| "What does Atlas do?" | unresolved | — | UNRESOLVED | ✅ |
| "Nothing to report." | unresolved | — | UNRESOLVED | ✅ |
| "Fix them." | unresolved | — | UNRESOLVED | ✅ (unsupported) |
| With an **empty** state, all positives | unresolved | — | UNRESOLVED | ✅ safe |

**Conclusion:** universal invocation is unsafe — ordinary technical turns would be
re-targeted. The false positives come from **substring** matching of single-word
triggers (`it`, `again`, `this`, `that`). The smallest safe contract is word-boundary
matching (refinement) + multi-word-only invocation for the first exposure.

---

## 6. D2 PATTERN COVERAGE

| Validated example | Existing pattern | Resolution result | Gap? | Action |
|---|---|---|---|---|
| "that investigation" (C3.1 t3) | `this/that/the investigation` → `current_investigation` | RESOLVED | none | in scope |
| "the investigation" | same | RESOLVED | none | in scope |
| "that result" / "the result" | `that result/the result/the findings` → `latest_result` | RESOLVED | none | in scope |
| "the findings" | → `latest_result` | RESOLVED | none | in scope |
| "what did you find?" | findings pattern → (`current_investigation`,`latest_result`) | AMBIGUOUS | none | in scope (clarifies) |
| "What did you find for it?" | findings pattern (substring) | AMBIGUOUS | none | in scope (clarifies) |
| "What tests did you find for it?" (C3.1 t4) | none (`"what did you find"` not a substring) → `it`→`current_task` | UNRESOLVED (likely) | unsupported | **out of scope** |
| "this result" | none → `this`→`current_subject` | RESOLVED(subject) | semantic mismatch | **excluded by multi-word-only rule** |
| "those components" (C3.1 t2) | none; `"it"`→`current_task` | wrong | unsupported | **out of scope** (referent not in state) |
| "Compare those two reports" | none | unresolved | unsupported | **out of scope** (multi-reference) |

---

## 7. D2 EXTENSION DECISION

**Outcome A — existing patterns are sufficient for the bounded first exposure. No pattern
extension is proposed.** The in-scope vocabulary is the resolver's existing **multi-word**
phrases mapping to existing `ConversationState` fields: investigation
(`this/that/the investigation` → `current_investigation`), result
(`that result/the result/the findings` → `latest_result`), findings
(`what did you find` → ambiguous `current_investigation`/`latest_result`). Unsupported
examples are explicitly out of scope because their referents (investigation components,
repository targets) are **not in `ConversationState`**; extending patterns would require
new state/semantic inference and is therefore rejected. No NLP/NLU, no external AI.

---

## 8. D3 POST-RESOLUTION SEMANTICS

**Resolution:** on `RESOLVED`, the referent is supplied as the turn's **structured
routing context/target** — i.e., the existing `TaskSpec` target field (`goal`, and the
investigation target) is set to the referent value **before** the single existing routing
cascade, with the original user text preserved (§11 option D "alter the TaskSpec before
normal routing"; §10 option C "replace only a structured TaskSpec field"). Classification
is unchanged; routing runs **once**. No new handler, no second cascade, no textual
rewriting, no persistence.

Semantics table:

| Resolver status | Action |
|---|---|
| RESOLVED | use referent as the turn's structured context/target for the same classification (single cascade) |
| AMBIGUOUS | existing clarification (`task_intake` `_CLARIFY_CUES["reference"]`); never guess |
| UNRESOLVED | routing **unchanged** (fail closed) |
| no reference | behavior **byte-identical** to today |

**Honest limitation:** this preserves context (e.g., re-routes an investigation follow-up
to the referenced subject instead of the literal meta-question) but does **not** create a
new answering surface. Follow-ups whose value requires a *synthesis answer* ("what should
I do next") are only partially served — see §10.

---

## 9. CONCRETE FOLLOW-UP TRACES

**Example 1** — Turn N: investigation; Turn N+1: "Based on that investigation, what should I do next?"
- detected: multi-word `"that investigation"`; resolved referent: `current_investigation` value.
- resulting intent: unchanged classification (`INVESTIGATION_REQUEST`); with D3 the effective target becomes the referenced subject (no literal re-investigation).
- existing handler: `_maybe_handle_investigation_request`. Answerable *fully*? No — it re-investigates; a synthesis answer would need the C3.3 report surface (§10). **Partial.**

**Example 2** — Turn N: investigation result; Turn N+1: "What did you find for it?"
- detected: `"what did you find"` (multi-word); resolved: **AMBIGUOUS** → existing clarification. The existing architecture answers via clarification (governed, never guesses). **Supported (clarification).**

**Example 3** — Turn N: repository impact result; Turn N+1: "Which of those components depend on it?"
- `ConversationState` does **not** contain the impact/dependent components; resolver does not cover `those components`; the `it` substring resolves to `current_task` (usually None). **Outside first exposure** (no structured referent).

**Example 4** — Turn N: development conversation; Turn N+1: "What about that plan?"
- `"that plan"` is not a pattern; `"that"` → `current_subject` (often None) → UNRESOLVED → unchanged. No existing DevelopmentNeed/TaskSpec mechanism consumes a referent safely here. **Outside first exposure.**

---

## 10. C3.3 SYNTHESIS BOUNDARY

- `_maybe_handle_report` (`conversation_service.py:2467`) requires a session/OWNER, then: if `state.evolution_proposal_id` is unset **and** `ConversationService._last_investigation_report` is retained, it returns the **C3.3 investigation synthesis** (`_handle_investigation_report`).
- Therefore an **existing** answering surface exists, but it is reached only through `REPORT_REQUEST` cues (`"final report"`, etc.). "What should I do next?" is **not** a report cue, so reference resolution alone cannot reach the synthesis surface without adding cues → **beyond GAP-C31-02's bounded scope**.
- Reuse of C3.3 is **possible but not via reference resolution as-is**; it would require routing/classification changes (a larger change, §19-C). C3.3 semantics are unchanged and must not be.

---

## 11. REFERENCE REWRITING DECISION

**Rejected: textual rewriting (A).** Rewriting the user message risks hidden behavior and
loss of original intent. **Chosen: (C) replace a structured `TaskSpec` field** (target/goal)
— preserves the original message, keeps routing single-pass, and uses existing structured
architecture (§10-C, §11-D). Options (B) attach-only and (D) another representation are
rejected because no existing consumer reads attached context (verified: handlers use
`original_text`/`spec.goal`, not an unused context field), so they would produce no
behavior change.

---

## 12. ROUTING RE-ENTRY DECISION

**Chosen: (D) alter the TaskSpec before normal routing** (single cascade). A second
routing cascade (B), direct handler call (C), or post-routing re-entry (A) are rejected:
there is no established two-pass pattern, and a second pass would risk duplicate
execution/state mutation/AI invocation. Exactly one cascade; no duplicate handler run.

---

## 13. AMBIGUOUS SEMANTICS

**Reused unchanged.** `AMBIGUOUS → clarification, never guess` (resolver contract
`reference_resolution.py:9`). The existing intake clarification (`_CLARIFY_CUES["reference"]`)
can express it; no modification is proposed. (A detected `AMBIGUOUS` is surfaced as a
clarification rather than acted upon.)

---

## 14. UNRESOLVED SEMANTICS

**Fail closed: routing unchanged.** Verified empirically: with an empty state every
positive reference is `UNRESOLVED`, and fields that are `None` are simply not candidates
(`reference_resolution.py:191-197`). No candidate / `None` field / empty state / reset
context → **no action**. No new behavior invented; no clarification forced.

---

## 15. TASK INTAKE RELATIONSHIP

**Resolution: (A) remain unchanged; (B) coordinate only via ordering.** TaskIntake's
`_AMBIGUOUS_PRONOUN_RE` (`task_intake.py:422`) is word-boundary and feeds
`needs_clarification` (ACTION/DEVELOPMENT only, `:1102-1105`). Reference resolution runs in
`ConversationService` **after** intake and **before** routing; both may act on a pronoun
turn: intake may request clarification, and resolution may resolve/leave unresolved. The
minimal deterministic ordering rule: **if intake already requires clarification, routing
takes that path unchanged; reference resolution is applied only when the turn is being
routed normally** (i.e., it acts on the resolved result, or falls through unchanged).
TaskIntake is not modified.

---

## 16. GOVERNANCE

Reference resolution is **interpretation only** and MUST NEVER authorize, approve,
execute, mutate repository state, promote, bypass governance, change permissions, or
invoke autonomous behavior. The resolver is side-effect-free
(`reference_resolution.py:19-20`); D3 only alters the routing target for the same
classification. No governance boundary changes.

---

## 17. MODEL-INDEPENDENCE

**PASS.** The resolver is pure/deterministic with no LLM, network, API key, endpoint,
embeddings, or model fallback. D1–D3 operate with the AI/model layer fully unavailable.

---

## 18. NON-REFERENCE REGRESSION CONTRACT

For messages with **no recognized reference** (multi-word phrase absent, or resolver
`UNRESOLVED`): `send()` must behave exactly as today — same routing, same `TaskSpec`,
same response, no hidden state, no resolver side effects, no extra AI calls. Verification:
(i) the invocation guard means the resolver result is only *acted on* for `RESOLVED`; the
guard is word-boundary multi-word only, so ordinary turns (including the false-positive
set in §5) never trigger it; (ii) existing conversation tests must remain green; (iii) a
new regression test asserts byte-identical behavior for non-reference turns.

---

## 19. FINAL ARCHITECTURAL DECISION

**B. BOUNDED RESOLVER EXTENSION REQUIRED BEFORE EXPOSURE.**

D1 cannot be satisfied with the resolver unchanged: its substring first-match produces
demonstrable false positives (priorit**it**y, arch**it**ecture, qual**it**y,
repos**it**ory, ag**ain**st). A bounded refinement — **word-boundary matching**, order and
patterns unchanged — is required before invocation is safe. D2 needs no extension
(existing multi-word patterns suffice for the bounded scope; unsupported examples are out
of scope). D3 is resolved (structured target via the single existing cascade).

Option A (already valid) is **not** selected because D1 is not satisfiable without the
refinement; option C (larger change) is **not** selected because D3 is bounded (the
partial-value limitation is documented, not a blocker).

---

## 20. MINIMUM RESOLVER EXTENSION (per option B)

- **File:** `atlas/conversation/reference_resolution.py` only (plus the eventual service
  integration in a later step).
- **Change:** match each pattern phrase as a **word-boundary** occurrence
  (e.g., precompiled anchored regexes) instead of `phrase in normalized`, preserving the
  existing pattern list, order, candidate fields, and the RESOLVED/UNRESOLVED/AMBIGUOUS
  semantics. No new patterns. No change to `ConversationState`, no persistence, no model.
- **Evidence:** §5 false-positive matrix (substring matches inside ordinary words).
- **Expected effect:** the §5 negatives become `UNRESOLVED`; positives (`that
  investigation`, `what did you find`) remain `RESOLVED`/`AMBIGUOUS`.
- **Ambiguity behavior:** unchanged (still AMBIGUOUS → clarification).
- **Risk:** existing `test_reference_resolution.py` must remain green; word-boundary
  matching may make some currently-matching substrings (e.g., `continue` inside
  `continued`) stop matching — acceptable and intended.
- Not implemented here.

---

## 21. ACCEPTANCE CRITERIA

1. No-reference turns unchanged (byte/behaviour-identical).
2. Reference detection has no known substring false positives (the §5 negatives → UNRESOLVED).
3. Supported references resolve deterministically.
4. Exact referent preserved.
5. Ambiguous references never guess.
6. Unresolved references fail closed.
7. Existing clarification remains governed/unchanged.
8. Existing routing reused (single cascade).
9. No second routing cascade.
10. No duplicate handler execution.
11. No unintended state mutation.
12. Zero external AI calls.
13. Deterministic repeated output.
14. Existing resolver tests pass (incl. after the refinement).
15. Existing conversation tests pass.
16. Real C3/C4 follow-up evidence improves only where the contract supports it.
17. Unsupported multi-/plural-reference cases remain unsupported.
18. Governance unchanged.

---

## 22. TEST STRATEGY (future)

Extend/reuse: `tests/test_reference_resolution.py` (add word-boundary false-positive cases,
preserve existing contract cases), `tests/test_conversation_service.py` /
`tests/test_p15_2_conversation_continuity.py` (`send()` resolved/ambiguous/unresolved,
multi-turn), `tests/test_conversation_task_intake.py` (non-reference regression),
`tests/test_conversation_state.py`, `tests/test_model_independence_p6.py`. New focused
tests: detection guard, resolved reference through `send()`, ambiguous → clarification,
unresolved → unchanged, no-reference regression, determinism, 0 AI calls. No test changes
now. Current relevant run: **125 passed**.

---

## 23. REAL-WORLD VALIDATION (future)

Real kernel, real `send()`, real state, real resolver, temp storage, failing-AI double:

| Case | Initial turn | Follow-up | Expected |
|---|---|---|---|
| A | investigate X | "Based on that investigation, what should I do next?" | RESOLVED(current_investigation); single cascade; context preserved; 0 AI calls |
| B | investigate X | "What did you find for it?" | AMBIGUOUS → clarification; 0 AI calls |
| C | investigate X | "Which of those components depend on it?" | UNSUPPORTED → unchanged (documented) |
| D | any | ambiguous reference | clarification, never guess |
| E | any | unresolved reference / empty state | routing unchanged |
| F | non-reference question | — | byte-identical behavior |
| G | plural/multi-reference | — | unsupported/unchanged |

Record classification, resolution status, routing path, response class, AI call count
(0), state mutation (none), deterministic repeatability. Plan only.

---

## 24. C7/C8/C9 BOUNDARY

References/continuity only. Not C5 (capability model), C6 (knowledge/learning), C8
(autonomy), C9 (evolution); no personality/emotion/profiling/implicit-state
inference/general NLP/semantic understanding.

---

## 25. REMAINING QUESTIONS

- Should the word-boundary refinement also restrict/drop the single-word triggers
  (`it`, `this`, `that`) for the first exposure (safest), or keep them word-boundary-guarded?
- Whether the partial-value limitation (context-preserving re-routing vs. a synthesis
  answer) is acceptable for the first exposure, or whether routing to the existing C3.3
  report surface is later authorized as a separate bounded step.
- Whether intake's clarification path and the resolver should share one clarification
  message (currently intake owns it).

---

## 26. RECOMMENDATION

**B. BOUNDED RESOLVER EXTENSION REQUIRED BEFORE EXPOSURE.**

D1 is resolved to "invoke only on bounded recognized forms" **and** "make the resolver's
matching word-boundary-correct" (substring false positives demonstrated, §5). D2 is
resolved to "no extension" (existing multi-word patterns; unsupported examples out of
scope). D3 is resolved to "structured TaskSpec/target context within the single existing
cascade" (§8/§11/§12). Because the small resolver refinement is a prerequisite, the
exposure is **not yet ready** for implementation authorization; the refinement is defined
precisely (§20) and must not be implemented in this command.

No implementation; no C7.1; no roadmap change.
