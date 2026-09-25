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
