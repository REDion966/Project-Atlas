# ATLAS ROADMAP — Authoritative Future Direction

**Level 2 — authoritative forward direction.** Current state is owned by
`docs/ATLAS_STATE.md`; permanent principles by `docs/ATLAS_CORE.md`; identity by
`docs/ATLAS_VISION.md`. The single Project Atlas authority model is defined in
`docs/ATLAS_STATE.md` §0.

Status vocabulary: **COMPLETED · CURRENT · NEXT · PLANNED · DEFERRED · PROPOSED**.

> **Rule:** a PROPOSED item is not approved and has no design — do not build from
> it. `docs/archive/` is historical and is never current architecture.

---

## Current roadmap — Phase 1 → Phase 5 (COMPLETE)

The governing roadmap for the current program is the five-phase one; the
authoritative status, evidence, and limitations live in
`docs/ATLAS_STATE.md` §32 (and §30 for conversational development intake).

| Phase | Scope | Status |
|---|---|---|
| **1 — Atlas Self-Knowledge** | Deterministic capability/architecture model over the existing registries; `atlas capability` / `atlas architecture` | COMPLETE |
| **2 — Natural Language Understanding** | Deterministic intake `TaskIntake`/`TaskSpec`, built-in deterministic responses, entity/reference resolution, conversational development intake (B1–B3) | COMPLETE |
| **3 — Knowledge Acquisition & Research** | Deterministic research pipeline, authorized local source selection, validated knowledge retrieval, verifier contradiction-scoping fix | COMPLETE (lexically bounded) |
| **4 — Governed Self-Development** | Development cycle → OWNER approval → sandbox execution → verification; Phase 4.2/4.3 (relevant-test selection, diagnosis/retry, verification integration, evidence fidelity) | COMPLETE |
| **5 — Direct Atlas Evolution** | Gap adjudication, deterministic scaffold authoring, bounded Development Driver, opt-in Development Envelope (sandbox-only), OWNER-only transactional promotion with CODE versioning and capability activation | **5.2 IMPLEMENTED · 5.3 VALIDATED (G1 closed)** |

**NEXT:** no implementation NEXT is defined. Any further work requires an
explicitly written, owner-approved, evidence-backed scope. **No Phase 6 and no
L11+ roadmap exists or is planned.**

---

## Completed (Core and post-Core) — do not reopen

- **Atlas Core** — Tracks A–D, Phase 21/22, post-core F1–F8 + hardening; released
  baseline **v0.20.0** (tag `v0.20.0`, `b92c5d9`). Atlas Core is COMPLETE.
- **Phase C — evidence-driven evolution (C0 → C9)** — reached its evidence
  boundary; C8 CLOSED with no evidence-backed gap; C9 READINESS COMPLETE; **C5.2
  NOT AUTHORIZED**. No C10 exists or is planned. (Details: `docs/ATLAS_STATE.md`
  §31; evidence reports: `docs/archive/phase-c/`.)
- **Post-core guided self-improvement** — Stage A1→H thread, Persistent Learning,
  deterministic semantic recall, forgetting-policy operationalization.

---

## DEFERRED / owner-gated

- Episodic context into the `RuntimeCoordinator` pipeline (locked stage order —
  requires an explicit pipeline review).
- Conversational routing of `DEVELOPMENT_REQUEST`s through the `DevelopmentDriver`
  (current direct-evolution surfaces are the kernel API and `atlas postcore drive`).
- Startup re-discovery of previously activated capabilities; durable
  (cross-process) promotion artifacts and authorizations.
- WS3b (sandbox repository snapshot) and WS4 (deeper self-knowledge integration
  into development reasoning).
- BootActivation re-verification semantics (owner decision pending).

---

## PROPOSED — not approved (do not implement)

Historical Capability-Track directions (multi-agent collaboration, human
collaboration, self-improvement) are referenced in archived material only. **No
Track E/F/G design, module, or milestone exists.** They must not be implemented
or presented as committed direction until an approved design exists and this
document is updated.

---

## Boundaries (unchanged)

Deterministic-first operation, model independence, human (OWNER) approval,
governed execution, authorization boundaries, sandbox verification, fail-closed
behaviour, and controlled self-evolution remain in force — see
`docs/ATLAS_STATE.md` §0, §16, §26, and §32.7.

---

## Maintenance rule

On a completed milestone: (1) update `docs/ATLAS_STATE.md`; (2) update this file;
(3) update `README.md` if the public status changed. Never archive/delete without
moving to `docs/archive/`, and never treat archived material as current.
