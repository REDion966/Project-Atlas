# Atlas Continuous Evolution (Phase 13)

How Atlas continues improving over time through **explicitly invoked, bounded,
governed evolution cycles** — without a daemon, scheduler, or autonomous loop.

## 1. What "continuous evolution" means here

Continuous evolution = *continued evolution over durable evidence*. A cycle runs
once, terminates, and persists what happened. A later — separate — invocation
loads that evidence and decides what (if anything) to attempt next.

It does **not** mean: infinite loops, daemons, background execution, cron,
timers, self-scheduling, or unrestricted self-modification. Those are
deliberately absent (see §6).

## 2. What already existed (reused, not rebuilt)

| need | existing mechanism |
| --- | --- |
| durable evolution state | `EvolutionMemory` + `SQLiteEvolutionStorage` (`store_*` / `load_*`, `restore()`) |
| bounded cycle with cooldown/budget/failure policy | `OperationController` + `OperationPolicy` (`ok`/`partial`/`failed`/`cooldown`/`no_work`) |
| bounded, rate-limited analysis tick | `EvolutionScheduler` (threshold-gated, single-threaded, no execution) |
| opportunity lifecycle vocabulary | `ImprovementStatus` (`IDENTIFIED`…`COMPLETED`/`REJECTED`/`DEFERRED`) |
| historical aggregation of durable evidence | `SelfManagementReview` (inert `MaintenanceNeed`s) |
| capability-gap discovery | Phase 10 `capability_discovery` |
| the governed lifecycle | Phase 11 `SelfEvolutionLoop` (discovery → … → activation → outcome learning) |
| runtime independence | Phase 12 (`docs/INDEPENDENCE.md`) |

## 3. The genuine gap (and the smallest fix)

Phase 11 records each cycle's outcome (`evolution_outcome`) durably, but **nothing
read those outcomes**, so a later invocation could blindly re-attempt a subject
that had already been completed, rejected, blocked, or failed non-retryably.

Two changes were required:

1. **Durable identity fix (Phase 11, `self_evolution.py`)** — the outcome record
   id was seeded on the per-instance cycle counter alone, so two distinct cycles
   could collide on one record id and become indistinguishable in durable
   history. Evidence: a probe running three cycles produced `SEV-000001` three
   times and one collapsed record. The id is now seeded on
   `cycle_id : subject : proposal_id : outcome_kind`.
2. **Continuity projection (new, read-only)** —
   `atlas/evolution/evolution_continuity.py` derives per-subject opportunity
   state from the persisted outcomes and gates new candidates against it.

No new store, scheduler, daemon, memory system, planner, or score was added.

## 4. Continuity states

| state | meaning | attemptable |
| --- | --- | --- |
| `COMPLETED` | capability already activated — do not repeat | no |
| `REJECTED` | deterministic rejection — a different subject/evidence is required | no |
| `BLOCKED` | blocked by an external condition (authority, dependency, inconsistent state) | no |
| `DEFERRED` | awaits an explicit human governance decision | no |
| `EVIDENCE_REQUIRED` | retryable, **but only with new or corrected evidence** | no |
| `READY` | no blocking history — may be attempted | yes |
| `IN_PROGRESS` | reserved for an active invocation; never derived from history | no |

Mapping: `activated → COMPLETED`; `stopped_at_approval`/`pending_promotion_review`/
`promotion_not_ready → DEFERRED`; `promotion_not_authorized`/`invalid_lifecycle_state`/
`self_model_inconsistent`/`ineligible → BLOCKED`; `rejected_candidate`/`promotion_failed
→ REJECTED`; `sandbox_failed`/`verification_failed`/`preparation_failed`/
`invalid_objective`/`research_required → EVIDENCE_REQUIRED`. An unrecognised or
missing terminal is `DEFERRED` — fail closed, never `READY`.

Each state also maps onto the existing `ImprovementStatus` vocabulary
(`READY → IDENTIFIED`, `EVIDENCE_REQUIRED → PLANNED`, `DEFERRED`/`BLOCKED →
DEFERRED`, `REJECTED → REJECTED`, `COMPLETED → COMPLETED`), so the continuity view
feeds the existing lifecycle model rather than replacing it.

## 5. The final architecture

### A single bounded cycle (unchanged from Phase 11)

```
Discovery → Eligibility → Objective → Evidence → Plan
  → HUMAN APPROVAL → Sandbox → Verification → Promotion Review
  → HUMAN PROMOTION AUTHORIZATION → Activation → Self-Model Validation
  → Outcome Learning → TERMINATE (next_cycle_allowed = False)
```

### A future cycle (new: the continuity bridge)

```
process ends / returns to caller
  → later explicit invocation
  → load durable history (EvolutionMemory.restore)
  → continuation_view(memory)        # per-subject states + reasons
  → gate_candidates(discovery_candidates, view)   # refusals explained
  → run the SAME bounded governed cycle for an admitted subject
  → TERMINATE again
```

There is no implicit recursive continuation: the bridge produces states, reasons
and an advisory gate — it never starts a cycle, approves anything, or schedules
itself.

## 6. Boundedness invariants

* `SelfEvolutionCycleResult.next_cycle_allowed` is always `False`.
* `SelfEvolutionPolicy.max_development_iterations` is capped at 3.
* `bounded_multi_cycle_plan` describes a finite sequence (hard cap
  `MAX_EXPLICIT_CYCLES`, further capped by an injected `OperationPolicy`).
* The continuity module contains no `while`, `threading`, `asyncio`, `time`,
  `subprocess`, or `socket` usage.
* No new scheduler/daemon/`run_forever` surface exists in Atlas.

## 7. Governance invariants (unchanged)

Each cycle requires its **own** explicit human approval and its **own** promotion
authorization (`owner_approved` and `promotion_authorized` default to `False`).
A previous approval does not authorize a later cycle; a previous promotion
authorization is not permanent; a successful cycle grants no new authority.
`ApprovalManager`, `PromotionGate`, `PromotionExecutor` and `CapabilityActivator`
remain the only path to production change, and production is still mutated only
inside governed promotion.

## 8. Known limitations

* `READY` is derived only for subjects with **no** blocking history; new work
  still comes from Phase-10 discovery evidence (history alone never invents a
  candidate).
* Retry eligibility is a *classification*, not a retry policy: no counters,
  backoff, or automatic re-attempt exist by design.
* The continuity projection is bounded by `max_records`; older records beyond the
  window are not consulted (and are never fabricated).
