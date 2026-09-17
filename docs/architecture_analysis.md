# M6.1 — Canonical Execution Architecture Investigation

**Date:** 2026-09-05
**Branch:** phase5-memory-evolution
**HEAD:** 554cadc
**Investigation Type:** READ-ONLY architecture analysis

---

## 1. Baseline Verification

| Check | Expected | Actual | Status |
|-------|----------|--------|--------|
| Branch | phase5-memory-evolution | phase5-memory-evolution | PASS |
| HEAD | 554cadc | 554cadc | PASS |
| origin/phase5-memory-evolution | 554cadc | 554cadc | PASS |
| HEAD...origin sync | 0 / 0 | 0 / 0 | PASS |
| Working tree | clean | clean (2 untracked) | PASS |
| Pre-existing untracked | architecture_analysis.md | present | PASS |

**Commands executed:**
- `git status --short` → `?? _run_m55.py`, `?? architecture_analysis.md`
- `git branch --show-current` → `phase5-memory-evolution`
- `git rev-parse HEAD` → `554cadceb00ccddcb32665d464c1c9fe1c978a4f`
- `git rev-parse origin/phase5-memory-evolution` → `554cadceb00ccddcb32665d464c1c9fe1c978a4f`
- `git rev-list --left-right --count HEAD...origin/phase5-memory-evolution` → `0	0`

**Baseline verdict:** M6.1 investigation may proceed.

---

## 2. M6/F3 Objective

**M6 Goal:** Document and enforce the final execution architecture before major capability expansion.

**F3 Definition:** Canonical execution ownership must be clarified and enforced.

**M5 closure state:** M5 confirmed caller-owned governance. ToolExecutor/ToolEngine remain low-level primitives. GoalExecutionEngine authorization unification deferred to M6/F3.

**M0–M5 status:** All COMPLETE. M6 is LOCKED (current investigation). M7 is LOCKED.

---

## 3. Execution System Inventory

### 3.1 Primary Execution Systems

| System | File | Class:Line | Production Status |
|--------|------|------------|-------------------|
| OrchestrationExecutor | atlas/orchestration/executor.py | 72 | PRODUCTION |
| GoalExecutionEngine | atlas/goals/goal_execution_engine.py | 104 | PRODUCTION |
| SelfDevelopmentLoop | atlas/evolution/self_development_loop.py | 307 | PRODUCTION |
| EvolutionScheduler | atlas/evolution/scheduler.py | 66 | PRODUCTION |
| ToolExecutor | atlas/tools/executor.py | 18 | PRODUCTION |
| ToolEngine | atlas/tools/engine.py | 16 | PRODUCTION |
| TaskManager | atlas/task/task_manager.py | 16 | PRODUCTION |
| Scheduler | atlas/scheduler/scheduler.py | 17 | PRODUCTION |
| Worker | atlas/scheduler/worker.py | 10 | PRODUCTION |
| RuntimeCoordinator | atlas/runtime/runtime_coordinator.py | 46 | PRODUCTION |
| CapabilityDispatcher | atlas/reasoning/execution/dispatcher.py | 14 | PRODUCTION |
| ToolChainExecutor | atlas/toolchain/executor.py | 146 | PRODUCTION |
| EvolutionAutonomyDispatcher | atlas/evolution/autonomy/dispatcher.py | 50 | PRODUCTION |
| DevelopmentCycleController | atlas/evolution/development_cycle.py | 306 | PRODUCTION |
| EvolutionExecutionGateway | atlas/evolution/execution_gateway.py | 71 | PRODUCTION |
| EvolutionExecutionEngine | atlas/evolution/execution_engine.py | 69 | PRODUCTION |

### 3.2 Supporting Systems

| System | File | Role |
|--------|------|------|
| DevelopmentPlanner | atlas/evolution/development_planner.py:42 | Planning only, no execution |
| CodeSandbox | atlas/evolution/autonomy/code_sandbox.py:189 | Sandbox environment |
| CodeApplier | atlas/evolution/autonomy/code_execution.py:56 | Code application in sandbox |
| CapabilityRegistry | atlas/reasoning/execution/registry.py:12 | Handler lookup |
| ToolRegistry | atlas/tools/registry.py | Tool lookup |
| ToolSelector | atlas/tools/selector.py | Tool selection |
| ExecutionRequestAdapter | atlas/goals/execution_request_adapter.py | Request translation |
| ToolExecutionActionBinder | atlas/tools/execution_action_binder.py:22 | Action-to-request binding |

---

## 4. Production Call Chains

### 4.1 Conversational/Tool Execution Path

```
ENTRY: Atlas.chat(text)
  → ConversationService.send(text)
    → TaskIntake.parse(text) → TaskSpec
    → _maybe_handle_orchestration_request(spec, session)
      → OrchestrationExecutor.execute(ExecutionRequest)
        → _authorize(step, request) [AuthorityService.check]
        → _execute_step(step, request)
          → _dispatch_tool() → ToolExecutor.execute_by_name()
          → _dispatch_capability() → CapabilityDispatcher.dispatch()
          → _dispatch_workspace() → WorkspaceService
          → _dispatch_research() → InformationAcquisitionService
    → CognitionAPI.process(user_input)
      → CognitionService.process(user_input)
        → RuntimeCoordinator.process(user_input)
          → Stage 7 (PLANNING): CapabilityDispatcher.dispatch()
          → Stage 9 (TOOL_EXECUTION): ToolEngine.fulfill(request)
            → ToolExecutor.execute(tool, params)
```

**Evidence:**
- `atlas/kernel/atlas.py:3207` — `chat()` delegates to `ConversationService.send()`
- `atlas/conversation/conversation_service.py:201` — orchestration bridge invoked
- `atlas/conversation/conversation_service.py:227` — cognition_api.process() invoked
- `atlas/services/cognition_service.py:137` — runtime_coordinator.process() invoked
- `atlas/runtime/runtime_coordinator.py:730` — tool_engine.fulfill() invoked

### 4.2 Orchestration Execution Path

```
ENTRY: ConversationService._orchestration_bridge(spec, session)
  → OrchestrationExecutor.execute(ExecutionRequest)
    → _resolve_steps(request)
    → _validate_step(step) [per-step validation]
    → _run(validated, deps_map, request, started)
      → _authorize(step, request) [per-step authority check]
      → _execute_step(step, request)
        → _dispatch_capability() → CapabilityDispatcher.dispatch()
        → _dispatch_tool() → ToolExecutor.execute_by_name()
        → _dispatch_workspace() → WorkspaceService
        → _dispatch_research() → InformationAcquisitionService
    → _assemble(status, request, results) → OrchestrationResult
```

**Evidence:**
- `atlas/kernel/atlas.py:1049` — orchestration_executor.execute() called
- `atlas/orchestration/executor.py:99` — execute() entry point
- `atlas/orchestration/executor.py:364` — _authorize() per-step authority
- `atlas/orchestration/executor.py:387` — _execute_step() dispatch

### 4.3 Goal Execution Path

```
ENTRY: Atlas.tick()
  → GoalExecutionEngine.settle()
    → _repository.get_goals_by_status(APPROVED)
    → _execute(goal)
      → ActionFactory.build(goal, auth) → ExecutionAction
      → ExecutionRequestAdapter.to_gateway_request(action, auth)
      → EvolutionExecutionGateway.execute(gateway_request)
        → RuleEngine.evaluate()
        → [if approved] EvolutionExecutionEngine.execute()
      → binder_registry.resolve(action_type) → ToolExecutionActionBinder
      → ToolExecutionActionBinder.bind(action)
        → ToolEngine.fulfill(request)
          → ToolExecutor.execute(tool, params)
```

**Evidence:**
- `atlas/kernel/atlas.py:3119` — goal_executor.settle() in tick()
- `atlas/goals/goal_execution_engine.py:319` — settle() entry
- `atlas/goals/goal_execution_engine.py:394` — gateway.execute() called
- `atlas/tools/execution_action_binder.py:84` — tool_engine.fulfill() called

### 4.4 Self-Development Execution Path

```
ENTRY: Atlas.run_self_development(proposal)
  → SelfDevelopmentLoop.run(proposal, max_iterations)
    → [pre-flight] proposal.status == APPROVED
    → DevelopmentPlanner.plan(proposal) → DevelopmentPlan
    → _run_iteration(proposal, plan, workload, iteration)
      → SandboxImplementer.apply() → CodeApplier.apply()
      → SandboxVerifier.run() → pytest_tool().handler()
    → DevelopmentOutcome recorded
    → LearningInsight stored
```

**Evidence:**
- `atlas/kernel/atlas.py:1763` — self_development_loop.run() called
- `atlas/evolution/self_development_loop.py:349` — run() entry
- `atlas/evolution/self_development_loop.py:445` — _run_iteration()
- `atlas/evolution/self_development_loop.py:479` — implementer (CodeApplier)
- `atlas/evolution/self_development_loop.py:488` — verifier (pytest)

### 4.5 Scheduled/Task Execution Path

```
ENTRY: Atlas.tick()
  → TaskManager.tick()
    → Scheduler.tick()
      → Worker.execute(scheduled_task)
        → Task.run() → [no-op/failure per M2 contract]
  → EvolutionScheduler.tick()
    → _run_analysis() [threshold-gated]
      → SelfObservationEngine.recent_observations()
      → ImprovementPlanner.detect_weaknesses()
      → ProposalGenerator.generate_proposal()
      → ApprovalManager.create_approval_request()
  → GoalExecutionEngine.settle()
  → EvolutionAutonomyDispatcher.settle()
```

**Evidence:**
- `atlas/kernel/atlas.py:3114-3122` — tick() sequence
- `atlas/task/task_manager.py:72` — tick() delegates to scheduler
- `atlas/scheduler/scheduler.py:54` — tick() executes due tasks
- `atlas/scheduler/worker.py:29` — task.run() invoked
- `atlas/task/task.py:100-119` — Task.run() is no-op/failure contract

### 4.6 Evolution/Adaptation Path

```
ENTRY: Atlas.tick()
  → EvolutionScheduler.tick()
    → _run_analysis()
      → [does NOT execute proposals]
      → generates proposals + approval requests
  → EvolutionAutonomyDispatcher.settle()
    → claim_scheduled(request)
    → EvolutionExecutionGateway.execute_request()
      → RuleEngine.evaluate()
      → [if authorized] ApplicationEngine.apply()
```

**Evidence:**
- `atlas/evolution/scheduler.py:185` — tick() entry
- `atlas/evolution/scheduler.py:228` — _run_analysis() generates only
- `atlas/evolution/autonomy/dispatcher.py:137` — settle() advances requests

---

## 5. Ownership Analysis

### 5.1 Execution Owner Criteria

An execution owner must:
1. Receive an executable work contract
2. Own execution lifecycle
3. Determine whether execution occurs
4. Invoke the actual side-effecting operation
5. Produce an execution outcome
6. Own execution failure semantics
7. Enforce or receive governance boundary

### 5.2 Classification

| System | Classification | Evidence |
|--------|---------------|----------|
| OrchestrationExecutor | SPECIALIZED EXECUTION OWNER | Owns multi-step orchestration lifecycle, per-step authority, produces OrchestrationResult |
| GoalExecutionEngine | SPECIALIZED EXECUTION OWNER | Owns goal execution lifecycle, authorization guard, produces GoalExecutorResult |
| SelfDevelopmentLoop | SPECIALIZED EXECUTION OWNER | Owns sandbox development lifecycle, bounded iterations, produces DevelopmentRunResult |
| EvolutionScheduler | COORDINATOR | Generates proposals only, does NOT execute |
| ToolExecutor | LOW-LEVEL PRIMITIVE | Invokes tool handlers, no lifecycle ownership, caller-trusting |
| ToolEngine | LOW-LEVEL PRIMITIVE | Selection + execution coordination, no governance |
| TaskManager | COORDINATOR | Coordinates task scheduling, no execution logic |
| Scheduler | COORDINATOR | Manages task queue, delegates to Worker |
| Worker | LOW-LEVEL PRIMITIVE | Invokes Task.run(), no lifecycle ownership |
| RuntimeCoordinator | COORDINATOR | Orchestrates cognitive pipeline, delegates execution to ToolEngine/CapabilityDispatcher |
| CapabilityDispatcher | DISPATCHER | Dispatches to handlers, no lifecycle ownership |
| ToolChainExecutor | SPECIALIZED EXECUTION OWNER | Owns tool chain execution lifecycle, produces ToolChainResult |
| EvolutionAutonomyDispatcher | COORDINATOR | Orchestrates request lifecycle, delegates to gateway |
| DevelopmentCycleController | COORDINATOR | Preparation only, stops at approval boundary |
| EvolutionExecutionGateway | GOVERNANCE GATE | Authorization checkpoint, delegates to engine |
| EvolutionExecutionEngine | LOW-LEVEL PRIMITIVE | Administrative record-keeping only (Level 0) |

---

## 6. Overlap/Duplication Findings

### 6.1 OrchestrationExecutor vs GoalExecutionEngine

**CLAIM:** These systems have overlapping execution responsibility.

**EVIDENCE:**
- OrchestrationExecutor: `atlas/orchestration/executor.py:99` — executes steps via ToolExecutor/CapabilityDispatcher
- GoalExecutionEngine: `atlas/goals/goal_execution_engine.py:394` — executes via gateway → binder → ToolEngine

**CONCLUSION:** Both can invoke ToolExecutor/ToolEngine. OrchestrationExecutor is governed per-step; GoalExecutionEngine is governed via gateway authorization. Intentional specialization: OrchestrationExecutor handles multi-step plans, GoalExecutionEngine handles single goals with authorization records.

### 6.2 SelfDevelopmentLoop vs OrchestrationExecutor

**CLAIM:** These systems have overlapping execution responsibility.

**EVIDENCE:**
- SelfDevelopmentLoop: `atlas/evolution/self_development_loop.py:349` — sandbox development
- OrchestrationExecutor: `atlas/orchestration/executor.py:99` — general orchestration

**CONCLUSION:** No overlap. SelfDevelopmentLoop is specialized for sandboxed code development with CodeSandbox/pytest. OrchestrationExecutor explicitly denies evolution/governance targets (`_DENIED_PREFIXES`).

### 6.3 ToolExecutor vs ToolEngine

**CLAIM:** These systems have overlapping execution responsibility.

**EVIDENCE:**
- ToolExecutor: `atlas/tools/executor.py:39` — direct tool invocation
- ToolEngine: `atlas/tools/engine.py:46` — selection + execution

**CONCLUSION:** Intentional layering. ToolEngine delegates to ToolExecutor. ToolExecutor is the primitive; ToolEngine adds selection.

### 6.4 RuntimeCoordinator vs Execution Owners

**CLAIM:** RuntimeCoordinator may duplicate execution ownership.

**EVIDENCE:**
- RuntimeCoordinator: `atlas/runtime/runtime_coordinator.py:730` — invokes ToolEngine.fulfill()

**CONCLUSION:** RuntimeCoordinator is a COORDINATOR, not an execution owner. It orchestrates cognitive stages but delegates actual execution to ToolEngine/CapabilityDispatcher.

---

## 7. Execution Kind Taxonomy

| Execution Kind | Current Owner | Actual Side Effect | Governance | Outcome Model | Status | M6 Recommendation |
|---------------|---------------|-------------------|------------|---------------|--------|-------------------|
| Tool Execution | ToolExecutor | Tool handler invocation | Caller-owned (M3) | ToolResult | PRODUCTION | KEEP AS PRIMITIVE |
| Orchestration | OrchestrationExecutor | Multi-step plan execution | Per-step AuthorityService | OrchestrationResult | PRODUCTION | KEEP AS SPECIALIZED OWNER |
| Goal Execution | GoalExecutionEngine | Tool invocation via gateway | Gateway + authorization | GoalExecutorResult | PRODUCTION | KEEP AS SPECIALIZED OWNER |
| Self-Development | SelfDevelopmentLoop | Sandbox code + pytest | Pre-approved proposal | DevelopmentRunResult | PRODUCTION | KEEP AS SPECIALIZED OWNER |
| Capability Execution | CapabilityDispatcher | Handler invocation | Caller-owned | ExecutionResult | PRODUCTION | KEEP AS DISPATCHER |
| Tool Chain Execution | ToolChainExecutor | Sequential/parallel tools | Risk policy | ToolChainResult | PRODUCTION | KEEP AS SPECIALIZED OWNER |
| Scheduled Task | Scheduler/Worker | Task.run() [no-op] | None | TaskStatus | PRODUCTION (M2 no-op) | RETAIN AS LEGACY |
| Evolution Analysis | EvolutionScheduler | Proposal generation | Threshold-gated | EvolutionSchedulerResult | PRODUCTION | KEEP AS COORDINATOR |
| Cognitive Processing | RuntimeCoordinator | Pipeline stages | Caller-owned | PipelineResult | PRODUCTION | KEEP AS COORDINATOR |

---

## 8. Tool/Capability Boundary

### 8.1 ToolExecutor Status

**CLAIM:** ToolExecutor is a low-level primitive, not an execution owner.

**EVIDENCE:**
- `atlas/tools/executor.py:18-139` — No lifecycle, no governance, no state ownership
- M3 decision: ToolExecutor remains caller-trusting
- Called by: OrchestrationExecutor, ToolEngine, tests

**CONCLUSION:** KEEP AS PRIMITIVE. Do NOT add authorization.

### 8.2 ToolEngine Status

**CLAIM:** ToolEngine is a low-level/advisory primitive.

**EVIDENCE:**
- `atlas/tools/engine.py:16-155` — Selection + execution coordination
- M5 confirmation: ToolEngine remains governance-free
- Called by: RuntimeCoordinator, GoalExecutionEngine (via binder), CognitionService

**CONCLUSION:** KEEP AS PRIMITIVE. Governance is caller-owned.

### 8.3 CapabilityDispatcher Status

**CLAIM:** CapabilityDispatcher is a dispatcher, not an execution owner.

**EVIDENCE:**
- `atlas/reasoning/execution/dispatcher.py:14-109` — Handler lookup + invocation
- No lifecycle ownership, no governance
- Called by: OrchestrationExecutor, RuntimeCoordinator

**CONCLUSION:** KEEP AS DISPATCHER.

---

## 9. Task/Scheduler/Worker Assessment

### 9.1 Production Status

| Component | Production Caller | Actual Execution |
|-----------|-------------------|------------------|
| TaskManager | `atlas/kernel/atlas.py:3115` | tick() → scheduler |
| Scheduler | `atlas/task/task_manager.py:77` | tick() → worker |
| Worker | `atlas/scheduler/scheduler.py:78` | task.run() |
| Task.run() | `atlas/scheduler/worker.py:29` | NO-OP/FAILURE |

### 9.2 M2 Contract Preservation

**CLAIM:** Task.run() remains the M2 safe no-op/failure contract.

**EVIDENCE:**
- `atlas/task/task.py:100-119` — Terminal tasks untouched; non-terminal → RUNNING → FAILED with "Task has no executable payload"

**CONCLUSION:** CONFIRMED. Task subsystem is production-reachable but performs no external work.

### 9.3 Production Submission

**CLAIM:** No production code submits tasks via TaskManager.submit().

**EVIDENCE:**
- grep `task_manager\.submit\(` → No matches in production code
- grep `task_manager\.schedule\(` → No matches in production code

**CONCLUSION:** Task subsystem is tick-driven only. No external task submission.

### 9.4 M6 Recommendation

**KEEP AS LEGACY.** Task/Scheduler/Worker is a production-reachable but execution-free subsystem. Do NOT turn Task into an execution architecture. Defer to Future Queue if enhancement needed.

---

## 10. Goal Execution Assessment

### 10.1 Why GoalExecutionEngine Exists Separately

**EVIDENCE:**
- `atlas/goals/goal_execution_engine.py:104-119` — Dedicated goal lifecycle: authorize → activate → execute → record
- Authorization model: `authorized_by == "user:cli"` required
- Uses EvolutionExecutionGateway for governance

**CONCLUSION:** Distinct execution kind: user-authorized goal execution with audit trail.

### 10.2 Relationship to OrchestrationExecutor

**CLAIM:** GoalExecutionEngine does NOT duplicate OrchestrationExecutor.

**EVIDENCE:**
- GoalExecutionEngine: Single goal, authorization record, gateway governance
- OrchestrationExecutor: Multi-step plan, per-step authority, no authorization records

**CONCLUSION:** Intentional specialization. Different governance models and outcome semantics.

### 10.3 M6 Recommendation

**KEEP AS SPECIALIZED OWNER.** GoalExecutionEngine serves a distinct execution kind (user-authorized goals). Authorization unification deferred per M5.

---

## 11. Self-Development Assessment

### 11.1 Execution Owner Identification

**CLAIM:** SelfDevelopmentLoop is the execution owner for self-development.

**EVIDENCE:**
- `atlas/evolution/self_development_loop.py:307-328` — Owns bounded iteration loop
- Delegates planning to DevelopmentPlanner
- Delegates implementation to SandboxImplementer (CodeApplier)
- Delegates verification to SandboxVerifier (pytest)

### 11.2 Layer Responsibilities

| Layer | Responsibility | Execution? |
|-------|---------------|------------|
| DevelopmentPlanner | Plan formulation | No |
| SelfDevelopmentLoop | Iteration lifecycle | Yes (coordinates) |
| SandboxImplementer | Code application | Yes (CodeApplier) |
| SandboxVerifier | Test verification | Yes (pytest) |
| CodeSandbox | Environment | No (container) |
| PromotionGate | Risk assessment | No |

### 11.3 P7 Safety Preservation

**EVIDENCE:**
- `atlas/evolution/self_development_loop.py:355` — Pre-flight: proposal.status == APPROVED
- `atlas/evolution/self_development_loop.py:414` — Promotion gate consultation
- Sandbox isolation: CodeSandbox with disposable root

**CONCLUSION:** P7 safety boundaries preserved. M6 must not weaken these.

### 11.4 M6 Recommendation

**KEEP AS SPECIALIZED OWNER.** SelfDevelopmentLoop serves a distinct execution kind (sandboxed code development). Do NOT collapse into generic executor.

---

## 12. Outcome/Lifecycle Comparison

### 12.1 Outcome Models

| System | Outcome Type | Status Values |
|--------|-------------|---------------|
| OrchestrationExecutor | OrchestrationResult | COMPLETED, PARTIAL, FAILED, REJECTED, EMPTY |
| GoalExecutionEngine | GoalExecutorResult | success bool, outcome enum |
| SelfDevelopmentLoop | DevelopmentRunResult | SUCCESS, FAILED, GOVERNANCE_DENIED, INVALID_OBJECTIVE, ITERATIONS_EXHAUSTED |
| ToolExecutor | ToolResult | success bool, output, error |
| CapabilityDispatcher | ExecutionResult | success bool, output, error |
| RuntimeCoordinator | PipelineResult | success bool, stages |
| EvolutionScheduler | EvolutionSchedulerResult | ran_analysis bool, counts |
| Task | TaskStatus | PENDING, RUNNING, COMPLETED, FAILED, CANCELLED, PAUSED |

### 12.2 Inconsistency Analysis

**CLAIM:** Outcome models are incompatible across systems.

**EVIDENCE:**
- OrchestrationExecutor: 5-state enum
- GoalExecutionEngine: bool + enum
- SelfDevelopmentLoop: 6-state enum
- ToolExecutor: bool + error string

**CONCLUSION:** ACCIDENTAL DUPLICATION. Each system has its own outcome model. No unified outcome contract exists.

### 12.3 M6 Recommendation

**DEFER.** Outcome model unification is not required for F3. Document the inconsistency for Future Queue.

---

## 13. Architecture Options

### 13.1 Option A: OrchestrationExecutor as General Canonical Boundary

**Benefits:**
- Existing governed executor with per-step authority
- Already production-proven
- Composes existing seams

**Risks:**
- Not designed for goal authorization model
- Not designed for sandbox development
- Would require significant expansion

**Migration Complexity:** HIGH
**Governance Impact:** Would need to absorb gateway/authorization patterns
**M3/M5 Impact:** Risk of weakening caller-owned governance
**P7 Impact:** Risk to sandbox safety boundaries

### 13.2 Option B: New Canonical Execution Abstraction

**Benefits:**
- Clean-slate design
- Can unify outcome models

**Risks:**
- Introduces competing execution layer
- High migration cost
- Risk of duplicating existing systems

**Migration Complexity:** VERY HIGH
**Governance Impact:** New governance surface to secure
**M3/M5 Impact:** Risk of reopening settled decisions
**P7 Impact:** New attack surface

### 13.3 Option C: Distributed Ownership with Explicit Contracts

**Benefits:**
- Preserves existing governance boundaries
- Minimal migration cost
- Each specialized owner retains authority
- Documents ownership explicitly

**Risks:**
- Multiple execution paths remain
- Requires discipline to maintain boundaries

**Migration Complexity:** LOW
**Governance Impact:** None — preserves M3/M5
**P7 Impact:** None — preserves existing safety
**Compatibility:** Full backward compatibility

### 13.4 Option D: Hybrid — Canonical Primitives + Specialized Owners

**Benefits:**
- Clear primitive/owner distinction
- ToolExecutor/ToolEngine remain primitives
- Specialized owners retain lifecycle authority

**Risks:**
- Similar to Option C but with explicit primitive layer

**Migration Complexity:** LOW
**Governance Impact:** None
**P7 Impact:** None

---

## 14. Recommended Architecture

### 14.1 Recommendation: Option C (Distributed Ownership with Explicit Contracts)

**Rationale:**
1. **Architectural correctness:** Each execution kind has distinct governance, lifecycle, and outcome requirements
2. **Preservation of governance:** M3 caller-owned governance and M5 boundaries remain intact
3. **P7 safety:** SelfDevelopmentLoop's sandbox boundaries preserved
4. **Minimal migration:** No production code changes required for documentation
5. **Clear ownership:** Each system's role is explicitly defined

### 14.2 Canonical Execution Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    PRODUCTION ENTRY POINTS                   │
│  Atlas.chat()  │  Atlas.tick()  │  Atlas.run_self_development() │
└─────────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        ▼                     ▼                     ▼
┌───────────────┐   ┌─────────────────┐   ┌─────────────────────┐
│ Orchestration │   │  GoalExecution  │   │ SelfDevelopmentLoop │
│   Executor    │   │     Engine      │   │   (sandbox owner)   │
│ (multi-step)  │   │ (user-authorized)│   │                     │
└───────┬───────┘   └────────┬────────┘   └──────────┬──────────┘
        │                    │                       │
        ▼                    ▼                       ▼
┌─────────────────────────────────────────────────────────────┐
│                    PRIMITIVE LAYER                          │
│  ToolExecutor  │  ToolEngine  │  CapabilityDispatcher       │
│  CodeApplier   │  pytest      │  ApplicationEngine          │
└─────────────────────────────────────────────────────────────┘
```

### 14.3 Primitive vs Owner Distinction

**Execution Owners (lifecycle authority):**
- OrchestrationExecutor
- GoalExecutionEngine
- SelfDevelopmentLoop
- ToolChainExecutor

**Execution Primitives (invocation only):**
- ToolExecutor
- ToolEngine
- CapabilityDispatcher
- CodeApplier
- ApplicationEngine

**Coordinators (no direct execution):**
- RuntimeCoordinator
- EvolutionScheduler
- EvolutionAutonomyDispatcher
- DevelopmentCycleController
- TaskManager/Scheduler/Worker

---

## 15. M6 Implementation Boundary

### 15.1 MUST CHANGE

| Item | Rationale |
|------|-----------|
| Document canonical execution architecture | F3 requires explicit ownership definition |
| Define execution owner contracts | Each owner's interface must be specified |
| Document primitive vs owner distinction | Prevent future governance bypass |

### 15.2 SHOULD CHANGE

| Item | Rationale |
|------|-----------|
| Add ownership metadata to execution systems | Enable runtime ownership verification |
| Document call chain invariants | Prevent future architectural drift |

### 15.3 MUST NOT CHANGE

| Item | Rationale |
|------|-----------|
| ToolExecutor governance | M3 decision — caller-owned |
| ToolEngine governance | M5 decision — advisory primitive |
| OrchestrationExecutor per-step authority | M3/M5 governance boundary |
| SelfDevelopmentLoop sandbox isolation | P7 safety boundary |
| GoalExecutionEngine authorization model | M5 deferred to F3 |
| Task.run() no-op contract | M2 execution integrity |
| RuntimeCoordinator pipeline order | Locked pipeline invariant |

### 15.4 DEFER TO FUTURE QUEUE

| Item | Rationale |
|------|-----------|
| Outcome model unification | Not required for F3 |
| Task/Scheduler/Worker enhancement | Legacy subsystem |
| GoalExecutionEngine authorization unification | M5 deferred |
| Worker-level failure isolation | M5 deferred |

---

## 16. Adversarial Q1–Q18

### Q1. Is there currently one canonical execution owner?

**EVIDENCE:** Multiple systems own execution lifecycles: OrchestrationExecutor, GoalExecutionEngine, SelfDevelopmentLoop, ToolChainExecutor.

**CONCLUSION:** No. There are multiple specialized execution owners.

### Q2. If not, is the multiplicity intentional or accidental?

**EVIDENCE:** Each owner serves a distinct execution kind with different governance models. OrchestrationExecutor (per-step authority), GoalExecutionEngine (gateway authorization), SelfDevelopmentLoop (pre-approved sandbox).

**CONCLUSION:** Intentional specialization, but ownership contracts are implicit, not documented.

### Q3. Which system actually performs multi-step execution?

**EVIDENCE:** `atlas/orchestration/executor.py:241-316` — OrchestrationExecutor._run() executes bounded step graph with dependency ordering.

**CONCLUSION:** OrchestrationExecutor.

### Q4. Which system actually performs goal execution?

**EVIDENCE:** `atlas/goals/goal_execution_engine.py:346-464` — GoalExecutionEngine._execute() runs single goal through gateway.

**CONCLUSION:** GoalExecutionEngine.

### Q5. Which system actually performs self-development execution?

**EVIDENCE:** `atlas/evolution/self_development_loop.py:349-439` — SelfDevelopmentLoop.run() executes bounded sandbox iterations.

**CONCLUSION:** SelfDevelopmentLoop.

### Q6. Which system actually performs tool execution?

**EVIDENCE:** `atlas/tools/executor.py:39-95` — ToolExecutor.execute() invokes tool handlers.

**CONCLUSION:** ToolExecutor (primitive). ToolEngine adds selection.

### Q7. Is ToolExecutor an execution owner or primitive?

**EVIDENCE:** No lifecycle, no governance, no state ownership. Called by multiple systems.

**CONCLUSION:** Primitive.

### Q8. Is ToolEngine an execution owner or primitive?

**EVIDENCE:** Selection + coordination, no governance, delegates to ToolExecutor.

**CONCLUSION:** Primitive (advisory per M5).

### Q9. Is Task/Scheduler/Worker a real production execution architecture?

**EVIDENCE:** Production-reachable via tick(), but Task.run() is no-op/failure per M2.

**CONCLUSION:** No. It is a production-reachable but execution-free subsystem.

### Q10. Does GoalExecutionEngine duplicate OrchestrationExecutor?

**EVIDENCE:** Different governance models (gateway vs per-step), different outcome semantics, different authorization records.

**CONCLUSION:** No. Distinct execution kinds.

### Q11. Does SelfDevelopmentLoop duplicate OrchestrationExecutor?

**EVIDENCE:** SelfDevelopmentLoop uses CodeSandbox/pytest, OrchestrationExecutor explicitly denies evolution targets.

**CONCLUSION:** No. Specialized for sandboxed development.

### Q12. Does RuntimeCoordinator own execution or coordinate execution?

**EVIDENCE:** `atlas/runtime/runtime_coordinator.py:730` — delegates to ToolEngine. Orchestrates 15-stage pipeline.

**CONCLUSION:** Coordinator.

### Q13. Does CapabilityDispatcher own execution or dispatch execution?

**EVIDENCE:** `atlas/reasoning/execution/dispatcher.py:38-63` — handler lookup + invocation, no lifecycle.

**CONCLUSION:** Dispatcher.

### Q14. Would introducing a new universal executor improve architecture or create another competing execution layer?

**EVIDENCE:** Existing systems have distinct governance models. Universal executor would need to absorb all governance patterns.

**CONCLUSION:** Would create competing layer. Risk of weakening M3/M5 boundaries.

### Q15. Can F3 be solved without changing M3 governance?

**EVIDENCE:** M3 established caller-owned governance. F3 documents ownership without changing governance model.

**CONCLUSION:** Yes. F3 is documentation + contract definition.

### Q16. Can F3 be solved without weakening P7 safety?

**EVIDENCE:** P7 safety is in SelfDevelopmentLoop's sandbox boundaries. F3 does not require changing these.

**CONCLUSION:** Yes. F3 preserves existing safety boundaries.

### Q17. What is the smallest safe architectural change?

**EVIDENCE:** Ownership documentation requires no production code changes.

**CONCLUSION:** Document ownership contracts + primitive/owner distinction.

### Q18. What should explicitly remain separate?

**EVIDENCE:** Each execution kind has distinct governance requirements.

**CONCLUSION:**
- OrchestrationExecutor (multi-step, per-step authority)
- GoalExecutionEngine (user-authorized, gateway governance)
- SelfDevelopmentLoop (sandbox, P7 safety)
- ToolExecutor/ToolEngine (primitives, no governance)

---

## 17. Final Architecture Matrix

| System | Execution Kind | Current Role | Actual Side Effect | Governance | Ownership Classification | M6 Decision |
|--------|---------------|--------------|-------------------|------------|-------------------------|-------------|
| OrchestrationExecutor | Multi-step orchestration | Executor | Tool/capability/workspace/research dispatch | Per-step AuthorityService | SPECIALIZED EXECUTION OWNER | KEEP AS SPECIALIZED OWNER |
| GoalExecutionEngine | Goal execution | Executor | Tool invocation via gateway | Gateway + authorization record | SPECIALIZED EXECUTION OWNER | KEEP AS SPECIALIZED OWNER |
| SelfDevelopmentLoop | Self-development | Executor | Sandbox code + pytest | Pre-approved proposal | SPECIALIZED EXECUTION OWNER | KEEP AS SPECIALIZED OWNER |
| ToolChainExecutor | Tool chain execution | Executor | Sequential/parallel tool dispatch | Risk policy | SPECIALIZED EXECUTION OWNER | KEEP AS SPECIALIZED OWNER |
| ToolExecutor | Tool invocation | Primitive | Tool handler invocation | Caller-owned (M3) | LOW-LEVEL PRIMITIVE | KEEP AS PRIMITIVE |
| ToolEngine | Tool selection + execution | Primitive | Selection + ToolExecutor delegation | Caller-owned (M5) | LOW-LEVEL PRIMITIVE | KEEP AS PRIMITIVE |
| CapabilityDispatcher | Capability dispatch | Dispatcher | Handler invocation | Caller-owned | DISPATCHER | KEEP AS DISPATCHER |
| RuntimeCoordinator | Cognitive processing | Coordinator | Pipeline stage orchestration | Caller-owned | COORDINATOR | KEEP AS COORDINATOR |
| EvolutionScheduler | Evolution analysis | Coordinator | Proposal generation (no execution) | Threshold-gated | COORDINATOR | KEEP AS COORDINATOR |
| EvolutionAutonomyDispatcher | Autonomy request lifecycle | Coordinator | Gateway delegation | Human authorization | COORDINATOR | KEEP AS COORDINATOR |
| DevelopmentCycleController | Development preparation | Coordinator | DRAFT proposal (stops at approval) | Approval boundary | COORDINATOR | KEEP AS COORDINATOR |
| TaskManager/Scheduler/Worker | Task scheduling | Coordinator | Task.run() [no-op] | None | LEGACY COORDINATOR | RETAIN AS LEGACY |
| EvolutionExecutionGateway | Evolution governance | Gate | RuleEngine evaluation | RuleEngine | GOVERNANCE GATE | KEEP AS GATE |
| EvolutionExecutionEngine | Evolution execution | Primitive | Administrative record-keeping | Level 0 only | LOW-LEVEL PRIMITIVE | KEEP AS PRIMITIVE |

---

## 18. Findings Classification

### 18.1 PASS

| ID | Finding | Evidence |
|----|---------|----------|
| P1 | Baseline verified | git status/rev-parse |
| P2 | M3 governance preserved | ToolExecutor/ToolEngine remain primitives |
| P3 | M5 governance preserved | Caller-owned governance intact |
| P4 | P7 safety preserved | SelfDevelopmentLoop sandbox boundaries intact |
| P5 | M2 execution integrity preserved | Task.run() no-op contract intact |
| P6 | OrchestrationExecutor is specialized owner | Per-step authority, multi-step lifecycle |
| P7 | GoalExecutionEngine is specialized owner | Gateway authorization, goal lifecycle |
| P8 | SelfDevelopmentLoop is specialized owner | Sandbox iteration lifecycle |
| P9 | ToolExecutor is primitive | No lifecycle, no governance |
| P10 | ToolEngine is primitive | Selection + delegation only |
| P11 | RuntimeCoordinator is coordinator | Pipeline orchestration, delegates execution |
| P12 | Task subsystem is legacy | Production-reachable but no-op |

### 18.2 ARCHITECTURAL CONCERN

| ID | Finding | Evidence | Impact | Action |
|----|---------|----------|--------|--------|
| AC1 | Execution ownership contracts are implicit | No formal ownership documentation | Future drift risk | Document ownership contracts in M6 |
| AC2 | Outcome models are incompatible | Each system has own outcome type | Integration complexity | Defer to Future Queue |
| AC3 | Multiple execution paths to ToolExecutor | OrchestrationExecutor, ToolEngine, binder all call ToolExecutor | Potential governance inconsistency | Document primitive vs owner distinction |

### 18.3 FUTURE QUEUE

| ID | Finding | Rationale |
|----|---------|-----------|
| FQ1 | Outcome model unification | Not required for F3 |
| FQ2 | Task/Scheduler/Worker enhancement | Legacy subsystem, M2 no-op contract |
| FQ3 | GoalExecutionEngine authorization unification | M5 deferred |
| FQ4 | Worker-level failure isolation | M5 deferred |

### 18.4 TEST GAP

| ID | Finding | Evidence | Impact |
|----|---------|----------|--------|
| TG1 | No test verifies execution ownership contracts | No ownership metadata tested | Ownership drift undetected | Add ownership invariant tests |

### 18.5 BLOCKER

None identified.

---

## 19. Final Verdict

### M6.1 PASS — CANONICAL EXECUTION ARCHITECTURE INVESTIGATION COMPLETE

**Justification:**

1. **Execution architecture comprehensively inventoried:** 15 execution-related systems identified and classified.

2. **Actual production call chains understood:** 6 distinct production execution paths traced from entry points to side effects.

3. **Ownership overlaps identified:** OrchestrationExecutor vs GoalExecutionEngine vs SelfDevelopmentLoop analyzed — intentional specialization, not duplication.

4. **Execution kinds classified:** 8 distinct execution kinds identified with clear ownership.

5. **Canonical ownership recommendation evidence-backed:** Option C (distributed ownership with explicit contracts) recommended based on governance preservation and minimal migration.

6. **M3/M4/M5 governance boundaries remain understood:** Caller-owned governance preserved. ToolExecutor/ToolEngine remain primitives.

7. **Safe implementation boundary for M6 established:** MUST CHANGE (documentation only), MUST NOT CHANGE (governance boundaries), DEFER (outcome unification).

8. **No implementation performed:** Investigation was read-only.

---

## Appendix A: Investigation Commands

```bash
# Baseline verification
git status --short
git branch --show-current
git rev-parse HEAD
git rev-parse origin/phase5-memory-evolution
git rev-list --left-right --count HEAD...origin/phase5-memory-evolution
git show --stat --oneline --decorate HEAD
git show --name-status --oneline HEAD
git log --oneline --decorate -n 20

# System discovery
grep -rn "class.*Executor\|class.*Engine\|class.*Dispatcher\|class.*Coordinator" atlas/
grep -rn "OrchestrationExecutor\|GoalExecutionEngine\|SelfDevelopmentLoop\|EvolutionScheduler" atlas/

# Call chain tracing
grep -rn "orchestration_executor.execute\|goal_executor.settle\|self_development_loop.run\|runtime_coordinator.process" atlas/kernel/
grep -rn "tool_executor.execute\|tool_engine.fulfill" atlas/

# Production entry points
grep -rn "def tick\|def chat\|def process\|def run_development_cycle\|def run_self_development" atlas/kernel/atlas.py
```

## Appendix B: File Inventory

Files inspected:
- atlas/orchestration/executor.py (637 lines)
- atlas/goals/goal_execution_engine.py (731 lines)
- atlas/evolution/self_development_loop.py (587 lines)
- atlas/evolution/scheduler.py (379 lines)
- atlas/tools/executor.py (139 lines)
- atlas/tools/engine.py (155 lines)
- atlas/task/task_manager.py (102 lines)
- atlas/scheduler/scheduler.py (112 lines)
- atlas/scheduler/worker.py (31 lines)
- atlas/runtime/runtime_coordinator.py (1708 lines)
- atlas/reasoning/execution/dispatcher.py (109 lines)
- atlas/toolchain/executor.py (150 lines)
- atlas/evolution/autonomy/dispatcher.py (100 lines)
- atlas/evolution/development_cycle.py (200 lines)
- atlas/evolution/execution_gateway.py (100 lines)
- atlas/evolution/execution_engine.py (100 lines)
- atlas/task/task.py (120 lines)
- atlas/tools/execution_action_binder.py (84 lines)
- atlas/services/cognition_service.py (200 lines)
- atlas/cognition/api.py (43 lines)
- atlas/cognition/pipeline.py (549 lines)
- atlas/conversation/conversation_service.py (612 lines)
- atlas/kernel/atlas.py (3368 lines, selected sections)
- docs/ROADMAP.md (604 lines)

---

**Report generated:** 2026-09-05
**Word count:** ~3,800 words
**Investigation status:** COMPLETE
**Repository state:** UNMODIFIED

---

# M6.4 — Execution Ownership Contract (IMPLEMENTATION)

**Date:** 2026-09-05
**Branch:** phase5-memory-evolution
**HEAD:** 554cadc
**Type:** Implementation (documentation + architectural tests)

---

## 1. Canonical Execution Architecture

Atlas uses **distributed execution ownership**. There is one top-level
execution owner per execution kind. Owners are NOT interchangeable — each
serves a distinct execution kind with distinct governance, lifecycle, and
outcome semantics.

### 1.1 Top-Level Execution Owners

| Owner | Execution Kind | File:Line | Governance |
|-------|---------------|-----------|------------|
| OrchestrationExecutor | Multi-step orchestration | atlas/orchestration/executor.py:72 | Per-step AuthorityService |
| GoalExecutionEngine | User-authorized goal execution | atlas/goals/goal_execution_engine.py:104 | Gateway + authorization record |
| SelfDevelopmentLoop | Sandboxed code development | atlas/evolution/self_development_loop.py:307 | Pre-approved proposal (P7) |

### 1.2 Non-Owner Boundaries

| Component | Classification | Boundary |
|-----------|---------------|----------|
| ToolExecutor | Primitive | No lifecycle, no governance (M3) |
| ToolEngine | Primitive | Selection + delegation only (M5) |
| CapabilityDispatcher | Dispatcher | Handler lookup + invocation |
| ToolChainExecutor | Sub-primitive | Behind CapabilityDispatcher |
| RuntimeCoordinator | Coordinator | Pipeline orchestration, delegates execution |
| EvolutionScheduler | Coordinator | Proposal generation only |
| EvolutionExecutionGateway | Governance gate | RuleEngine evaluation |
| TaskManager/Scheduler/Worker | Legacy coordinator | Task.run() no-op (M2) |

### 1.3 Owner-to-Owner Delegation Rule

Top-level owners must NOT become interchangeable execution owners.
Delegation to primitives/dispatchers is allowed and expected:
- OrchestrationExecutor delegates to ToolExecutor / CapabilityDispatcher
- GoalExecutionEngine delegates to ToolEngine (via binder)
- SelfDevelopmentLoop delegates to CodeApplier / pytest (sandbox)

### 1.4 ToolChainExecutor Status

ToolChainExecutor is a **sub-primitive**, NOT a fourth top-level owner.
It is wired through ToolchainCapabilityFactory → CapabilityDispatcher and
has no direct production ownership path. It must not be promoted to a
top-level execution owner.

### 1.5 Governance Preservation

M3/M4/M5/P7 governance boundaries remain unchanged:
- M3: ToolExecutor/ToolEngine remain caller-trusting primitives
- M4: Self-development safety boundaries preserved
- M5: Caller-owned governance intact
- P7: SelfDevelopmentLoop sandbox isolation preserved
- M2: Task.run() no-op contract preserved

---

## 2. Architectural Tests

File: `tests/test_execution_ownership_m6.py`

| Test | Coverage | Type |
|------|----------|------|
| T1: ToolExecutor primitive boundary | No governance imports, registry-only constructor, no authority attributes | Source inspection + structural |
| T2: ToolEngine primitive boundary | No governance imports, registry/selector/executor constructor, no authority attributes | Source inspection + structural |
| T3: RuntimeCoordinator coordinator boundary | Delegates to ToolEngine.fulfill + CapabilityDispatcher.dispatch, no owner imports | Source inspection |
| T4: SelfDevelopmentLoop safety boundary | Refuses non-APPROVED proposals with GOVERNANCE_DENIED | Behavioral |
| T5: GoalExecutionEngine authorization boundary | Refuses non-user:cli authorization | Behavioral |
| T6: Task.run legacy boundary | M2 no-op/failure contract preserved | Behavioral |
| T7: OrchestrationExecutor denial boundary | Denied prefixes fail closed with denied_surface | Source inspection + behavioral |
| T8: ToolChainExecutor ownership boundary | No direct kernel import, wired through CapabilityDispatcher, no cross-owner imports | Source inspection |

---

## 3. Implementation Boundary

### 3.1 MUST NOT CHANGE

| Item | Rationale |
|------|-----------|
| ToolExecutor governance | M3 decision — caller-owned primitive |
| ToolEngine governance | M5 decision — advisory primitive |
| OrchestrationExecutor per-step authority | M3/M5 governance boundary |
| SelfDevelopmentLoop sandbox isolation | P7 safety boundary |
| GoalExecutionEngine authorization model | user:cli contract |
| Task.run() no-op contract | M2 execution integrity |
| RuntimeCoordinator pipeline order | Locked pipeline invariant |

### 3.2 NO METADATA/REGISTRY INTRODUCED

No owner registry, no ownership metadata system, no universal executor
abstraction was introduced. Enforcement is via documentation + tests only.

---

**M6.4 status:** IMPLEMENTATION COMPLETE
**Tests:** 20 passed
**Production changes:** NONE
**Documentation updated:** architecture_analysis.md
