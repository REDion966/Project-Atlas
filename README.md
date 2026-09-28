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
- **The post-L10 evidence-driven step arc is COMPLETE (Steps 1 → 7)** — additive,
  model-independent, and owner-gated; no new engine, planner, scheduler or store
  was introduced, and no later step is defined (see `docs/ATLAS_STATE.md` §34.10
  through §34.13):
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
  - The validated loop is the demonstrated evidence-gap remedy class
    (`untested_component` → deterministic coverage module), **not** unrestricted
    autonomous self-development. **The next step is NOT STARTED** and stays
    evidence-driven.
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
