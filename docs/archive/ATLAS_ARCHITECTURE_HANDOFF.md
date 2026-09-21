# ATLAS CURRENT ARCHITECTURE HANDOFF

## 1. Baseline

- Branch: `main`
- HEAD: `f6737dbdc6c9e254b37c3abf588a4a2c54be945a` — "feat: expand bounded language recognition from L9 evidence" (L10)
- origin/main: identical (`f6737db`); 0 ahead / 0 behind
- Working tree: clean apart from three intentional untracked artifacts (`atlas_entry_inspection.txt`, `atlas_entry_references.txt`, `mission_output.txt`). `.pytest_cache/` exists but is git-ignored (`!!`), so it does not appear in `git status`.
- Unexpected changes: none in the working tree. Note for context: HEAD is 17 commits past my own last local commit `3a959ad` ("feat: expand deterministic conversational intent aliases"); those commits (`499d30b` … `f6737db`, the L1–L10 track) are present, are ancestors-inclusive, and the Phase 1/Phase 2 conversational changes (`cd9ab42`, `3a959ad`) are still in history and still present in the current source. No history was rewritten by this investigation.

## 2. Actual Entry Point

- `main.py` → `from atlas.cli.cli import AtlasCLI` → `main()` (14 lines total).
- `atlas/cli/cli.py::AtlasCLI` constructs the kernel (`Atlas()` from `atlas/kernel/atlas.py:352`) and a `CommandRouter` (`atlas/cli/command_router.py`).
- `AtlasCLI.run()` (cli.py:16-59): reads `input("You > ")`, exits on `exit|/exit|quit`, routes slash commands through `CommandRouter.execute(...)`, otherwise prints `Atlas > ` and iterates `self._atlas.stream(user_input)` — i.e. **the interactive language path is `Atlas.stream`, not `Atlas.send`** — then calls `self._atlas.tick()` once per completed interaction and `self._atlas.shutdown()` in `finally`.
- Kernel wiring: `atlas/kernel/atlas.py` (`Atlas.__init__`, :362) builds `atlas/kernel/service_container.py`; `Atlas.stream/send` delegate to `ConversationService` (`atlas/conversation/conversation_service.py:156`), which is constructed with `task_intake`, `builtin_response`, `cognition_api`, `deterministic_fallback`, memory/knowledge managers, and the approval/authority services.
- Non-interactive entry points also exist (`atlas/cli/main.py`, command modules), but casual language enters only through `ConversationService.send` / `.stream`.

## 3. Actual Execution Flow

Compact form (send/stream are parallel implementations of the same cascade; `stream` at conversation_service.py:751, `send` at :470):

```
CLI input
→ Atlas.stream(text)
→ ConversationService.stream/send
→ Message(role="user") appended to Conversation        (conversation/conversation.py)
→ ConversationContext prompt build (memory_query=text)  (conversation/context.py)
→ TaskIntake.intake(text) → TaskSpec                    (task_intake.py:777)
→ _apply_entity_identification(spec, text)              (entity_identification.py:101)
→ _apply_reference_resolution(spec, text)               (reference_resolution.py:313)
     └ UNRESOLVED / AMBIGUOUS → bounded reply, RETURN
→ governed TaskType cascade (order matters):
     INVESTIGATION_REQUEST → APPROVAL/REJECTION → PLANNING_REQUEST →
     EXECUTION_REQUEST → RECOVERY_REQUEST → VERIFICATION_REQUEST →
     REPORT_REQUEST → REPOSITORY_IMPACT_REQUEST →
     AUTONOMY_REQUEST → L2_ → L3_ → L4_ → L5_AUTONOMY_REQUEST →
     development request → development-need confirmation
     └ any handler returning a Message → append and RETURN
→ BuiltinResponseService.respond(text, spec, message_count, context)
     └ casual intent claimed → deterministic reply, RETURN (no provider)
→ orchestration bridge
→ Cognition: cognition_api.process(user_input=text, goal=spec.goal_string(),
      metadata={"task": spec.to_dict(), ...}, turn_meaning=build_turn_meaning(spec, text))
     (conversation_service.py:654-702; cognition/api.py:33-61)
→ PromptBuilder.build(context) → ai.chat(prompt, routing_context=...)
     └ exception → _builtin_after_failure → deterministic_fallback.resolve → degraded notice
→ Message(role="assistant") appended to Conversation
→ CLI streams response text to USER
```

Key structural fact: **language interpretation never triggers action directly.** The conversational layer only selects one branch; every branch that mutates state goes through the existing governed handlers.

## 4. Language / Understanding Components

| Capability | Status | Actual implementation | Evidence |
|---|---|---|---|
| Lexical normalization | IMPLEMENTED | `conversation/normalization.py::collapse_whitespace`, consumed by `builtin_response`, `task_intake`, `reference_resolution`, `investigation._clean_target`, `deterministic_fallback`, `development_need_dialogue`, `repository_impact` | whitespace fixes `499d30b` … `c44b300` |
| Deterministic pattern matching | IMPLEMENTED | `task_intake.py` cue frozensets (`_QUESTION_CUES`, `_INVESTIGATION_CUES`, `_DEVELOPMENT_CUES`, …); `builtin_response.py` compiled phrase regexes + `_alias_hit` | task_intake.py:88-129 |
| Intent classification | IMPLEMENTED (bounded) | `TaskType` enum (task_intake.py:59-81, 20 members) produced by `TaskIntake`; casual intents produced by `BuiltinResponseService._classify` (builtin_response.py:~240) with a fixed precedence: commands → capabilities (+aliases) → help → identity (+alias) → capability_detail → status (+alias) → recall → greeting → unsupported | builtin_response.py:262-290 |
| Meaning representation | PARTIAL | `TaskSpec` (operational) and `TurnMeaning` (`turn_meaning.py:65`, frozen/slots: intent, uncertainty, reference, source_text, provenance) | `build_turn_meaning` :150 |
| Entity extraction | PARTIAL | `entity_identification.py::identify_entities`, `EntityCatalog.from_names`, `MAX_IDENTIFIED_ENTITIES = 8` — only explicitly named, catalog-registered names; recorded as evidence, routing untouched | entity_identification.py:28-101 |
| Reference resolution | PARTIAL | `reference_resolution.py`: `has_bounded_reference`, `ConversationReferenceResolver.resolve/resolve_contextual`, `ReferenceResolutionStatus`, `_established_subject`, `_MAX_CONTEXT_SUBJECTS = 8` | reference_resolution.py:53-451 |
| Context / multi-turn | PARTIAL | `conversation_context.py::ConversationContext` (`MAX_CONTEXT_TURNS = 10`, `MAX_CONTEXT_CHARS = 500`), `conversation_state.py` (`pending_question`), turn-recall in `conversation_service` (bounded ~400 chars) | commits `d7270d3`, `504af7b` |
| Ambiguity / uncertainty | PARTIAL | `TaskSpec.ambiguity` + `needs_clarification` → `_clarification_message`; `TurnMeaning.uncertainty.ambiguity_score`; clarification recorded via `_record_pending_question` | conversation_service.py:1366,1458 |
| Correction / reformulation | NOT PRESENT | no reformulation intent, no "I meant" handling in `TaskIntake` or `_classify`; probe 3 returns unsupported | runtime probe 3 |
| Compositional meaning | NOT PRESENT | interpretation is whole-phrase family matching; no combinator over slots | builtin_response.py alias block |
| Meaning → reasoning/planning | PARTIAL | `TurnMeaning.to_reasoning_meaning()` (turn_meaning.py:85) → `runtime_coordinator._project_meaning` (:46) → `meaning=` parameter on the reasoning/planning call (:197) | commit `e580a17` |
| Response understanding/composition | PARTIAL | per-intent renderers in `builtin_response.py`; governed renderers in `conversation_service.py` (`_clarification_message`, `_orchestration_clarification_message`, report/verify handlers); `prompt_builder.py` for the provider path | commit `92522a6` |
| `atlas/understanding/` subsystem | DIFFERENT DOMAIN | `understanding_engine.py:55` extracts concepts/patterns/insights from text and observations (`process_text`, `process_observation`, `process_experiences`, `_run_pipeline`); consumed by `cognition/pipeline.py:335` and `runtime/runtime_coordinator.py:480` — it builds knowledge/experience insight, not per-turn language meaning | understanding_engine.py:130-217 |

## 5. Meaning Representation

- Operative machine meaning today is **`TaskSpec`** (`task_intake.py:777`): `task_type`, goal, constraints, priorities, success criteria, `needs_clarification`, `confidence`, `source`, `verified`, `input_hash`, `ambiguity`, and a `context` dict (which may carry `resolved_reference`).
- The typed boundary contract is **`TurnMeaning`** (`turn_meaning.py:65`), created by `ConversationService._build_turn_meaning` (conversation_service.py:404) via `build_turn_meaning(spec, text)`; it deep-copies the intent fields, attaches `spec.ambiguity`, and lifts `spec.context["resolved_reference"]`.
- Created at: conversation_service.py:676 (send) and :966 (stream), only when a `TaskSpec` exists.
- Consumed at: `cognition/api.py:48` (`accept_turn_meaning`, fail-closed shape check) → passed into the cognition engine and `services/cognition_service.py:99-153`, then `runtime/runtime_coordinator.py:_project_meaning` (:46) → `meaning=` (:197) for reasoning/planning.
- Important characterization: `TurnMeaning` is a **projection of `TaskSpec`**, not an independently computed semantic interpretation. It carries no new meaning beyond what intake already produced, and its docstring states it is behaviour-neutral at the L1 boundary.

## 6. Context / References

- **Previous turns**: `Conversation.messages` (raw, unnormalized, always preserved) plus a bounded read-only projection `ConversationContext` (`conversation_context.py:93 build_conversation_context`), capped at 10 turns / 500 chars and passed to the builtin layer (conversation_service.py:392-401). `ConversationState.pending_question` carries a pending clarification across turns.
- **Entities**: `EntityCatalog` + `identify_entities` — a bounded list (max 8) of names that appear verbatim in the current turn and exist in the catalog; they are attached as evidence on the spec.
- **References** ("that", "this", "previous result"): bounded deterministic phrase matching only (`has_bounded_reference`, `ConversationReferenceResolver`). Non-recognized references are not resolved. Probe 4 ("What about the previous result?") returned the unsupported notice even with prior turns in the conversation; the resolver's contextual AMBIGUOUS branch is deliberately not surfaced for casual turns. `resolved_reference` is documented as evidence-only.
- **Corrections / reformulations**: absent. There is no mechanism to retract or amend a prior interpretation; probe 3 ("No, I meant the cognition pipeline.") returned unsupported.

## 7. Language → Cognition / Reasoning

The connection exists and is explicit, but narrow:

- `conversation_service.py:676` (send) / `:966` (stream) → `CognitionAPI.process(user_input, goal, metadata, turn_meaning=...)` (`cognition/api.py:33`).
- `cognition/api.py:48` validates the contract with `accept_turn_meaning` (malformed → dropped, fail-closed) and forwards it; `services/cognition_service.py:99-153` passes it down; `runtime/runtime_coordinator.py:46-55, 171-197` projects it to `meaning=` for `ReasoningController`/`PlanningEngine`.
- Before that point, meaning reaches cognition only as `metadata["task"] = spec.to_dict()` and `goal = spec.goal_string()`.
- So: intent/uncertainty/reference **do** cross the boundary, but the conversational intent vocabulary (greeting/help/identity/capabilities/status/recall) does not — those turns are answered by the builtin layer and never enter cognition.

## 8. Runtime Probe Summary

Executed against the real kernel (`Atlas().start()`, `external_providers=False`, providers not contacted) — 5 probes:

| Input | Result | Interpretation |
|---|---|---|
| What can you do? | `builtin_intent=help`, `model_used=False`; deterministic help text listing supported surfaces | bounded intent matched at `_classify`; no provider |
| Check that again. | `builtin_intent=unsupported`, `model_used=False` | no re-run/imperative reference handling; falls to the honest unsupported notice |
| No, I meant the cognition pipeline. | `builtin_intent=unsupported`, `model_used=False` | no correction/reformulation semantics |
| What about the previous result? | `builtin_intent=unsupported`, `model_used=False` | free-form reference to a prior turn is not resolved, despite history being present |
| Investigate this and tell me what you find. | `investigation` metadata present, `model_used=None`; governed investigation report produced | imperative investigation recognized and routed to the governed read-only path |

All five were answered without any provider call; no repository mutation occurred (working tree unchanged after the probes).

## 9. Current Architectural Character

**Hybrid, dominated by bounded vocabulary/pattern handling.**

Evidence for "bounded": both interpreters are phrase/cue driven — `TaskIntake` cue frozensets producing a 20-member `TaskType`, and `BuiltinResponseService._classify` as a fixed ordered chain over compiled regexes with an explicit alias block (capability/identity/status alias tuples + `_alias_hit`). Probes 2–4 show that anything outside the enumerated families lands in `unsupported`.

Evidence for "structured" (partial): a real typed contract crosses into cognition (`TurnMeaning` with intent/uncertainty/reference/provenance, deep-copied, fail-closed validated), ambiguity is represented on `TaskSpec`, a bounded context projection exists, and a reference resolver with an explicit status enum exists.

The hybrid is asymmetric: the *structured* parts are plumbing/projection around meaning that was already decided by *phrase matching*; there is no step that composes meaning from parts.

## 10. Existing Pieces Relevant to Richer Understanding

Existing components that could participate (no recommendation implied): `TaskSpec` (structured slots + `ambiguity`), `TurnMeaning`/`to_reasoning_meaning` (typed boundary + reasoning projection), `ConversationState.pending_question` (dialogue state), `ConversationContext` (bounded history projection), `EntityCatalog`/`identify_entities` (named entities), `ConversationReferenceResolver` + `ReferenceResolutionStatus` + `_established_subject` (reference machinery), `normalization.collapse_whitespace` (shared surface normalization), `BuiltinResponseService._classify` (single precedence point), `TaskIntake` cue sets, `cognition/api.py::accept_turn_meaning` (boundary validation), `runtime_coordinator._project_meaning` (meaning → reasoning), `investigation.py`/`investigation_synthesis.py` (governed read-only reasoning), `deterministic_fallback.py` (degraded-path answering), and `atlas/understanding/` (insight extraction over text, currently used for concepts/patterns rather than per-turn meaning).

## 11. Confirmed Limitations

All evidence-backed:

1. Interpretation is whole-phrase/family matching; novel but equivalent phrasings fall to `unsupported` (probes 2–4).
2. No correction/reformulation semantics — a follow-up cannot amend, retract, or narrow a previous interpretation (probe 3).
3. Reference resolution is bounded to recognized phrases; a stated referent ("previous result") is not resolved even when turn history exists (probe 4).
4. Context exposure is capped (10 turns / 500 chars) and read-only; it informs the builtin layer but does not change interpretation.
5. Ambiguity is representable (`TaskSpec.ambiguity`, `needs_clarification`) but not computed for casual turns; the clarification path is driven by the governed handlers.
6. `TurnMeaning` adds no interpretation of its own — it is a bounded projection of `TaskSpec`, so richer semantics cannot enter cognition unless intake produces them first.
7. Recall remains a bounded keyword lookup over injected memory/knowledge stores, not turn-level conversational memory.
8. `atlas/understanding/` operates on text to produce concepts/patterns/insights; it is not wired as the per-turn language interpreter.

## 12. Architectural Observation

Question: *does the current architecture have a genuine language-understanding boundary that is capable of evolving beyond bounded phrase/alias expansion?*

Evidence for **yes, a boundary exists**: there is exactly one ordered classification point per layer (`TaskIntake`, then `BuiltinResponseService._classify`), an explicit typed contract that crosses into cognition with fail-closed validation (`accept_turn_meaning`), a bounded immutable context projection, a reference resolver with a status enum, and an ambiguity field already carried into reasoning (`to_reasoning_meaning`). New mechanisms would have a place to plug in without disturbing governance.

Evidence for **not yet capable in practice**: every one of those structures is fed by phrase/cue matching, the contract is a projection rather than a computed meaning, there is no composition step, no dialogue-act state machine, and no correction handling, so richer input currently has no representation to occupy. The observed failures (probes 2–4) are not missing vocabulary alone — they are missing an interpretation step over the structures that already exist.

Both statements are supported by the same code paths; the boundary is real but currently shallow.

## 13. Evidence Index

- `main.py`; `atlas/cli/cli.py` (`AtlasCLI.run`); `atlas/cli/command_router.py`
- `atlas/kernel/atlas.py` (`Atlas` :352, `start/tick/shutdown`, service wiring); `atlas/kernel/service_container.py`
- `atlas/conversation/conversation_service.py` (send :470, stream :751, `_maybe_handle_builtin_response` :370, `_build_conversation_context` :392, `_build_turn_meaning` :404, cascade :524-652, cognition :654-702, failure path :718-743)
- `atlas/conversation/task_intake.py` (`TaskType` :59, cue sets :88-129, `TaskSpec` :777)
- `atlas/conversation/builtin_response.py` (`_RECALL_RE` :98, alias block after `_GREETING_RE`, `_classify` :240)
- `atlas/conversation/turn_meaning.py` (:65 `TurnMeaning`, :85 `to_reasoning_meaning`, :150 `build_turn_meaning`, :195 `accept_turn_meaning`)
- `atlas/conversation/normalization.py`; `reference_resolution.py`; `entity_identification.py`; `conversation_context.py`; `conversation_state.py`
- `atlas/cognition/api.py` (:33-61); `atlas/cognition/pipeline.py` (:328-342); `atlas/services/cognition_service.py` (:99-153); `atlas/runtime/runtime_coordinator.py` (:46-55, :171-197, :303-308)
- `atlas/understanding/understanding_engine.py` (:55-217)
- `atlas/ai/ai_manager.py` (`LOCAL_PROVIDER_NAME = "Mock Provider"` :47, `external_providers` :57-74); `atlas/ai/routing/router.py` (:75-79 `LOCAL_PROVIDER_NAMES` gate); `atlas/ai/providers/mock_provider.py`
