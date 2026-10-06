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

---

## 8. Resolution of the open Step 10/11 failures (investigation + research compounds)

The five failures recorded above are now **resolved**. They were not a single
defect and were not caused by the preceding step; they are two independent
problems, separated by direct evidence.

### 8.1 Provenance (measured, not assumed)

Reproduced in an isolated worktree at the commits themselves:

| Commit | Date | Result |
|---|---|---|
| `1bca82d` (Step 10) | 2026-09-28 | 2 failed (`partial` vs `completed`) |
| `52cc22d` (Step 11) | 2026-09-28 | 3 failed (`partial` vs `completed`) |
| `95a18d2` (compound delegation) | 2026-10-02 | 5 failed (`KeyError: 'orchestration'`) |
| HEAD before this change | 2026-10-03 | 5 failed, identical |

The assertions were **never reliably green**, even at the commit that introduced
them: the `research` step fails `NO_EVIDENCE` against an empty validated-knowledge
store, so `"Done. Steps completed: 2/2."` / `status == "completed"` were
unachievable by construction with that fixture.

### 8.2 Problem A — superseded test contract (owner-adjudicated)

Two committed routes had contradictory contracts for the same input
("Investigate X and also research Y"):

- `_maybe_handle_multi_step` (Step 10, `conversation_service.py`) **declines** a
  compound whose clauses are each owned by an existing authoritative handler, so
  the operation/result lifecycle is recorded exactly once by the existing
  investigation/knowledge seams — introduced by `95a18d2`.
- `_maybe_handle_multi_intent` (Step 6) then claims the same turn.

The Step 10/11 real-kernel tests asserted the **older** orchestration contract
(`orchestration.status`, `multi_step.ordered`). The OWNER adjudicated that
**per-clause delegation is authoritative**.

Measured behaviour under delegation (real kernel, model-OFF) confirms the
decision is correct rather than a regression: every clause is answered
(`unhandled == []`), and **both** lifecycles record themselves —
`last_operation.kind == "investigation_request"`, a latest result, and a
knowledge result — while the orchestration bridge is correctly absent from the
conversation as the source of truth. The dependent case ("…and then analyze the
findings") still runs through the orchestration bridge unchanged.

**Correction.** The four superseded tests were rewritten to assert the delegation
contract, and to assert **more** than they did before: both lifecycles recorded,
user order preserved, nothing unhandled, no internal identifiers leaked, and the
orchestration bridge explicitly *not* used. No production code changed for this
part, and no test was weakened or deleted.

### 8.3 Problem B — real determinism defect (genuine, fixed in production code)

The fifth failure, `test_send_stream_parity`, was **not** a routing issue. `send`
and `stream` produced byte-identical behaviour and differed only in one token:

```
-**Proposal ID:** INV-PROP-20261004193957-0001
+**Proposal ID:** INV-PROP-20261004194036-0001
```

`InvestigationProposalGenerator.generate_proposal` minted its id from
`datetime.now()`. Because that id is rendered into conversational output, the
**same investigation produced different text on every run**, at different
instants — a direct violation of the deterministic-first invariant, and the reason
parity was unachievable by construction. No routing change could have fixed it.

**Correction.** The id is now derived from the EVIDENCE the proposal represents
(target, diagnosis, components, findings, affected files) via the module's
existing `hashlib` content-hash convention, retaining the `INV-PROP-` prefix and
the per-instance counter for uniqueness. Verified that nothing in Atlas parses the
id for a timestamp (CLI, governance and promotion paths treat it as an opaque
lookup key).

Scope deliberately **excludes** the sibling `DEV-CONV-` conversion id in
`investigation.py` and `PROP-` in `evolution/proposal_generator.py`, which show the
same pattern: they are not on the observed failing path, and changing them is not
justified by current evidence. They remain a recorded, validated gap.

---

## 9. Model-OFF live interaction trial — correction/referent handling (evidence, NOT a phase)

A fresh live trial was run through the documented human entry point (`python
main.py` → `AtlasCLI.run()` → the production kernel), model assistance OFF
(`[ai].external_providers = false`), covering contextual references, multi-turn
continuity, repair/correction, elliptical language, compound requests, comparison
with earlier context, and casual/Romanized-Bangla phrasing. Two classes of finding
resulted: one closed here, and two recorded as remaining.

### 9.1 Gap 1 — a bare demonstrative installed as a literal subject (CLOSED)

**Observed.** After a real investigation was established:

```
USER : Investigate the memory service.
ATLAS: ## Investigation: Investigate the memory service ...
USER : I did not mean that.
ATLAS: Understood — I corrected the active subject to 'that'. The previous
       investigation is no longer the active subject. ...
```

Atlas installed the word "that" as a NEW subject and superseded the retained
investigation. A meta-utterance that names no subject was treated as a subject
replacement, overwriting a real active subject with a single word.

**Boundary (measured, real kernel).** The defect is narrow, not general:

| Input | Installed a subject? | Investigation superseded? |
|---|---|---|
| `"I did not mean that."` / `"I meant that."` / `"I did not mean this."` / `"I meant it."` | **yes (the pointer)** | **yes** |
| `"That's not what I meant."` / `"Sorry, that's wrong."` / `"Wrong."` / `"Forget it."` | no | no |
| `"No, I meant the storage layer."` | yes (`storage layer`, correct) | yes (correct) |
| `"No, I meant the previous one."` | no | no (existing earlier-item surface) |

**Root cause.** `semantic_frame.corrected_subject()` extracts the text after the
latest replacement marker (`"i did not mean"` → tail `"that."`) with **no
referent-type filter**, and `_maybe_handle_correction` rejected a corrected reading
only when it was empty or matched `_ORDINAL_REFERENCE_RE`. A bare demonstrative is
neither, so it was accepted as a subject (and, via the existing hand-off,
`current_investigation` was cleared).

**Finding that shaped the fix.** Atlas already represented this correctly and the
signal already flowed end to end: `_enrich` populates `SemanticFrame.reference`
from the EXISTING `lexicon.REFERENCE_WORDS` for **every** frame, and `AtlasMeaning`
carries that frame verbatim. Verified before changing anything —
`frame.reference == "that"` for `"I meant that."`, and `""` for a named subject.
The consumer simply never read it. `semantic_frame.py` therefore required **no**
change; the investigation's initial "propagation gap" was a consumer that ignored a
correct signal.

**Correction (bounded, existing mechanism).** One guard in
`_maybe_handle_correction`, beside the existing ordinal guard, reusing the existing
`return None` fail-closed convention:

```python
if set(tokens(corrected)) <= REFERENCE_WORDS:
    return None
```

A corrected reading made up ENTIRELY of reference words names no subject, so it
defers to Atlas's existing fail-closed reference/ordinal surfaces instead of
inventing a referent. `atlas/conversation/conversation_service.py` only: **+14 / −1**
(1 import, 1 guard). No new module, state, registry, authority, parser, or
vocabulary — the canonical `REFERENCE_WORDS` set already existed and is the same set
`_enrich` uses.

**Why no external technology was justified.** Every required capability already
existed inside Atlas; the defect was a dropped check in a deterministic pipeline.
An external model would not have fixed it and would have violated model
independence.

**Verification (actually executed).**

| Suite | Result |
|---|---|
| New Gap 1 regression (`tests/test_correction_demonstrative_subject.py`) | 31 passed |
| Correction/reference suites (`correction_routing`, `target_state_g1`, `evidence_improvement_2/3`, `step7_context_and_reference`, `lexical_canonicalization`) | 400 passed |
| Broader conversation regression (12 files) | 356 passed |
| Wider conversation/investigation (10 files) | 500 passed |
| **Total** | **1,287 passed, 0 failed** |

Re-verified after the fix: **399 passed, 0 failed** across the new regression plus
the correction/reference suites. Determinism: 7 cases × 5 fresh runs, all
identical. The new tests assert the SEMANTIC outcome (no literal pointer
installed, investigation not superseded, fail-closed, named correction still works,
result still recallable) rather than a response string. No existing test was
weakened, rewritten or deleted.

**Live end-to-end verification (`python main.py`, real kernel, model-OFF).** All
four defect forms now leave the active investigation intact and keep the result
recallable (`The active investigation: Investigate the memory service`, then
`The most recent result: …`), the named correction still installs its subject
(`I corrected the active subject to 'storage layer'`), and every control keeps its
exact prior behaviour.

### 9.2 Remaining validated gaps (recorded, NOT implemented)

- **Gap 2 — a discourse marker over-split as a separate intent.** `"Okay,
  investigate the remaining problem."` is represented as two intents
  (`acknowledge` on `"Okay"`, then `investigate`). The request is not dropped and
  the answer is truthful, but the decomposition of a single natural request is
  arguably incorrect. Root cause is localized: `_operation_comma_index` treats a
  bare comma as a boundary when **both** sides name a bounded operation, and
  `interpret("Okay")` returns the operation `acknowledge` (role
  `acknowledgement`, domain `casual`) for every bare acknowledgement token, so
  `"Okay,"` satisfies that test. Atlas already distinguishes an acknowledgement
  (`SemanticRole.ACKNOWLEDGEMENT`) from an actionable intent, so the concept
  exists; the comma rule does not consult it. Investigated read-only; see §9.3.
  **CLOSED in §9.4.**
- **Gap 3 — Romanized-Bangla (Banglish) unsupported.** All four Banglish forms
  declined honestly with no misrouting and no fabrication. **Not classified as a
  capability gap:** honest decline is consistent with Atlas's deliberate
  deterministic, model-independent design, and widening lexical coverage is not
  justified by current evidence.
- **Sibling id generators** (`DEV-CONV-`, `PROP-`) still embed wall-clock
  timestamps — unchanged, as recorded in §8.3.

### 9.3 Gap 2 read-only investigation (no code changed)

Traced end to end without modifying anything:

1. **Entry.** The turn enters through the normal intake path; `interpret()` reads
   the WHOLE utterance as ONE investigation
   (`role=new_objective`, `domain=investigation`, `operation=investigate`).
2. **"Okay" classification.** `split_intents` splits on the bare comma via
   `_operation_comma_index`, whose contract is "both sides name a bounded
   operation". `interpret("Okay")` returns `operation="acknowledge"`,
   `role=acknowledgement`, `domain=casual` — so the head passes the test.
   Every bare acknowledgement token behaves the same (`Ok`, `Alright`, `Sure`,
   `Thanks`, `Got it`, `Fine`, `Yes`), and `"Hello,"` behaves identically
   (`greet` + `investigate`).
3. **Remaining request.** Read correctly as `investigate the remaining problem`.
4. **Why two intents.** The comma rule was designed so an enumerative subject
   ("investigate the memory service, the cache layer") is never over-split; its
   guard is "operation on BOTH sides", and an acknowledgement's `acknowledge`
   operation satisfies it. The guard is doing exactly what it was written to do.
5. **Existing concept.** Yes — `SemanticRole.ACKNOWLEDGEMENT`, the
   `ACKNOWLEDGEMENT` operation, and the acknowledgement class in `_enrich` already
   distinguish a discourse marker from an actionable intent.
6. **Downstream consequence — measured, and it is NOT what the split causes.**
   A live kernel run recorded `multi_intent = {handled: ["Okay", "investigate the
   remaining problem"], unhandled: []}`, the investigation ran, the result was
   stored and stayed recallable, and no approval/execution/promotion/authorization
   key or pending promotion review was created. `current_investigation` was
   replaced — but a control matrix proves that is **not** attributable to the
   split:

   | Turn | Split? | Active investigation |
   |---|---|---|
   | `"Okay, investigate the remaining problem."` | yes (2) | `investigate the remaining problem` |
   | `"Investigate the remaining problem."` | no | `Investigate the remaining problem` |
   | `"Please investigate the remaining problem."` | no | `Please investigate the remaining problem` |
   | `"Hello, investigate the remaining problem."` | yes (2) | `investigate the remaining problem` |

   A new investigation legitimately replaces the active one in **every** case; the
   leading marker only additionally changes the subject string (`"Please …"` keeps
   the filler, `"Okay …"` does not). So the split's only observed effect is the
   **framing** — the reply is introduced as "That request carries more than one
   intent. I answered 2 of 2" and an `acknowledge` clause is listed. No state,
   routing, execution, or governance consequence was observed.

**Classification: B — a bounded deterministic classification defect**, localized to
the comma-boundary rule, and materially smaller than first observed: the request is
never dropped and nothing is mis-executed, but a single natural request is described
as two intents. The concept needed to fix it already exists in Atlas
(`SemanticRole.ACKNOWLEDGEMENT`); the comma rule does not consult it. Note the
`acknowledge`/`greet` operation on the head is not itself wrong — it is the correct
reading of the word — only its use as a *join* is.

### 9.4 Gap 2 — closed by a bounded native correction

Authorized separately after the read-only investigation above, and implemented
without broadening the architecture.

**Root cause (confirmed).** `_operation_comma_index` (`semantic_frame.py`) treats a
bare comma as a compound-intent boundary when **both** sides name a bounded
operation. That guard is correct and load-bearing: it is what keeps an enumerative
subject (`"investigate the memory service, the cache layer"`) unsplit. But
`interpret("Okay")` returns `operation="acknowledge"` with evidence
`acknowledgement-class`, and `interpret("Hello")` returns `operation="greet"` with
evidence `greeting-class`, so a pure discourse marker satisfied the BOTH-sides test
and one natural request was represented as two intents.

**Correction (bounded, existing concepts).** Two additions to
`atlas/conversation/semantic_frame.py` only: a `_is_discourse_marker(frame)` helper
and one guard in `_operation_comma_index` that `continue`s when the HEAD is a
whole-turn acknowledgement/greeting. The marker set is **not** new vocabulary — it is
read from Atlas's own classification evidence (`acknowledgement-class`,
`greeting-class`), so `"Okay"`, `"Ok"`, `"Alright"`, `"Sure"`, `"Yes"`, `"Thanks"`,
`"Got it"` and `"Hello"` are all covered by the concepts the architecture already had,
with no per-word special-casing. No new module, parser, vocabulary, conversation
state, dialogue-act system, semantic router, coreference system, or model.

The function's original purpose is preserved: it still joins two **actionable** sides
and still never splits an enumerative subject. A standalone acknowledgement is never
silenced — it is only ever a HEAD of a join.

**Verification (actually executed).**

| Suite | Result |
|---|---|
| New Gap 2 regression (`tests/test_gap2_discourse_marker_intent.py`) | 39 passed |
| Intent/decomposition suites (`mixed_compound_ownership`, `step6`, `step10`, `compound_conversational_moves`, `target_state_g1`, `evidence_improvement_2`, `step7`, `step9`, `phase3_conversation_replay`, `lexical_canonicalization`) | 497 passed, 1 skipped, 0 failed |
| Broader conversation regression (18 files, incl. `investigation`, `step11`, Gap 1 suite) | 775 passed, 0 failed |

Contract coverage: all four required acknowledgement-led forms plus a greeting-led
form are unsplit; the actionable request is still understood as one investigation;
genuine compounds (strong coordinator, ordered, plain-comma, plain "and") still yield
exactly two intents; all three enumerative-subject guards remain unsplit; standalone
acknowledgements still classify as `ACKNOWLEDGEMENT`/`acknowledge` and a standalone
greeting still classifies as `greet`; the helper is fail-closed on non-frame input;
and repeated readings are identical. No existing test was weakened, rewritten or
deleted.

**Live end-to-end verification (`python main.py`, real kernel, model-OFF).**

| Turn | Observed |
|---|---|
| `"Okay, investigate the remaining problem."` | `## Investigation: Okay, investigate the remaining problem` — one request, **no** multi-intent framing |
| `"Hello, investigate the remaining problem."` | `## Investigation: Hello, investigate the remaining problem` — same |
| `"Investigate the memory service and also research …"` | `That request carries more than one intent. I answered 2 of 2:` — compound preserved |
| `"First investigate …, then research …"` | `That request carries more than one intent. I answered 2 of 2:` — compound preserved |
| `"Investigate the memory service, the cache layer"` | `## Investigation: Investigate the memory service, the cache layer` — enumerative subject protected |
| `"Okay."` / `"Thanks."` | `Noted, and no action taken.` / `You're welcome.` — standalone acknowledgements unchanged |

The investigation still executes exactly as before, no approval/execution/promotion
boundary changed, and governance is untouched.

**Gap 2 is therefore CLOSED** on both deterministic and real-kernel evidence.

---

## 10. Bounded source-aware authoring context (evidence, NOT a phase)

### 10.1 The measured gap

The end-to-end authoring evaluation (previous work, evaluation only) established that
every layer of the model-assisted authoring path behaved correctly EXCEPT the authoring
context itself:

| Layer | Result |
| --- | --- |
| architectural target resolution | correct for the resolvable targets tested |
| BM25 repository ranking | found the expected module in 5/5 tasks (rank 1 in 4/5) |
| ranking determinism | identical across repeated calls and rebuilt maps |
| context bound | bounded and small |
| provider boundary (OFF) | `None`, zero provider calls |
| provider boundary (ON stub) | received request + `Repository context` |
| `CodeChangeSet` validation | rejected every malformed payload |
| promotion / governance | unchanged |

But the context contained **no implementation source**. Measured against the real
88-line `atlas/conversation/history.py`, **0/6** distinctive implementation lines
appeared in the prompt; the whole context was module paths plus `class`/`method`
signature lines. Meanwhile `CodeChangeSet.content` is documented as *"the full
replacement content for the path"*.

That is a **structural representation mismatch on the Atlas side**, not a retrieval or
model failure:

> full-file replacement requires implementation context, but the authoring context
> provided only structural metadata.

### 10.2 The correction

The repository-map builder **already read each file's full text** in order to
`ast.parse` it, and then discarded the text. `ModuleInfo` now retains a bounded
`source_excerpt` taken from **that same in-memory text**, plus `source_truncated` to
record honestly whether the excerpt omits part of the file.

No new I/O, parser, dependency, index, embedding, dense/hybrid retrieval or retrieval
architecture was introduced. `MAX_SOURCE_EXCERPT_CHARS = 4000` is a fixed module
constant, never per-request; retaining excerpts costs ~3.7 MB for 1,140 modules (333
complete files, 807 truncated).

`_build_authoring_context` now emits, per ranked module:

* the bounded **source** excerpt, labelled `source (truncated: first N of M lines)`
  when cut — truncation is explicit, never silent;
* the module's resolved **internal imports** (bounded by `MAX_CONTEXT_IMPORTS`);
* the existing bounded **symbol signatures** (unchanged).

A global budget (`MAX_CONTEXT_SOURCE_CHARS = 16000`) is spent in ranked order so a
large target cannot be starved; a new `_prioritise_declared_target` step moves a
DECLARED target component to the front of the **existing** ranking (ranking itself is
unchanged), and the existing production-over-test preference is retained.

### 10.3 `history.py` — distinctive-line measurement, before vs after

| Metric | Before | After |
| --- | --- | --- |
| distinctive implementation lines in the prompt | **0/6** | **12/12** |
| target source present | none | **complete 88-line file** |
| imports present | none | `atlas.conversation.conversation` |
| signatures present | yes | yes (unchanged) |
| context size | ~8.9k chars | ~20.2k chars |

The after-figure samples distinctive lines **evenly across the whole file**, so it is
not biased toward the excerpt head — the full file really is present.

### 10.4 Controlled task results

| Task | Lines | BM25 rank | Target first | Source in context | Distinctive lines | Overall |
| --- | --- | --- | --- | --- | --- | --- |
| `atlas.conversation.history` | 88 | 1 | yes | **complete file** | **12/12** | SUFFICIENT |
| `atlas.services.memory_service` | 24 | 5 | yes (declared) | **complete file** | **8/8** | SUFFICIENT |
| `atlas.evolution.promotion_gate` | 739 | 1 | yes | bounded excerpt + all signatures | 3/12 | PARTIALLY SUFFICIENT |
| `atlas.self_knowledge.capability_specification` | 582 | 1 | yes | bounded excerpt + all signatures | 3/12 | PARTIALLY SUFFICIENT |
| `atlas.conversation.conversation_service` | 8,675 | 1 | yes | capped 4,000-char excerpt (~1.5%) | 1/12 | PARTIALLY SUFFICIENT |

Note on `memory_service.py`: lexical ranking placed it 5th, and the declared-target
rule is what moved it to the front — the source budget therefore went to the module
the request was actually about. This is the intended division of labour: ranking is
evidence, the declared target is instruction.

### 10.5 Structural limitation (stated, not hidden)

For a **very large** module the existing full-file-replacement contract in
`CodeChangeSet` is **not reachable** from a bounded source context: a bounded excerpt
cannot reconstruct an 8,675-line file. This is a property of the change
representation, which is deliberately **not** redesigned in this phase. Small and
medium modules — the common authoring case — are now authorable from the context.

### 10.6 Boundary, validation and governance re-verified

| Check | Result |
| --- | --- |
| provider OFF | `supply_changes → None`, **0 provider invocations**; context still built locally and deterministically |
| provider ON (controlled stub) | receives the source-aware context, request/spec, target identity, authoring rules; context within bound |
| malformed / raising / non-JSON output | still fails closed → `None` |
| valid draft | still `origin="model-assisted-draft"` |
| `CodeChangeSet` validation | untouched and authoritative |
| `PromotionGate`, approval, sandbox, provider policy | untouched |
| production change promoted automatically | none |
| map absent / raising / lacking source | context degrades safely to the previous structure-only form |

Determinism: same repository + same query → byte-identical context, including across
an independently constructed map; ordering never depends on dictionary/set iteration.
Safety: every emitted path comes from the repository map (no invented path, no
invented source, no absolute path, no traversal), and the excerpt is verified to be a
literal prefix of the real file.

### 10.7 Tests

50 new/updated capability tests in `tests/test_authoring_source_context.py` and
`tests/test_repository_ranking_authoring_context.py` cover source inclusion,
explicit truncation, boundedness (module count, per-module cap, global budget),
determinism, target priority, production preference, path/source integrity and the
provider boundary — all passing.

Two stale assertions in `tests/test_evolution_model_assisted_activation.py` asserted
the pre-`EvidenceChangeSupplier` composition length (2 / 3). They **failed at
`e681bb8`** before this phase — the deliberate `EvidenceChangeSupplier` member was
added to the composition after those B4 tests were written — and were corrected to
assert the real order Deterministic → Scaffold → Evidence → Model, which is strictly
more informative than the old counts.

### 10.8 Broader regression

A full-suite run (11,201 tests) reports 22 failures. **All 22 reproduce on a pristine
`e681bb8` checkout** (verified: 21/21 in a subset re-run plus `test_intake_contract[H7-0]`),
so **this phase introduces zero regressions**. None of the 22 involves repository
content, ranking or authoring; they span intent/reference routing, the L9 corpus
contract, the evidence/promotion lifecycle and antecedent projection, and belong to
the explicitly deferred work (clause-level target resolution, stale-correction replay,
topic-switch antecedent staleness). They are reported for accuracy and deliberately
**not** touched in this phase.

---

## 11. Correction-state integrity — the final conversation capability

### 11.1 Reproduction (current tree, model assistance OFF)

    T1 "investigate the memory subsystem"   -> investigation established, proposal raised
    T2 "I meant the cache layer."           -> corrected subject installed
    T3 "Sorry, that's wrong."               -> REPLAYED the T2 correction, forever
    T4 "That's not what I meant."           -> installed the WHOLE utterance as the
                                               corrected subject and overwrote the
                                               active objective with a meta-utterance

Instrumented state confirmed both halves rather than assuming them: at T3 the
`corrections` record was **unchanged** (count stayed 1) yet the consumer re-emitted the
stale acknowledgement, while at T4 a **new** record appeared whose `corrected` value
was the literal utterance.

### 11.2 Root cause — two coordinated defects, one missing rule

`detect_turn_role` classifies `"Sorry, that's wrong."` as a correction (its
replacement-phrase list contains `"sorry"`) while `_detect_correction` records nothing
for it (its cue list does not). That mismatch exposed the stale record:

* **Consumer** — `_maybe_handle_correction` read `state.corrections[-1]`, the
  *accumulated* history, rather than the correction the *current* turn produced. Any
  later turn that merely read as a correction replayed an already-superseded subject,
  without limit.
* **Engine** — `_detect_correction` fell back to `spec.intent or text` when
  `corrected_subject` extracted nothing, recording the whole utterance as a new
  subject. Because `_SUBSTRING_REPLACEMENT_MARKERS` ⊇ `CORRECTION_MARKERS`, that
  fallback fired precisely and only on bare meta-corrections.

A **third defect of the same class was found by the new tests while implementing**,
not assumed: `"I didn't mean that."` extracted the bare pointer `'that'` and installed
it as the active objective.

The rule now enforced at both points:

> A correction installs — and is consumed as — a **subject** only when the turn itself
> names a bounded replacement subject.

### 11.3 Repair — existing mechanisms only

* `ConversationEngine._detect_correction` records a correction only when
  `corrected_subject` yields a bounded subject, and rejects a subject made up
  **entirely** of reference words using the **same** predicate the conversation layer
  already applies to the same class (`set(tokens(corrected)) <= REFERENCE_WORDS`, from
  the existing `atlas.conversation.lexicon`).
* `ConversationService._maybe_handle_correction` takes the record from the turn's own
  `semantic_intake.corrections` — the per-turn projection that **already** rides
  `TaskSpec.context` and `AtlasMeaning` — instead of the accumulated history.

No new state field, carrier, vocabulary list, parser, module, model or authority; no
sentence-specific case. The Gap 1 consumer guard is retained as defence in depth.

### 11.4 Deterministic and real-kernel evidence

| Check | Result |
| --- | --- |
| stale `'cache layer'` acknowledgement | emitted **exactly once** (T2); never replayed |
| `"Sorry, that's wrong."` | installs nothing; preserves the active objective |
| `"That's not what I meant."` | installs nothing; no objective corruption |
| `"I didn't mean that."` | bare pointer `'that'` never installed |
| `"Actually, I meant the storage layer."` | genuinely new correction still applied |
| correction record count | unchanged by repeated disagreement |
| repeats | byte-identical across fresh sessions |

Real `python main.py`, model OFF, 6-turn session: replay count 1, pointer installed
`False`, new correction applied `True`.

### 11.5 Capability matrix (real kernel, model OFF)

27 checks, **27 PASS, 0 FAIL** — casual conversation, ordinary question, direct
command, multi-turn follow-up, contextual reference, correction, correction-state
integrity, new correction, topic switch, compound request ("answered 2 of 2"),
development+investigation compound, development request, nonexistent target,
ambiguous/unresolved target, empty-input fail-closed, plus the 11 development
checks (target resolution, capability specification, ranking, source-aware context,
small/medium target, provider OFF/ON, malformed output, governed approval, sandbox
verification).

### 11.6 Authoring-provider validation (Stage 4)

| Case | Result |
| --- | --- |
| small module / medium module / symbol-level / internal-imports | target first, real source, imports, symbols, within all bounds |
| real source lines present | 3/3 in every case |
| provider OFF | `supply_changes → None`, **0 invocations** |
| provider ON (stub) | 1 invocation; receives governed request + target + real source + rules |
| valid draft | `origin="model-assisted-draft"`, 1 change |
| `not json` / `{}` / wrong types / path traversal / absolute path / provider exception | **all fail closed** (`None`) |
| `confidence: 9.9` | clamped to 1.0 (documented, intentional) |
| `content: ""` | **accepted** — see limitation below |
| `pending_promotion_reviews` after all of the above | empty |

**Observed, non-blocking limitation (NOT repaired; outside this command's scope).**
An empty `content` string is accepted by both the supplier and
`CodeChangeSet.from_payload` by **original design** — each requires `content` to be a
`str` and enforces an upper size bound, but no minimum. It is not a regression, it
grants no authority, and it bypasses no governance stage: such a payload is still only
a `model-assisted-draft` that must pass approval, sandbox verification and promotion.
Tightening it would mean changing `CodeChangeSet` validation semantics, which this
command explicitly excludes.
