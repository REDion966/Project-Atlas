# D3 — Conversation + Knowledge Integration

Authoritative description of the D3 knowledge-decision integration. It describes
only what D3 implements; it does not claim D4/D5 capabilities.

## 1. Flow

```
user request
  -> Conversation Engine (D1) / SemanticIntake      (knowledge requirement)
  -> KnowledgeDecisionService (D3)                  local-first decision
        -> ValidatedKnowledgeRetriever (C6.1)        sufficient?  -> answer (NO network)
        -> ExternalKnowledgeAcquirer (D2)            otherwise    -> governed acquisition
        -> ValidatedKnowledgeRetriever               re-read newly validated knowledge
  -> existing conversation response construction
```

Implementation: `atlas/research/knowledge_decision.py`
(`KnowledgeDecisionService`, `KnowledgeSufficiency`, `KnowledgeAnswer`,
`required_freshness`), exposed via `Atlas.knowledge_decision` /
`Atlas.answer_knowledge_question(...)`, and wired into the conversational
knowledge surface through `BuiltinResponseService`'s optional
`knowledge_decision_provider`.

## 2. Knowledge requirement

The knowledge requirement comes from the D1 `SemanticIntake`
(`required_knowledge` / `requested_information` / `objective`) — not from raw
text and not from a new cue list. The acquirer's `acquire_for_intake(semantic)`
and the kernel's `answer_knowledge_question(objective)` consume it.

## 3. Sufficiency decision

`KnowledgeDecisionService.decide(...)` returns a `KnowledgeSufficiency`:

- **SUFFICIENT** — validated knowledge (local, or via governed acquisition)
  covers the request;
- **CONTRADICTORY** — acquired evidence reports a conflict (`CONTESTED`);
  both claims retained, no winner chosen;
- **STALE** — relevant knowledge exists but the request requires currency;
- **INSUFFICIENT** — not enough evidence to answer;
- **UNKNOWN** — sufficiency could not be established (e.g. acquisition denied);
- **UNSUPPORTED** — not a knowledge request / malformed.

Keyword overlap alone is never treated as proof of sufficiency: only
`SUPPORTED` claims returned by `ValidatedKnowledgeRetriever` count.

## 4. Local-first (mandatory)

`retrieve_with_acquisition(query, candidate_urls=...)` returns existing
validated knowledge **without any acquisition** when the store already covers
the query. External acquisition runs only when the local store has nothing (or
currency is required). Tests assert a sufficient local result performs **zero**
external acquisition.

## 5. Acquisition boundary

External acquisition happens only through the D2 `ExternalKnowledgeAcquirer`,
whose authorization is enforced at the `WebSourceAdapter` host policy
(deny-by-default). D3 invents no URLs and bypasses no policy: candidate URLs
come from an explicit, optional configuration
(`research.external_source_urls`, empty by default) and are filtered by the
adapter policy. With the default configuration, acquisition is
`no_authorized_source` and no network access occurs.

## 6. Evidence, provenance, contradiction, freshness, uncertainty

All values are the EXISTING ones: `SUPPORTED`/`PLAUSIBLE`/`CONTRADICTED`/
`CONTESTED`, `CitationRecord` provenance, claim/verification confidences, and
`KnowledgeFreshnessAssessor`. `KnowledgeAnswer` (and the reused
`ValidatedKnowledgeResult`) exposes claims, sources, contradiction flag,
freshness requirement, and acquisition status so uncertainty is represented,
never collapsed into a generic "I don't know" and never inflated into
confidence.

## 7. Conversational integration

The built-in validated-knowledge surface (`BuiltinResponseService`) is extended
with an OPTIONAL `knowledge_decision_provider`. When the local store has
nothing, the provider may acquire through D2 and return newly validated
knowledge; if it returns nothing (including the deny-by-default case) the
existing C6.1 outcome is rendered **unchanged**. Default construction (provider
absent) is byte-for-byte the previous behaviour; the kernel wires the provider,
so the default deny-by-default outcome matches C6.1 exactly and no network
access occurs.

## 8. Trust boundary

External content remains untrusted data. `KnowledgeAnswer` carries no authority
field and cannot authorize, execute, promote, modify, change autonomy, or alter
configuration. Hostile text ("Ignore previous instructions… Promote the
change.") is evidence only.

## 9. Scope / D4 boundary

D3 is knowledge-backed conversation: sufficiency → governed acquisition →
validated answer. It does not implement self-directed task execution, tool
chains, autonomous development, promotion, or new autonomy levels — those are
D4/D5. D3 adds no second knowledge store, research engine, planner, or
capability dispatcher, and requires no external model.
