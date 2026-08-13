# Phase 22 — Toolchain Execution & Learned-Skill Progression

**Status:** SPECIFIED — approved for validation, not yet implemented.
**Applies to:** `atlas/toolchain/` (Track B)
**Depends on:** Phase 20 (invariant) + Phase 21 (accepted, unreleased locally)

## 1. Objective and scope

Extend the existing Track B tool-chain execution and learning surfaces with
the three already-recorded NEXT roadmap items, integrated additively into the
current architecture:

1. **CONDITIONAL execution** — select later steps from prior step output.
2. **PARALLEL execution** — fan-out/fan-in of independent steps.
3. **Learned-skill authoring/promotion** — surface a deterministic
   authoring/promotion boundary over the existing `ToolLearner` output.

Scope is strictly confined to `atlas/toolchain/` + `atlas/storage/` additive
tables + `atlas/kernel/atlas.py` wiring + tests. Nothing else changes.

## 2. Batch structure (each batch lands green independently)

- **Batch 1 — CONDITIONAL execution:** implement conditional semantics.
- **Batch 2 — PARALLEL execution:** implement parallel fan-out/fan-in.
- **Batch 3 — Learned-skill authoring/promotion:** authoring + governed promotion.
- **Batch 4 — Integration and final acceptance:** wire capability handlers,
  kernel, storage, and run the full acceptance suite.

## 3. CONDITIONAL execution semantics

- **Dependency/output conditions:** conditional steps may declare dependent
  output via `ToolStep.depends_on` (existing field). A step is eligible only
  when its declared dependencies are satisfied by a prior step result; the
  condition evaluates a deterministic predicate over a prior step's `output`
  dict (no free-form expression evaluation).
- **Predicate vocabulary (OWNER DECISION 3):** no general expression language.
  Batch 1 must use a small, deterministic predicate mechanism over prior step
  output dictionaries. The exact predicate vocabulary is an implementation
  detail to be finalized when Batch 1 begins; it is NOT Phase 22 scope and
  must not be expanded now.
- **Deterministic behavior:** selection of the next step must be pure and
  reproducible for identical prior outputs. No randomness, no wall-clock
  dependence affecting selection.
- **Failure behavior:** a failed step breaks the conditional chain and fails
  the overall `ToolChainResult` with a descriptive error, matching the
  existing sequential-style fail-closed convention.
- **Step limits:** `RiskPolicy.max_steps` and `max_execution_time_ms` apply
  to conditional runs exactly as they apply to sequential runs today.
- **No hidden routing mechanism:** the executor is the only decision point;
  it decides which conditional step to run next. No planner, router,
  dispatcher, or selection engine is added. Conditional planning (emitting
  the full candidate list, as today) is unchanged.

## 4. PARALLEL execution semantics

- **Concurrency:** NO actual threads/async/subprocess. The existing promise
  "No threading. No async. No subprocess." is preserved verbatim and remains
  in force. (See §5 for the explicit resolution.)
- **Fan-out/fan-in:** an ordered tuple of step results is collected and a
  deterministic fan-in merges them into `ToolChainResult.step_results`.
- **Deterministic result ordering:** `step_results` is returned in original
  step order regardless of execution timing.
- **Partial failure behavior:** if any step fails, the overall result is
  treated as a failure with the failing step's error surfaced, consistent
  with the strong fail-closed convention.
- **Step/time limits:** `RiskPolicy.max_steps` and `max_execution_time_ms`
  apply to the fan-out batch exactly as they apply to sequential runs today.
- **Resource/concurrency limits:** a deterministic cap on the maximum number
  of steps ever executed (the existing catalog cap `MAX_PLAN_STEPS`), plus
  the existing `RiskPolicy` limits. No dynamic resource budget is introduced.

## 5. Resolution of "No threading. No async. No subprocess."

**Option A is selected.** Phase 22 preserves the deterministic sequential
fan-out/fan-in approach. The promise is not removed; it remains in force and
is documented here explicitly as an invariant of the toolchain executor.

Decision rationale (repository evidence):
- The executor's `RiskPolicy` and existing strategy dispatch are fully
  synchronous and time-boxed.
- No existing repository evidence implies a need for true concurrency; all
  tools invoked via the `ToolInvoker` protocol are synchronous calls.
- Deterministic execution preserves order stability and test reproducibility,
  which are core Phase 18/19/20/21 values.

## 6. Learned-skill authoring/promotion boundaries

- **Authoring:** a new pure `ToolSkillAuthor` produces a `Skill` with a
  `ToolChain` (sequential or conditionally composed) from planner + learner
  outputs. It must not mutate storage or call the gateway.
- **Promotion:** promotion is the *governed* act of changing skill status
  (e.g. `DRAFT → ACTIVE`). It must go through `ToolchainIngestBridge` /
  GOV-009 exactly as skill activation does today. The bridge fails closed
  without a sink.
- **Persistence (OWNER DECISION 2):** learned-skill promotion candidates stay
  IN-MEMORY for Phase 22. No migration or persistence is introduced for
  speculative future needs; the existing architecture does not strictly
  require persistence per any already-approved acceptance criterion. If a
  later batch proves persistence is strictly required by an approved
  criterion, this decision must be revisited and reported before any
  additive migration is introduced.

## 7. GOV-009 governance boundary

- **Candidate generation may occur:** an author-authored skill, a
  `ToolLearningRecommendation`, or a promotion candidate may be produced and
  held as a candidate without mutating Atlas state.
- **Activation/mutation must remain governed:** changing `SkillStatus`,
  registering a new skill with `SkillRegistry`, or persisting an activated
  skill must go through `ToolchainIngestBridge` → `GOV-009` (INFORMATION
  scope; fail-closed without a sink).
- **No fail-closed boundary may be bypassed:** without a wired sink, no skill
  activation may be silently applied. Refusals must be recorded.

## 8. Required tests and acceptance criteria per batch

Existing test conventions are reused (fake invoker/provider/registry; pure
assertions; determinism checks).

- **Batch 1 (CONDITIONAL):**
  - conditional selection depends deterministically on prior step output;
  - failed step → chain failure with descriptive error;
  - `RiskPolicy` step/time caps apply;
  - unsupported-strategy guard removed only for the implemented conditional
    path (tests prove `conditional` no longer fails closed in the supported
    surface).
- **Batch 2 (PARALLEL):**
  - fan-out executes every eligible tool exactly once;
  - `step_results` ordering is stable;
  - partial failure surfaces the failing step's error;
  - step/time caps apply;
  - no actual concurrency (no thread/async leakage);
  - `parallel` no longer fails closed in the supported surface.
- **Batch 3 (authoring/promotion):**
  - authored skill carries the correct chain/strategy;
  - promotion candidate does not mutate until governed;
  - WITHOUT a sink, promotion fails closed and records a refusal;
  - WITH a sink, activation hands a governed request through GOV-009.
- **Batch 4 (integration & acceptance):**
  - a RunCoordinator plan → `toolchain.execute_chain` → new executor path
    produces a success/failure ExecutionResult;
  - capability registry/routing/dispatch invariants hold;
  - memory/learning/reflection boundaries untouched;
  - full suite passes (except pre-existing Ollama environmental failure).

## 9. Phase 20/21 invariants that must remain untouched

- RuntimeCoordinator 15-stage order.
- REASONING candidate-only; PLANNING performs dispatch.
- Production CapabilityRegistry → CapabilityRouter → CapabilityDispatcher path.
- CognitionService public decision-payload reconciliation.
- ModelRouter behavior.
- EvolutionScheduler → Intelligence lifecycle.
- `Atlas.tick()`.
- Track D provider wiring.
- LearningMemory feedback boundary (capability-keyed StrategyPerformance).
- Governed ResearchIngestBridge fail-closed.
- Kernel-private service ownership (single coordinator; no ServiceContainer
  registrations for track-private services).
- Additive-only migrations; import boundaries.

## 10. Non-goals

- No second planner/router/dispatcher/discovery architecture.
- No RuntimeCoordinator redesign.
- No ModelRouter changes.
- No Phase 16 revival.
- No unrelated memory/context work (Track C deferred items stay out).
- No actual OS-level concurrency.

## 11. Release strategy

Phase 21 is implemented and accepted but remains unreleased locally.

**OWNER DECISION 1 (RESOLVED):** Phase 21 is treated as completed local
development and will be **bundled with the upcoming Phase 22
milestone/release** rather than released/tagged separately now. No tag is
created for Phase 21 on its own. Nothing is pushed as part of Phase 22
preparation.
