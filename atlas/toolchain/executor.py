"""Atlas Toolchain — Safe Execution (Phase 18.5).

Executes :class:`ToolChain` / :class:`ToolChainPlan` artifacts against an
injected tool-execution surface. Deterministic, fail-closed, protocol-based,
and fully typed.

Supported strategies:
  - SEQUENTIAL  — steps run one-after-another; all must succeed.
  - FALLBACK    — steps are tried in order; first success wins.
  - CONDITIONAL — steps are selected based on deterministic predicates
      over prior step output (Phase 22, Batch 1; see
      :mod:`atlas.toolchain.conditional`). The executor is the only
      decision point — no planner/router/dispatcher involvement.
  - PARALLEL  — deterministic sequential fan-out/fan-in (Phase 22,
      Batch 2; docs/PHASE_22_DESIGN.md §4/§5): every eligible step
      executes exactly once, results are collected in declared order, and
      any step failure fails the overall result while sibling results are
      preserved. No threading/async/subprocess — the "no real
      concurrency" invariant remains in force.

Unsupported strategies:
  - Any strategy not listed above returns a failed
    :class:`ToolChainResult`; never raises.

The executor never raises. Every error condition (unknown tool, denied tool,
unsupported strategy, handler exception, malformed input) produces a failed
:class:`ToolChainResult` with a descriptive error message.

No threading. No async. No subprocess. No shell execution. No concrete
``atlas.tools`` imports — tool invocation is via the :class:`ToolInvoker`
protocol.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from atlas.toolchain.conditional import (
    evaluate_condition,
    extract_condition,
    is_supported_condition,
)
from atlas.toolchain.models import ToolChain, ToolChainPlan, ToolChainResult, ToolStep


# ---------------------------------------------------------------------------
# Protocol — dependency injection
# ---------------------------------------------------------------------------


@runtime_checkable
class ToolInvoker(Protocol):
    """Tool execution surface the chain executor consults.

    Decouples the executor from :class:`~atlas.tools.executor.ToolExecutor`
    so the executor stays pure and testable with fakes. Any object exposing
    ``execute_by_name(name, params)`` returning a tool-result-like object
    (with ``success``, ``output``, ``error``, ``execution_time_ms``
    attributes) satisfies this protocol.
    """

    def execute_by_name(
        self,
        name: str,
        params: dict[str, Any] | None = None,
    ) -> Any: ...


# ---------------------------------------------------------------------------
# Risk policy
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RiskPolicy:
    """Deterministic risk policy for tool chain execution.

    Controls which tools may be executed via allow/deny lists. Fail-closed:
    when a tool is in both the allow and deny lists, it is denied. When the
    allow list is non-empty, only listed tools are permitted (minus the deny
    list). When the allow list is empty, all tools not in the deny list are
    permitted.

    Attributes:
        allow_list: Tools permitted to execute. Empty = allow all (except
            deny list).
        deny_list: Tools forbidden from executing. Always wins over allow.
        max_steps: Maximum number of steps to execute (0 = no limit).
        max_execution_time_ms: Maximum total execution time in milliseconds
            (0.0 = no limit).
    """

    allow_list: frozenset[str] = frozenset()
    deny_list: frozenset[str] = frozenset()
    max_steps: int = 0
    max_execution_time_ms: float = 0.0

    def is_allowed(self, tool_name: str) -> bool:
        """Check if a tool is permitted by the policy.

        Args:
            tool_name: The tool name to check.

        Returns:
            True if the tool is allowed, False if denied.
        """
        if tool_name in self.deny_list:
            return False
        if self.allow_list and tool_name not in self.allow_list:
            return False
        return True

    @property
    def has_step_limit(self) -> bool:
        """True when a step limit is configured."""
        return self.max_steps > 0

    @property
    def has_time_limit(self) -> bool:
        """True when a time limit is configured."""
        return self.max_execution_time_ms > 0.0


# ---------------------------------------------------------------------------
# Strategy constants
# ---------------------------------------------------------------------------

#: Strategies the executor supports.
SUPPORTED_STRATEGIES: frozenset[str] = frozenset(
    {"sequential", "fallback", "conditional", "parallel"}
)

#: Strategies the executor explicitly does not support. Empty for Phase 22
#: Batch 2 — every declared strategy now has an implementation. Unknown
#: strategies still fail closed via the generic unsupported-strategy guard.
UNSUPPORTED_STRATEGIES: frozenset[str] = frozenset()


# ---------------------------------------------------------------------------
# Executor
# ---------------------------------------------------------------------------


class ToolChainExecutor:
    """Deterministic, fail-closed tool chain executor.

    Executes :class:`ToolChain` or :class:`ToolChainPlan` artifacts against
    an injected :class:`ToolInvoker` (protocol-injected). The executor never
    raises — every error condition produces a failed
    :class:`ToolChainResult`.

    No threading, async, subprocess, or shell execution. No concrete
    ``atlas.tools`` imports.
    """

    def __init__(
        self,
        tool_invoker: ToolInvoker | None = None,
        risk_policy: RiskPolicy | None = None,
    ) -> None:
        """Initialise the executor.

        Args:
            tool_invoker: A :class:`ToolInvoker`-shaped object. If ``None``,
                all executions fail (no tool surface available).
            risk_policy: Optional risk policy. If ``None``, a permissive
                default policy is used.
        """
        self._invoker: ToolInvoker | None = tool_invoker
        self._policy: RiskPolicy = risk_policy or RiskPolicy()

    @property
    def has_invoker(self) -> bool:
        """True when a tool invoker is wired."""
        return self._invoker is not None

    @property
    def risk_policy(self) -> RiskPolicy:
        """The active risk policy."""
        return self._policy

    # ------------------------------------------------------------------
    # Public execution
    # ------------------------------------------------------------------

    def execute(
        self,
        chain: ToolChain | ToolChainPlan,
        *,
        parameters: dict[str, Any] | None = None,
    ) -> ToolChainResult:
        """Execute a tool chain or plan.

        Deterministic and fail-closed. Never raises.

        Args:
            chain: The :class:`ToolChain` or :class:`ToolChainPlan` to
                execute.
            parameters: Optional shared parameters merged into each step's
                own parameters (step parameters take precedence).

        Returns:
            A :class:`ToolChainResult`. Failed results always carry a
            descriptive error message.
        """
        start: float = time.perf_counter()

        # --- Fail-closed: malformed input (not a recognised chain type) ---
        if not isinstance(chain, (ToolChain, ToolChainPlan)):
            return self._failed_result(
                "unknown",
                "Input is not a ToolChain or ToolChainPlan.",
                start,
                {"reason": "malformed_input"},
            )

        chain_id: str = self._chain_id(chain)
        strategy: str = self._strategy(chain)
        steps: tuple[ToolStep, ...] = self._steps(chain)
        shared_params: dict[str, Any] = parameters or {}

        # --- Fail-closed: no invoker ---
        if self._invoker is None:
            return self._failed_result(
                chain_id,
                "No tool invoker configured.",
                start,
                {"reason": "no_invoker"},
            )

        # --- Fail-closed: unsupported strategy ---
        if strategy not in SUPPORTED_STRATEGIES:
            return self._failed_result(
                chain_id,
                f"Unsupported execution strategy: '{strategy}'.",
                start,
                {"reason": "unsupported_strategy", "strategy": strategy},
            )

        # --- Fail-closed: malformed input (no steps) ---
        if not steps:
            return self._failed_result(
                chain_id,
                "Chain has no steps to execute.",
                start,
                {"reason": "empty_chain"},
            )

        # --- Fail-closed: step limit exceeded ---
        if self._policy.has_step_limit and len(steps) > self._policy.max_steps:
            return self._failed_result(
                chain_id,
                (
                    f"Chain has {len(steps)} steps but policy limits "
                    f"to {self._policy.max_steps}."
                ),
                start,
                {"reason": "step_limit_exceeded"},
            )

        # --- Dispatch by strategy ---
        if strategy == "sequential":
            return self._execute_sequential(chain_id, steps, shared_params, start)
        if strategy == "fallback":
            return self._execute_fallback(chain_id, steps, shared_params, start)
        if strategy == "conditional":
            return self._execute_conditional(chain_id, steps, shared_params, start)
        if strategy == "parallel":
            return self._execute_parallel(chain_id, steps, shared_params, start)

        # Should not reach here due to earlier check, but fail-closed.
        return self._failed_result(
            chain_id,
            f"Unsupported execution strategy: '{strategy}'.",
            start,
            {"reason": "unsupported_strategy", "strategy": strategy},
        )

    def _execute_conditional(
        self,
        chain_id: str,
        steps: tuple[ToolStep, ...],
        shared_params: dict[str, Any],
        start: float,
    ) -> ToolChainResult:
        """Execute a conditional chain deterministically.

        Phase 22 Batch 1 semantics (docs/PHASE_22_DESIGN.md §3):

          * Steps are walked in declared order. A step's declared
            prerequisites (``step.depends_on``) must have executed
            successfully first (verified by an ordered walk of the chain).
          * A step with an express condition (``ToolStep.parameters``,
            see :mod:`atlas.toolchain.conditional`) is eligible only when
            the condition evaluates to ``True`` against the most recently
            produced step output.
          * A step that is not eligible is recorded as a skipped step
            (``success=False``, ``skipped=True``) and the chain continues.
          * An unsupported/malformed condition fails safely: the step is
            recorded as skipped with reason ``unsupported_condition`` and is
            never executed (no arbitrary logic runs).
          * A failed prerequisite produces a deterministic chain failure
            BEFORE any dependent step executes — a dependent step's tool is
            never invoked.
          * ``RiskPolicy.max_steps`` and ``max_execution_time_ms`` apply
            exactly as they do to sequential execution.
          * Stable result ordering is preserved.

        The executor is the ONLY decision point. No planner, router,
        dispatcher, or selection engine is involved. Purely synchronous and
        deterministic. Never raises.
        """
        step_results: list[dict[str, Any]] = []
        completed: set[str] = set()
        last_output: dict[str, Any] | None = None
        executed_count: int = 0
        index: int = 0

        while index < len(steps):
            # --- Time limit check (applies across the whole run) ---
            if self._policy.has_time_limit:
                elapsed_ms = (time.perf_counter() - start) * 1000
                if elapsed_ms > self._policy.max_execution_time_ms:
                    return ToolChainResult(
                        chain_id=chain_id,
                        success=False,
                        step_results=tuple(step_results),
                        error=(
                            f"Execution time limit exceeded: "
                            f"{elapsed_ms:.1f}ms > "
                            f"{self._policy.max_execution_time_ms}ms."
                        ),
                        execution_time_ms=elapsed_ms,
                        metadata={"reason": "time_limit_exceeded", "strategy": "conditional"},
                    )

            step = steps[index]

            # --- Failed prerequisite: dependent step never executes ---
            missing: list[str] = [
                dep for dep in step.depends_on if dep not in completed
            ]
            if missing:
                elapsed_ms = (time.perf_counter() - start) * 1000
                return ToolChainResult(
                    chain_id=chain_id,
                    success=False,
                    step_results=tuple(step_results),
                    error=(
                        f"Step '{step.step_id}' has unsatisfied prerequisite "
                        f"steps: {', '.join(sorted(missing))}."
                    ),
                    execution_time_ms=elapsed_ms,
                    metadata={
                        "reason": "unsatisfied_prerequisite",
                        "strategy": "conditional",
                        "step_id": step.step_id,
                    },
                )

            # --- Condition check (deterministic predicate) ---
            condition = extract_condition(step.parameters)
            if condition is not None:
                if not is_supported_condition(condition):
                    step_results.append(
                        self._skipped_step_result(
                            step,
                            skipped_reason="unsupported_condition",
                        )
                    )
                    index += 1
                    continue
                eligible = evaluate_condition(condition, last_output or {})
                if not eligible:
                    step_results.append(
                        self._skipped_step_result(
                            step,
                            skipped_reason="condition_false",
                        )
                    )
                    index += 1
                    continue

            # --- Step limit check (counts real executions, not skips) ---
            if (
                self._policy.has_step_limit
                and executed_count >= self._policy.max_steps
            ):
                elapsed_ms = (time.perf_counter() - start) * 1000
                return ToolChainResult(
                    chain_id=chain_id,
                    success=False,
                    step_results=tuple(step_results),
                    error=(
                        f"Step limit reached: {self._policy.max_steps} "
                        f"executed steps."
                    ),
                    execution_time_ms=elapsed_ms,
                    metadata={"reason": "step_limit_exceeded", "strategy": "conditional"},
                )

            result = self._execute_step(step, shared_params)
            step_results.append(result)
            executed_count += 1
            completed.add(step.step_id)
            if result.get("success", False):
                last_output = dict(result.get("output", {}) or {})

            if not result.get("success", False):
                elapsed_ms = (time.perf_counter() - start) * 1000
                return ToolChainResult(
                    chain_id=chain_id,
                    success=False,
                    step_results=tuple(step_results),
                    error=(
                        f"Step '{step.step_id}' (tool '{step.tool_name}') "
                        f"failed: {result.get('error', 'unknown error')}."
                    ),
                    execution_time_ms=elapsed_ms,
                    metadata={"reason": "step_failed", "strategy": "conditional"},
                )

            index += 1

        elapsed_ms = (time.perf_counter() - start) * 1000
        return ToolChainResult(
            chain_id=chain_id,
            success=True,
            step_results=tuple(step_results),
            execution_time_ms=elapsed_ms,
            metadata={"strategy": "conditional", "step_count": len(step_results)},
        )

    @staticmethod
    def _skipped_step_result(
        step: ToolStep,
        skipped_reason: str,
    ) -> dict[str, Any]:
        """Record a deterministically-skipped conditional step.

        Skipped steps keep ``success=False`` so ``step_results`` ordering
        and the result/error structure stay stable, and carry ``skipped``
        metadata so consumers can distinguish a skip from an error.
        """
        return {
            "step_id": step.step_id,
            "tool_name": step.tool_name,
            "success": False,
            "output": {},
            "error": "",
            "execution_time_ms": 0.0,
            "skipped": True,
            "skipped_reason": skipped_reason,
        }

    # ------------------------------------------------------------------
    # Strategy implementations
    # ------------------------------------------------------------------

    def _execute_sequential(
        self,
        chain_id: str,
        steps: tuple[ToolStep, ...],
        shared_params: dict[str, Any],
        start: float,
    ) -> ToolChainResult:
        """Execute steps in order; all must succeed."""
        step_results: list[dict[str, Any]] = []

        for step in steps:
            # Time limit check
            if self._policy.has_time_limit:
                elapsed_ms = (time.perf_counter() - start) * 1000
                if elapsed_ms > self._policy.max_execution_time_ms:
                    return ToolChainResult(
                        chain_id=chain_id,
                        success=False,
                        step_results=tuple(step_results),
                        error=(
                            f"Execution time limit exceeded: "
                            f"{elapsed_ms:.1f}ms > "
                            f"{self._policy.max_execution_time_ms}ms."
                        ),
                        execution_time_ms=elapsed_ms,
                        metadata={"reason": "time_limit_exceeded"},
                    )

            result = self._execute_step(step, shared_params)
            step_results.append(result)

            if not result.get("success", False):
                elapsed_ms = (time.perf_counter() - start) * 1000
                return ToolChainResult(
                    chain_id=chain_id,
                    success=False,
                    step_results=tuple(step_results),
                    error=(
                        f"Step '{step.step_id}' (tool '{step.tool_name}') "
                        f"failed: {result.get('error', 'unknown error')}."
                    ),
                    execution_time_ms=elapsed_ms,
                    metadata={"reason": "step_failed", "strategy": "sequential"},
                )

        elapsed_ms = (time.perf_counter() - start) * 1000
        return ToolChainResult(
            chain_id=chain_id,
            success=True,
            step_results=tuple(step_results),
            execution_time_ms=elapsed_ms,
            metadata={"strategy": "sequential", "step_count": len(steps)},
        )

    def _execute_fallback(
        self,
        chain_id: str,
        steps: tuple[ToolStep, ...],
        shared_params: dict[str, Any],
        start: float,
    ) -> ToolChainResult:
        """Try steps in order; first success wins."""
        step_results: list[dict[str, Any]] = []

        for step in steps:
            # Time limit check
            if self._policy.has_time_limit:
                elapsed_ms = (time.perf_counter() - start) * 1000
                if elapsed_ms > self._policy.max_execution_time_ms:
                    return ToolChainResult(
                        chain_id=chain_id,
                        success=False,
                        step_results=tuple(step_results),
                        error=(
                            f"Execution time limit exceeded: "
                            f"{elapsed_ms:.1f}ms > "
                            f"{self._policy.max_execution_time_ms}ms."
                        ),
                        execution_time_ms=elapsed_ms,
                        metadata={"reason": "time_limit_exceeded"},
                    )

            result = self._execute_step(step, shared_params)
            step_results.append(result)

            if result.get("success", False):
                elapsed_ms = (time.perf_counter() - start) * 1000
                return ToolChainResult(
                    chain_id=chain_id,
                    success=True,
                    step_results=tuple(step_results),
                    execution_time_ms=elapsed_ms,
                    metadata={
                        "strategy": "fallback",
                        "winning_step": step.step_id,
                        "winning_tool": step.tool_name,
                        "attempts": len(step_results),
                    },
                )

        elapsed_ms = (time.perf_counter() - start) * 1000
        return ToolChainResult(
            chain_id=chain_id,
            success=False,
            step_results=tuple(step_results),
            error="All fallback steps failed.",
            execution_time_ms=elapsed_ms,
            metadata={"reason": "all_failed", "strategy": "fallback"},
        )

    def _execute_parallel(
        self,
        chain_id: str,
        steps: tuple[ToolStep, ...],
        shared_params: dict[str, Any],
        start: float,
    ) -> ToolChainResult:
        """Execute a parallel chain as a deterministic sequential fan-out.

        Phase 22 Batch 2 semantics (docs/PHASE_22_DESIGN.md §4/§5 and the
        project's "No threading. No async. No subprocess." invariant):

          * Fan-out — steps are walked once in declared order. Every
            eligible step executes EXACTLY ONCE via :meth:`_execute_step`
            (which enforces the allow/deny policy). A step is ineligible
            only when a declared prerequisite (``step.depends_on``) has not
            completed successfully before its position in the walk; such a
            step is never invoked and is recorded in declared order as a
            skipped entry (``success=False``, ``skipped=True``, reason
            ``unsatisfied_prerequisite``). One failed step does NOT prevent
            later eligible siblings from executing — mirroring a parallel
            fan-out where all branches run. No threads, async, subprocess,
            or hidden concurrency: the fan-out is a plain synchronous loop.
          * Fan-in — executed step results and skipped entries are
            collected in declared step order (the tuple is a total
            function over the declared steps). If any step failed (tool
            failure, denied tool, invoker exception, malformed result),
            the overall ``ToolChainResult`` is a failure whose error
            surfaces the FIRST failing step's tool, id, and error; every
            sibling result — including successful siblings executed after
            the failure — is preserved. No failed invocation is converted
            into a success and no successful sibling result is discarded.
          * Failed prerequisites — a prerequisite step that itself failed
            is (like every failure) surfaced by the fan-in; the dependent
            step's tool is never invoked because the prerequisite never
            completed successfully.
          * Risk limits — the pre-flight ``max_steps`` check applies to
            the whole declared batch (identical to sequential/fallback/
            conditional); per-step eligibility is a boolean signature and
            skipped steps never consume the execution budget by
            construction. ``max_execution_time_ms`` is enforced as a
            whole-run cap every iteration, exactly like the other
            strategies.

        Deterministic: identical inputs produce identical step execution,
        identical result ordering, and identical overall success. The
        executor is the only decision point. Never raises. Purely
        synchronous.
        """
        step_results: list[dict[str, Any]] = []
        completed: set[str] = set()
        first_failure: tuple[ToolStep, dict[str, Any]] | None = None

        for step in steps:
            # --- Time limit check (applies across the whole run) ---
            if self._policy.has_time_limit:
                elapsed_ms = (time.perf_counter() - start) * 1000
                if elapsed_ms > self._policy.max_execution_time_ms:
                    return ToolChainResult(
                        chain_id=chain_id,
                        success=False,
                        step_results=tuple(step_results),
                        error=(
                            f"Execution time limit exceeded: "
                            f"{elapsed_ms:.1f}ms > "
                            f"{self._policy.max_execution_time_ms}ms."
                        ),
                        execution_time_ms=elapsed_ms,
                        metadata={"reason": "time_limit_exceeded", "strategy": "parallel"},
                    )

            # --- Unsatisfied prerequisite: never execute this step ---
            missing: list[str] = [
                dep for dep in step.depends_on if dep not in completed
            ]
            if missing:
                step_results.append(
                    self._skipped_step_result(
                        step,
                        skipped_reason="unsatisfied_prerequisite",
                    )
                )
                continue

            result = self._execute_step(step, shared_params)
            step_results.append(result)

            if result.get("success", False):
                completed.add(step.step_id)
            elif first_failure is None:
                # Record the first (deterministic: lowest declared position)
                # failing step; the walk continues so every eligible sibling
                # still fans out exactly once.
                first_failure = (step, result)

        if first_failure is not None:
            failing_step, failing_result = first_failure
            elapsed_ms = (time.perf_counter() - start) * 1000
            return ToolChainResult(
                chain_id=chain_id,
                success=False,
                step_results=tuple(step_results),
                error=(
                    f"Step '{failing_step.step_id}' (tool "
                    f"'{failing_step.tool_name}') failed: "
                    f"{failing_result.get('error', 'unknown error')}."
                ),
                execution_time_ms=elapsed_ms,
                metadata={
                    "reason": "step_failed",
                    "strategy": "parallel",
                    "step_id": failing_step.step_id,
                },
            )

        elapsed_ms = (time.perf_counter() - start) * 1000
        return ToolChainResult(
            chain_id=chain_id,
            success=True,
            step_results=tuple(step_results),
            execution_time_ms=elapsed_ms,
            metadata={"strategy": "parallel", "step_count": len(step_results)},
        )

    # ------------------------------------------------------------------
    # Step execution
    # ------------------------------------------------------------------

    def _execute_step(
        self,
        step: ToolStep,
        shared_params: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute a single step via the invoker.

        Fail-closed: any error (denied tool, unknown tool, handler
        exception, malformed parameters) produces a failed step result dict.
        """
        tool_name: str = step.tool_name

        # --- Risk policy check ---
        if not self._policy.is_allowed(tool_name):
            return {
                "step_id": step.step_id,
                "tool_name": tool_name,
                "success": False,
                "output": {},
                "error": f"Tool '{tool_name}' denied by risk policy.",
                "execution_time_ms": 0.0,
                "denied": True,
            }

        # --- Merge parameters (step overrides shared) ---
        merged_params: dict[str, Any] = {**shared_params, **step.parameters}

        # --- Invoke tool ---
        invoker = self._invoker
        if invoker is None:  # defensive — checked in execute()
            return {
                "step_id": step.step_id,
                "tool_name": tool_name,
                "success": False,
                "output": {},
                "error": "No tool invoker configured.",
                "execution_time_ms": 0.0,
            }

        step_start: float = time.perf_counter()
        try:
            result = invoker.execute_by_name(tool_name, merged_params)
        except Exception as exc:
            elapsed_ms = (time.perf_counter() - step_start) * 1000
            return {
                "step_id": step.step_id,
                "tool_name": tool_name,
                "success": False,
                "output": {},
                "error": f"Tool invoker raised: {exc}",
                "execution_time_ms": elapsed_ms,
                "exception": type(exc).__name__,
            }

        elapsed_ms = (time.perf_counter() - step_start) * 1000
        return self._normalize_result(step, result, elapsed_ms)

    # ------------------------------------------------------------------
    # Result normalization
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_result(
        step: ToolStep,
        result: Any,
        elapsed_ms: float,
    ) -> dict[str, Any]:
        """Normalize an invoker result into a step result dict.

        Handles tool-result-like objects (with ``success``, ``output``,
        ``error``, ``execution_time_ms`` attributes) and plain dicts.
        Fail-closed: unexpected result types produce a failed step.
        """
        if result is None:
            return {
                "step_id": step.step_id,
                "tool_name": step.tool_name,
                "success": False,
                "output": {},
                "error": "Tool returned None.",
                "execution_time_ms": elapsed_ms,
            }

        # Handle dict-like results
        if isinstance(result, dict):
            return {
                "step_id": step.step_id,
                "tool_name": step.tool_name,
                "success": bool(result.get("success", False)),
                "output": dict(result.get("output", {})),
                "error": str(result.get("error", "")),
                "execution_time_ms": float(
                    result.get("execution_time_ms", elapsed_ms)
                ),
            }

        # Handle object-like results (duck typing)
        success: bool = bool(getattr(result, "success", False))
        output_attr: Any = getattr(result, "output", {})
        output: dict[str, Any] = dict(output_attr) if output_attr else {}
        error: str = str(getattr(result, "error", "") or "")
        result_time: float = float(
            getattr(result, "execution_time_ms", elapsed_ms) or elapsed_ms
        )

        return {
            "step_id": step.step_id,
            "tool_name": step.tool_name,
            "success": success,
            "output": output,
            "error": error,
            "execution_time_ms": result_time,
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _chain_id(chain: ToolChain | ToolChainPlan) -> str:
        """Extract the chain/plan id."""
        if isinstance(chain, ToolChain):
            return chain.chain_id
        return chain.plan_id

    @staticmethod
    def _strategy(chain: ToolChain | ToolChainPlan) -> str:
        """Extract the strategy, normalized to lowercase."""
        return (getattr(chain, "strategy", "sequential") or "sequential").lower()

    @staticmethod
    def _steps(chain: ToolChain | ToolChainPlan) -> tuple[ToolStep, ...]:
        """Extract the steps tuple."""
        steps: Any = getattr(chain, "steps", None)
        if steps is None:
            return ()
        return tuple(steps)

    @staticmethod
    def _failed_result(
        chain_id: str,
        error: str,
        start: float,
        metadata: dict[str, Any] | None = None,
    ) -> ToolChainResult:
        """Build a failed result with timing."""
        elapsed_ms = (time.perf_counter() - start) * 1000
        return ToolChainResult(
            chain_id=chain_id,
            success=False,
            step_results=(),
            error=error,
            execution_time_ms=elapsed_ms,
            metadata=metadata or {},
        )
