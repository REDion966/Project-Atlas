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
- **The post-L10 evidence-driven step arc is COMPLETE (Steps 1 → 15)** — additive,
  model-independent, and owner-gated; no new engine, planner, scheduler or store
  was introduced, and no later step is defined (see `docs/ATLAS_STATE.md` §34.10
  through §34.21):
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
  - The validated loop is the demonstrated evidence-gap remedy class
    (`untested_component` → deterministic coverage module), **not** unrestricted
    autonomous self-development. **Steps 1 → 15 are COMPLETE; the next step
    (Step 16) is NOT STARTED** and stays evidence-driven.
- Atlas is **not** autonomously self-modifying: development is sandbox-only,
  promotion/activation are OWNER-only, and there is no tick/daemon autonomy.
- **Latest verified full-suite baseline (historical, not re-run for the Phase 3–5
  reconciliation):** 5,945 test items executed — 5,876 test cases passed (+67
  subtests), 0 failed, 0 errors, 2 skipped. Focused suites were used for the recent
  reconciliations. Current schema version: **11**.

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
