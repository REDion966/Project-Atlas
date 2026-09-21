# ATLAS SEMANTIC BOUNDARY HANDOFF

## 1. Baseline

- Branch: `main`
- HEAD: `f6737dbdc6c9e254b37c3abf588a4a2c54be945a` — "feat: expand bounded language recognition from L9 evidence"
- origin/main: identical (`f6737db`); 0 ahead / 0 behind
- Working tree: no tracked modifications, nothing staged. Untracked: `ATLAS_ARCHITECTURE_HANDOFF.md` (created by the previous investigation), plus the three pre-existing artifacts `atlas_entry_inspection.txt`, `atlas_entry_references.txt`, `mission_output.txt`.
- This investigation changed no source, no test, and no documentation other than the single file below.

## 2. TaskSpec

`TaskSpec` (`atlas/conversation/task_intake.py:776-820`) is a frozen dataclass with 16 fields:

| Field | What is actually in it | How it is produced |
|---|---|---|
| `task_id`, `input_hash` | stable hash of the raw text (same value twice) | `_stable_hash(raw)` :1221, :1236 |
| `task_type` | one of 20 `TaskType` enum values (:59-81) | `_classify(normalized)` :949-1121, single-label cue cascade |
| `intent` | a **text slice** starting at the first recognized objective cue | `_extract_objective` :1123-1137 |
| `goal` | a template rendering of type + intent + constraints + priorities + success criteria | `_render_goal` :1199-1205 |
| `constraints` | text spans following a cue from `_CONSTRAINT_CUES` (:408: must/without/using/only/keep/do not/avoid) | `_extract_items` :1154 |
| `priorities` | text spans after `_PRIORITY_CUES` (:420: first/urgent/priority/important/asap) | `_extract_items` :1155 |
| `success_criteria` | text spans after `_SUCCESS_CUES` (:429: done when/so that/verify/make sure/until) | `_extract_items` :1156 |
| `context` | `{history_length, concepts, token_count, length}` (:890-898) — `concepts` is literally the **first N tokens** of the text; plus dynamically added keys `resolved_reference` and `identified_entities` | `_build_context` :890; enriched by conversation_service.py:1240, :1152 |
| `ambiguity` | `AmbiguityReport{ambiguity_score, ambiguities, clarification_questions}` (:770-773) | `_assess_ambiguity` :1185 |
| `confidence` | rule-derived float from type/objective/success/model-assist | `_confidence` :1192 |
| `needs_clarification` | `task_type in (ACTION_REQUEST, DEVELOPMENT_REQUEST) and ambiguity_score >= 0.5` | :1206-1209 |
| `source`, `verified`, `model_metadata` | `"deterministic"`/`"model_assisted"`, `verified = not using_model`, model metadata only when a parser was injected | :1211-1218 |
| `created_at` | clock timestamp — the only non-deterministic field | :1235 |

**Genuinely represented:** the operational act (`task_type`), a provenance anchor, and a single bounded text slice. **Merely inferred temporarily during classification:** `intent`, `goal`, `constraints`, `priorities`, `success_criteria` are cue-triggered substrings, not parsed structures. Nothing carries operand structure, negation scope, relations between items, or alternatives. Even `context["concepts"]` is a token slice, not concepts. `TaskSpec` is therefore a **routing record with provenance**, not a meaning structure.

## 3. TurnMeaning and ReasoningMeaning

`TurnMeaning` (`atlas/conversation/turn_meaning.py:65-114`) holds `intent`, `uncertainty`, `reference`, `source_text`, `provenance`:

- `intent` — deep copy of the 12 `_INTENT_FIELDS` (:49-62: task_id, task_type, intent, goal, constraints, priorities, success_criteria, confidence, needs_clarification, source, verified, input_hash).
- `uncertainty` — copy of `spec.ambiguity.to_dict()` (:166-171).
- `reference` — copy of `spec.context["resolved_reference"]` if present (:173-178).
- `source_text` — bounded 500 chars (`MAX_SOURCE_TEXT_CHARS` :39).
- `provenance` — `{source: "deterministic", task_id, input_hash}` (:180-184).

Its own docstring settles the canonical question: *"Not a second TaskSpec — it is a bounded projection of existing fields"* (:21), *"behaviour-neutral"* (:23). `_INTENT_FIELDS` deliberately excludes `ambiguity` and `context` because they ride in their own blocks (:46-48).

There is **no class named `ReasoningMeaning`.** `to_reasoning_meaning()` (:85-114) returns a plain `dict` containing task_type, intent, goal, constraints, priorities, success_criteria, confidence, needs_clarification, ambiguity_score, ambiguities, and `reference{field,value}`. So "ReasoningMeaning" is a projection method, not a type.

- **Information added:** bounds, role separation, deep-copy isolation. No new meaning.
- **Information lost:** `context` (including `identified_entities`), `source`, `verified`, `model_metadata`, `created_at`, `task_id` (absent from the reasoning projection; present only in `provenance`), and `ambiguity.clarification_questions` (not projected).
- **Actual path:** `conversation_service.py:676` (send) / `:966` (stream) → `CognitionAPI.process(..., turn_meaning=...)` → `cognition/api.py:48` `accept_turn_meaning` (fail-closed shape check; malformed is dropped, and the contract "is never consumed here", :45) → `services/cognition_service.py:127`/`:153` → `runtime_coordinator.process` → `state.meaning = _project_meaning(turn_meaning)` (`runtime_coordinator.py:197`, `CognitionState.meaning` at `atlas/cognition/models.py:179`).
- **What actually reaches cognition and is used:** only three things. `meaning["goal"]` becomes the reasoning text when no explicit goal was given (:557-567); `needs_clarification` gates capabilities and blocks planning (:590-595, :652-671); the rest of the dict is echoed into `decision_data`/`reasoning_data`/`planning_data` under `"meaning"` (:577-578, :610-611, :663).
- **What never reaches cognition:** identified entities, and every field of the contract that has no reader — `atlas/reasoning/` contains **zero** occurrences of the string `meaning`, so the reasoning and planning *modules* never read the structured meaning at all; only the coordinator does.

## 4. Context / References / Entities / Ambiguity

**ConversationState** (`conversation_state.py:32-121`) is immutable with all-Optional slots: `current_subject`, `current_task`, `current_investigation`, `active_proposal_id`, `active_proposal_fingerprint`, `pending_approval_id`, `evolution_proposal_id`, `recovery_proposal_id`, `recovery_approval_id`, autonomy counters, `development_intent`, `pending_question`, `pending_confirmation`, `latest_result`, `relevant_prior_action`, `turn_id`. Managed by `ConversationStateManager` (:155-239: update/clear/reset_field/begin_turn/replace_topic). **Limitation:** every fact is a **single scalar** (one subject, one result, one prior action) with no history and no record of *why* it was set — and it stores **facts, not interpretations** (its own header states "a decision surface — it stores facts", :11).

**ConversationContext** (`conversation_context.py:36-104`): bounded window of the last 10 messages × 500 chars plus a copy of `state`. Read-only by value. Consumers: the builtin responder and the resolver's contextual pass.

**References** (`reference_resolution.py`): `_REFERENCE_PATTERNS` (:120-189) is an ordered (longest-phrase-first) table mapping phrase groups → candidate **state fields** → category. `resolve` (:319-382) returns `RESOLVED` only when exactly one candidate field is populated; multiple → `AMBIGUOUS` (never guesses); none → `UNRESOLVED`. `resolve_contextual` (:384-448) handles `the <phrase>` and bare `it/that/this` against candidate subjects drawn from `current_investigation`, recent user turns carrying a subject lead cue, or `current_subject` as a last-resort fallback (:290-310). Consumers: `conversation_service._apply_reference_resolution` (:1159-1228). Only `AMBIGUOUS` changes behaviour (early return of a clarification message via `_orchestration_clarification_message`); `RESOLVED` merely attaches evidence via `_attach_resolved_reference` (:1230-1241). **Crucial limitation:** `has_bounded_reference` (:53-73) requires a **multi-word** phrase, so bare `it`/`that`/`this`/`again`/`continue` never even invoke the lexicon pass, and the resolved evidence has **no reader** — the only occurrence of `resolved_reference` anywhere in `atlas/` outside its writer is `turn_meaning.py:176`.

**Entities** (`entity_identification.py:101-128`): literal, separator-tolerant, word-bounded matching of catalog names only, most-specific-first, max 8 (`MAX_IDENTIFIED_ENTITIES`). Consumers: `conversation_service._apply_entity_identification` (:1120-1157) writes `spec.context["identified_entities"]` and, **only when exactly one entity is named**, sets `state.current_subject` so that a *later* subject reference can resolve. The `identified_entities` key has no other reader in `atlas/`.

**Ambiguity:** `AmbiguityReport` is computed during intake, drives `needs_clarification` only for ACTION/DEVELOPMENT requests, and `pending_question` stores the clarification being awaited. `TurnMeaning` carries score + ambiguities but not the question list.

**Net effect:** of the four structures, only two can change a turn's outcome — `ConversationState` (via the unique-referent resolution and via `pending_*`) and the AMBIGUOUS clarification branch. Resolved references and identified entities are **evidence only**.

## 5. Semantic Expressiveness

| Capability | Classification | Evidence |
|---|---|---|
| Correction / reformulation | **NOT REPRESENTABLE** | No field for a superseded reading; `_classify` has no reformulation cue; `"No, I meant X"` matches no cue and resolves to the unsupported notice |
| Continuation | **PARTIALLY** | `continue` / `continue with that` are phrases → (`current_task`, `current_investigation`, `development_intent`) (:129-132) but result is evidence only |
| Contrast | **NOT REPRESENTABLE** | No structure for two conflicting propositions; "compare X with Y" becomes one goal string |
| Clarification | **PARTIALLY** | `needs_clarification`, `clarification_questions`, `pending_question`, and a real early-return message path exist, but only for ACTION/DEVELOPMENT ambiguity and AMBIGUOUS references — not for general language ambiguity |
| Repetition ("again") | **PARTIALLY** | `again` / `do that again` / `run it again` are phrases (`current_task`, `relevant_prior_action`) (:134-137); evidence only, and no re-execution semantics (deliberately) |
| Temporal relations | **NOT REPRESENTABLE** | `created_at` and `turn_id` exist, but no before/after relation between turns or events is represented |
| Causal relations | **NOT REPRESENTABLE** | No dependency slot on the spec; causal prose exists in investigation output, not as carried structure |
| Comparison | **NOT REPRESENTABLE** | No operand pair; multiple entities become an unrelated name list |
| Negation | **PARTIALLY** | `_NEGATION_PREFIXES` (:182-188) suppresses a cue during classification; negation is never represented with scope/operand |
| Multiple related concepts in one utterance | **PARTIALLY** | Up to 8 identified names, but **no relation between them**; `context["concepts"]` is a token slice |
| References to prior results/turns | **PARTIALLY** | Multi-word phrase table + bounded contextual forms, unique-referent only, attached as unread evidence |
| Changing / narrowing a previous request | **NOT REPRESENTABLE** | No amendment mechanism; `replace_topic` replaces a topic, it does not narrow a request, and no interpretation consumes it |
| Alternative interpretations | **PARTIALLY** | `ambiguity_score` + `ambiguities` strings + a fail-closed gate; alternatives are never enumerated as structured readings |

No label above is inferred from the mere existence of a field: each was checked for whether the information can be produced from text **and** carried to a consumer that acts on it.

## 6. Information-Loss Trace

1. **"Check that again."** — Node: `TaskIntake`. No cue matches, so `_classify` yields CONVERSATION/QUESTION; `has_bounded_reference` returns **False** because the multi-word guard excludes bare `again` (:69-70), so `_apply_reference_resolution` never runs the lexicon pass and `spec.context` is never enriched. `TurnMeaning.reference` stays `{}`; the reasoning goal becomes the raw text slice. **Loss point: intake + the multi-word guard.** The act ("repeat the prior action") and the referent of "that" are never represented.
2. **"No, I meant the cognition pipeline."** — Node: `TaskIntake`. `no` is only a negation *suppressor* (:182-188); `meant` has no cue; classification is CONVERSATION. If "cognition pipeline" is in the entity catalog it is recorded on `spec.context["identified_entities"]` — where nothing reads it. **Loss point: intake.** There is no correction act, no reference to the superseded reading, and no consumer for the entity evidence.
3. **"What about the previous result?"** — Nodes: reference resolver + its consumer. `the result` **is** in the table (:159) and is multi-word, so `resolve` runs; with `latest_result` empty it returns `UNRESOLVED` ("No active result found in current state", :356-361), then `resolve_contextual` matches `the previous result` as an explicit context phrase, finds no subject match, returns `UNRESOLVED`, and the spec is returned unchanged (:1227-1228). Even when it *does* resolve, the value lands on `spec.context["resolved_reference"]`, whose only reader is `turn_meaning.py:176`. **Loss points: the qualifier "previous" has no representation, and the resolved evidence is unread.** Observed outcome: unsupported.
4. **"Investigate the cognition pipeline and compare it with the previous result."** — Node: classification + the handler cascade. `INVESTIGATION_REQUEST` wins on the `investigate` cue, and `_maybe_handle_investigation_request` returns at `conversation_service.py:526-532`, so **cognition is never reached for this turn**. The two-act structure is flattened into a single `task_type` plus one `intent`/`goal` slice; "compare it with the previous result" survives only as text. **Loss point: single-label classification.** `_REFERENCE_PATTERNS` has no comparator category, and `TurnMeaning` has no slot for a second operand.

Common structure of the loss: classification is single-label, `intent`/`goal` are text slices, there is no act-with-operands representation, and the two evidence channels that do get populated (`resolved_reference`, `identified_entities`) have no readers.

## 7. UnderstandingEngine

`atlas/understanding/understanding_engine.py:55` orchestrates Concept extraction → consolidation → graph update → abstraction → relationship detection → pattern analysis → insight generation → insight consolidation (:1-13, :183-215).

- **Inputs:** `process_text(text, source)` (:130), `process_observation(observation)` (:140), `process_experiences(list[StructuredExperience])` (:158).
- **Outputs:** `list[UnderstandingInsight]`, plus side effects on `UnderstandingGraph` / `UnderstandingMemory` (`add_concepts`, `store_concept`, :200-201).
- **Consumers:** `runtime_coordinator._stage_understanding` (:470-498) calls `process_text(state.user_input, source="runtime_coordinator")` on every pipeline run and stores insights/concepts/patterns on `CognitionState`; the REASONING stage echoes insight summaries into `decision_data` (:572-575). Also `experience/self_model_engine.py:262-267` and `runtime/feedback_coordinator.py`.
- **Is it conversational language understanding?** No. It produces concepts/patterns/insights *about* text, appends them to a graph, and has no act/intent/reference output and no influence on routing.
- **Is it knowledge/insight extraction?** Yes — its own pipeline stages and its consolidation/persistence concerns are knowledge-graph concerns.
- **Is the separation intentional?** Yes, and visible in code: `cognition/api.py:12` imports from `atlas.conversation.turn_meaning`, while `runtime_coordinator.py:49-53` deliberately **duck-types** the projection so the runtime need not import the conversation layer; the understanding layer has no import relationship with the conversation layer at all.
- **Could it participate in per-turn interpretation today?** Only its *input plumbing* already exists — it receives the raw turn text each run (:480-483). It exposes no per-turn semantic output that routing or reasoning could consume, so participation would require new output semantics, not merely new wiring. (Not redesigned here.)

## 8. Canonical Meaning Model

**Answer: C — a projection chain**, with one operational representation and derived, lossy transports.

- `TaskSpec` is the **only** object that determines behaviour: `TaskType` drives the entire handler cascade (`conversation_service.py:524-652`).
- `TurnMeaning` is a **projection** of the same spec, by construction (`build_turn_meaning(spec, text)` :150-192) and by its own contract text ("Not a second TaskSpec", :21).
- The reasoning-layer "meaning" is not a type at all — it is a `dict` from `to_reasoning_meaning()` wrapped by the duck-typed `_project_meaning()` (`runtime_coordinator.py:46-64`).
- Overlap between `TaskSpec` and `TurnMeaning.intent` is real (hence B is superficially attractive), but the relationship is strictly one-way, derived, and lossy, so C is exact.
- Consequence: meaning is written **once** at intake and then transported or dropped; nothing in the pipeline refines or composes it.

## 9. Smallest Semantic Boundary

Framed as a contract question only:

- **What enters:** the normalized turn text (already produced by `collapse_whitespace`), the bounded `ConversationContext`, the structured `ConversationState`, the entity catalog, and the ambiguity report intake already computes.
- **What semantic information would need to leave it:** exactly the information today's structures cannot hold — (a) the requested **operation distinguished from nouns/operands in its target**, (b) **operands/referents bound** to state with the existing uniqueness rule, (c) a representation for **correction/amendment** and for **multiple related operands**, (d) **explicit alternative readings**.
- **Which existing structures could consume it:** the `TaskSpec.context` evidence channel (already used by references/entities), `ConversationState.current_subject`/`current_task`/`current_investigation`, the builtin claim decision, and the governed handlers' target extraction.
- **Which existing structure would be insufficient:** `TurnMeaning` cannot (it is a snapshot of already-decided fields, excludes `context`, and most of it has no reader); `ConversationState` cannot (single scalar facts, no interpretations, no alternatives); `_REFERENCE_PATTERNS` cannot (phrase → scalar state field lookup, no operands or relations).
- **What must remain unchanged:** the deterministic governed spine — single-label `TaskType` routing and the handler cascade order, approval/execution/verification authority, fail-closed behaviour, `needs_clarification` blocking planning, model independence (runtime runs with `external_providers=False`; `ai/routing/router.py:75-79` admits only `LOCAL_PROVIDER_NAMES`), and the rule that conversational understanding grants no authority. Interpretation may produce meaning and evidence; it must never select, bypass, or authorize a governed handler.

## 10. Architectural Conclusion

- **What Atlas already has:** deterministic cue-based intake with provenance; a single-label routing spine; bounded immutable projections (`TurnMeaning`, `ConversationContext`); a typed state container with explicit lifecycle; a bounded reference resolver with a status enum and a unique-referent (never-guess) rule; bounded entity identification; an ambiguity score with a real fail-closed gate; and a clean, intentional separation between conversational turn meaning and graph-level knowledge insight.
- **What Atlas does not yet have:** any representation of propositional content. No act-with-operands structure, no conjunction/comparison/contrast, no correction or amendment, no temporal or causal relation, no enumeration of alternative readings — and no consumer for the reference/entity evidence that *is* produced.
- **Single most important architectural gap:** there is **no interpretation step**. Meaning is produced once as a classification plus text slices and is then only transported; two evidence channels are populated with no readers.
- **Vocabulary expansion or a missing step?** A **missing interpretation step**. The decisive evidence is the writer-without-reader asymmetry: `the result` is already in `_REFERENCE_PATTERNS`, `identify_entities` already records names, and neither changes any outcome (`turn_meaning.py:176` is the sole reader). Adding cues to `_classify` or phrases to `_REFERENCE_PATTERNS` cannot produce operands, relations, or corrections, because neither structure has anywhere to put them — classification is single-label and the phrase table maps to scalar state fields. Aliases change **which label** is chosen, never **what is represented**.
- **Evidence required before implementation should begin:** (1) a concrete utterance class that is mis-routed or under-represented *and* provably not fixable by one cue/phrase addition; (2) a target structure that can hold the new information **plus at least one consumer that would behave differently** (today's evidence writers have none); (3) a demonstration that single-label routing, fail-closed ambiguity, and zero provider dependence are preserved; (4) tests pinning unchanged behaviour across every governed handler. No stage name is proposed and no implementation is authorized here.

## 11. Evidence Index

- `atlas/conversation/task_intake.py`: `TaskType` :59-81; cue sets :88-129, :408-439, :166-188; `AmbiguityReport` :770-773; `TaskSpec` :776-820; `IntentParser` :823-835; `intake` :858-884; `_build_context` :890-898; `_sanitize_model_fields` :904-943; `_classify` :949-1121; `_extract_objective` :1123-1137; `_build_spec` :1143-1237
- `atlas/conversation/turn_meaning.py`: docstring contract :1-30; bounds :39-44; `_INTENT_FIELDS` :49-62; `TurnMeaning` :65-114; `to_reasoning_meaning` :85-114; `build_turn_meaning` :150-192; `accept_turn_meaning` :195+
- `atlas/cognition/api.py`: `process` :27-62 (acceptance :48-55)
- `atlas/cognition/models.py`: `CognitionState.meaning` :179 (doc :151-155)
- `atlas/services/cognition_service.py`: `process` :93-131; `_process_via_runtime_coordinator` :137-154
- `atlas/runtime/runtime_coordinator.py`: `_project_meaning` :46-64; `_requires_clarification` :67-69; `process` :165-198; `_stage_understanding` :470-498; REASONING meaning use :550-623; PLANNING fail-closed gate :646-671
- `atlas/conversation/conversation_context.py`: :29-104
- `atlas/conversation/conversation_state.py`: `ConversationState` :32-152; `ConversationStateManager` :155-239
- `atlas/conversation/reference_resolution.py`: `has_bounded_reference` :53-73; status enum :76-81; result :84-108; `_REFERENCE_PATTERNS` :120-189; candidate helpers :244-310; `resolve` :319-382; `resolve_contextual` :384-448
- `atlas/conversation/entity_identification.py`: :25-128
- `atlas/conversation/conversation_service.py`: `_apply_entity_identification` :1120-1157; `_apply_reference_resolution` :1159-1228; `_attach_resolved_reference` :1230-1241; handler cascade :524-652; turn-meaning pass :676, :966
- `atlas/understanding/understanding_engine.py`: docstring :1-13; entry points :130-181; `_run_pipeline` :183-215; consolidation :217+
- `atlas/ai/routing/router.py`: local-only gate :75-79
- Tests establishing contracts: `tests/test_turn_meaning_boundary.py` (determinism :49-53, immutability :55-58, nested isolation :60-71, role separation :73-84, reference block :86-96, source bound :102, acceptance :110-118), `tests/test_conversation_state.py`, `tests/test_reference_resolution.py`, `tests/test_reference_exposure.py`, `tests/test_reference_stream_parity.py`, `tests/test_entity_identification.py`, `tests/test_conversation_task_intake.py`, `tests/test_cognition_reasoning_integration.py`, `tests/test_understanding_models.py`
