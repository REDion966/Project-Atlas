# ATLAS NEXT ARCHITECTURE PROPOSAL

Baseline: branch `main`, HEAD `f6737dbdc6c9e254b37c3abf588a4a2c54be945a` (== `origin/main`, 0 ahead / 0 behind), tracked tree clean. Untracked: `ATLAS_ARCHITECTURE_HANDOFF.md`, `ATLAS_SEMANTIC_BOUNDARY_HANDOFF.md`, and the three pre-existing artifacts. No source, test, or documentation change; no commit; no push.

## 1. Current Architectural Finding

Atlas's language path is real but split across two layers that do not share a representation.

**Layer 1 — the conversational boundary (where turns actually arrive).** `ConversationService.send` (`atlas/conversation/conversation_service.py:433`) and `.stream` (`:702`) run: `_intake` → `_apply_entity_identification` → `_apply_reference_resolution` → a **single-label handler cascade** (`:524-652`) that returns as soon as one `TaskType` claims the turn → `_maybe_handle_builtin_response` (`:356-375`) → and only *then*, if nothing claimed the turn, `self._cognition_api.process(...)` (`:654-698`).

**Layer 2 — the cognition runtime.** `RuntimeCoordinator.process` (`atlas/runtime/runtime_coordinator.py:165`) runs a fixed 15-stage pipeline (`:359-379`) with `UNDERSTANDING` at stage 4, `REASONING` at 6, `PLANNING` at 7, and capability routing/dispatch inside PLANNING (`:687-689`).

Three consequences follow directly from the code, and they matter more than any single missing feature:

1. **Cognition is reached only by the residue.** For every turn a governed handler claims — investigation, planning, approval, execution, recovery, verification, report, autonomy — `send` returns before `cognition_api.process` is ever called. Three of the four example utterances from the prior handoff are in this category: "Investigate the cognition pipeline…" is claimed by the investigation handler, and the two reference turns never reach the runtime either (they are answered, or declared unsupported, at the builtin layer). **Any interpretation step placed inside the runtime pipeline is architecturally unreachable for exactly the utterances that motivated this investigation.** That reframes the problem: the interpretation step belongs at the conversational boundary, where the meaning is decided, not inside a runtime that only sees the leftover.

2. **The routing decision is single-label and is made by substring cues.** `TaskType` is one of 20 enum values and `_classify` (`task_intake.py:949-1121`) returns the first cue family that hits, with hand-written guards for the few compounds it must tolerate (`_investigation_leads_compound`, `_mention_only_hijack`, `:971-1006`). Compound awareness therefore exists as **special-case exceptions**, not as representation.

3. **Meaning is produced once and then transported three different ways.** `[A]` the full `TaskSpec` crosses into cognition as `metadata["task"] = spec.to_dict()` (`conversation_service.py:657`); `[B]` `TurnMeaning` crosses as a dedicated parameter (`:676`, `:966`) and lands in `CognitionState.meaning` (`runtime_coordinator.py:197`); `[C]` the projected dict is echoed back into `decision_data`/`reasoning_data`/`planning_data` under `"meaning"` (`:577-578`, `:610-611`, `:663`). Only two things in that payload are ever acted on: `needs_clarification`, which fail-closedly blocks capability analysis and planning (`:590-595`, `:652-671`), and `meaning["goal"]` as a reasoning-text fallback (`:557-567`). `atlas/reasoning/` contains no occurrence of the string `meaning` at all — the reasoning and planning *modules* never read it; only the coordinator does.

So the system has **recognition without representation and without consumption**. That is the finding to develop, and it is sharper than "a phrase table is too small".

## 2. Validated Capability Gap

Four claims were re-checked against source. Two hold, two are corrections to the prior handoff — stated explicitly as requested.

**Corrected — the handoff's "one projection" model understates the boundary.** It is not `TaskSpec → TurnMeaning → cognition`. `TaskSpec` **itself** crosses, as `metadata["task"]` (`conversation_service.py:657`), independently of `TurnMeaning`. There are three parallel transports of overlapping data with three different consumers, and no single owner of "the meaning of this turn". A change that only extends `TurnMeaning` would leave transports `[A]` and `[C]` untouched and inconsistent.

**Corrected — "reference and entity mechanisms produce evidence with little or no downstream consumer" is too uniform.** `resolved_reference` is genuinely write-only: its only occurrence outside its writer (`conversation_service.py:1230-1241`) is the reader in `turn_meaning.py:176`. But `identified_entities` **does** have a real consumer chain: `_apply_entity_identification` (`:1120-1157`) writes the evidence *and*, when exactly one entity is named, sets `state.current_subject` — which the reference resolver later consults via `_established_subject` (`reference_resolution.py:290-310`). Entity identification is therefore the **only** interpretation feature in Atlas that closes its own loop end-to-end. That is a constructive precedent, not a deficiency, and the proposal below is modelled on it.

**Confirmed — no operand/act representation exists.** `TaskSpec.intent` is a text slice from the first cue onward (`task_intake.py:1123-1137`); `goal` is a template rendering of that slice; `constraints`/`priorities`/`success_criteria` are cue-triggered spans (`:408-439`). Nothing can say *which part of the text is the target of which operation*, which is precisely what "Investigate the cognition pipeline and compare it with the previous result" requires.

**Confirmed and sharpened — the unreachability problem.** My working hypothesis during this investigation was that reference failures are caused by unpopulated state (`latest_result` never written). That is **false**: `latest_result` is written on eleven governed paths (`:1521, 1600, 1782, 2011, 2172, 2406, 2545, 3325, 3451, 3576, 3701, 3828`). The failure of "What about the previous result?" is therefore *not* a missing write. "The result" is a recognized phrase (`reference_resolution.py:159`); the turn fails because (i) the qualifier **"previous"** — a discourse-ordering concept — has no representation, and (ii) even a successful resolution is unread. Two independent gaps (representation, consumption) behind one symptom.

**The demonstrated gap, stated once:** Atlas can decide *which kind of turn* this is, but cannot represent *what was said about what*, and has no place to put such a representation that any consumer reads. Multi-act requests degrade to one label; corrections have no act; comparisons have no operands; and referenced values, once bound, change nothing.

## 3. Architectural Options Considered

**Option A — Extend `TaskSpec` in place** (add operand/act fields to the existing frozen dataclass). Cheap, and `TaskSpec` is already the only behaviour-determining object. Rejected as the *primary* step: `TaskSpec` is a routing record whose `to_dict()` is serialized into cognition metadata; growing it with discourse structure would couple routing to interpretation, keep the "one object, two jobs" problem, and make every existing consumer of `to_dict()` carry a larger, less stable payload.

**Option B — A dedicated deterministic interpretation step at the conversational boundary, emitting a bounded reading; reuse `TurnMeaning` as the contract that carries it.** The interpreter is a pure function over inputs that already exist (normalized text, `ConversationState`, `ConversationContext`, entity catalog, ambiguity report); `TurnMeaning` already is immutable, already crosses the boundary, and already has a fail-closed shape-acceptor (`accept_turn_meaning`, `cognition/api.py:48`). Existing evidence producers (entities, references, normalization) become its building blocks rather than parallel silos. **Recommended.**

**Option C — Evolve `UnderstandingEngine` into the turn interpreter.** Rejected. It runs inside the pipeline (stage 4) so it is unreachable for handler-claimed turns; its lifecycle is knowledge accumulation over a persisted graph (`understanding_engine.py:183-215`, storage sync), not per-turn meaning; and its outputs (concepts/insights/patterns) have no act or operand semantics. Making it interpret turns would conflate durable knowledge with ephemeral meaning and put turn interpretation behind a storage dependency.

**Option D — Do nothing structural; wire the existing evidence to existing consumers.** Rejected as sufficient, retained as a mandatory prerequisite probe. It is genuinely small, and for `resolved_reference` alone it would fix "you found it and ignored it". But it cannot fix "What about the previous result?" (the qualifier is not representable), cannot express multi-act turns, and cannot represent a correction — so it is a step *inside* the recommended direction, not an alternative to it.

**Option E — A semantic graph / AST / dialogue manager / embeddings.** Rejected outright. There is no repository evidence of a demonstrated capability that requires it, it violates the smallest-change rule and model independence, and it would create a second intelligence identity alongside the deterministic one. Explicitly out of scope.

These are not scored; they differ in *where the representation lives*, and B is chosen because the code shows the decision point is at the conversational boundary and the contract object already exists there.

## 4. Recommended Direction

**Recommendation (not authorization):** introduce one deterministic interpretation step at the conversational boundary that produces a **bounded reading** — an ordered, bounded set of acts, each with operands bound to text or state — and make that reading *consumable*, using `TurnMeaning` as the transport and one existing consumer per capability.

Three properties make this the smallest change that actually closes the gap:

- It reuses the boundary that already exists (`_intake` in `conversation_service.py:1012`) instead of adding a runtime stage that the interesting turns never reach.
- It reuses the contract that already crosses the boundary (`TurnMeaning`) instead of creating a second meaning channel, and it inherits the existing fail-closed acceptance check.
- It follows the one feature in the repository that already works end-to-end (`identified_entities` → `current_subject` → reference resolution), generalizing that pattern rather than inventing a new one.

`TaskType` remains the routing decision. The reading supplies **what the operands are**; it does not decide which governed handler runs, and it never authorizes. Where the reading is ambiguous, existing behaviour is preserved (fail closed), and in the one case where it can improve on today's behaviour, it improves the *answer*, not the authority.

## 5. Proposed Boundary and Responsibilities

**The boundary is the conversational turn, not a pipeline stage.** Two artefacts:

- **Interpreter (new, pure):** `text → reading`, given `ConversationState`, `ConversationContext`, entity catalog, and the existing ambiguity assessment. Deterministic, side-effect free, no I/O, no provider, no mutation of state. Responsibilities: segment a turn into bounded acts; identify each act's operation using the *existing* cue vocabulary where possible; bind operands from recognized entities, resolvable references, and bounded text spans; mark each act's status (`resolved` / `unresolved` / `ambiguous`); link a correction to the reading it supersedes. It must not select a handler, must not produce a plan, must not execute.
- **Reading (contract):** the structured output, carried on `TurnMeaning`. Immutable, versioned, bounded in size, JSON-safe, and accepted at the cognition boundary by the existing fail-closed shape check.

**Responsibilities explicitly retained elsewhere.** `TaskIntake` keeps classification. Governed handlers keep authority, approval, and execution. `ConversationState` keeps being the store of *facts* (it must not become a store of interpretations). The runtime keeps its stage order and its `needs_clarification` gate. The builtin responder keeps rendering.

**Separation that must be preserved.** The interpreter must not import the runtime, must not be called by `RuntimeCoordinator`, and must not appear in `_build_stage_definitions`. The runtime may receive the reading as data (as it already receives `metadata["task"]`), but it must never *depend* on it, and the existing duck-typed projection (`runtime_coordinator.py:46-64`) must keep degrading to `{}` when absent.

## 6. Meaning Representation Requirements

Requirements only — deliberately not a full design.

1. **Acts are ordered and bounded.** A turn yields a small, capped sequence of acts (a single-act turn is the common case). Order matters because multi-part requests are sequential ("investigate X **and compare** it with Y").
2. **Each act names an operation and its operands.** The operation reuses the existing `TaskType` vocabulary where it applies, so the reading does not invent a parallel type system; an act whose operation is not recognized is carried as an explicitly unknown act rather than silently dropped.
3. **Operands carry a role and a provenance.** At minimum: the text span the operand came from, or the state field it was bound to. Provenance is what makes the reading auditable and is the mechanism by which a consumer can decide *not* to act.
4. **References reuse the existing resolution enum.** `RESOLVED` / `UNRESOLVED` / `AMBIGUOUS` (`reference_resolution.py:76-81`) and the unique-referent rule are already correct and fail closed; the reading records the outcome rather than re-deciding it.
5. **Ambiguity is per-act, not per-turn.** Today ambiguity is one score for the whole turn (`task_intake.py:1135-1181`). A turn can be unambiguous in its first act and ambiguous in its second; representing that is what keeps fail-closed behaviour usable instead of blunt.
6. **Corrections are a relation, not a new utterance.** A correction must be able to name the reading it supersedes and the operand it replaces, so "No, I meant the cognition pipeline" can rebind rather than restart.
7. **Residue is representable.** Acts the system did not handle must survive into the response path so the answer can be honest ("I did the first part; I cannot do the second") instead of silently truncated.
8. **Bounded and versioned.** A fixed maximum on acts, operands per act, and span length; an explicit version marker; unknown/missing blocks degrade to today's behaviour.

## 7. Integration With Existing Atlas Systems

- **`TaskSpec` / `TaskIntake`:** unchanged in contract. The interpreter may *read* the spec's ambiguity and classification as inputs; it must not become a second classifier. Operand binding optionally improves the target the governed handlers resolve (today `_extract_objective` slices text from a cue, `task_intake.py:1123-1137`), which is the one place a handler target could legitimately become operand-derived.
- **`ConversationState`:** consumed read-only. No new interpretation storage in state. The one existing write pattern (`current_subject` on a unique entity, `conversation_service.py:1155-1156`) stays as-is and is the precedent for how a reading may influence later turns.
- **References / entities / context:** these stop being parallel silos and become the interpreter's inputs; their outputs are recorded in the reading with provenance, so `resolved_reference` finally has a reader.
- **`TurnMeaning` / cognition boundary:** the reading rides on the existing contract; `accept_turn_meaning` keeps rejecting malformed input; `TurnMeaning` stops being a lossless-copy exercise and becomes the carrier of the reading.
- **Cognition / reasoning / planning:** the reading reaches the runtime as data and may inform the reasoning *text*; it must not inject plan steps or capabilities. The existing `needs_clarification` gate (`runtime_coordinator.py:590-595, 652-671`) stays the only meaning→behaviour coupling in the runtime.
- **Builtin responder:** the first, cheapest consumer — a bound operand lets "What about the previous result?" be answered from `latest_result` instead of the unsupported notice. It already receives `message_count` and an unused `session_context` parameter (`builtin_response.py:195, 226`), so the plumbing exists.
- **Governed handlers:** consume the reading only as target evidence. Approval, execution, verification, recovery, and investigation flows are otherwise untouched.

## 8. Governance / Safety / Model Independence

- **No authority is created.** The interpreter produces a reading; `TaskType` still selects the handler; handlers still own approval and execution. The reading cannot approve, execute, mutate, or dispatch — `RuntimeCoordinator` remains the only orchestrator and its stage order is untouched.
- **Fail-closed is preserved and extended.** Unknown operations become unknown acts, not guesses. Ambiguous references stay ambiguous. Unresolvable operands leave the act unresolved and the existing unsupported/clarification path answers. If the reading cannot be built, the turn behaves exactly as today.
- **Determinism holds.** The interpreter is a pure function over deterministic inputs using the existing `collapse_whitespace` normalization; no randomness, no clock, no network, no provider. `model_used` stays `False` and the local-only provider gate (`atlas/ai/routing/router.py:75-79`) is untouched.
- **Model independence is definitional.** The reading's vocabulary is Atlas's own; external models remain development collaborators and never a runtime interpreter.
- **Ambiguity must never become action silently.** Per-act ambiguity is the mechanism that lets one act proceed while another blocks — but only where the *existing* governed path already permits that act to proceed.
- **No new milestone.** This is a change within existing boundaries, not a roadmap item; no L11, no reopened phase.

## 9. Smallest Proof-of-Capability

The smallest demonstration that the boundary is *working* — not merely present — needs one utterance where the reading changes an observable, deterministic outcome, plus one where it must fail closed:

**Probe 1 (consumption).** "What about the previous result?" — after a governed turn has written `latest_result`, the interpreter binds an operand `{role: result, state_field: latest_result, reference_status: RESOLVED}` and the builtin responder answers from it. Observable change: `unsupported` → a deterministic answer citing the prior result. This proves a previously write-only channel now has a reader.

**Probe 2 (representation).** "Investigate the cognition pipeline and compare it with the previous result." — the reading yields two ordered acts: `{operation: investigate, operand: "the cognition pipeline"}` and `{operation: unknown/compare, operands: [turn-1 act, latest_result]}`. Observable change: routing is unchanged (the investigation handler still claims the turn, per current behaviour), and the response honestly reports that the second act was not performed. This proves multi-act meaning is representable and that residue is surfaced rather than silently dropped.

**Probe 3 (fail-closed).** "No, I meant the cognition pipeline." — with no prior reading to supersede, the correction act is carried as `unresolved` and the turn falls back to today's behaviour exactly. This proves the new capability does not guess.

Probes 1 and 2 are the capability proof; Probe 3 is the safety proof. Each is deterministic and can be asserted as a unit test.

## 10. Implementation Scope

If implementation is authorized, the smallest coherent scope is:

- **New:** one pure interpreter module under `atlas/conversation/` (segmentation, act identification over the existing cue vocabulary, operand binding from entities/references/spans, per-act status, correction linkage) plus its unit tests.
- **Extended:** `turn_meaning.py` — a bounded, versioned `acts`/`operands` block with provenance; the existing fields and `to_reasoning_meaning()` remain unchanged so every current consumer is unaffected.
- **One consumer:** `builtin_response.py` answering from a bound operand (Probe 1/2), wired through the existing `session_context` seam.
- **Optional second consumer:** operand-derived target in the governed-target path, only if Probe 2 shows the slice-based target is actually wrong.
- **Tests:** interpreter unit tests (including negative/overmatch cases), contract acceptance tests proving an old-shaped and new-shaped contract both pass, regression tests proving `TaskType` routing, handler selection, approval/execution flows, and the `needs_clarification` gate are unchanged.

Not in scope: any runtime stage change, any handler behaviour change beyond target evidence, any state schema change, any new roadmap item.

## 11. Risks and Failure Modes

- **Interpretation becomes a second router.** The most likely failure. Mitigation: the reading never selects a handler; `TaskType` routing and the cascade order are pinned by regression tests.
- **Contract bloat and version skew.** Three transports already overlap; adding a fourth would be worse. Mitigation: extend `TurnMeaning` only, keep `metadata["task"]` stable, and make the new block optional and versioned so absent means today's behaviour.
- **Over-interpretation (confident wrong readings).** Mitigation: per-act status, provenance on every operand, unknown acts stay unknown, and ambiguous acts fail closed.
- **Silent capability inflation.** Multi-act residue must be reported, never quietly performed or quietly dropped.
- **Coupling the interpreter to the runtime.** Mitigation: the interpreter imports nothing from `atlas/runtime`; a test asserts it is not referenced by `_build_stage_definitions`.
- **Performance/complexity creep.** Mitigation: hard caps on acts, operands, and spans.
- **Test-surface growth.** Mitigation: extend contract tests rather than duplicating them; keep one assertion per required behaviour.

## 12. Acceptance Criteria

1. `TaskType` classification, handler selection, and the handler cascade order are byte-for-byte unchanged for the existing suites.
2. Approval, execution, verification, recovery, and investigation flows are unchanged, including all fail-closed paths.
3. A malformed or absent reading leaves behaviour identical to today (the existing acceptance check keeps passing).
4. Probe 1: a resolvable result reference produces a deterministic answer instead of the unsupported notice.
5. Probe 2: a two-act turn yields two ordered acts with a represented residue, and the response reports the unperformed act honestly; routing is unchanged.
6. Probe 3: an unlinked correction does not guess and falls back to current behaviour exactly.
7. Determinism: identical inputs → identical readings; `model_used` remains `False`; no provider contact; no network.
8. Bounds: readings respect the act/operand/span caps; JSON-safe serialization holds.
9. Model independence and the local-only provider gate are unchanged.
10. No new runtime stage; the interpreter is not imported by the runtime.

## 13. Evidence Index

- `atlas/conversation/conversation_service.py`: `send` :433; `stream` :702; handler cascade :524-652; cognition handoff `metadata["task"]` :657 and task echo :698; turn-meaning pass :676, :966; `_intake` :1012; `_apply_entity_identification` :1120-1157 (state write :1155-1156); `_apply_reference_resolution` :1159-1228; `_attach_resolved_reference` :1230-1241; `latest_result` writes :1521, :1600, :1782, :2011, :2172, :2406, :2545, :3325, :3451, :3576, :3701, :3828
- `atlas/conversation/task_intake.py`: `TaskType` :59-81; cue sets :88-129, :166-188, :408-439; `_classify` :949-1121 (compounds :971-1006); `_extract_objective` :1123-1137; `_assess_ambiguity` :1135-1181; `TaskSpec` :776-820
- `atlas/conversation/turn_meaning.py`: contract :65-114; `_INTENT_FIELDS` :49-62; `to_reasoning_meaning` :85-114; `build_turn_meaning` :150-192; `resolved_reference` reader :176
- `atlas/conversation/reference_resolution.py`: status enum :76-81; `_REFERENCE_PATTERNS` :120-189; `resolve` :319-382; `resolve_contextual` :384-448; `_established_subject` :290-310; multi-word guard :53-73
- `atlas/conversation/entity_identification.py`: :101-128
- `atlas/conversation/conversation_state.py`: `ConversationState` :32-152; `ConversationStateManager` :155-239
- `atlas/conversation/conversation_context.py`: :29-104
- `atlas/conversation/builtin_response.py`: `respond` :191-220 (`session_context` :195, `message_count` :196); `_classify` :240-285; `_render_status` :486; unsupported :623-634
- `atlas/cognition/api.py`: acceptance :48-55
- `atlas/cognition/models.py`: `CognitionState.meaning` :179
- `atlas/runtime/runtime_coordinator.py`: `_project_meaning` :46-64; `_requires_clarification` :67-69; stage list :359-379; `_stage_understanding` :470-498; REASONING meaning use :550-623; PLANNING gate :646-671; capability route/dispatch :687-689
- `atlas/understanding/understanding_engine.py`: :1-13, :130-215
- `atlas/ai/routing/router.py`: local-only gate :75-79
- `atlas/reasoning/controller.py`: `create_plan` :20-32
- Precedent test: `tests/test_turn_meaning_boundary.py` (determinism :49-53, immutability :55-58, reference block :86-96, acceptance :110-118)

## Final Statement

**Is implementation justified now?** Not yet, on the evidence in this document alone. The gap is validated in two of four claims and corrected in two; the direction is architecturally sound, but the repository does not yet contain a demonstration that a consumer would observably behave differently for the *representation* half (only for the consumption half, via Probe 1). One cheap prerequisite probe closes that gap.

**Smallest implementation.** One pure interpreter at the conversational boundary producing bounded per-act readings with operands and provenance, carried on an extended `TurnMeaning`, consumed first by the builtin responder via the existing `session_context` seam. No runtime stage, no handler behaviour change, no state schema change.

**Must be verified before implementation.** (1) Reproduce the four example utterances at HEAD with deterministic probes and record current outcomes; (2) confirm Probe 1's observable change is achievable using only the existing `latest_result` writes; (3) confirm the handler cascade really does return before cognition for those turns, so the boundary choice is justified; (4) confirm both old-shaped and new-shaped `TurnMeaning` payloads pass `accept_turn_meaning`; (5) confirm the existing suites pin `TaskType` routing and the `needs_clarification` gate before any change.

**Explicitly should NOT be implemented yet.** A semantic graph or AST; embeddings or vector search; any LLM/classifier participation in interpretation; a dialogue manager; a new runtime pipeline stage; capability dispatch or planning driven by the reading; autonomous action from interpretations; re-planning; any new roadmap milestone (no L11, no reopened phase); and no change to `ConversationState`'s role as a facts-only container.
