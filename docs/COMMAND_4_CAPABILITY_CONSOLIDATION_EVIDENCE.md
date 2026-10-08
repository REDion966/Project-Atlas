# COMMAND 4 — CAPABILITY CONSOLIDATION — EVIDENCE

Starting commit: `4f2ce7c` (Command 3 complete, HEAD == origin/main, clean tree)

## 1. What this command actually changed

Two bounded, high-value increments — both driven by real measured behaviour, not
by a research recommendation:

1. **A structured CHANGE-REQUEST meaning layer (L1/L3/L6)** that decides
   development intent from STRUCTURE (modality × action class × addressee ×
   negation × named targets) instead of from a list of accepted surface phrases,
   plus the two concrete defects that were blocking the development route.
2. **Bounded, deterministic FAULT LOCALIZATION** (§20/§22) that turns change +
   verification + graph evidence into a ranked suspect list with reasons.

No architecture was rewritten, no working system replaced, no second registry or
governance layer added, no model made mandatory, no L11+ roadmap invented.

## 2. The measured problem (before → after)

Command 3 ended with an unexplained finding: a realistic development request
returned `{}` from `development_supplied_edit`. Command 4 diagnosed it exactly —
there were **two** distinct defects, both measured on the real pipeline:

**Defect A — a lexical gate misread MEANING.** `DEVELOPMENT_REQUEST` came from a
maintained list of accepted cue FORMS. Equivalent requests with different
modality were classified as conversation or a question:

| phrasing | before | after |
| --- | --- | --- |
| "Implement X." | `conversation` | `development_request` |
| "Can you implement X?" | `question` | `development_request` |
| "I need X implemented." | `conversation` | `development_request` |
| "Please add X." | `conversation` | `development_request` |
| "Could you make X work?" | `question` | `development_request` |
| "I want Atlas to support X." | `conversation` | `development_request` |
| "There's something missing here; can you add it?" | `question` | `development_request` |
| "I need you to implement X." | `conversation` | `development_request` |

**Defect B — over-clarification held fully-specified requests.** A development
request scored `objective(0.25) + reference(0.30) = 0.55` against a `0.5`
clarification threshold, so it was gated out of the pipeline. The `reference`
reason came from `_RELATIVE_THAT_RE = <det> \w+ that`, which only matched a
ONE-WORD subject — so the relative "that" in *"a small bounded helper function to
the repository relevance module **that** returns …"* was misread as an unresolved
reference.

Result of the fix: **19/19 measured natural phrasings now classify as development
requests, and 15/19 reach the development need bridge** — the remaining 4 are
genuinely unresolvable without conversation context ("this module", "fix it",
"make this work") and still fail closed exactly as L6 requires.

## 3. Conversation capabilities implemented

### L1/L3 — structured change-request meaning (`atlas/conversation/development_intent.py`, new)

A pure, bounded, deterministic, Atlas-owned representation:

* `RequestModality` — imperative / request / need / question / statement
* `ChangeAction` — a **closed** semantic vocabulary: create / modify / remove /
  repair / document (with auditable surface forms; `action_forms()`)
* `TargetSurface` + `TargetKind` — syntactic target evidence: path / module /
  symbol / code_unit
* `MeaningStatus` — **exactly** the L6 set: known / inferred / ambiguous /
  unknown / unsupported
* `DevelopmentIntent` — the bounded bundle, with `evidence`, `constraints`,
  `negated`, `addressed_to_atlas`, `action_surface`

Two refinements came from real measurements, not from theory:

* **A gerund or past form cannot open an imperative.** "Fixing the capability is
  important." and "Built the capability." are STATEMENTS. Without this, the new
  layer read reports as change requests. (Found by the existing test suite.)
* **"make" is a LIGHT verb: its object decides.** "Can you make **that**
  simpler?" is a follow-up about the previous RESPONSE; "Could you make **X**
  work?" names an object. (Found by the conversation probe matrix.)

### L6 — ambiguity and uncertainty
Uncertainty is now explicit and typed rather than implicit: a change request that
names a concrete target is `known`, one that names only a code unit is
`inferred`, one that refers only by pronoun is `ambiguous`, and a change Atlas
cannot act on is `unsupported`.

### L4/L5 — partial
The layer grounds references against **the request's own named targets** (paths,
dotted modules, quoted identifiers). It does NOT yet resolve references against
CONVERSATION STATE — see §8.

## 4. Development capabilities implemented

* **§17 development language bridge — FIXED and proven end-to-end.** Natural
  phrasing now reliably enters the existing governed pipeline (see §5).
* **§22 fault localization** (`atlas/evolution/fault_localization.py`, new;
  `Atlas.fault_localization(...)`): ranks suspect locations from the change
  guard's changed paths/symbols, the plan's bounded verification target, and the
  existing repository graph (symbol regions, unambiguous callers/callees, import
  relations). Every suspect carries the evidence that produced it; distinct
  weights make the ordering auditable; no evidence ⇒ no suspects.

The existing pipeline — localization → context → ChangePlan → authoring →
structural authoring → sandbox verification → attribution → repair → approval →
promotion — is **unchanged**.

## 5. Real-world probes (real repository, real model, real pipeline)

### Development — the Command 3 gap is CLOSED

`Atlas.development_authoring_request(...)` with the real `qwen2.5-coder:7b`:

| request | before Command 4 | after |
| --- | --- | --- |
| "**Can you add** a module-level docstring line to `atlas/research/relevance.py` …, preserving behaviour?" | `{}` (classified `question`) | `ok=true`, `DEV-ed02c5e0d0c5e9f3`, **PENDING_APPROVAL**, 61 s |
| "Add a small bounded helper function to the repository relevance module **that** returns … Target `atlas/research/relevance.py`." | `{}` (over-gated as ambiguous) | `ok=true`, `DEV-01482ca9ca47c0b9`, **PENDING_APPROVAL**, 28 s |

Both: meaning status `known`, action `create`, correct localized target
`atlas/research/relevance.py`, `authorized=false`, `executed=false`, **0
promotions**. The human approval boundary held.

### Fault localization — real repository
```
changed_paths   ["atlas/evolution/change_guard.py"]
changed_symbols ["atlas.evolution.change_guard.characterise_change"]
verify_target   "tests/test_evolution_change_guard.py"
→ #1 characterise_change            score 1.00  lines 185-314  (changed_symbol)
  #2 atlas.evolution.change_guard   score 0.90  (changed_module + test_referenced)
  #3 atlas.evolution.development_diagnostic 0.50 (test_referenced + import_neighbour)
  #5 SelfDevelopmentLoop._guard_change 0.45 lines 752-787 (caller_of_changed)
  #6 TestCleanChanges.test_bounded_... 0.45 (caller_of_changed)
→ no evidence: available=false, reasons=["no change evidence was supplied"]
```
Real regions, real callers, and a test that exercises the changed symbol — all
correct, and nothing invented.

### Conversation probe matrix (§14, 19 turns, model-free)
Every turn produced a response (19/19). By category:

| category | turns | development reached | clarified |
| --- | --- | --- | --- |
| casual | 3 | 0 | 0 |
| follow_up | 3 | 0 | 1 |
| development | 7 | 4 | 3 |
| ambiguous | 3 | 0 | 3 |
| contextual | 3 | 1 | 1 |

Casual turns never leaked into the development route; the ambiguous category
("Change that." / "Fix this." / "Make it better.") produced **bounded
clarification, never an arbitrary selection** — L6 working as designed.

§17 convergence (deterministic): 8 equivalent phrasings → all change requests,
all `action=create`, modalities {imperative, need, request}. **Equivalent meaning
now converges on one Atlas representation.**

## 6. Specialist models

**Added: none.** Command 4 added **no** model and **no** dependency. This is a
deliberate outcome, not an omission:

* the highest-value work was architectural (the language/meaning layer), and it
  is deterministic — a model would have been strictly worse;
* the Command 3 candidate inventory already classified the remaining candidates,
  and nothing in this command's evidence changed those classifications;
* Atlas's dependency set is still **`requests>=2.28`** (+ `pytest` test extra).

Specialist status is unchanged from Command 3 where relevant: the semantic
similarity specialist is INTEGRATED / REAL-EXECUTED / VALIDATED; the code
generation specialist is INTEGRATED / REAL-EXECUTED / VALIDATED.

**Rejected/deferred:** unchanged from `docs/COMMAND_3_SPECIALIST_CANDIDATE_INVENTORY.md`.

## 7. Architectural mechanisms adapted (not imported)

* ast-outline / Probe / Astra / Aider **mechanisms** — already absorbed natively
  in Commands 2–3; Command 4 added the *change-request meaning* layer those
  projects do not have.
* §6/§11 L1/L3/L6 semantics — implemented **natively**, reusing the existing
  `TaskIntake` precedence chain (the new layer is consulted only for FALLBACK
  types; every governance/lifecycle/planning/investigation route still returns
  first).
* §22 fault localization — implemented natively from the existing repository
  graph. SBFL/Ochiai, mutation testing and model-based rankers were **NOT**
  added: no evidence justifies that machinery.

## 8. Tests

| File | Focus | Count |
| --- | --- | --- |
| `tests/test_development_intent.py` (new) | meaning layer (modality, action class, targets, L6 status, negation, light verb, malformed input, bounds), §17 convergence, and the **preserved** classification contracts | 34 |
| `tests/test_fault_localization.py` (new) | ranking, evidence reasons, real regions, bounds, determinism, fail-closed, contract | 19 |

Plus the modified suites: `test_conversation_task_intake.py`,
`test_conversation_development_intake.py` — **all green**.

**Coherent regression: 800 tests + 39 subtests passed, 0 failed** (23 files
spanning conversation, meaning, reference, semantics, repository map/context,
change guard, verification attribution, held-out boundary, specialist seams).

Two regressions were introduced by the first implementation pass and are
recorded honestly rather than reclassified:
1. the upgrade initially promoted `ACTION_REQUEST` too broadly ("Create a
   report.", "Write the report." must stay actions) — fixed by restricting the
   upgrade to fallback types plus an evidence test for action requests;
2. the light-verb over-reach ("Can you make that simpler?") — fixed by the
   light-verb/object rule.

## 9. Performance / resource observations

* No new dependency, no new resident model, no new process.
* The meaning layer is pure string work: sub-millisecond, no I/O.
* Fault localization over the real repository: bounded, in-memory; region/caller
  lookups reuse the cached `RepositoryMap` (which is built once, lazily, ~10 s on
  first use for this repository, thereafter cached).
* Real model latency in the probes: 28–78 s per governed authoring request
  (unchanged from Command 3 — Command 4 changed routing, not inference).

## 10. Known failures

**Pre-existing (NOT Command 4), reproduced at pristine `4f2ce7c`:**
* `tests/test_ambiguity_uncertainty.py::TestPendingQuestionRecording::test_orchestration_ambiguity_gate_records_the_pending_question`
  — **newly identified** during this command and verified to fail at the
  pristine baseline, so it is NOT caused by Command 4. Not modified, weakened or
  reclassified.
* `tests/test_builtin_self_knowledge.py::TestKernelWiring::test_kernel_architecture_provider_is_cache_only`
* `tests/test_evidence_governed_development.py::TestRealKernel`,
  `tests/test_evidence_directed_development.py::TestRealKernel::test_real_gap_produces_a_pending_approval_proposal`
* `test_intake_contract[H7-0]`, `test_development_need_confirmation_fails_closed`

**New failures: none.**

## 11. Remaining limitations (exact)

1. **Reference resolution from conversation state is NOT implemented.** A turn
   whose only target is a pronoun/demonstrative ("Could you modify this module?",
   "There's a bug in X; can you fix it?", "Now add tests for it.") still fails
   closed to clarification, because `TaskIntake.intake(text, history_length)` has
   no parameter for bounded conversation context and the `ConversationService`
   path routes through the D1 engine. This is the ONE remaining blocker for the
   full §14 development set. It is a **known, bounded, deliberately deferred**
   gap — not a silent one.
2. `Please make this work.` stays `action_request` (an artifact-action contract
   that existing tests explicitly protect) rather than development.
3. Fault localization has no wired consumer inside the repair loop yet: it is
   exposed as a read-only kernel surface (`Atlas.fault_localization`), like the
   other development-intelligence surfaces. Wiring it into repair CONtext
   selection is a bounded follow-up.
4. §18 (development specialist models) and §21 (test intelligence) were not
   started — no model was added, and no evidence demanded one.
5. §23/§24 (self-knowledge / specialist registry extension) were not touched:
   the existing catalogues and the existing specialist seam were already
   sufficient for everything this command did.

## 12. Exact next recommended step

**Implement bounded, explicit reference grounding through the conversation
state** — the single remaining blocker for §14's full development set, and the
completion of L4/L5.

Concretely (and in this order):
1. add an OPTIONAL, evidence-carrying parameter to `TaskIntake.intake`
   (`grounded_targets: tuple[str, ...] = ()`) that a caller WITH bounded state
   supplies; a `reference` ambiguity reason is then not raised when the reference
   is resolvable against those targets;
2. surface the bounded candidate set from `ConversationWorld` /
   `discourse_state` (already present — no new state, no transcript-as-state);
3. thread it through the D1 `ConversationEngine` call site.

This must stay evidence-driven: the caller supplies the referents it actually
has, and an unresolvable reference must still fail closed.
