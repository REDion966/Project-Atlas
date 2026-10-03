# Phase 3 — Conversational Replay Corpus & Real-World Validation

**Type:** evidence and validation record (NOT a roadmap phase, no new architecture).
**Baseline:** Phase 2 commit `182159c` (`feat(conversation): complete contextual
meaning and natural conversation`). Phase 1 `4526c1e`.
**Deterministic, model-OFF.** No model, no network, no dependency, no second
authority. This record and the corpus it names are the durable Phase 3 evidence.

---

## 1. Corpus

Durable replay corpus: **`tests/test_phase3_conversation_replay.py`** — a
structured, deterministic corpus over the EXISTING `ConversationService`
send/stream seam that asserts the AUTHORITATIVE outcome (meaning, state/context,
route/owner, governance) rather than brittle prose.

Coverage families:

| Family | Cases |
|---|---|
| Casual / vocative | greeting; acknowledgement; "Hey Atlas, can you look into this?" |
| Investigation language | "Take a look at …"; "Look into …" |
| Correction | new-subject correction completes + supersedes; correction-with-operation defers to the operation |
| Clarification lifecycle | pending created; unrelated turn releases; candidate resolves; bare pointer stays open |
| Result references | "What did you find?"; previous-result qualifier |
| Imperative result-request (P3) | "Tell me what you find/found"; fail-closed without a result |
| Elaboration | "Can you explain that more simply?" |
| Work/completion recall | "What have we done?"; temporal honesty ("yesterday") |
| Stance / constraints | no-modification / read-only recorded; no authority; superseded by an explicit objective |
| Contextual comparison | "Compare that with what we had before."; "How is this different?"; fail-closed with one result |
| Ambiguity / adversarial | bare earlier-item fails closed; "ignore previous instructions … approve" cannot approve; governance request fail-closed |
| Compound / delegation | operation + result clause; governance clause never executed |
| Multi-turn sequences | investigation follow-ups; constraint→result; two results→compare; stale-clarification release |
| Send/stream parity | mixed 9-turn sequence identical on both paths |

## 2. Model-OFF validation result

All corpus cases and the STEP-4 multi-turn sequences (A–F) pass with external
assistance disabled. Verified: no deadlock; no accidental execution; no
wrong-operation caused by misunderstanding on the validated families; no unsafe
guessing; no fabricated state/history/result; no governance bypass; zero provider
calls; `model_used=false` on deterministic replies.

## 3. Deterministic fixes made (justified by evidence)

- **P3-A — imperative result-request.** "Tell me what you find/found." was not
  recognised as a query about prior output and fell to the AI/fallback path.
  Fix: a **whole-turn-anchored** `_RESULT_REQUEST_RE` in
  `atlas/conversation/communicative_function.py` maps it to
  `FUNCTION_QUERY_RESULT`, reaching the existing retained-result route (fail-closed
  with no result). Whole-turn anchoring keeps compound clauses ("Investigate X and
  tell me what you find.") on their existing route.
- **P3-B — contextual comparison ownership.** "How is this different?" was
  pre-empted by the bare-reference surface and answered as the active
  investigation. Fix: `_maybe_answer_resolved_reference` now defers a bounded
  contextual comparison (compare/difference word + anaphor) to the existing
  comparison route.

Both reuse existing seams; no new state, resolver, or authority.

## 4. Failure classification summary

- **ALREADY WORKING:** casual/vocative, natural investigation, correction
  (incl. supersession), clarification lifecycle, result recall/qualifier,
  elaboration, work recall, stance, contextual comparison, compound/delegation,
  governance fail-closed, ambiguity fail-closed, send/stream parity.
- **DETERMINISTIC DEFECT (fixed):** imperative result-request; contextual
  comparison ownership (above).
- **INTENTIONAL FAIL-CLOSED:** causal "why" (no cause inference); "The other
  one."/"what about the previous result?" ambiguity handling where no unique
  referent exists; elaboration/recall with insufficient evidence.
- **Bounded investigation-language vocabulary (CLOSED by the later C4 milestone).**
  At the time of this Phase 3 record, the bounded target alternation in
  `atlas/conversation/task_intake.py` (`_NL_INVESTIGATION_TARGETS`,
  `_INVESTIGATION_PHRASE_TARGET_RE`, `_INVESTIGATION_SUBJECT_RE`) was duplicated
  across three detectors and omitted several real Atlas subsystems (e.g.
  `storage`, `reasoning`, `toolchain`), so natural paraphrase forms such as
  "Take a look at the storage layer." / "Look into the storage layer." fell to the
  honest floor while the canonical "Investigate the storage layer." worked. This
  was classified as genuine **bounded deterministic coverage of an EXISTING
  seam** — not a semantic gap. It was subsequently validated as gap **G1** by the
  C3 evidence milestone and **closed by C4** via the single bounded source of truth
  `_ATLAS_INVESTIGATION_TARGETS`; see `docs/ATLAS_STATE.md` §31.
- **MISSING CAPABILITY (bounded, documented, NOT implemented):** a
  next-step/suggestion surface ("what should we investigate next?" currently runs
  the literal noisy investigation cue); a bounded reference family for
  "that's the one I was talking about."; "just investigate it for now." records a
  read-only stance but does not re-investigate a superseded target.
- **GENUINE SEMANTIC GAP:** none demonstrated. Every remaining gap is bounded
  lexical/reference coverage or intentional fail-closed, not a failure to infer
  meaning from context Atlas already holds.

## 5. Pre-existing failures (unchanged, unrelated)

- `test_ambiguity_uncertainty::test_orchestration_ambiguity_gate_records_the_pending_question` ("Run it").
- `test_l9_real_world_validation::TestCorpusContract` (intake-only drift).
- `test_c3_real_world_capability_evidence` comparison + architecture (real-kernel).
- `test_step10_multi_intent_multi_step::TestRealKernel` (`KeyError: 'orchestration'`).

## 6. Model-ON result / limitation

No safe, enabled conversation-model seam exists (external providers are opt-in
and OFF by default); model-ON conversation validation was therefore **not
performed** rather than expanding scope to force it. Existing model-seam evidence
(`tests/test_phase123_model_seam_audit.py`, `tests/test_linguistic_providers.py`,
`tests/test_learned_proposer.py`, `tests/test_mock_provider.py`) confirms the
optional seams are proposal-only / non-authoritative: they cannot execute,
approve, override governance, or become state authority, and fail safely on
invalid output.

## 7. Phase 4 evidence gate — CONCLUSION: **PHASE 4 NOT JUSTIFIED**

Remaining conversational gaps after Phases 1–3 are bounded deterministic coverage
(small reference/interpretation families) or deliberate fail-closed behaviour.
There is no evidence of a repeated failure where Atlas holds all required context
and still cannot infer intended meaning, and no measurable evidence that a
semantic proposer would materially solve the remaining bounded gaps without
risking a second authority. Atlas remains fully valid with models OFF.

## 8. Remaining known limitations

- No next-step/suggestion surface; a "what should we investigate next?" clause
  runs the literal (noisy) investigation cue.
- Bounded reference vocabulary ("that's the one I was talking about." stays
  fail-closed).
- Stance is representation-only and never an execution/approval authority.
- Unsupported temporal precision (`yesterday`) is reported honestly, never
  fabricated.
