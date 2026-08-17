# Atlas Changelog

All notable changes to Project Atlas are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to a milestone- and track-based release model
(Phase/track releases, not strict daily semantic releases).

---

## [v0.20.0] — Atlas Core Release — 2026-08-16

### Atlas Core is COMPLETE at Phase 22

Phase 22 (Toolchain Execution & Learned-Skill Progression) is the **FINAL
numbered implementation phase for Atlas Core**. There is **NO Phase 23**.
Development has transitioned to **post-core guided self-improvement**: Atlas
improves itself through the existing governed mechanisms
(`Observe/record → analyze/plan → propose → approve → execute governed changes
→ verify → repeat`) with `SELF_CONFIG`/`INFORMATION` as the enabled governed
scopes and `CODE_ARTIFACT`/`SANDBOXED`/`AUTONOMOUS` remaining locked in
accordance with the constitution.

### Post-Core Improvements (F1–F8)

- **F1 — Runtime observation coverage**: five observation categories per
  runtime cycle (`atlas/evolution/runtime_observations.py`).
- **F2 — Planner observation aggregation**: weakness detectors average the
  relevant metric over the bounded per-category observation window instead of
  only the newest observation (`ImprovementPlanner._mean_value`).
- **F3 — Subsumed by F8**: proposal list/show/audit visibility supersedes the
  separate audit item.
- **F4 — Deferred/monitored**: `EvolutionScheduler.tick()` has a shared tick
  counter, a new-observations gate, and a reentrancy guard; duplicate-analysis
  risk is monitored, no change was made.
- **F5 — Scheduler fail-soft diagnostics**: `EvolutionSchedulerResult.last_error`
  exposes the most recent integration error while fail-soft semantics remain
  byte-identical.
- **F6 — Expected behavior**: SQLite evolution storage's memory-only fallback
  is the documented degraded mode; `evolution.storage.unavailable` is emitted.
- **F7 — Closed learning feedback loop**: deterministic failure
  `EvolutionRecord`s → insight → planner feedback.
- **F8 — Evolution audit/proposal visibility**: `get_proposal_audit()` plus a
  read-only `atlas proposals list|show|audit` CLI, exposing approval decisions,
  execution outcomes, and failure error/status.

### Hardening

- **Cognition Mock Provider routing**: the cognition runtime test now routes
  via Mock Provider (the `ModelRouter.route → None` patch is scoped to the
  `send()` call), eliminating the previously pre-existing Ollama 404.
- **SQLite INTEGER overflow clamp**: understanding `frequency` /
  `observed_count` binds are saturated deterministically at `2**63 - 1`,
  eliminating the `OverflowError` caused by unbounded counter accumulation
  across restore/merge cycles.

### Test Status

- **3260 passed, 0 failed, 57 subtests, 2 warnings** at HEAD `b2b4674`.
- The 2 warnings are **non-blocking** `asyncio.iscoroutinefunction`
  deprecation warnings in `test_phase21_research_coordinator.py` (they become
  errors only on Python ≥ 3.16).

### Governance

- **Autonomous code mutation remains disabled.** `CODE_ARTIFACT` (3),
  `SANDBOXED` (4), and `AUTONOMOUS` (5) execution levels remain locked and
  unreachable; `SELF_CONFIG` (1) and `INFORMATION` (2) remain the enabled
  governed scopes.
- All state mutation continues to flow through the Evolution Framework; the
  `EvolutionExecutionGateway` remains the single execution choke point and the
  `EvolutionAutonomyDispatcher` its sole caller.
- Capability dispatch remains exclusively
  `CapabilityRegistry → CapabilityRouter → CapabilityDispatcher`; REASONING
  remains candidate-only; the RuntimeCoordinator retains exactly 15 stages.

### Components Changed Since v0.20 (post-core)

- `atlas/evolution/scheduler.py` — fail-soft error diagnostics (`last_error`).
- `atlas/evolution/improvement_planner.py` — window mean aggregation.
- `atlas/cli/evolution_commands.py`, `atlas/cli/main.py` — `proposals` CLI.
- `atlas/storage/understanding_storage.py` — INTEGER saturation clamp.
- Related post-core test suites: F1, F2, F5, F7, F8, hardening clamp, and the
  cognition runtime routing correction.
