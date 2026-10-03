# Natural Conversation Roadmap — Closure Audit Record

**Type:** final acceptance/closure audit record (NOT a roadmap phase). Evidence-based;
no product capability implemented by this record.
**Audit HEAD:** `6d342e18afa277a537939a654a39a0fb70de3d69` (Phase 3).
**Committed path:** Phase 1 `4526c1e` → Phase 2 `182159c` → Phase 3 `6d342e1`.

---

## Objective (as stated)

Make Atlas capable of natural, casual, contextual, multi-turn conversation
without rigid command syntax — while **Atlas retains authority** over State,
Meaning, Reasoning, Planning, Routing, Execution, Governance, Evidence, Memory,
and Verification.

## Phase 0–3 acceptance matrix

| Phase | Claimed status | Evidence | Result |
|---|---|---|---|
| L0–L10 | complete/frozen | `docs/ROADMAP.md` (Phase 1 items 1.1–1.12); no L11+ | PASS |
| Phase 0 — Diagnostic baseline | complete | read-only diagnostic; findings drove P1-1…P1-4 | PASS |
| Phase 1 — Deterministic conversational foundation | complete | commit `4526c1e`; P1-1…P1-4 in `conversation_service.py`; `test_step9_ambiguity_and_clarification`, `test_correction_routing`, `test_nl_semantic_function_gap`, `test_lexical_canonicalization`, `test_last_operation_repeat`, `test_reference_consumption` | PASS |
| Phase 2 — Contextual meaning & natural conversation | complete | commit `182159c`; P2-1…P2-4 in `conversation_service.py`, `communicative_function.py`, `conversation_state.py`; `test_phase2_contextual_conversation` | PASS |
| Phase 3 — Conversational replay & real-world validation | complete | commit `6d342e1`; `test_phase3_conversation_replay` (33), `docs/PHASE3_CONVERSATION_REPLAY_VALIDATION.md` | PASS |
| Phase 4 — Optional semantic proposer | not justified / not implemented | no code; Phase 3 evidence gate | NOT JUSTIFIED |

## Capability matrix (evidence at audit HEAD)

PASS: natural phrasing; casual language; conversational markers/vocatives;
clarification (+ supersession/release); correction/repair; contextual references;
referential integrity / result qualifiers; result references; earlier-result /
ordinal ambiguity (fail-closed); work/activity recall; honest temporal behaviour;
result-grounded follow-ups ("What did you find?", "Tell me what you found.",
"Explain that more simply."); status-vs-investigation routing; stance/read-only
constraints (non-authoritative); contextual comparison; multi-turn continuity;
compound + mixed conversational/operational turns; governance-sensitive language
(fail-closed); approval/fail-closed; ambiguous requests (clarify/fail-closed);
model-OFF; send/stream parity; no accidental execution; no fabricated results; no
deadlocks; no authority leakage; deterministic-first; architecture preserved;
external-model optionality.

PASS WITH BOUNDED LIMITATION: **investigation paraphrase/phrase coverage is
bounded by an explicit target vocabulary** — see limitations. (The G1 vocabulary
gap recorded at this closure was subsequently CLOSED by the C4 milestone; see
the "Post-closure amendment" note below and `docs/ATLAS_STATE.md` §31.)

INTENTIONAL FAIL-CLOSED: causal "why" without causal evidence; unsupported
semantic questions; insufficient-evidence elaboration/recall.

MISSING CAPABILITY (bounded, documented, NOT implemented): next-step/suggestion
surface; bounded reference "that's the one I was talking about.".

## Evidence (focused)

- `tests/test_phase3_conversation_replay.py` — 33 passed (families incl.
  casual/vocative, investigation, correction, clarification lifecycle, result
  references/imperative result-request, elaboration, work recall, stance,
  comparison, ambiguity/adversarial, compound, multi-turn A–F, send/stream parity).
- Focused acceptance batch (Phase 3 corpus + Phase 2 + step9 + correction +
  nl_semantic + reference_consumption + compound + builtin_response):
  **203 passed, 37 subtests passed**.
- Model-OFF probes (A–O) pass with zero provider calls; `model_used=false`.
- Model-ON: no enabled conversation-model seam exists; model-seam audits
  (`test_phase123_model_seam_audit`, `test_mock_provider`, `test_learned_proposer`,
  `test_linguistic_providers`) confirm optional seams are proposal-only /
  non-authoritative.

## Remaining bounded limitations

1. ~~**Investigation paraphrase/phrase target vocabulary.**~~ **RESOLVED by the C4
   milestone** (after this closure was recorded). At closure time the bounded
   target alternation in `atlas/conversation/task_intake.py` was duplicated
   across three detectors and omitted several real Atlas subsystems (e.g.
   `storage`, `reasoning`, `toolchain`), so "Take a look at the storage layer." /
   "Look into the storage layer." fell to the honest floor while the canonical
   "Investigate the storage layer." worked. C3 subsequently classified this as a
   genuine bounded understanding gap (G1), and C4 closed it by introducing the
   single bounded source of truth `_ATLAS_INVESTIGATION_TARGETS` — reused by
   `_NL_INVESTIGATION_TARGETS`, `_INVESTIGATION_PHRASE_TARGET_RE` and
   `_INVESTIGATION_SUBJECT_RE` — extended only with validated Atlas subsystem
   targets grounded in the repository's registered `CORE_COMPONENTS`. The natural
   forms now reach the EXISTING read-only investigation and ordinary knowledge
   questions remain non-investigation. Deterministic and model-independent; no new
   architecture or authority. Evidence: `docs/ATLAS_STATE.md` §31 (C4/G1). The
   historical observation above is preserved as written at closure time.
2. No next-step/suggestion surface ("what should we investigate next?" runs the
   literal noisy investigation cue).
3. Bounded reference vocabulary ("that's the one I was talking about." fails closed).
4. Stance is representation-only (deliberate authority boundary; never execution).
5. Temporal precision is honest-only ("yesterday"); no fabricated timestamps.

## Phase 4 evidence gate — **NOT JUSTIFIED**

Remaining gaps are bounded deterministic coverage or intentional fail-closed. There
is no repeated realistic failure where Atlas holds all required context and still
cannot infer intended meaning, and no measurable benefit from a semantic proposer
that would not risk a second authority. Atlas remains fully valid with models OFF.

## Known pre-existing failures (unchanged, unrelated to Natural Conversation)

`test_ambiguity_uncertainty::test_orchestration_ambiguity_gate_records_the_pending_question`
("Run it" — frame-clarification ownership); `test_l9_real_world_validation::TestCorpusContract`
(intake drift); `test_c3_real_world_capability_evidence` comparison + architecture
(real-kernel); `test_step10_multi_intent_multi_step::TestRealKernel`
(`KeyError: 'orchestration'`). None are Natural Conversation blockers.

## Architecture / governance / model independence

`ConversationService` remains the authoritative dispatcher; existing handlers,
state, discourse/referents, dialogue threads, salience, and the evidence/result
lifecycle remain authoritative. No second state/dialogue/memory/referent/execution/
orchestration/governance authority was introduced. No authority metadata leaks into
user-facing behaviour. External models remain optional, non-authoritative. L0–L10
remain frozen; no L11, Phase 4, or later stage is created.

## Final determination

**NATURAL CONVERSATION OBJECTIVE SATISFIED.** Phases 0–3 acceptance is substantively
met; remaining limitations are bounded, intentional, or honest; Phase 4 is not
justified; architecture and governance are intact. The roadmap can be formally
closed. The smallest optional future evidence-driven improvement (NOT scheduled,
NOT a phase) is the bounded target-vocabulary extension for natural investigation
paraphrases.

## Post-closure amendment — G1 closed by C4

The "smallest optional future evidence-driven improvement" named above was
subsequently validated by the **C3** milestone as a genuine bounded understanding
gap (G1: the investigation-target vocabulary was duplicated across three bounded
detectors in `atlas/conversation/task_intake.py`, so real Atlas subsystems such as
`storage`, `reasoning` and `toolchain` were recognised by the canonical cue route
while natural paraphrase forms declined them), and was then **closed by C4** with a
single bounded source of truth (`_ATLAS_INVESTIGATION_TARGETS`). See
`docs/ATLAS_STATE.md` §31. This amendment records that history; it does not reopen
the Natural Conversation roadmap, change its determination, or create any new
phase, milestone or capability requirement.
