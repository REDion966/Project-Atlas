# Evidence-Driven Improvement 2 — Conversational State Semantics

Post-Phase-D refinement of the D1 conversation layer. No new phase, no new
engine, no external model, no `config.toml` change. Baseline: HEAD
`8ec67fb58de3643591fe3e588512a47d96e3f0dd` (Improvement 1 uncommitted on top).

## Problem (evidence)

`ConversationEngine.state_updates` set `current_objective` to the turn's
extracted objective for **every** turn with a spec. Any meta turn therefore
clobbered the active work objective, and a correction was only *recorded*
(`ConversationState.corrections`) without altering the active interpretation:

- `"Do that again."` → `current_objective` overwritten
- `"What did we discuss?"` → `current_objective` overwritten
- `"Thanks, that helps."` → `current_objective` overwritten
- corrections recorded but never applied

## 1. Implementation

### Files changed

| File | Change |
| --- | --- |
| `atlas/conversation/turn_role.py` | **new** — bounded, deterministic turn-role representation (`TurnRole` enum + `detect_turn_role` + `corrected_subject` + marker sets) |
| `atlas/conversation/engine.py` | computes the turn role during `interpret`, exposes it on `EngineInterpretation`, records the extracted corrected subject, and makes `state_updates` role-aware |
| `atlas/conversation/semantic_intake.py` | new bounded `turn_role` field on `SemanticIntake` (+ `to_dict`, `build_semantic_intake(..., turn_role=...)`) |
| `tests/test_evidence_improvement_2.py` | **new** — 54 focused tests |
| `tests/test_investigation.py` | reconciled the one proven-stale test (see §2) |

Reused rather than duplicated: the L10 acknowledgement cue, the Phase-5
conversation-recall cues (from the existing builtin surface) and the bounded
repeat recognition (`is_repeat_request`). No second engine/intent system.

### Exact semantic-state changes

`TurnRole`: `NEW_OBJECTIVE`, `FOLLOW_UP`, `CORRECTION`, `CLARIFICATION`,
`REFERENCE`, `RECALL`, `ACKNOWLEDGEMENT`, `META_CONVERSATION`, `CONTINUATION`.

Detection precedence (most specific first): acknowledgement → recall →
continuation → correction (needs a prior objective) → clarification (needs a
prior objective) → bounded reference/repeat → bounded follow-up → meta →
default. Reference/follow-up/meta forms are **whole-turn anchored**, so a
genuinely instructed turn that merely contains "it"/"that"
("Research the Voyager mission and summarize it.") stays a new objective.

`state_updates` (the only writer of these bounded fields):

- `NEW_OBJECTIVE` → replaces `current_objective`
- `CORRECTION` → replaces `current_objective` with the **corrected subject**
- every other role → **preserves** `current_objective` (no update emitted, so the
  `ConversationStateManager` state object is not even churned)
- `subtasks` / `corrections` handling unchanged

### Correction-flow changes

Before: `_detect_correction` recorded `Correction(previous=current_objective,
corrected=<whole turn text>)` and `state_updates` then set `current_objective` to
that whole turn text; the corrected reading never drove anything.

After: `corrected_subject(text)` deterministically extracts the replacement
subject after the latest replacement marker (stripping fillers/articles, e.g.
`"Actually, I meant the Europa Clipper mission."` →
`"Europa Clipper mission"`). That subject is (a) the recorded
`Correction.corrected` and (b) installed as `current_objective`. The explicit
`correction` marker was added to the record cue set so `"Correction: ..."` is
recorded AND classified as a correction.

## 2. Tests

- **Focused (Stage 1):** `python -m pytest tests/test_evidence_improvement_2.py -q` → **54 passed**.
- **Stage 2 (directly affected):** conversation engine/state/service/core/context/
  task-intake/utterance/development-intake/bridge/antecedent/orchestration/
  turn-recall/independence + builtin (response, routing, self-knowledge, state
  answers) + both Improvement 1 files → **570 passed, 53 subtests passed**.
- **Stage 3 (regression batch):** D1–D5, C4.1, C5, C6.1, NLU1–6, L8, model
  provenance, phase116/123/125/129, capability routing/execution, architecture
  model, C3, phase32/33/58, approval manager, level2 approval, phase610,
  governance assurance, **and `tests/test_investigation.py`** →
  **810 passed, 1 failed** (the stale test below). After reconciliation:
  `TestAuthoringWiring` → **4 passed**.

### Stale test encountered (reconciled)

`tests/test_investigation.py::TestAuthoringWiring::test_kernel_wiring_has_no_change_supplier`
asserted `atlas._conversation._proposal_converter._change_supplier is None`
("no bounded deterministic author exists yet"). That premise was superseded by
the committed change-supplier unification (`ab2b63d`): the kernel wires ONE
authoritative `CompositeChangeSupplier([DeterministicChangeSupplier(),
ScaffoldChangeSupplier(), model_supplier])` into both the F9 controller and the
conversational P17 authoring seam, with the model supplier present only when
`development.model_assisted_authoring` is explicitly true. Verified empirically:
the supplier is not `None`. The assertion contradicted the current authoritative
contract, so it was **updated** — renamed to
`test_kernel_wiring_uses_bounded_deterministic_change_supplier` and asserting the
current contract (composite wired, deterministic-first order, no model supplier
by default) with the reason documented in the test docstring. Nothing was
deleted; coverage of the wiring contract was preserved.

`tests/test_conversation_turn_recall.py::...::test_recall_does_not_mutate_state_manager`
(the pre-existing failure from Improvement 1) now **passes** — it was not stale,
it was detecting exactly this defect and is now satisfied.

No environmental failures; no unresolved failures carried forward.

## 3. Real interaction

Fresh temporary database, real `Atlas.chat(...)`.

**Sequence 1** — `Research the Artemis moon program.` / `What did you find?` /
`Thanks, that helps.` / `What were we talking about?` / `Continue.` /
`Actually, I meant the Europa Clipper mission.` / `What did you find about that?`

| Turn | `current_objective` after | Verdict |
| --- | --- | --- |
| 1 Research the Artemis moon program. | `Research the Artemis moon program.` | PASS |
| 2 What did you find? | unchanged | PASS |
| 3 Thanks, that helps. | unchanged | PASS |
| 4 What were we talking about? | unchanged | PASS |
| 5 Continue. | unchanged | PASS |
| 6 Actually, I meant the Europa Clipper mission. | `Europa Clipper mission` (+ `corrections[0].corrected = "Europa Clipper mission"`, `captured_entities = ["Europa Clipper"]`) | PASS |
| 7 What did you find about that? | `Europa Clipper mission` (corrected context used) | PASS |

**Sequence 2** — `Explain how you work.` / `Thanks.` / `What did we discuss?`
→ `current_objective` stays `None` throughout, and the self-knowledge/recall
answers are byte-for-byte the existing deterministic responses. PASS.

**Variants** (objective set first, then the meta turn): `Thanks.`, `Got it.`,
`Okay, understood.`, `Go on.`, `Keep going.`, `Do that again.`,
`Tell me more about that.`, `What about its latest launch?` → **all preserved**.
`Now investigate SpaceX.` → objective replaced. PASS.

**Knowledge context** (`last_knowledge`): created by the knowledge turn, and
still identical after `Thanks.` and `What did we discuss?`; `What did you find?`
answers from it (metadata `knowledge_followup.kind == "find"`). PASS.

## 4. Architecture audit

- No new engine / intent system / memory store / research path.
- No external model dependency (`model_used=False` throughout; no config change).
- No new authority: `SemanticIntake.provenance["authority"] == "none"` unchanged;
  approval language still returns `no_active_proposal`/`no_session` and creates
  no proposal (test-pinned).
- No governance/authority/dispatcher/D4/D5 modification.
- `config.toml` unchanged; no roadmap change; no D6.
- Fail-closed intact (unrecognized turns keep default behaviour; no fabrication).
- Improvement 1 intact (all Improvement 1 tests pass; knowledge context preserved).

## 5. Remaining evidence-backed gaps

Observed by this validation only:

- Bounded reference coverage is intentionally narrow: bare single-word
  references ("What about its latest launch?" is covered; a standalone pronoun
  turn with no bounded phrase is not) still rely on the existing
  reference-resolution handler, which may return UNRESOLVED.
- `"What did you find about that?"` reaches the knowledge path with the literal
  topic "that" (no knowledge match) — a bounded topic-extraction gap in the
  Improvement 1 bridge, not a state-semantics defect. The corrected context is
  preserved in state, but the knowledge query is not rewritten from it.
- Correction semantics replace the objective with the corrected subject; they do
  not merge it with the superseded objective ("the current mission status" style
  refinements are stored as their own subject).

No speculative features are proposed.

## 6. Git state

- HEAD: `8ec67fb58de3643591fe3e588512a47d96e3f0dd` (unchanged; no commit, no push)
- Branch: `main`
- Modified: `atlas/conversation/builtin_response.py`,
  `atlas/conversation/conversation_service.py`,
  `atlas/conversation/conversation_state.py` (Improvement 1),
  `atlas/conversation/engine.py`,
  `atlas/conversation/semantic_intake.py`,
  `tests/test_investigation.py`
- Untracked: `atlas/conversation/turn_role.py`,
  `tests/test_evidence_improvement_1.py`, `tests/test_evidence_improvement_2.py`,
  `docs/EVIDENCE_IMPROVEMENT_1.md`, `docs/EVIDENCE_IMPROVEMENT_2.md`
- `config.toml`: unchanged
