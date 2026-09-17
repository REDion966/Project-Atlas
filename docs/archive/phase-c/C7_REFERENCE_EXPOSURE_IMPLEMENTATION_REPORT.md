# C7 GAP-C31-02 — Bounded Reference/Context Resolution

## IMPLEMENTATION REPORT

Authoritative contract: `C7_REFERENCE_EXPOSURE_CONTRACT_RESOLUTION.md`
(recommendation **B — bounded resolver extension required before exposure**).

---

## 1. STATUS

**C7 GAP-C31-02 — IMPLEMENTED AND VALIDATED**

Only GAP-C31-02 is closed. No other C7 work is claimed complete (see §20).

---

## 2. BASELINE

Recorded before any modification:

| Item | Value |
| --- | --- |
| Branch | `main` |
| HEAD | `f85de89` |
| Working tree | dirty (pre-existing user modifications preserved) |
| Staged files | none |
| Modified (tracked) at baseline | `atlas/cli/main.py`, `atlas/conversation/conversation_service.py`, `atlas/conversation/investigation.py`, `atlas/conversation/task_intake.py`, `atlas/evolution/development_cycle.py`, `atlas/kernel/atlas.py`, `tests/test_conversation_state.py`, `tests/test_investigation.py` |
| Untracked at baseline | `mission_output.txt`, `test_results.log`, `test_results_p18.log`, `tests/test_c1_1_dependency_inversion.py` (+ prior-phase reports) |

No `reset`, `clean`, `stash`, `commit`, `push`, checkout/discard, rename or delete was performed.
HEAD is still `f85de89` after implementation.

---

## 3. IMPLEMENTED FILES

| File | Change |
| --- | --- |
| `atlas/conversation/reference_resolution.py` | +41 / −1 — word-boundary phrase matching + bounded detection guard |
| `atlas/conversation/conversation_service.py` | additive — one call site in `send()` + `_apply_reference_resolution` helper |
| `tests/test_reference_resolution.py` | +95 — 26 new focused tests |
| `tests/test_reference_exposure.py` | **new** — 13 production `send()` tests |

No other production file was touched. `task_intake.py`, `conversation_state.py`,
`reference_resolution` pattern tables, CLI, kernel, governance, autonomy, storage
and the roadmap were **not** modified.

---

## 4. RESOLVER MATCHING CHANGE

The only behavioural change in the resolver:

```python
_PHRASE_PATTERN_CACHE: dict[str, re.Pattern[str]] = {}

def _phrase_pattern(phrase: str) -> re.Pattern[str]:
    pattern = _PHRASE_PATTERN_CACHE.get(phrase)
    if pattern is None:
        pattern = re.compile(rf"\b{re.escape(phrase)}\b")
        _PHRASE_PATTERN_CACHE[phrase] = pattern
    return pattern
```

and in `resolve()`:

```python
- if any(phrase in normalized for phrase in phrases):
+ if any(_phrase_pattern(phrase).search(normalized) for phrase in phrases):
```

Preserved exactly: the pattern list, pattern ordering, candidate field tuples,
candidate semantics, `RESOLVED` / `UNRESOLVED` / `AMBIGUOUS`, the state-field
mappings, the public API, and the normalisation (`text.strip().lower()`).

Deterministic, case-insensitive, no new inference, no semantic matching.

---

## 5. REFERENCE DETECTION CONTRACT

Substring false positives are eliminated as required:

| Input | Before | After |
| --- | --- | --- |
| `"What is the priority of the release?"` | RESOLVED (`it` inside `prior*it*y`) | **UNRESOLVED** |
| `"Is the architecture documented?"` | RESOLVED (`it` in `arch*it*ecture`) | **UNRESOLVED** |
| `"How is the quality of the output?"` | RESOLVED (`it` in `qual*it*y`) | **UNRESOLVED** |
| `"Please summarise the repository structure."` | RESOLVED (`it` in `repos*it*ory`) | **UNRESOLVED** |
| `"We voted against the rule."` | AMBIGUOUS (`again` in `ag*ain*st`) | **UNRESOLVED** |

Valid bounded phrases continue to resolve: `that investigation` / `the
investigation` → `current_investigation`; `that result` / `the result` / `the
findings` → `latest_result`; `what did you find` → AMBIGUOUS (unchanged).

**Bounded production invocation.** A new deterministic guard in the resolver
module gates the production flow:

```python
def has_bounded_reference(text: str) -> bool:
    # True only for recognized MULTI-WORD reference phrases.
```

Only multi-word phrases (`"that investigation"`, `"what did you find"`, `"run it
again"`, …) qualify. Bare single-word triggers (`it`, `that`, `this`, `them`,
`those`, `again`, `continue`) can therefore never invoke the resolver from the
production turn flow — including inside ordinary words, because matching is
word-boundary based. No new patterns were added; the reference vocabulary is
unchanged.

---

## 6. TASKSPEC / STRUCTURED CONTEXT INTEGRATION

On **RESOLVED** the referent is attached to the **existing** `TaskSpec.context`
dict (no new field, no new type), using the same `dataclasses.replace` pattern
already used by `ConversationService._attach_session_to_spec`:

```python
enriched = dict(spec.context) if isinstance(spec.context, dict) else {}
enriched["resolved_reference"] = {
    "field": result.resolved_field,
    "value": result.resolved_value,
}
return _replace(spec, context=enriched), None
```

* The session attribution keys (`session_id`, `principal_id`, `authority`)
  written earlier by `_attach_session_to_spec` are preserved.
* `TaskSpec` is frozen; the original spec object is never mutated.
* The **user's original message is preserved**: `send()` still passes
  `original_text=text` to handlers and never rewrites, truncates or synthesises
  the message.
* The spec object returned to the caller is identity-unchanged for
  non-reference and UNRESOLVED turns.

No invented `resolved_context` architecture was required — `TaskSpec.context` is
the existing structured context field and is already consumed downstream (e.g.
`_attach_session_to_spec`, `development_need_detector`, `development_intake`).

---

## 7. ROUTING BEHAVIOR

Insertion point: in `ConversationService.send()`, immediately after task intake
and session attribution, **before** the existing investigation/development/
orchestration/cognition cascade:

```python
if spec is not None:
    spec, reference_response = self._apply_reference_resolution(spec, text)
    if reference_response is not None:
        self._conversation.add_message(reference_response)
        return reference_response
```

* Exactly **one** routing cascade runs. There is no second pass, no re-entry and
  no direct handler invocation.
* RESOLVED: attaches structured context and falls through to the **unchanged**
  cascade. `task_type`, `intent`, `goal`, `needs_clarification`, confidence and
  `model_metadata` are untouched, so routing decisions are identical to before.
* No new router, no new answering subsystem, no routing architecture change.

---

## 8. AMBIGUOUS / UNRESOLVED BEHAVIOR

**AMBIGUOUS** → the **existing** clarification mechanism is reused: the
resolver's own deterministic `reason` is injected as the clarification question
into a replaced spec, and the existing
`ConversationService._orchestration_clarification_message(spec)` renders the
response. No new clarification system was created; the resolver never guesses,
and no referent is fabricated.

Observed: `"What did you find?"` (both `current_investigation` and
`latest_result` set) →

```
I need a bit more detail before I can run this.
- Multiple plausible findings referents: current_investigation, latest_result. Clarification required.
```

**UNRESOLVED** → fail closed: the spec is returned unchanged and routing proceeds
exactly as before. **NO REFERENCE** → the guard short-circuits before the
resolver is consulted; behaviour is byte-for-byte unchanged. Reference
resolution never overrides unrelated intake clarification logic.

---

## 9. TEST CHANGES

* `tests/test_reference_resolution.py` — 32 → **58 tests** (+26):
  `TestWordBoundaryMatching` (substring false positives removed; bounded
  multi-word references still resolve; ambiguity unchanged; determinism) and
  `TestBoundedReferenceGuard` (multi-word detection; single-word and
  false-positive sentences not detected).
* `tests/test_reference_exposure.py` — **new, 13 tests**: unit coverage of
  `_apply_reference_resolution` (identity for non-reference, no resolver call
  for false positives, structured context on RESOLVED, existing clarification on
  AMBIGUOUS, unchanged on UNRESOLVED) plus production `send()` integration
  (non-reference regression, false-positive regression, ambiguous clarification
  with 0 AI calls, unresolved routing preserved, resolved context reaches routing
  exactly once with the original text intact, unsupported plural reference not
  resolved, read-only/governance metadata, determinism).

No existing test was modified, weakened or deleted.

---

## 10. FOCUSED TEST RESULTS

| Suite | Result |
| --- | --- |
| `tests/test_reference_resolution.py` | **58 passed** |
| `tests/test_reference_exposure.py` | **13 passed** |
| Conversation regression set (`test_conversation_service`, `test_p15_2_conversation_continuity`, `test_conversation_task_intake`, `test_conversation_state`, `test_conversation_orchestration`, `test_conversation_development_intake`, `test_conversation_development_bridge`, `test_model_independence_p6`, `test_level1_analysis_contract`, `test_p18_integration_e2e`) | **195 passed** in 87.8 s |

No focused failure occurred; nothing was carried forward.

---

## 11. FULL REGRESSION RESULTS

`python -m pytest -q --junitxml=…` (full suite, monitor task `m1phta2h`, exit 0):

| Metric | Value |
| --- | --- |
| tests | **5945** |
| failures | **0** |
| errors | **0** |
| skipped | **2** (pre-existing) |
| duration | 2787.9 s |

Baseline after C6.1 was 5906 tests; the 39 new C7 tests bring the expected total
to 5945 — exactly matched.

---

## 12. MODEL-INDEPENDENCE RESULTS

Run against a failing-AI double (`RuntimeError("No AI available")`) on the real
kernel:

* Reference **resolution itself makes zero AI calls**. In the real-world run the
  investigation follow-up and the ambiguous turn both reported `ai_calls = 0`.
* AMBIGUOUS clarification is produced deterministically before the cognition/AI
  path is reached (0 AI calls).
* RESOLVED attaches context and hands off to the unchanged cascade; any AI call
  observed on such a turn (1, for the QUESTION-classified `"Based on that result,
  what does it mean?"`) belongs to the pre-existing normal routing, not to
  reference resolution.
* Detection (`has_bounded_reference`) and matching are pure regex — no model,
  network, embedding or external dependency.

---

## 13. GOVERNANCE RESULTS

Reference exposure is strictly read-only and cannot authorize, approve, execute,
mutate, promote, change permissions or bypass governance:

* `_apply_reference_resolution` only reads `ConversationState` and returns a
  (possibly replaced) immutable `TaskSpec` plus, at most, a clarification
  `Message`.
* It performs no store write, no execution call, no approval call, no authority
  check and no prompt/permission change.
* The clarification response carries no `execution` / `approval` metadata
  (asserted in `test_reference_exposure_is_read_only_and_governed`).
* No governance mechanism was introduced or modified.

---

## 14. REAL-WORLD VALIDATION

Real kernel (`Atlas()` + `atlas.chat()` → real `ConversationService.send()`),
real `ConversationState`, real resolver, isolated temporary evolution storage,
failing-AI double (script `c7_validation.py`; `git_unchanged = true`).

**Scenario A — investigation follow-up.** Real investigation of the conversation
subsystem, then `"Based on that investigation, what should I do next?"`:
reference cue recognized, resolver **RESOLVED** to
`current_investigation = "Investigate the conversation subsystem"`, original
message preserved, referent attached to `TaskSpec.context["resolved_reference"]`,
single routing pass, `ai_calls = 0`, no mutation.

> **Honest limitation (not a claim of a new answer surface).** The downstream
> investigation handler derives its target from `original_text` (unchanged), so
> the resolved referent is *exposed structurally* but does not by itself rewrite
> what the investigation targets or produce an investigation-synthesis answer for
> this wording. This is precisely the boundary the contract anticipated: the
> objective is correct context exposure, not the invention of an answer surface.

**Scenario B — result reference.** `"Based on that result, what does it mean?"`:
supported, resolver **RESOLVED** to `latest_result`; routing unchanged (normal
AI-fallback response; the single AI call is ordinary QUESTION routing, not
resolution).

**Scenario C — ambiguous.** `"What did you find?"` → **AMBIGUOUS** → existing
clarification, no guess, no fabricated referent, no second routing cascade,
`ai_calls = 0`.

**Scenario D — unsupported plural/component reference.** `"Which of those
components depend on it?"` → **not resolved** at exposure level (guard blocks
invocation); no fabricated resolution, routing unchanged.

**Scenario E — ordinary language.** `"What is the priority of the release?"` and
`"We voted against the rule."` → **not resolved**; normal routing.

**Scenario F — empty/reset context.** After `state_manager.clear()`,
`"what did you find?"` → resolver **UNRESOLVED**; no fabricated referent, no
mutation, no model dependency; the turn proceeded through ordinary routing (the
bounded clarification shown came from the pre-existing orchestration path, not
from reference resolution).

**Scenario G — repeatability.** The ambiguous turn was run repeatedly: identical
clarification content, identical structured results.

---

## 15. DETERMINISM RESULTS

* Resolver: repeated identical inputs produce identical
  `(status, resolved_field, resolved_value)`.
* Clarification content byte-identical across repeats (`G_repeatable`).
* `_phrase_pattern` is a pure cached compilation — stable ordering, no
  set-iteration ordering, no time/random input.
* Same classification, same resolution status, same referent, same routing
  classification across runs.

---

## 16. FALSE-POSITIVE RESULTS

Eliminated at both levels:

* **Resolver level** — `priority`, `architecture`, `quality`, `repository`,
  `against` and ordinary sentences now return `UNRESOLVED`.
* **Exposure level** — the multi-word guard means the production flow does not
  even invoke the resolver on such turns (asserted with a call-recording
  resolver: `spy.calls == []`).
* `"Which of those components depend on it?"` is likewise never resolved by the
  production flow.

---

## 17. SCOPE AUDIT

Confirmed **not** introduced: new reference patterns; general NLP/NLU; semantic
search; embeddings; external model dependency; new persistence; new schema; a new
router; a second routing cascade; a new answering subsystem; governance or
autonomy changes; C5/C6/C8/C9 work; roadmap changes; modifications to
`TaskIntake`, `ConversationState` or the resolver's pattern tables.

Changes are confined to §3. No out-of-scope change was found to revert.

---

## 18. GIT / READ-ONLY BASELINE INTEGRITY

* HEAD unchanged: `f85de89`.
* Pre-existing tracked modifications preserved verbatim; pre-existing untracked
  files untouched.
* New files: `tests/test_reference_exposure.py` and this report (plus the earlier
  phase reports). No generated junk, no temporary artifact, no scratchpad file
  committed to the repo.
* `git status` in the validation run matched its own baseline (`git_unchanged =
  true`).
* Nothing was committed or pushed.

---

## 19. DEFECTS / LIMITATIONS

1. **Context exposure only (bounded by design).** RESOLVED populates
   `TaskSpec.context["resolved_reference"]`, but the existing downstream
   investigation handler prefers `original_text`; the referent is therefore
   available structurally without changing the handler's target. No answer
   surface was invented, per the contract.
2. **`send()` only.** The exposure is wired into `ConversationService.send()`
   (the primary production turn flow, used by `Atlas.chat`). `stream()` was left
   untouched to keep the change to the smallest authorized point; the two paths
   therefore differ for reference-bearing turns only.
3. **Bare single-word triggers remain resolver-supported but are never invoked
   in production.** Calling the resolver directly with a bare `it`/`this`/`that`
   still resolves as before; the production guard is deliberately multi-word
   only (conservative).
4. **Unsupported forms stay unsupported.** plural/component references
   (`those components`, `which of those components…`) and multi-reference
   expressions receive no resolution.

No unresolved failure, regression or governance concern remains.

---

## 20. C7 GAP-C31-02 STATUS

**GAP-C31-02 (Category B — existing capability, exposure missing): CLOSED.**

The existing deterministic `ConversationReferenceResolver` is now exposed
through the production turn flow with safe word-boundary matching, bounded
multi-word detection, structured `TaskSpec.context` exposure on RESOLVED,
existing clarification on AMBIGUOUS, and fail-closed behavior on
UNRESOLVED/no-reference.

C7 as a whole is **not** declared complete. One observation from the real-world
validation — that resolved context is exposed but not yet consumed by downstream
handlers (limitation 1) — is recorded as **potential future evidence**, not as a
newly established gap; establishing it as a C7.x gap would require a separate
evidence-based scope investigation and is **not** authorized or performed here.

---

## 21. RECOMMENDATION

Accept GAP-C31-02 as implemented and validated (5945 tests, 0 failures, 0 errors,
2 pre-existing skips; real-world scenarios A–G pass; deterministic; model
independent; governance-neutral). Do **not** open C7.1, C8 or C9 on the basis of
this implementation; any further work requires its own evidence-based scope and
explicit authorization.

**STOP.**
