# D5 — Atlas Development Independence

Authoritative description of the D5 development-independence coordinator. It
describes what D5 implements; Atlas is **not** fully autonomous after D5 —
D5 means Atlas can coordinate an authorized governed development workflow
itself, using its own existing infrastructure.

## 1. Architecture

`atlas/orchestration/development_orchestrator.py` (`DevelopmentOrchestrator`,
`DevelopmentRun`, `DevelopmentState`), exposed via `Atlas.development_orchestrator`
/ `Atlas.run_development_objective(...)`.

D5 sits **under** D4: D4 remains the outer objective/work coordinator; D5
provides the development-specific governed lifecycle and delegates every
authority-bearing action to the component that owns it, injected by the kernel:

| Stage | Authoritative owner (reused, injected callable) |
|---|---|
| investigation / gap + proposal | existing `Atlas.run_development_driver` |
| approval state | existing persisted proposal status (`EvolutionMemory` / `ApprovalManager`) |
| sandbox implementation | existing `Atlas.run_development_execution` (OWNER-gated, sandboxed) |
| verification | existing `DevelopmentVerification` (via the run result) |
| promotion review | existing `Atlas.submit_development_for_promotion_review` |
| promotion | existing `Atlas.promote_validated_change` (OWNER-only gate + executor) |
| self-knowledge | existing `Atlas.capability_model` |

No second approval system, sandbox, verification engine, promotion logic, or
knowledge store is introduced. D5 is deterministic and model-independent (no
`atlas.ai` import, no network).

## 2. Lifecycle states

`RECEIVED → INVESTIGATING → PROPOSAL_CREATED → [AWAITING_OWNER] → IMPLEMENTING →
VERIFYING → PROMOTING → COMPLETED`, with bounded failure terminals `FAILED`,
`VERIFICATION_FAILED`, `PROMOTION_FAILED`. Each run records a deterministic
`transitions` trace.

## 3. Governance boundaries

- **Approval boundary:** the orchestrator NEVER approves. It *reads* the
  existing approval state; without approval it stops at `AWAITING_OWNER` and
  performs no implementation, no sandbox run, no verification, and no promotion.
- **Sandbox boundary:** implementation runs only through the existing
  OWNER-gated, sandboxed execution runner; D5 does not touch the live repository.
- **Verification boundary:** promotion requires a `SUCCESS` execution **and**
  `verified` status; otherwise `VERIFICATION_FAILED` and no promotion.
- **Promotion boundary:** D5 delegates to the existing promotion review +
  owner-only promotion executor; it cannot promote itself, and a failure yields
  `PROMOTION_FAILED` with no acceptance.
- **Self-authorization:** the orchestrator exposes no `approve`/`authorize`/
  `promote` method; language, external content, or self-knowledge cannot create
  approval.

## 4. Self-knowledge integration

Self-knowledge is refreshed **only after successful promotion**, using the
existing capability model (read-only counts). On verification or promotion
failure the snapshot is not produced, so self-knowledge never falsely reports a
capability as promoted. Self-knowledge is descriptive, never authority.

## 5. Model independence / security

No external model, no network, no dependency changes. External content and
natural language never grant development authority; existing OWNER identity and
approval identity remain authoritative across the lifecycle.

## 6. Explicit limitations

D5 coordinates the existing governed development lifecycle; it does not design
capabilities, generate arbitrary code, extend the sandbox, or add autonomy
levels. Promotion writes the live repository and therefore remains an explicit
OWNER action performed by the existing executor (tests inject a fake at that
existing boundary). There is no D6 and no speculative post-D5 roadmap: the
post-D5 direction is evidence-driven refinement and validation.
