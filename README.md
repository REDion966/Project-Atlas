# Project Atlas

**Atlas is a personal, modular AI operating framework** — not a chatbot, not a
model wrapper, not a demo. It orchestrates replaceable AI models while owning its
own memory, knowledge, reasoning, planning, learning, tooling, and — under
governance — its own governed development.

> *AI models are tools. Atlas is the intelligence. Models may change. Atlas remains.*

---

## Architectural philosophy

- **Deterministic-first, model-independent.** External AI (providers/models) is
  optional and replaceable, never a permanent dependency, authority, or source of
  truth. The deterministic path makes no provider or network call.
- **Human ownership.** One logical OWNER. No autonomous code mutation; no
  autonomous scheduling; all privileged actions are approval-gated and fail closed.
- **Additive evolution.** New capability is layered on the existing Evolution
  Framework; locked packages (kernel, runtime pipeline, reasoning core, storage)
  are extended, never redesigned.
- **Clean layering.** `CLI → Services → Managers/Engines → Repositories → Storage`;
  pure-logic modules never import infrastructure.

---

## Current status

- **Atlas Core** (Phase 22) and **Phase C** are complete; released baseline
  **v0.20.0** (tag `v0.20.0`). No Phase 23 exists.
- **Phase 1–5 direct-evolution program is COMPLETE:**
  - **Phase 1** — Atlas self-knowledge (capability/architecture model).
  - **Phase 2** — deterministic natural-language understanding and conversational
    development intake.
  - **Phase 3** — knowledge acquisition & research (deterministic authorized
    source selection; validated knowledge retrieval).
  - **Phase 4** — governed self-development (development cycle → OWNER approval →
    sandbox execution → verification, with relevant-test selection and bounded
    correction).
  - **Phase 5** — direct Atlas evolution: gap adjudication, deterministic scaffold
    authoring, a bounded Development Driver, an opt-in Development Envelope for
    **sandbox-only** execution, and **OWNER-only transactional promotion** with
    CODE versioning and capability activation. **Phase 5.2 is implemented and
    Phase 5.3 is validated (G1 — capability activation — closed).**
- **Target-state gates G1 → G3 are COMPLETE** (owner-scoped, additive; no G4 is
  defined or authorized — see `docs/ATLAS_STATE.md` §33):
  - **G1** — general conversational understanding: one deterministic,
    model-independent semantic layer (`SemanticFrame`) supplying bounded meaning
    to the EXISTING routing surfaces (which stay authoritative). (This gate label
    is distinct from the Phase 5.3 "G1" capability-activation closure above.)
  - **G2** — deep self-knowledge + open-ended knowledge: relationship/dependency
    answers from the existing architecture model for an explicit named target,
    and an unmatched knowledge question reports the existing D3 knowledge
    decision's own sufficiency and governed-acquisition status instead of a bare
    no-match.
  - **G3** — governed self-development: a conversational development request now
    reaches the EXISTING bounded `DevelopmentDriver` (gap → authoring →
    envelope-authorized sandbox → verification → promotion request), with the
    bounded capability-handler scaffold specification derived deterministically
    from the request's own words. The Development Envelope stays disabled by
    default, promotion remains OWNER-only, and nothing is approved, executed, or
    promoted by conversation.
- **The post-L10 evidence-driven step arc is COMPLETE (Steps 1 → 23)** — additive,
  model-independent, and owner-gated; no new engine, planner, scheduler or store
  was introduced, and no later step is defined (see `docs/ATLAS_STATE.md` §34.10
  through §34.29):
  - **Step 1** — open-ended conversation over the existing provider seam, with
    Atlas (not any model) remaining the authority.
  - **Step 2** — goal-centered orchestration: compound requests sequence as
    bounded multi-step goals over existing services through the existing
    `OrchestrationExecutor`, with bounded data-only result carry, bounded retained
    plan state and multi-turn plan resumption.
  - **Step 3** — evidence → self-development: a validated evidence gap
    (`untested_component`) becomes a development need, resolves to the component's
    real source file through the existing self-knowledge, and is carried by the
    existing development lifecycle through OWNER development approval, sandbox
    execution, verification, promotion review, a separate OWNER promotion approval
    and the existing `PromotionExecutor`.
  - **Step 4** — continuous self-improvement validation: the complete loop was
    validated with real-kernel evidence across two isolated Atlas instances over
    persisted state (the promoted change is observed by a fresh investigation, the
    original gap is no longer reported, and no redundant development is created); a
    control run without the promotion still reports the gap. **Step 4 required no
    production change.**
  - **Step 5** — natural-language understanding: the shared semantic layer
    interprets genuinely unseen phrasing into a bounded frame (role, owning
    domain, operation, subject) over word classes rather than literals, and an
    unhandled turn whose frame names no bounded operation now answers with what
    was read, states that the request is out of scope rather than a missing model,
    restates the bounded capability surface and records the interpretation —
    instead of reporting it as a model-unavailable problem. Interpretation only:
    no routing, approval, execution, promotion, permission or model change.
  - **Step 6** — intent & goal understanding: a bounded coordinator split of the
    existing semantic frame reads the multiple intents inside one request, every
    understood intent is answered by the existing deterministic surface, and any
    intent that cannot be mapped is reported explicitly as *not attempted*
    (with a bounded `multi_intent` record) instead of being silently discarded.
    The existing goal decomposition and goal-centered orchestration are unchanged.
  - **Step 7** — context & reference understanding: existing pronoun,
    demonstrative, location and most-recent-result references already resolve
    against the retained conversation state; an earlier-item reference
    ("the previous one") that names an item in a list is now reported as
    *unresolved* — with the active subject restated — instead of falling to the
    generic floor, so no referent is ever invented.
  - **Step 8** — conversational world state: a bounded, deterministic
    representation of the ACTIVE conversation topic (and what kind of thing it
    is), the bounded history of PRIOR topics, and the most recent unresolved
    reference, carried on the existing `ConversationState`. It distinguishes
    ACTIVE from HISTORICAL context, so a prior topic stops leaking into the
    current turn (a pronoun after a topic switch now resolves to the active topic
    instead of falling to the floor), returning to a prior topic is representable
    and non-mutating, completed work is marked distinct from active, and an
    unresolved reference stays unresolved. Representation only — no routing,
    approval, execution, promotion, permission or model change.
  - **Step 9** — ambiguity & clarification: Atlas detects genuine ambiguity, asks
    a bounded clarification only when the context does not justify one
    interpretation, preserves the competing candidates in a bounded
    `PendingClarification`, and resolves the user's follow-up deterministically
    (by name, ordinal or distinctive token) while resuming the correct existing
    route — e.g. a general contextual reference ambiguity now asks instead of
    falling to the model-unavailable floor, and an underspecified
    "Investigate it." asks for the subject instead of acting on the literal
    pronoun. Clear requests and unsupported input are never over-clarified.
    Representation only — no routing/approval/execution/promotion/permission
    change.
  - **Step 10** — multi-intent & multi-step understanding: a bounded,
    deterministic representation reads the distinct steps of a multi-intent
    request, preserves order only when the language expresses it, records a
    dependency only when a later step reasons over an earlier result, and routes
    the runnable read-only steps through the EXISTING orchestration bridge while
    answering casual clauses through the EXISTING builtin surface and reporting
    every other step truthfully (unsupported/governed/blocked). Two independent
    operational intents, explicit "first … then …" ordering and a dependent
    "investigate A, then analyze the findings" are now understood instead of
    being silently dropped or run over stale evidence.
  - **Step 11** — natural response generation: one bounded, deterministic,
    model-free response-realization layer presents an already-established outcome
    in a single truthful shape — each step with a human label for what it *was*,
    the recorded subject, the recorded state, and its OWN recorded result (or the
    recorded reason when it did not succeed). The mechanical report that echoed
    the whole request, exposed internal step ids/targets and printed internal
    attribution is gone, while the deterministic audit metadata is unchanged.
  - **Step 12** — unified capability model: the existing canonical capability
    model (registered capabilities/tools) is extended with a bounded,
    evidence-grounded **operational capability catalogue** (investigate,
    research, plan, approve, multi-step, clarify, follow-up, …), each grounded in
    the existing route that implements it and carrying identity, category,
    supported operations, state, dependency, owning evidence and limitations.
    Capability lookup (`capability_contract`), the CLI/kernel view and the
    conversational capability inventory/`explain` answers now speak the same
    grounded view — unavailable (model-backed / unwired governed) and unknown
    capabilities are reported truthfully rather than claimed. Representation
    only.
  - **Step 13** — capability state & self-knowledge: each known capability now
    exposes a bounded, grounded **state** (`available` / `unavailable` /
    `partially_supported` / `blocked` / `governed` / `unknown`) with a reason,
    its governing condition and any blocking dependency, derived deterministically
    from the evidence Atlas already holds (registration/wiring, dependency class,
    component health, the OWNER approval boundary). The kernel contract and the
    conversation agree, an external-model-dependent capability is truthfully
    unavailable without a provider, and capability-state questions ("Is
    investigation available?", "Why can't you research?", "Which capabilities are
    unavailable?") are answered from the same model. Representation only.
  - **Step 14** — architecture self-understanding: the existing architecture
    model is joined with the unified capability model into one consistent view —
    which component OWNS each capability (or, for an operational capability, its
    backing route), grounded governance boundaries, and an explicit known/unknown
    architecture knowledge boundary. Bounded conversation questions ("Which
    component owns X?", "Where is X implemented?", "What is the responsibility of
    the X component?", "What are your governance boundaries?", "What architecture
    information do you not know?") are answered from that join, and an
    unregistered component is reported honestly rather than resolved to a
    spurious symbol. Representation only.
  - **Step 15** — autonomous knowledge need detection: a bounded, deterministic,
    model-free classification of the evidence Atlas already holds (the D3
    sufficiency decision, the D2 acquisition outcome, and the Step 12–13
    capability state) into ONE structured `KnowledgeNeed` — kind (`none` /
    `missing` / `stale` / `insufficient` / `contradictory` /
    `unsupported_capability` / `ambiguous` / `unknown`), actionability
    (`satisfied` / `actionable` / `unsatisfiable` / `unknown`), a grounded reason
    and bounded evidence. It is never inferred from unfamiliar wording, never
    turns an unavailable capability into missing knowledge, and fails closed to
    `unknown`. Two closed explicit forms ("what is the latest X?", "who won Y?")
    are recognised as knowledge requests instead of falling to the unsupported
    floor, and every knowledge answer carries the need as additive metadata.
    Detection only — no research, acquisition, storage/learning or
    capability-gap detection.
  - **Step 16** — autonomous research: a bounded, deterministic, model-free
    orchestration that ACTS on an actionable knowledge need through the EXISTING
    governed acquisition boundary (the deny-by-default host policy + the existing
    F8 pipeline) and returns ONE structured `ResearchOutcome` — status
    (`not_needed` / `researched` / `no_authorized_source` / `insufficient` /
    `failed` / `unknown`), mechanism, the bounded request formulated from the
    need, and the source identity + raw evidence preserved for the later
    provenance step. `researched` requires validated claims to actually have been
    established; a denied host is refused before any I/O, nothing is persisted or
    promoted, and no model decides whether research is valid.
  - **Step 17** — source evaluation & provenance: a bounded, deterministic,
    model-free representation of the chain **research → source → evidence →
    claim**, built read-only over the EXISTING claims/citations/verifications.
    Each source is evaluated only from recorded evidence (authorization outcome,
    whether it was used, whether its identity is known, whether any claim cites
    it, and the existing verification verdict); citation metadata is kept
    distinct from the acquired claim; `verified` (2+ supporting sources) is
    separated from `supported` (one source) and from merely-retrieved; conflicting
    and insufficient provenance are surfaced rather than silently trusted. Source
    credibility is never inferred from domain names or popularity, and
    reachability alone is never treated as truth.
  - **Step 18** — knowledge representation & learning: justified knowledge is
    represented as bounded `KnowledgeRecord`s carrying the Step 17 provenance
    chain verbatim, under a closed deterministic retention rule — a claim is
    retained only when the existing verification stands at `verified` (2+
    supporting sources) or `supported` (one source) **and** it carries a
    provenance link; `contested`, `unverified`, `unknown` and unattributed claims
    are refused with their reason recorded, duplicates are collapsed by claim id,
    and nothing is written, promoted or model-decided. The existing retrieval
    surface is now standing-aware (each retrieved claim reports its standing and
    its evidence ids), so an opaque `SUPPORTED` item can no longer be mistaken for
    corroborated knowledge.
  - **Step 19** — temporal & freshness-aware knowledge: retained knowledge now
    carries its EXISTING event timestamps (citation `retrieved_at`, claim
    `extracted_at`, verification `verified_at`) and a bounded temporal status
    computed by the EXISTING freshness assessor — `current_relative` (current
    **relative to when Atlas acquired it**, never a claim that the content is true
    now), `historical`, `undated` or `unknown`. Content time (when the knowledge
    is *about*) is kept strictly apart and stays unknown unless a source recorded
    one; absent temporal evidence is never treated as freshness, and no dates,
    validity periods or thresholds are invented.
  - **Step 20** — knowledge refresh: stale retained knowledge can now be
    re-validated on demand through the EXISTING governed acquisition pipeline — a
    bounded request is derived from the existing provenance (using the existing
    freshness assessor's action and recorded sources), the recorded web sources
    are authorized by the existing deny-by-default policy, and the refreshed
    evidence is read back through the Step 17–18 rules. A replacement is accepted
    **only** when it is justified and at least as strong as the retained standing;
    weaker, unjustified, denied, insufficient or failed refreshes explicitly
    preserve the original — refresh never means "overwrite because newer data was
    fetched", and nothing is scheduled or promoted.
  - **Step 21** — continuous information monitoring: a bounded, deterministic,
    model-free monitoring pass represents monitoring targets for retained knowledge
    and reports which require attention (`fresh` / `stale` / `uncertain` /
    `temporally_unknown` / `unknown`) using the existing temporal/freshness
    machinery, emitting idempotent observations that carry the existing refresh
    request. It observes only — no fetch, write, replacement or promotion — and
    refresh happens only when a caller explicitly invokes the existing governed
    path. It is deliberately **not** wired into `Atlas.tick()`: there is no timer,
    thread or background loop, so nothing is authorized, fetched or replaced just
    because a condition fires.
  - **Step 22** — general capability gap detection: one bounded, evidence-backed
    diagnosis (`supported` / `temporarily_blocked` / `governed` /
    `missing_knowledge` / `ambiguous` / `execution_failure` /
    `unsupported_capability` / `unknown`) reconciling the existing request-level
    adjudicator, the existing unified capability model's per-capability state and
    the existing knowledge need. A gap is claimed **only** when no capability
    covers a request whose subject is known from validated knowledge — never from
    unfamiliar wording, unknown entities, temporary source denial or missing
    knowledge; an unavailable capability is distinguished from an absent one, a
    governed one from a missing one, and a failed run from a missing capability.
    Nothing is wired into the conversation cascade.
  - **Step 23** — capability specification & development design: a CONFIRMED
    genuine gap becomes one bounded, reviewable specification — purpose, implied
    operations, dependencies, affected architecture areas (from the existing
    architecture model), constraints (its own scope boundaries), the existing
    governance boundary and verification requirements, and the existing advisory
    mechanism — with an explicit split between what the evidence establishes and
    what remains unresolved, and alternatives **listed** rather than silently
    chosen. Non-gaps are refused with a reason; inputs and outputs are never
    invented; it generates no implementation, code changes or proposal and grants
    no authority.
  - **Step 24** — Atlas direct self-development: an **authorized** specification
    becomes a governed development workflow. Only a specified, complete design is
    accepted (everything else is refused with a reason); it is translated into the
    existing development need and prepared through the existing development cycle,
    which stops at a bounded human approval request — a design is never silently
    converted into authorization. Implementation, verification and promotion
    readiness run only when the proposal already carries an authorizing status or
    an explicit authorization bound to it, and only ever through the existing
    sandbox execution, read-only verification and promotion gate: failed or
    unverified work is never promoted, and promotion itself stays a separate OWNER
    decision. The result records what changed, why and how it was verified.
  - **Step 25** — integrated autonomous intelligence loop: the completed
    capabilities now run as **one governed cycle** — request → understanding →
    knowledge assessment (research, provenance, retention, freshness, refresh,
    monitoring) → capability adjudication → specification → governed
    self-development → verification → promotion boundary → truthful response —
    with each stage delegating to the existing mechanism and routing on that
    mechanism's own typed result. The loop approves, authorizes, promotes and
    refreshes nothing by itself, stops at the existing human approval boundary,
    reports a promotion boundary only after verification actually succeeded, and
    a human approval can interrupt and resume it without losing state.
  - **Conversational exposure policy** (temporary post-roadmap step, not a
    roadmap phase): Atlas now states in one place which bounded read-only
    internal state may be exposed conversationally, and questions about its OWN
    state — a capability's state or declared requirements, the freshness of the
    knowledge it itself retains, and the source-authorization policy — are
    answered from those existing seams **before** the generic knowledge/research
    routes can reinterpret them. A request to *change* source authorization is
    answered only by a bounded explanation of the existing deny-by-default
    policy; conversation never authorizes, configures, executes or promotes
    anything.
  - **Conversational interface closure** (temporary post-roadmap step, not a
    roadmap phase): natural variations of the same intent now reach the correct
    existing surface — an explicit "what validated facts do you have about X?"
    is answered by the knowledge store instead of a self-knowledge page,
    subject-scoped staleness/currency questions are answered from the existing
    temporal assessment (only when Atlas actually retains knowledge about the
    subject, and scoped to that knowledge), structure/composition questions
    ("how is the conversation service structured?") are answered from the
    existing architecture model, and the bounded investigation idioms ("look
    into X") reach the read-only investigation route. Nothing new is authorized
    or executed by understanding a sentence.
  - **Development loop closure** (temporary post-roadmap step, not a roadmap
    phase): a natural-language development request now reports, from the EXISTING
    Step-22 adjudicator, whether a capability or retained knowledge already
    covers it — and, when it is a genuine capability gap, the bounded design the
    existing specification produced (what it is for, what it would touch, how it
    must be verified and the governance boundary it must respect) — ahead of the
    unchanged governed `DevelopmentDriver` report. Understanding a request still
    authorizes nothing: implementation needs a bounded change payload and the
    OWNER's approval, focused tests run in the sandbox before any promotion, and
    a failed test yields no promotion request.
  - **Research → learning → development** (temporary post-roadmap step, not a
    roadmap phase): a request that names an explicit external source (a URL or a
    GitHub repository) is now carried through the existing governed research
    pipeline — deny-by-default host authorization, acquisition, provenance and
    evaluation, retention of only justified knowledge — and then reused: the
    retained knowledge resolves the original knowledge gap, retrieval answers
    from it, and a development request that needed it reaches the existing
    capability specification. The host allowlist stays the authority (an
    unauthorized host is reported as denied and nothing is stored), external
    content is treated as data only, and research still authorizes nothing.
  - **Self-architecture understanding** (temporary post-roadmap step, not a
    roadmap phase): the existing architecture model's declared facts are now
    reachable conversationally — what a component or subsystem depends on, which
    registered components/subsystems depend on a given target, and an honest
    answer for contracts/extension points (the model records no interfaces, so it
    says so and reports the registry facts it does hold). A missing architectural
    fact travels the existing governed research path, and the retained knowledge
    grounds the existing capability specification. Nothing is invented, and no
    architecture answer grants authority.
  - The validated loop is the demonstrated evidence-gap remedy class
    (`untested_component` → deterministic coverage module) plus a
    specification-driven workflow and the integrated cycle above — every one of
    them stopping at each existing governance boundary — **not** unrestricted
    autonomous self-development. **Steps 1 → 25 are COMPLETE**; no later roadmap
    step exists or is implied, and the work in progress is a bounded temporary
    step rather than a new roadmap phase.
- Atlas is **not** autonomously self-modifying: development is sandbox-only,
  promotion/activation are OWNER-only, and there is no tick/daemon autonomy.
- **Full-suite baseline (measured at the Step 25 checkpoint):** 9,602 passed, 3
  skipped, 368 subtests passed, **30 failed** (3:43:48). All 30 failures were
  reproduced identically against a pristine HEAD — they are **pre-existing** and
  entirely in conversation/reference-resolution and evidence-gap-remedy suites
  (`test_reference_consumption`, `test_lexical_canonicalization`,
  `test_last_operation_repeat`, `test_p15_2_conversation_continuity`,
  `test_ambiguity_uncertainty`, `test_nlu6_model_independence_failure_proof`,
  `test_l9_*`, `test_c3_*`, `test_c5_*`, `test_c6_*`,
  `test_continuous_self_improvement_validation`,
  `test_evolution_model_assisted_activation`, and the evidence-development suites
  that report "no resolvable real evidence gap"); none is caused by Step 25 and
  none is in Step-25 scope. The earlier 5,945-item/0-failure figure predates the
  post-L10 steps 14-24, which were validated with focused suites only. Current
  schema version: **11**.

---

## Authoritative documentation

1. **`docs/ATLAS_STATE.md`** — the single authoritative current-state handbook
   (architecture, modules, capabilities, governance, development lifecycle,
   verification status, limitations, roadmap status).
2. **`docs/ROADMAP.md`** — authoritative forward direction (Phase 1–5 complete;
   no Phase 6/L11+).
3. **`docs/ATLAS_CORE.md`** — permanent architectural principles.
4. **`docs/ATLAS_VISION.md`** — identity and purpose.
5. **`docs/adr/`** — architectural decision records.
6. **`CHANGELOG.md`**, **`docs/archive/`** — historical record only (never current
   authority).

This `README.md` is a public entry point, not an authority.

---

## Getting started

```bash
# Python 3.11+ required
python -m venv .venv
.venv\Scripts\Activate.ps1          # Windows PowerShell
pip install -r requirements.txt
pip install -e ".[test]"

python main.py                      # interactive Atlas
pytest -q                           # test suite
```

## Repository layout (brief)

```
atlas/     kernel, runtime, cognition, reasoning, research, toolchain, longterm,
           advanced_reasoning, evolution, memory/knowledge/understanding,
           learning_engine, conversation, storage, cli
tests/     test suite
docs/      documentation (see above)
main.py    interactive entry point
```

Primary CLIs: `atlas research | toolchain | skill | memory | reasoning | evolution |
proposals | goal`, and the governed development surfaces
`atlas postcore develop | drive | confirm | execute | approve-promotion | promote`.

---

## Author

AB AL Mamun
