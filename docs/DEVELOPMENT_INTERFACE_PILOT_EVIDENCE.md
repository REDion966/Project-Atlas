# Development-Interface Real-World Pilot — Evidence Record

**Type:** real-world evidence pilot (additive; NOT a new roadmap phase, no new
architecture). Deterministic and model-OFF; the real `ConversationService`
conversation/development path was exercised end-to-end.
**Baseline:** C4 commit `e055db1e5d596d3bfad4b8ae21b23a23805b5346f`
(`feat(conversation): close C4 evidence-driven investigation vocabulary`).

**Question.** After C4, can Atlas's existing conversational/development system
function as a practical interface for Atlas development requests, and what
genuine capability gaps remain? This pilot does NOT attempt to complete that
long-term objective; it measures the CURRENT system.

---

## 1. Scope and method

A compact, deterministic corpus of 24 realistic developer utterances was sent
through the real `ConversationService.send` path (real intake, real development
intake, real investigation surface), grouped by intent:

| Family | Cases |
|---|---|
| A — Self-understanding | "How is Atlas's conversation system structured?", "What handles development requests?", "Where is the approval boundary?", "How does Atlas verify a proposed change?" |
| B — Investigation | "Take a look at the storage layer.", "Investigate how Atlas handles development requests.", "Look into why this subsystem behaves this way.", "Review the relevant implementation and tell me what you find." |
| C — Development requests | "Add a small deterministic test for this behavior.", "Fix this specific documented bug.", "Improve this existing behavior while preserving the current contract.", "Investigate this issue and propose the smallest safe change." |
| D — Development follow-up | "What did you find?", "What would you change?", "Why is that the safest approach?", "Go ahead with that change.", "Verify it.", "What changed?" |
| E — Repair / correction | "No, that's not what I meant…", "I was asking about the implementation, not the documentation.", "Don't change anything yet; just investigate it." |
| F — Safety / governance | "Investigate … but do not modify anything.", "Approve the pending proposal.", "Just analyze it, don't change anything." |
| G — Compound realistic | "Investigate the conversation system, explain the problem, and propose a fix without executing it." |

---

## 2. Results (model-OFF)

**Investigation (B) and governance (F):** all correctly understood and routed to
the EXISTING read-only investigation; no approval was created; no modification
occurred. "Approve the pending proposal." with no session correctly failed closed
("No active session. Approval requires an authenticated session.").

**Result grounding (D):** "What did you find?" returned the most recent recorded
investigation result; "What would you change?" returned the recorded result
rather than inventing one; "Go ahead with that change." reported the active
investigation instead of acting. No fabricated results were observed anywhere.

**Self-understanding (A):** answered where the existing deterministic
self-knowledge surfaces cover the question (status, approval boundary); declined
honestly where they do not ("What handles development requests?" → out of
scope; "How does Atlas verify a proposed change?" → no recorded result, no
invention).

**Development requests (C) — the one genuine gap.** Before this pilot,
"Add a small deterministic test for this behavior.", "Fix this specific
documented bug." and "Improve this existing behavior while preserving the
current contract." were classified `CONVERSATION` and answered with the
unsupported-floor notice, even though every other governed development surface
existed. Cause: the intake's development gate required an explicit **self-target**
(`atlas`, `yourself`, `a module`, `a capability`, `the framework`, or the literal
words `capability`/`module`) in addition to the development cue. A developer
speaking *to* Atlas routinely names a code/test/repository work object instead
("a test", "the bug", "the code", "the repository"), so the request never entered
the governed development path.

**Zero provider calls** were made for every deterministic case
(`external_providers = false`).

---

## 3. Change implemented (minimal, deterministic, evidence-backed)

One bounded intake change in `atlas/conversation/task_intake.py`: a
whole-word `_DEVELOPMENT_CODE_TARGETS` set (`test(s)`, `code`, `bug`,
`implementation`, `repository`, `repo`, `documentation`, `readme`, `docstring`,
`unit test`) now qualifies a development request exactly as a self-target does.
The gate is **not** removed: a development cue is still required, negation still
wins ("Don't fix anything yet." is still not a development request), and a bare
noun mention is still not enough. No new route, handler, state, authority,
model, dependency, or architecture was introduced — the requests now reach the
EXISTING governed development path, which already fails closed into bounded
clarification when under-specified.

Verified end-to-end: a code-target request is recognised as a development
request, is clarified when under-specified (no executable need, no approval
created), and an explicit self-target request behaves exactly as before.

---

## 4. Failure classification

- **Correctly understood and routed:** investigation, result recall, approval
  fail-closed, compound investigate-and-propose-without-executing.
- **Correctly understood, intentionally bounded / fail-closed:** under-specified
  development requests (clarified), unsupported self-knowledge questions
  (declined honestly), causal follow-ups without evidence.
- **Genuine capability gap (fixed):** development requests naming a code/test/
  repository target — see §3.
- **Pre-existing, unrelated (unchanged):** the two
  `tests/test_c3_real_world_capability_evidence.py` prose-contract failures
  (comparison wording, architecture-step report), the acknowledgement-surface
  failures in `tests/test_l10_evidence_driven_expansion.py`, and the previously
  documented unrelated failures. None were introduced by this pilot; none were
  fixed here.

---

## 5. Conclusion

Within the tested scope, the EXISTING C2/C3/C4 conversation and governed
development path is sufficient as a practical interface for Atlas development
requests once a code/test/repository work target is recognised as a development
target. No new architecture, planning system, agent, or model capability is
required or justified by this evidence. Further development remains
evidence-driven.

---

## 6. Post-pilot addition — live interaction trial: capability-detail routing gap

A subsequent **live interactive trial** through the documented human entry point
(`python main.py`), model-OFF, produced a reproducible natural-language routing
mismatch. Recorded here as a subsequent evidence-driven change; the sections
above are preserved as originally written.

### Observed

| Input | Observed result (before) |
|---|---|
| "What does the investigation capability do?" | **correct** — existing capability detail |
| "Explain the investigation capability." | **wrong** — repository investigation + development proposal |
| "Can you tell me more about the investigation capability?" | **wrong** — repository investigation + development proposal |
| "Explain the investigation capability. What can it do, what can it not do, and how does it work?" | **wrong** — first clause routed to repository investigation; the remaining questions unanswered |
| "Can you explain those 24 capabilities in a way I can understand?" | **wrong** — declined as out of scope (separate contextual-reference limitation) |

### Root cause (read from the implementation)

`BuiltinResponseService._match_capability_detail` resolves a named capability
through bounded regexes in `atlas/conversation/builtin_response.py`. The detail
question accepted the qualifier ("capability"/"tool") only **BEFORE** the name
(`(?:the )?(capability|tool) `), so "explain the investigation capability"
captured the name as `the investigation capability`, which resolved to nothing.
The unresolved name made the turn fall through to the investigation surface. A
second, narrower gap: `tell me more about` was absent from the verb list (only
`tell me about` was present). The "what does X do?" form worked because
`_CAPABILITY_DETAIL_DO_RE` has its own, correct trailing-qualifier handling.

### Correction

One bounded deterministic change in `atlas/conversation/builtin_response.py`:
a new `_CAPABILITY_DETAIL_TRAILING_RE` (same verb vocabulary, qualifier AFTER
the name, qualifier excluded from the capture) is tried FIRST, and
`tell me more about` was added to the shared verb group. The original
`_CAPABILITY_DETAIL_RE` and `_CAPABILITY_DETAIL_DO_RE` are otherwise unchanged,
so every form they already accepted keeps its exact previous behaviour. An
unresolvable name still declines (fail-closed) exactly as before.

### Verification (model-OFF, real kernel)

Capability-detail positives now answer with the capability detail; the genuine
investigation controls ("Investigate the storage layer.", "Investigate the
conversation system.", "Investigate the memory service but do not modify
anything.", "Investigate the investigation capability implementation.") still
route to repository investigation; no approval or development proposal is
created by an informational question. Focused suites: 99 passed
(`test_builtin_self_knowledge.py`) and the investigation/conversation regression
set passed (exit 0).

### Separately unresolved (left unchanged)

"Can you explain those 24 capabilities in a way I can understand?" is a distinct
**contextual-reference** limitation: "those 24 capabilities" must be resolved
against the immediately preceding capability inventory. It is not the same
defect (the capability-detail surface is never reached), and resolving it would
require broader discourse/context machinery than this bounded routing
correction. It is recorded as an observed gap only and was deliberately NOT
changed.

---

## 7. Post-pilot addition — live trial: compound development-request intake gap

A further live REPL trial issued a genuine self-directed development request:

> "I want you to add a small deterministic regression test for the
> capability-explanation behavior we just discussed. First investigate the
> relevant implementation and existing tests, then explain what you would change
> and why. Do not modify anything yet."

Atlas answered with a repository-investigation report over the malformed subject
`"want add small deterministic regression test capability explanation behavior
just"`, then a development proposal.

### Root cause (two bounded deterministic defects)

1. **Negation scope.** `TaskIntake` decided development per *utterance*: a single
   negated cue cancelled the whole request. "Add a deterministic test. Do not
   modify anything yet." carries an un-negated `add` and a negated `modify`, so
   the request was cancelled and fell to the unsupported floor — even though the
   existing stance surface had already recorded `no_modification` correctly.
   Corrected to per-cue: a request is negated only when EVERY development cue
   it carries is negated, so existing negatives ("don't fix anything yet") are
   unchanged.
2. **Precedence.** The investigation branch was evaluated BEFORE the development
   evidence, so any turn also carrying an investigation cue ("Add a test. First
   investigate the implementation.") was claimed as `INVESTIGATION_REQUEST` and
   the development request was lost. The existing L3 rule (an explicitly
   development-framed request is development) now applies before the
   investigation/planning checks. An investigation-FIRST compound
   ("Investigate the conversation system, create a development proposal, and
   present it for my approval") is still investigation.

The malformed subject is a *consequence* of (2): once the investigation route
claims the turn, `_extract_objective` returns everything from the earliest cue
onward and the route strips stop-words. It is not an independent defect.

**Contextual reference is NOT involved.** The single-sentence form
("I want you to add a test for the capability-explanation behavior we just
discussed.") already routed as `DEVELOPMENT_REQUEST` before any change, so
"we just discussed" was never the cause and no discourse/memory machinery was
added or required.

### Correction

`atlas/conversation/task_intake.py` only: a `_word_cue_present` helper, the
per-cue negation rule, and the development decision moved ahead of the
investigation/planning checks (its duplicate later evaluation removed). No new
module, classifier, router, state, memory or authority.

### Verification

Intake-level: the original request and 12 controlled variants/negatives all
classify correctly, including the plain-investigation and
investigation-first-compound controls. Focused suites: 102 passed
(`test_conversation_development_intake.py`, `test_conversation_task_intake.py`);
broader conversation/intake regressions 327 passed with only the 3
already-documented pre-existing acknowledgement-surface failures (re-verified
against a pristine HEAD extraction).

### Residual — since CORRECTED (the original diagnosis was wrong)

The earlier note here blamed `ConversationService._maybe_handle_multi_intent` and
recorded the behaviour as an unfixable limitation. Tracing the real `send`
cascade disproves that: `_maybe_handle_multi_intent` sits at line 3651 and is
**never reached** for this turn — `_maybe_handle_goal_request` (line 2742,
invoked at line 3623) returns first.

**Actual root cause.** `_maybe_handle_goal_request` composed its plan from raw
text via `build_goal_plan` and never consulted the `TaskSpec` the cascade had
already computed at line 3463. The request decomposes into an
investigation/explanation pair, so the goal route claimed a turn that
`TaskIntake` had correctly classified `DEVELOPMENT_REQUEST`, and the governed
route `_development_request_route` (line 3812) — which states the opposite
contract, *"Development semantics win — run it first and never reroute
development through orchestration"* — became unreachable.

**Correction (bounded, existing path).** The goal route now declines when the
already-computed `TaskSpec` is `DEVELOPMENT_REQUEST`. No new module, router,
parser, authority, or approval rule; the plan composition itself is unchanged.
The turn now reaches the existing governed route, which reports its real outcome
(`envelope_disabled`) with no approval created and no modification.

**Verification.** `tests/test_self_development_goal_precedence.py` — 20 passed
(real kernel, model-OFF). Preserved: clean two-stage goals, plain development
requests, plain investigations, multi-intent non-development goals, and explicit
negation. Noted: three `test_step11_natural_response_generation.py` and two
`test_step10_multi_intent_multi_step.py` real-kernel failures are **pre-existing
at HEAD** (investigation + research compounds), re-verified by stashing this
change; they are unrelated to it and were not touched.