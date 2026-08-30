"""Atlas Orchestration — Governed Step Executor (P2/B2.2).

Executes bounded steps of an :class:`OrchestrationPlan` (or explicit
:class:`ExecutionStep` tuples) through EXISTING Atlas infrastructure only:

    CAPABILITY  → CapabilityRegistry.has + CapabilityDispatcher.dispatch
    TOOL        → ToolExecutor.execute_by_name
    WORKSPACE   → injected WorkspaceService public metadata API
    RESEARCH    → injected InformationAcquisitionService.acquire
    GOAL        → NOT wired (owner decision): fails closed MISSING_TARGET

The executor is NOT a new tool/capability/governance system and NOT a
workflow engine. It composes existing seams, attributes every step to the
B1.2 SessionContext via AuthorityService, and is fail-closed and bounded
(max steps, dependency ordering, no recursion, no threads, no arbitrary
code execution). It never holds references to evolution approval/gateway/
promotion machinery, so those boundaries cannot be bypassed.

Pure orchestration: no kernel, runtime, AI, storage, or evolution imports.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from atlas.authority.service import AuthorityService
from atlas.orchestration.execution_models import (
    ExecutionRequest,
    ExecutionState,
    ExecutionStatus,
    ExecutionStep,
    OrchestrationResult,
    StepExecutionResult,
    new_run_id,
)
from atlas.orchestration.models import NodeKind
from atlas.reasoning.capabilities.models import Capability
from atlas.reasoning.execution.dispatcher import CapabilityDispatcher
from atlas.reasoning.execution.registry import CapabilityRegistry

if TYPE_CHECKING:
    from atlas.session.context import SessionContext
    from atlas.tools.executor import ToolExecutor

#: Targets under these prefixes would reach evolution/approval/gateway
#: machinery the executor must never touch. Defense in depth — the executor
#: also holds no references to those surfaces.
_DENIED_PREFIXES: tuple[str, ...] = (
    "evolution.",
    "autonomy.",
    "governance.",
    "approval.",
    "promotion.",
    "gateway.",
    "application.",
    "schedule.",
)


@dataclass(frozen=True, slots=True)
class _AuthOutcome:
    """Internal authority-check outcome for one step."""

    allowed: bool
    error: str = ""
    principal_id: str | None = None
    authority: str | None = None


class OrchestrationExecutor:
    """Deterministic, governed executor over the orchestration step graph.

    All collaborators are injected and optional. Missing seams degrade to
    deterministic fail-closed step results; the executor never raises.
    """

    def __init__(
        self,
        capability_registry: CapabilityRegistry | None = None,
        capability_dispatcher: CapabilityDispatcher | None = None,
        tool_executor: ToolExecutor | None = None,
        workspace_service: Any | None = None,
        research_service: Any | None = None,
        authority_service: AuthorityService | None = None,
    ) -> None:
        self._capability_registry = capability_registry
        self._capability_dispatcher = capability_dispatcher
        self._tool_executor = tool_executor
        self._workspace_service = workspace_service
        self._research_service = research_service
        self._authority_service = authority_service

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def execute(self, request: ExecutionRequest) -> OrchestrationResult:
        """Execute a bounded orchestration request.

        Fail-closed and deterministic. Never raises.

        Args:
            request: The bounded ExecutionRequest (plan or explicit steps).

        Returns:
            A structured :class:`OrchestrationResult`.
        """
        started = time.perf_counter()

        # --- Run-level fail-closed guards ---
        session_context = request.session_context
        if session_context is None:
            return self._assemble(
                ExecutionStatus.REJECTED,
                request,
                steps=[],
                error="missing session context (fail-closed)",
                started=started,
            )

        steps = self._resolve_steps(request)
        if not steps:
            return self._assemble(
                ExecutionStatus.EMPTY,
                request,
                steps=[],
                error="no plan or steps to execute",
                started=started,
            )

        deps_map = {step.step_id: tuple(step.depends_on) for step in steps}

        # --- Pre-validate every step (no execution yet) ---
        validated = [self._validate_step(step) for step in steps]

        results = self._run(validated, deps_map, request, started)
        status = self._overall_status(results)
        return self._assemble(status, request, results, "", started)

    # ------------------------------------------------------------------
    # Step resolution (plan → steps 1:1, never synthesizes)
    # ------------------------------------------------------------------

    def _resolve_steps(self, request: ExecutionRequest) -> list[ExecutionStep]:
        if request.steps:
            return list(request.steps)

        plan = request.plan
        if plan is None or not plan.graph.nodes:
            return []

        # Depends_on from SEQUENTIAL edges (deterministic linear chain).
        edge_map: dict[str, list[str]] = {}
        for edge in plan.graph.edges:
            edge_map.setdefault(edge.to_id, []).append(edge.from_id)

        steps: list[ExecutionStep] = []
        for node in plan.graph.nodes:
            target = node.capability_name or node.action
            steps.append(
                ExecutionStep(
                    step_id=node.node_id,
                    kind=node.kind,
                    target=target or "",
                    inputs=dict(node.parameters),
                    depends_on=tuple(edge_map.get(node.node_id, ())),
                    description=node.description,
                )
            )
        return steps

    # ------------------------------------------------------------------
    # Validation (deterministic, no execution)
    # ------------------------------------------------------------------

    def _validate_step(self, step: ExecutionStep) -> StepExecutionResult:
        base = StepExecutionResult(
            step_id=step.step_id,
            kind=step.kind,
            target=step.target,
            state=ExecutionState.PENDING,
            metadata={"inputs": dict(step.inputs), "depends_on": tuple(step.depends_on)},
        )
        if not isinstance(step.target, str) or not step.target.strip():
            return self._failure(
                base, ExecutionState.FAILED, "invalid_input", "step target is empty"
            )
        if self._is_denied_target(step.target):
            return self._failure(
                base,
                ExecutionState.FAILED,
                "denied_surface",
                f"target '{step.target}' is denied (governed surface)",
            )
        if step.kind is NodeKind.GOAL:
            return self._failure(
                base,
                ExecutionState.FAILED,
                "missing_target",
                "goal execution is not wired (fails closed)",
            )
        if not self._has_target(step):
            return self._failure(
                base,
                ExecutionState.FAILED,
                "missing_target",
                f"no registered {step.kind.value} target: '{step.target}'",
            )
        return base

    def _has_target(self, step: ExecutionStep) -> bool:
        """True when the step's target is registered in the relevant seam."""
        if step.kind is NodeKind.CAPABILITY:
            if self._capability_registry is None:
                return False
            return self._capability_registry.has(step.target)
        if step.kind is NodeKind.TOOL:
            if self._tool_executor is None:
                return False
            registry = getattr(self._tool_executor, "_registry", None)
            if registry is None:
                return False
            return registry.get(step.target) is not None
        if step.kind is NodeKind.WORKSPACE:
            return self._workspace_service is not None
        if step.kind is NodeKind.RESEARCH:
            return self._research_service is not None
        return False

    @staticmethod
    def _is_denied_target(target: str) -> bool:
        lowered = target.lower().strip()
        return any(lowered.startswith(prefix) for prefix in _DENIED_PREFIXES)

    # ------------------------------------------------------------------
    # Execution loop (iterative; no recursion; each step at most once)
    # ------------------------------------------------------------------

    def _run(
        self,
        validated: list[StepExecutionResult],
        deps_map: dict[str, tuple[str, ...]],
        request: ExecutionRequest,
        started: float,
    ) -> list[StepExecutionResult]:
        results = list(validated)
        executed: set[str] = set()
        executed_count = 0
        terminal_authority_failure = False

        while True:
            pending = [
                r for r in results
                if r.state is ExecutionState.PENDING and r.step_id not in executed
            ]
            if not pending:
                break

            step = pending[0]
            idx = results.index(step)

            # --- Bound check (executed steps, not pending) ---
            if executed_count >= request.max_steps:
                self._skip_remaining(results, executed, "bound_exceeded", f"max_steps={request.max_steps} reached")
                break

            # --- Dependency check: never execute a blocked step ---
            deps = deps_map.get(step.step_id, ())
            completed = {
                r.step_id for r in results if r.state is ExecutionState.COMPLETED
            }
            missing = [d for d in deps if d not in completed]
            if missing:
                results[idx] = self._failure(
                    step,
                    ExecutionState.BLOCKED,
                    "dependency_failed",
                    f"dependency not completed: {', '.join(sorted(missing))}",
                )
                executed.add(step.step_id)
                continue

            # --- Authority check (per step; never from user text) ---
            auth = self._authorize(step, request)
            if not auth.allowed:
                results[idx] = self._failure(
                    step,
                    ExecutionState.FAILED,
                    "authorization_failed",
                    auth.error,
                    principal_id=auth.principal_id,
                    authority=auth.authority,
                )
                executed.add(step.step_id)
                terminal_authority_failure = True
                break

            # --- Execute the step (PENDING → RUNNING → terminal) ---
            results[idx] = self._execute_step(step, request)
            executed.add(step.step_id)
            executed_count += 1

            if results[idx].failed:
                if not request.continue_on_failure:
                    # Fail-closed default: stop the run. Dependents of the
                    # failed step are BLOCKED (never executable); independent
                    # remaining steps are SKIPPED.
                    self._stop_after_failure(results, executed, deps_map)
                    break

        if terminal_authority_failure:
            self._skip_remaining(results, executed, "dependency_failed", "run stopped after authorization failure")

        return results

    @staticmethod
    def _stop_after_failure(
        results: list[StepExecutionResult],
        executed: set[str],
        deps_map: dict[str, tuple[str, ...]],
    ) -> None:
        """Mark remaining steps after a run-stopping failure.

        A step whose dependency is not COMPLETED is BLOCKED (never
        executable); an independent pending step is SKIPPED.
        """
        completed = {
            r.step_id for r in results if r.state is ExecutionState.COMPLETED
        }
        for i, r in enumerate(results):
            if r.step_id in executed or r.state is not ExecutionState.PENDING:
                continue
            deps = deps_map.get(r.step_id, ())
            if any(d not in completed for d in deps):
                results[i] = OrchestrationExecutor._failure(
                    r,
                    ExecutionState.BLOCKED,
                    "dependency_failed",
                    "dependency not completed after run stopped",
                )
            else:
                results[i] = OrchestrationExecutor._failure(
                    r,
                    ExecutionState.SKIPPED,
                    "dependency_failed",
                    "run stopped after step failure",
                )

    @staticmethod
    def _skip_remaining(
        results: list[StepExecutionResult],
        executed: set[str],
        failure_kind: str,
        reason: str,
    ) -> None:
        for i, r in enumerate(results):
            if r.step_id not in executed and r.state is ExecutionState.PENDING:
                results[i] = OrchestrationExecutor._failure(
                    r, ExecutionState.SKIPPED, failure_kind, reason
                )

    def _authorize(self, step: StepExecutionResult, request: ExecutionRequest) -> _AuthOutcome:
        session_context = request.session_context
        principal_id = session_context.principal_id if session_context else None
        authority = session_context.authority.value if session_context else None
        if self._authority_service is None or session_context is None:
            return _AuthOutcome(
                allowed=False,
                error="authority service not wired (fail-closed)",
                principal_id=principal_id,
                authority=authority,
            )
        decision = self._authority_service.check(
            principal_id,
            request.required_authority,
            action=f"orchestration:{step.target}",
        )
        return _AuthOutcome(
            allowed=decision.allowed,
            error="" if decision.allowed else (decision.reason or "authority denied"),
            principal_id=principal_id,
            authority=authority,
        )

    def _execute_step(
        self,
        step: StepExecutionResult,
        request: ExecutionRequest,
    ) -> StepExecutionResult:
        kind = step.kind
        target = step.target
        session_context = request.session_context
        principal_id = session_context.principal_id if session_context else None
        authority = session_context.authority.value if session_context else None

        inputs = dict(step.metadata.get("inputs", {}) or {})
        params = self._attributed_inputs(step, inputs, session_context)

        start = time.perf_counter()
        try:
            if kind is NodeKind.CAPABILITY:
                result = self._dispatch_capability(step, params)
            elif kind is NodeKind.TOOL:
                result = self._dispatch_tool(step, params)
            elif kind is NodeKind.WORKSPACE:
                result = self._dispatch_workspace(step, params)
            elif kind is NodeKind.RESEARCH:
                result = self._dispatch_research(step, params)
            else:
                result = {"success": False, "error": f"unsupported step kind: {kind.value}"}
        except Exception as exc:  # defensive — seams never raise, but fail closed
            elapsed = (time.perf_counter() - start) * 1000
            return StepExecutionResult(
                step_id=step.step_id,
                kind=kind,
                target=target,
                state=ExecutionState.FAILED,
                failure_kind="execution_failed",
                error=str(exc),
                execution_time_ms=elapsed,
                principal_id=principal_id,
                authority=authority,
                allowed=True,
            )

        elapsed = (time.perf_counter() - start) * 1000
        success = bool(result.get("success", False))
        output = dict(result.get("output", {}) or {})
        error = str(result.get("error", "") or "")
        if success:
            return StepExecutionResult(
                step_id=step.step_id,
                kind=kind,
                target=target,
                state=ExecutionState.COMPLETED,
                output=output,
                execution_time_ms=elapsed,
                principal_id=principal_id,
                authority=authority,
                allowed=True,
                metadata={"result": _safe_snapshot(result.get("metadata", {}))},
            )
        return StepExecutionResult(
            step_id=step.step_id,
            kind=kind,
            target=target,
            state=ExecutionState.FAILED,
            failure_kind="execution_failed",
            error=error or "step execution failed",
            output=output,
            execution_time_ms=elapsed,
            principal_id=principal_id,
            authority=authority,
            allowed=True,
        )

    # ------------------------------------------------------------------
    # Seam dispatch (existing infrastructure only)
    # ------------------------------------------------------------------

    def _dispatch_capability(self, step: StepExecutionResult, params: dict) -> dict:
        dispatcher = self._capability_dispatcher
        if dispatcher is None:
            return {"success": False, "error": "capability dispatcher not wired"}
        capability = Capability(name=step.target, metadata=dict(params))
        results = dispatcher.dispatch([capability])
        result = results[0] if results else None
        if result is None:
            return {"success": False, "error": "dispatcher returned no result"}
        return {
            "success": bool(result.success),
            "output": dict(result.output or {}),
            "error": result.error or "",
            "metadata": dict(result.metadata or {}),
        }

    def _dispatch_tool(self, step: StepExecutionResult, params: dict) -> dict:
        executor = self._tool_executor
        if executor is None:
            return {"success": False, "error": "tool executor not wired"}
        result = executor.execute_by_name(step.target, dict(params))
        return {
            "success": bool(result.success),
            "output": dict(result.output or {}),
            "error": result.error or "",
            "metadata": dict(result.metadata or {}),
        }

    def _dispatch_workspace(self, step: StepExecutionResult, params: dict) -> dict:
        service = self._workspace_service
        if service is None:
            return {"success": False, "error": "workspace service not wired (fails closed)"}
        op = step.target
        handler = getattr(service, op, None)
        if not callable(handler):
            return {"success": False, "error": f"workspace operation '{op}' not found"}
        try:
            result = handler(**{k: v for k, v in params.items() if k != "session"})
        except Exception as exc:
            return {"success": False, "error": f"workspace operation failed: {exc}"}
        if hasattr(result, "to_dict"):
            return {"success": True, "output": {"result": _safe_snapshot(result.to_dict())}}
        return {"success": True, "output": {"result": _safe_snapshot(result)}}

    def _dispatch_research(self, step: StepExecutionResult, params: dict) -> dict:
        service = self._research_service
        if service is None:
            return {"success": False, "error": "research service not wired (fails closed)"}
        kwargs = {k: v for k, v in params.items() if k != "session"}
        try:
            result = service.acquire(**kwargs)
        except Exception as exc:
            return {"success": False, "error": f"research acquisition failed: {exc}"}
        status = getattr(result, "status", "failed")
        if status == "failed":
            failures = getattr(result, "failures", ()) or ()
            return {
                "success": False,
                "error": f"research acquisition failed: {_safe_snapshot(failures)}",
                "output": _result_dict(result),
            }
        return {
            "success": status in ("ok", "noop", "partial"),
            "output": _result_dict(result),
            "error": "" if status in ("ok", "noop") else f"research partial: {status}",
        }

    # ------------------------------------------------------------------
    # Attribution helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _attributed_inputs(
        step: StepExecutionResult,
        params: dict,
        session_context: SessionContext | None,
    ) -> dict:
        """Attach read-only session attribution to handler-visible params.

        The run's result attribution never comes from handler output; the
        handler cannot override the SessionContext.
        """
        params = dict(params)
        if session_context is not None:
            params["session"] = {
                "session_id": session_context.session_id,
                "principal_id": session_context.principal_id,
                "authority": session_context.authority.value,
            }
        return params

    # ------------------------------------------------------------------
    # Result assembly
    # ------------------------------------------------------------------

    def _assemble(
        self,
        status: ExecutionStatus,
        request: ExecutionRequest,
        steps: list[StepExecutionResult],
        error: str,
        started: float,
    ) -> OrchestrationResult:
        session_context = request.session_context
        return OrchestrationResult(
            run_id=new_run_id(),
            status=status,
            steps=tuple(steps),
            error=error,
            session_id=session_context.session_id if session_context else None,
            principal_id=session_context.principal_id if session_context else None,
            authority=session_context.authority.value if session_context else None,
            required_authority=request.required_authority.value,
            max_steps=request.max_steps,
            continue_on_failure=request.continue_on_failure,
            elapsed_ms=(time.perf_counter() - started) * 1000,
            metadata=dict(request.metadata),
        )

    def _overall_status(self, results: list[StepExecutionResult]) -> ExecutionStatus:
        if not results:
            return ExecutionStatus.EMPTY
        if any(r.failed and r.failure_kind == "authorization_failed" for r in results):
            return ExecutionStatus.REJECTED
        if all(r.completed for r in results):
            return ExecutionStatus.COMPLETED
        if any(r.completed for r in results):
            return ExecutionStatus.PARTIAL
        return ExecutionStatus.FAILED

    @staticmethod
    def _failure(
        step: StepExecutionResult,
        state: ExecutionState,
        failure_kind: str,
        error: str,
        principal_id: str | None = None,
        authority: str | None = None,
    ) -> StepExecutionResult:
        return StepExecutionResult(
            step_id=step.step_id,
            kind=step.kind,
            target=step.target,
            state=state,
            failure_kind=failure_kind,
            error=error,
            principal_id=principal_id,
            authority=authority,
        )


def _result_dict(result: Any) -> dict:
    """Deterministic dict projection of a seam result object."""
    if hasattr(result, "to_dict"):
        try:
            return dict(result.to_dict())
        except Exception:
            pass
    return _safe_snapshot(result)


def _safe_snapshot(value: Any) -> Any:
    """Best-effort JSON-safe projection (never raises)."""
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): _safe_snapshot(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe_snapshot(v) for v in value]
    try:
        return str(value)
    except Exception:
        return "<unserializable>"
