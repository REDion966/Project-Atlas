# D1 — Conversation Engine

Authoritative description of the D1 Conversation Engine architecture. This
document describes **only what D1 implements**; it does not claim D2/D3
capabilities that do not exist yet.

## 1. Responsibility

The Conversation Engine is the smallest interaction/interpretation/orchestration
boundary between human language and Atlas's existing deterministic systems:

```
user text
  -> ConversationEngine.interpret(...)      interpretation only
  -> SemanticIntake                          bounded meaning
  -> existing ConversationService routing    unchanged, authoritative
  -> existing governed handlers/services
```

It is **not** a brain, planner, capability dispatcher, governance system,
memory system, model, or authority. It performs no routing, execution,
approval, or promotion, and it never calls an external model or the network.

Implementation: `atlas/conversation/engine.py` (`ConversationEngine`,
`EngineInterpretation`, `detect_subtasks`).

## 2. SemanticIntake contract

`atlas/conversation/semantic_intake.py` defines `SemanticIntake`, a frozen,
deterministic, JSON-safe projection built by `build_semantic_intake(spec, text,
...)`. It is derived from the existing `TaskSpec` (plus the engine's bounded
extras) and covers:

`act`, `objective`, `operation`, `entities`, `resolved_reference`,
`constraints`, `priorities`, `success_criteria`, `subtasks`, `ambiguities`,
`clarification_questions`, `requested_information`, `requested_operation`,
`required_capabilities`, `required_knowledge`, `requested_response`,
`corrections`, `task_type`, `confidence`, `provenance`.

The projection rides the existing `TaskSpec.context` under the key
`semantic_intake` (`engine.SEMANTIC_INTAKE_KEY`); every other context key is
preserved. Malformed pieces degrade to empty — the builder never raises for
malformed input.

## 3. Authority boundary

Semantic interpretation **never grants authority**. `SemanticIntake` has no
`authorized`/`approved`/`permission` field, and
`provenance["authority"] == "none"` is a machine-checkable marker.

Interpretation of "I approve this." may yield an act/correction, but it must not
approve a proposal, create an approval, authorize execution, promote, or change
governed state. Only the existing authoritative mechanisms may grant authority:
OWNER/session authority, the approval manager, the promotion gate/executor, and
the kernel authorization checks. External or user-provided content is never
trusted instruction merely because the engine parsed it.

## 4. Conversation-state boundary

The bounded extension of the existing `ConversationState`
(`atlas/conversation/conversation_state.py`) adds three session-scoped,
representation-only fields plus one record type:

- `current_objective` — the current bounded objective (what the human asked for).
- `subtasks` — ordered subtasks of a compound request (representation only).
- `corrections` — a bounded tuple of `Correction(previous, corrected, turn_id)`
  recording superseded readings.

Bounds: `MAX_SUBTASKS = 4`, `MAX_CORRECTIONS = 5` (older entries dropped).
`to_dict()` is JSON-safe and `update()` preserves the typed values across a
`to_dict` round-trip.

Conversational state holds **facts, never authority**. It cannot replay
approval, grant authorization or execution permission, or bypass session
checks. There is no new conversation store and no durable conversational
memory.

## 5. chat / stream integration

`ConversationService._intake` routes interpretation through the engine for both
`Atlas.chat()` and `Atlas.stream()` (identical path — streaming cannot bypass
it). The existing routing cascade is unchanged: repeat handling,
capability-detail precedence (C4), investigation/approval/planning/execution/
recovery/verification/report/impact/autonomy, the development bridge, the
deterministic builtin floor, orchestration, cognition, and the AI path.

Legacy behavior is preserved exactly when `task_intake=None` (the engine is not
constructed).

## 6. Determinism and model independence

The engine reuses the existing deterministic `TaskIntake` and resolvers. With
`ai.external_providers=false` and `development.model_assisted_authoring=false`
(the defaults) it is fully functional, makes no network call, and requires no
external model. Entity/reference inputs come from the existing
identification/resolution stages.

## 7. Extension points for D2/D3

- `required_knowledge` / `requested_information` on `SemanticIntake` are the
  declared semantic requirement a future Conversation↔Knowledge bridge (D3) can
  consume to decide insufficiency and formulate a bounded research requirement.
- `required_capabilities` is advisory; the existing
  `CapabilityRegistry`/`Router`/`Dispatcher` remains authoritative.
- `subtasks` provides the bounded compound representation D4 can later act on
  through existing orchestration — never through a new planner.
- No D1 code enables external internet access or modifies the web allowlist
  (`research.web_allowed_hosts`); that remains D2 scope.

## 8. Conversational self-knowledge bridge (bounded)

Atlas can now map bounded natural-language questions about its OWN systems onto
EXISTING verified self-knowledge surfaces. The conceptual path is:

    natural language
      -> TaskIntake / TaskSpec
      -> shared SemanticFrame bounded semantic SUBJECT
      -> self-knowledge topic routing
      -> existing capability / architecture / repository / research /
         development surfaces
      -> deterministic, evidence-backed response

Supported bounded subject families (semantic concept classes, so ordinary
paraphrases converge): capabilities; architecture/components; capability
contracts; repository-symbol intelligence; external repository/research;
evidence/trust; capability gaps; the governed development lifecycle; sandbox/
verification; governance/OWNER authorization; promotion/activation;
self-knowledge refresh; model independence. The lifecycle answer reconstructs
the ACTUAL order (understand -> inspect/gap -> research/evidence -> design ->
sandbox -> test -> verification -> promotion request -> OWNER authorization ->
activation -> self-knowledge refresh); explaining it conversationally does NOT
execute or authorize it.

Bounds and invariants (unchanged):

- No new knowledge database, no second capability registry, no second repository
  map, no new memory subsystem, no daemon. Answers come only from existing
  surfaces and verified anchors.
- Immediate conversational continuity ("What were we just talking about?")
  resolves from EXISTING structured conversation state / prior turns; with no
  reliable antecedent it stays fail-closed (clarify/refuse) — never fabricated.
- Deterministic with `ai.external_providers=false`; external models remain
  optional, untrusted interpretation aids with no authority, and cannot approve,
  promote, activate, bypass verification, or mutate live Atlas.
- Known bounded limits: the subject vocabulary is bounded; context-dependent
  questions need a reliable antecedent; free-form architecture reasoning outside
  the supported families stays unsupported.

Evidence: `tests/test_self_knowledge_bridge.py`.
