# Evidence-Driven Improvement 3 — Conversational Knowledge Integration

Post-Phase-D refinement implementing the single gap identified by Re-Baseline 2
(G-A/G-B/G-C, plus the G-I reporting defect where it is caused by this
integration). No new phase, no new engine, store, provider, planner, dispatcher
or governance layer. Baseline: HEAD `8ec67fb58de3643591fe3e588512a47d96e3f0dd`.

## Problem (evidence)

A conversational research/knowledge request never reached the existing D3
knowledge decision: `Research <subject>` entered the older P17 research/
orchestration bridge, which failed with `no_evidence` (31 prompts) or ran a
codebase-scoped acquisition and reported `Done` (4 prompts) — while
`answer_knowledge_question(<subject>)` independently reported `SUFFICIENT` and
`run_work_objective(<subject>)` completed. Because that bridge never populated
`ConversationState.last_knowledge`, every Improvement-1 follow-up failed after a
research turn, and an applied correction (Improvement 2) never reached the
knowledge operation.

## Changes

| File | Change | Why |
| --- | --- | --- |
| `atlas/conversation/builtin_response.py` | Bounded research-request cue vocabulary (`_RESEARCH_REQUEST_RES`), compound-turn guard, `research_request_subject`, `knowledge_topic` (public case-insensitive reduction), `BOUNDED_REFERENCE_HEADS` / `is_bounded_reference_subject` / `substitute_reference_subject`; shared local-first `_knowledge_result`; public `match_knowledge_request(subject)` | Reuse the EXISTING local-first path (validated retrieval → D3 `retrieve_with_acquisition`, which owns governed D2) for a research request, with a bounded, reference-aware subject |
| `atlas/conversation/conversation_service.py` | `_maybe_handle_knowledge_request` (D3-first claim, gated on the existing intake ambiguity report and the NLU-2 subject gap), `_active_knowledge_subject` (corrected-subject-aware), `_knowledge_message_for`, extended `_maybe_handle_knowledge_followup` (+`_knowledge_followup_replay`), wired into `send()`/`stream()` | Route the turn to D3 before the work-acquisition flow; make the corrected subject reach the knowledge query; resolve bounded references instead of passing `that`/`its` literally |
| `tests/test_evidence_improvement_3.py` | **new** — 42 focused tests | Acceptance evidence |
| `tests/test_c3_real_world_capability_evidence.py`, `test_c4_1_capability_detail_routing.py`, `test_c6_1_validated_knowledge_conversation.py`, `test_c6_acquisition_reuse_evidence.py`, `test_c6_knowledge_learning_evidence.py`, `test_nlu6_model_independence_failure_proof.py` | 8 tests reconciled | Each pinned the superseded research→orchestration routing; every guarded invariant preserved (see below) |

No D4/D5/governance/authority/config change. No new store: the answer is
retained in the EXISTING `ConversationState.last_knowledge`
(`{query, status, content}`, provenance rendered inside `content`).

## Required flow (as implemented)

1. deterministic interpretation (existing `TaskIntake` + D1 engine);
2. active subject determined; a CORRECTION supersedes the retained subject
   (`_active_knowledge_subject`);
3. bounded references resolved from state (`that`/`this`/`it`/`its …`);
4. the subject is passed to the EXISTING local-first path;
5. validated local knowledge wins and D3 is not even consulted (local-first);
6. otherwise the D3 provider (`retrieve_with_acquisition`) runs — governed D2
   only, deny-by-default preserved;
7. the resulting answer is recorded into `last_knowledge` and rendered by the
   existing renderer (claims + provenance, or the honest `empty` /
   `store_unavailable` outcome);
8. no authorized knowledge ⇒ honest no-match; never a fabricated answer and
   never a generic `Done`;
9. the existing Improvement-1 follow-up surface consumes `last_knowledge`.

Out of scope (deliberately unchanged, still reachable): compound requests
(`Research X and …`), `Investigate …` (repository investigation), and explicit
D4/D5 API work objectives.

## Reconciled stale tests (justification)

All eight pinned the pre-I3 routing (research ⇒ orchestration) and were proven
stale by the new contract; none of their guarded invariants was weakened:

- `test_c6_1_...::test_ordinary_research_uses_the_knowledge_path` — still asserts
  no capability-detail/orchestration capture and no `Done`.
- `test_c6_acquisition_reuse_evidence::test_research_turn_reuses_existing_validated_knowledge` —
  now asserts the validated answer is served with the source already deleted.
- `test_c4_1::test_research_request_not_capability_detail` — still asserts no
  capability-detail and no investigation capture.
- `test_c3::test_named_subject_is_understood_and_routed_but_has_no_authorized_source`,
  `test_generic_domain_research_declines_honestly`,
  `test_correction_utterance_response_stays_bounded` — assert the same honest,
  non-fabricating decline from the authoritative knowledge path.
- `test_c6_knowledge_learning_evidence`: research outcome retained in
  `last_knowledge`; the C6.1 recall bridge still surfaces validated knowledge
  (now seeded through the authorized acquisition API); research turn asserts
  `model_used is False`.
- `test_nlu6`: the three model-independence tests keep every invariant
  (deterministic, provider-free, no outbound attempt) and drop only the
  orchestration-report shape.

## Tests

- Focused: `tests/test_evidence_improvement_3.py` → **42 passed**.
- Stage 2 (conversation engine/state/service/core + knowledge decision +
  external acquisition + knowledge follow-up + provenance + NLU1–6 + builtin +
  Improvements 1/2) → **926 passed**.
- Stage 3 (D1–D5, C4.1, C5, C3, capability/architecture, acquisition phases
  81–84/88/89, governance/approval, evolution knowledge) → **574 passed**.
- Combined final run (Stage 2 + Stage 3) → **1377 passed, 81 subtests**.
- Investigation + development/evolution/knowledge batch → **439 passed**.

One implementation defect was found and fixed during testing: an ambiguous
reference (`Find out what module handles this capability.`) was initially
captured into a knowledge subject; the existing intake ambiguity report is now
honoured, so the governed clarification is preserved.

## Architecture audit

No second knowledge/research engine, store, planner, dispatcher, governance or
authority path · no external model (`model_used=False`; Ollama not required) ·
no direct web access from the conversation layer · D3 remains authoritative for
sufficiency and D2 remains the only acquisition mechanism · `last_knowledge`
remains the existing conversation context · D4/D5, Improvements 1 and 2 intact ·
`config.toml` unchanged · no D6 · roadmap unchanged.

## Remaining evidence-backed gaps (observed here only)

- Compound requests (`Research X and …`) keep the pre-existing orchestration
  path and can still report `Done`/`no_evidence`.
- A knowledge follow-up turn ("What source supports that?") still replaces
  `current_objective` (Improvement 2 role coverage).
- `Explain the research capability.` / design questions still reach the
  orchestration bridge (the G-I reporting defect for non-research phrasings).
- Paraphrase coverage of self-knowledge/capability questions remains bounded.
