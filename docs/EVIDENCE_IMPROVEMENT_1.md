# Evidence-Driven Improvement 1 — Deep Self-Knowledge + Conversational Knowledge Integration

Post-Phase-D, evidence-driven refinement. No new phase, no new architecture, no
duplicate systems. Baseline: read-only real-world conversation validation at Git
HEAD `8ec67fb58de3643591fe3e588512a47d96e3f0dd`.

## Problem (evidence)

The baseline found two integration/extension gaps in EXISTING systems:

1. **Self-knowledge is structurally accurate but shallow.** Atlas could report
   architecture counts but could not answer component/responsibility,
   relationship, request-flow, development-flow, OWNER-approval, sandbox,
   authorization-boundary, or extension-point questions.
2. **Conversational knowledge integration is incomplete.** External-subject
   "current status" requests were misrouted to Atlas's own status report; general
   conversation did not reliably recognise external-knowledge requests or retain
   the result for follow-ups ("What did you find?", "What source supports that?",
   "Can you continue?").

## Changes (all additive; no new subsystem)

| File | Change | Why |
| --- | --- | --- |
| `atlas/conversation/builtin_response.py` | New Atlas-specific self-knowledge topics (`request flow`, `development process`, `owner approval`, `sandbox execution`, `authorization boundary`, `extension points`) with **verified module anchors**; `_COMPONENT_HINTS` (bounded description → actual component, module verified before reporting) rendered by the existing architecture surface; `_EXTERNAL_KNOWLEDGE_RES` matcher; `_match_external_knowledge`; two public claim methods (`match_self_knowledge_topic`, `match_external_knowledge`); message building factored into `_build_message` | Answer the evidenced self-knowledge questions from existing structural sources; route external-subject status to the governed knowledge path |
| `atlas/conversation/conversation_service.py` | Early, deterministic claim of Atlas-specific self-knowledge topics and external-knowledge requests (mirrors the existing C4.1 pre-check); `_record_knowledge_result` (bounded `last_knowledge` snapshot); `_maybe_handle_knowledge_followup` (whole-turn-anchored `find`/`source`/`continue`) | Make the two gaps reachable from free-text conversation before development/execution handlers; preserve knowledge-result continuity |
| `atlas/conversation/conversation_state.py` | Bounded `last_knowledge: dict \| None` field (+ `to_dict` / `update` round-trip) | Retain the minimum context for immediate follow-ups |

No store, engine, registry, research path, governance, authorization, sandbox, or
promotion mechanism was added.

## Self-knowledge improvements (baseline failures)

| Question | After | Result |
| --- | --- | --- |
| Which component decides whether external knowledge is necessary? | `KnowledgeDecisionService` in `atlas/research/knowledge_decision.py` | PASS |
| Which component coordinates work execution? | `WorkOrchestrator` in `atlas/orchestration/work_orchestrator.py` | PASS |
| How does a user request travel through your system? | `request flow` topic; ConversationService → engine/SemanticIntake → KnowledgeDecisionService → D4/D5 | PASS |
| How does your development process work? | `development process` topic; DevelopmentDriver → PENDING_APPROVAL → CodeSandbox → DevelopmentVerification → PromotionGate | PASS |
| Where does OWNER approval happen? | `owner approval` topic; AuthorityService/SessionManager + ApprovalManager | PASS |
| How is sandbox execution enforced? | `sandbox execution` topic; CodeSandbox via SelfDevelopmentLoop; live repo never modified | PASS |
| What prevents a natural-language request from authorizing itself? | `authorization boundary` topic; SemanticIntake carries no authority field | PASS |
| If you needed a new capability, where would it fit? | `extension points` topic; CapabilityRegistry, reuse existing services, governed verification | PASS |

Unknown subjects fall back to the deterministic architecture summary and never
invent a component/class.

## Conversational knowledge improvements (baseline failures)

| Turn | After | Result |
| --- | --- | --- |
| "What is the current status of the Artemis moon program?" | `validated_knowledge` (local-first, then D3/D2); NOT the status report | PASS |
| "What did you find?" | resolves against `last_knowledge` (query/status/content) | PASS |
| "What source supports that?" | returns attached provenance, or honestly states none exists | PASS |
| "Can you continue?" | resolves against the current knowledge context; states it does not autonomously continue | PASS |
| "What is your status?" (self) | still the Atlas status report | PASS |

## Invariants preserved

- Self-knowledge is **read-only** (no proposal/approval/execution/promotion; verified by test).
- External knowledge is **not authoritative**; D2 acquisition stays deny-by-default (`research.web_allowed_hosts` unchanged).
- No external model, no network dependency introduced into core; `model_used=False` on every deterministic answer.
- No authority from natural language; no D4/D5 authorization broadened.
- Fail-closed: unknown/ambiguous turns fall through to existing behaviour; follow-ups without context are not fabricated.

## Tests

- New: `tests/test_evidence_improvement_1.py` — 31 tests (`python -m pytest tests/test_evidence_improvement_1.py -q`).
- Focused regression batch 1 (D1–D5, C4.1, C5, C6.1, NLU1, L8, provenance, phase116/129/125/123): **283 passed**.
- Focused regression batch 2 (builtin/capability/architecture/conversation/development-intake/NLU2–6/C3/approval/governance): **863 passed, 1 failed**.

The single failure —
`tests/test_conversation_turn_recall.py::TestTurnRecallIntegration::test_recall_does_not_mutate_state_manager`
— is **pre-existing at pristine HEAD** (verified by stashing this change set; it
fails identically). It is a stale test predating D1's `current_objective` state
update, of the same class as the already-known stale `tests/test_investigation.py`.
Not fixed here (out of the evidenced scope).

An initial broader `request flow` pattern regressed
`tests/test_builtin_self_knowledge.py::TestSelfKnowledgeRoutingPrecedence::test_process_question_is_self_knowledge`;
it was tightened (verified the test passes again). No unresolved regression.

## Remaining evidence-backed gaps (unchanged by this improvement)

- Natural-language paraphrase coverage remains bounded (only evidenced phrase families).
- Conversational context/reference resolution and **correction handling** remain partial.
- D4/D5 orchestration is still not reachable from free-text chat (explicit kernel APIs only) — this change does not widen that, by design.
- Broader architecture reasoning (arbitrary relationship/impact questions) and broader self-development planning remain shallow.

## Recommendation

Do not declare the natural-language problem solved. One focused improvement
(correction application, currently recorded but not applied) is the smallest next
evidence-backed candidate.
