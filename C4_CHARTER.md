# PROJECT ATLAS — C4 CHARTER (AMENDED) + C4.2 AUTHORITATIVE SCOPE

Milestone: C4 — Evidence-Driven Capability Evolution (Phase C)
Status: Charter amendment recorded; C4.2 scope defined (NOT implemented)
Provenance: derived from C4.1 evidence in `C4_1_CAPABILITY_GAP_EVIDENCE.md`

> This artifact records the narrowly-justified C4 scope amendment and the
> C4.2 target. It does not rewrite historical roadmap documents
> (`docs/ROADMAP.md` M0–M7 remains historical and unmodified), change any
> completed milestone status, or authorize C4.3+.

---

## Part A — C4 CHARTER (AMENDED)

### A.1 Objective

Enable Atlas to turn a **validated real-world capability need** into a
governed, verified, evidence-backed capability improvement using Atlas's
existing evolution machinery. Evolution is justified by real-world evidence,
not by developer convenience.

### A.2 Mandatory invariants (unchanged)

- Atlas is model-independent.
- External AI models are optional tools only.
- Atlas itself is the intelligence.
- Deterministic-first operation.
- Human approval for governed development.
- Governed execution.
- Sandbox verification.
- Fail-closed behavior.
- Evidence-driven evolution.
- No uncontrolled self-modification.
- No autonomous coding.
- No autonomous promotion/apply.
- No governance bypass.
- No roadmap drift.

### A.3 Non-goals (unchanged)

C4 is NOT unrestricted self-modification; autonomous coding; external-LLM
reasoning; promotion/apply automation; a replacement for the governance layer;
general conversational reference resolution (GAP-C31-02); C5 self-knowledge;
C6 knowledge maturity; C7 human understanding; C8 autonomy expansion; C9
continuous evolution.

### A.4 Amendment — new bounded category: "C4 Capability-Exposure / Integration Evolution"

**Previous boundary.** C4 concerned turning a *validated capability gap* (in
which the required ability was considered missing) into a governed improvement.

**Evidence supporting the amendment (from C4.1).** Real-world use through
`Atlas.chat(...)` reproduced a genuine, bounded, deterministic limitation:
Atlas already owns a deterministic repository dependency/impact capability
(`RepositoryMap.dependencies_of` `:114`, `dependents_of` `:119`,
`impact_set` `:123`; `RepositoryMapBuilder.build` `:208`), and uses it
internally (`atlas/evolution/development_planner.py:241`), yet the production
conversational path cannot answer the corresponding real-world request
("If I change `<module>`, which other modules depend on it and what would be
affected?") — it degrades to a `degraded_notice`. C4.1 classified this as
**category D — interface / capability-exposure / integration limitation**, not
a defect and not a missing core capability. Evidence:
`C4_1_CAPABILITY_GAP_EVIDENCE.md` (§4, §7, §8, §9).

**Amended C4 boundary.** C4 may additionally evolve Atlas when ALL of the
following hold:

1. a useful deterministic capability already exists internally;
2. real-world evidence demonstrates that Atlas users cannot naturally
   access/use that capability through the production Atlas interface;
3. the limitation is reproducible;
4. the limitation is not an existing contract defect;
5. the improvement is bounded;
6. objective verification is possible;
7. no external AI model is required for the capability;
8. governance and approval boundaries remain unchanged;
9. the change does not pull C5–C9 functionality forward;
10. the target improves Atlas's actual capability usage/exposure rather than
    merely cosmetic UI behavior.

This category is a legitimate C4 target **only** when every requirement above
is satisfied. It does not broaden C4 into unrestricted interface development,
and it does not make every usability issue a C4 target.

---

## Part B — C4.2 AUTHORITATIVE SCOPE

### B.1 Identity

**C4.2 — DETERMINISTIC REPOSITORY IMPACT-ANALYSIS CONVERSATIONAL EXPOSURE**

### B.2 Objective

Allow Atlas to naturally answer a **bounded class** of real-world repository
impact-analysis questions through the production `Atlas.chat(...)`
conversational path by exposing its already-existing deterministic repository
dependency/impact capabilities.

Representative user request:

> "If I change `atlas.conversation.conversation_state`, which other modules
> depend on it and what would be affected?"

C4.2 is NOT a general natural-language reasoning engine. The target is the
smallest deterministic integration that connects an already-existing Atlas
capability to an actual production conversational request.

### B.3 Production path (unchanged architecture)

```
USER REQUEST
    ↓
Atlas.chat(...)
    ↓
ConversationService (bounded impact-request recognition/routing)
    ↓
existing deterministic RepositoryMap capability
    ↓
impact/dependency result
    ↓
evidence-grounded conversational response
```

No redesign of `ConversationService`; no generalized reasoning architecture;
no LLM; no autonomous coding.

### B.4 Bounded capability (must include)

- A. Production conversational entry: `Atlas.chat(...)` → `ConversationService.send(...)`.
- B. Deterministic recognition/routing of the bounded repository impact-analysis request.
- C. Use of existing repository-map capabilities: `dependencies_of`, `dependents_of`, `impact_set`.
- D. Deterministic, evidence-grounded response.
- E. Clear distinction between: direct dependencies/dependents; transitive impact where available; affected repository components; unsupported/unresolved targets.
- F. Fail-closed behavior when the request cannot be safely resolved.
- G. No external AI model required.
- H. No mutation of the repository.
- I. No autonomous implementation.
- J. No change to authorization/governance boundaries.

### B.5 Explicit non-goals (must NOT implement)

General conversational reference resolution; GAP-C31-02; broad natural-language
understanding; general-purpose semantic parsing; C5 self-knowledge/capability
model; C6 memory/learning maturity; C7 human-understanding functionality; C8
autonomous development; promotion/apply automation; CODE writer; autonomous
code generation; external LLM reasoning; Ollama/Qwen/OpenAI/Anthropic
dependency; new autonomous mutation paths; governance changes; sandbox
redesign; speculative future capabilities; cosmetic-only UI improvements.
Do not reopen closed C3.3 work; do not reinterpret C4.2 as "make Atlas
understand arbitrary language."

### B.6 Acceptance criteria

- **ARC-4.2-01** A real user can submit a bounded repository impact-analysis question through `Atlas.chat(...)`.
- **ARC-4.2-02** The production conversational path reaches deterministic Atlas logic capable of answering the bounded request.
- **ARC-4.2-03** The implementation uses the existing repository dependency/impact machinery rather than duplicating repository graph logic unnecessarily.
- **ARC-4.2-04** For a valid repository target, Atlas returns deterministic, evidence-grounded impact information.
- **ARC-4.2-05** Direct and/or transitive impact is represented accurately according to the existing repository-map contract.
- **ARC-4.2-06** Repeated identical inputs produce stable deterministic results.
- **ARC-4.2-07** The behavior works without an external AI model.
- **ARC-4.2-08** AI failure/unavailability does not prevent the deterministic capability from functioning.
- **ARC-4.2-09** Unknown or ambiguous targets fail closed rather than producing invented impact information.
- **ARC-4.2-10** No repository mutation occurs during impact analysis.
- **ARC-4.2-11** Existing governance, authorization, sandbox, execution, and promotion contracts remain unchanged.
- **ARC-4.2-12** Existing regression tests remain clean.
- **ARC-4.2-13** The feature does not implement GAP-C31-02/general reference resolution.
- **ARC-4.2-14** The implementation remains model-independent.
- **ARC-4.2-15** A real production-entrypoint verification demonstrates that the capability is actually usable through `Atlas.chat(...)`, not merely through an internal function/unit test.
- **ARC-4.2-16** The final evidence demonstrates: real-world request → conversational routing → deterministic repository reasoning → evidence-grounded answer.

### B.7 Evidence base

- `C4_1_CAPABILITY_GAP_EVIDENCE.md` — category-D finding, reproduction, and architectural investigation.
- Existing capability: `atlas/research/repository_map.py:114,119,123,208`; internal production use at `atlas/evolution/development_planner.py:241`.

---

## Integrity notes

- This artifact adds the C4 amendment and C4.2 scope only.
- No production Python behavior, tests, governance, authorization, execution,
  sandbox, or external-model integration is modified by recording this scope.
- Historical roadmap documents are not rewritten; no completed milestone status
  changes; no C4.3+ is invented.
