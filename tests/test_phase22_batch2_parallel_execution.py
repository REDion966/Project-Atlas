"""Phase 22 Batch 2 — PARALLEL tool-chain execution.

Covers the Phase 22 design §4/§5 and Batch 2 acceptance criteria:

  - ``parallel`` is now a supported strategy (no longer fail-closed).
  - Deterministic sequential fan-out: every eligible tool executes exactly
    once, in declared order.
  - Deterministic fan-in: ``step_results`` is a total, order-stable tuple
    over the declared steps (executed results and deterministic skipped
    entries), regardless of evaluation order.
  - ``depends_on`` is respected: a step with an unsatisfied prerequisite is
    never invoked and is recorded as a skipped entry in declared order.
  - Partial failure: one failing step surfaces explicitly while every
    sibling result — including successful siblings executed after the
    failure — is preserved. No failed invocation becomes a success.
  - Existing risk limits still apply (``RiskPolicy.max_steps``,
    ``max_execution_time_ms``, allow/deny policy).
  - No threading / async / subprocess / hidden concurrency.
  - Existing sequential / fallback / conditional behaviour stays green.
"""

from dataclasses import dataclass, field
from typing import Any

from atlas.toolchain.executor import (
    RiskPolicy,
    SUPPORTED_STRATEGIES,
    ToolChainExecutor,
    UNSUPPORTED_STRATEGIES,
)
from atlas.toolchain.models import ToolChain, ToolChainPlan, ToolChainResult, ToolStep


# ---------------------------------------------------------------------------
# Fakes (mirroring tests/test_toolchain_executor.py conventions)
# ---------------------------------------------------------------------------


@dataclass
class FakeToolResult:
    tool_name: str = ""
    success: bool = False
    output: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    execution_time_ms: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


class FakeToolInvoker:
    """Deterministic fake implementing the ToolInvoker protocol."""

    def __init__(self, results: dict[str, Any] | None = None) -> None:
        self._results: dict[str, Any] = results or {}
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def execute_by_name(
        self,
        name: str,
        params: dict[str, Any] | None = None,
    ) -> Any:
        self.calls.append((name, params or {}))
        result = self._results.get(name)
        if result is None:
            return FakeToolResult(
                tool_name=name,
                success=False,
                error=f"Tool '{name}' is not registered.",
            )
        if callable(result):
            return result(params or {})
        return result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _step(step_id: str, tool_name: str, **params: Any) -> ToolStep:
    return ToolStep(step_id=step_id, tool_name=tool_name, parameters=params)


def _dep_step(step_id: str, tool_name: str, *deps: str) -> ToolStep:
    return ToolStep(step_id=step_id, tool_name=tool_name, depends_on=deps)


def _chain(steps: list[ToolStep], strategy: str = "parallel") -> ToolChain:
    return ToolChain(
        chain_id="test-chain",
        goal="test goal",
        steps=tuple(steps),
        strategy=strategy,
    )


def _ok(tool_name: str, output: dict[str, Any] | None = None) -> FakeToolResult:
    return FakeToolResult(tool_name=tool_name, success=True, output=output or {})


# ---------------------------------------------------------------------------
# Supported-strategy surface
# ---------------------------------------------------------------------------


class TestSupportedStrategy:
    def test_parallel_is_supported(self):
        assert "parallel" in SUPPORTED_STRATEGIES

    def test_parallel_no_longer_unsupported(self):
        assert "parallel" not in UNSUPPORTED_STRATEGIES


# ---------------------------------------------------------------------------
# Fan-out / fan-in
# ---------------------------------------------------------------------------


class TestFanOut:
    def test_every_eligible_tool_executes_exactly_once_in_declared_order(self):
        """Fan-out invokes each eligible tool exactly once, in order."""
        invoker = FakeToolInvoker(
            results={f"tool_{i}": _ok(f"tool_{i}") for i in range(4)}
        )
        executor = ToolChainExecutor(invoker)
        chain = _chain(
            [
                _step("step:0000", "tool_0"),
                _step("step:0001", "tool_1"),
                _step("step:0002", "tool_2"),
                _step("step:0003", "tool_3"),
            ]
        )
        result = executor.execute(chain)
        assert result.success
        assert result.metadata["strategy"] == "parallel"
        assert [call[0] for call in invoker.calls] == [
            "tool_0",
            "tool_1",
            "tool_2",
            "tool_3",
        ]
        # Exactly once per tool.
        assert len(invoker.calls) == 4

    def test_single_step_success(self):
        invoker = FakeToolInvoker(results={"tool_a": _ok("tool_a")})
        executor = ToolChainExecutor(invoker)
        chain = _chain([_step("step:0000", "tool_a")])
        result = executor.execute(chain)
        assert result.success
        assert len(result.step_results) == 1


class TestFanIn:
    def test_step_results_preserve_declared_order(self):
        """step_results is returned in declared step order."""
        invoker = FakeToolInvoker(
            results={
                "tool_a": _ok("tool_a", {"run": 1}),
                "tool_b": _ok("tool_b", {"run": 2}),
                "tool_c": _ok("tool_c", {"run": 3}),
            }
        )
        executor = ToolChainExecutor(invoker)
        chain = _chain(
            [
                _step("step:0000", "tool_a"),
                _step("step:0001", "tool_b"),
                _step("step:0002", "tool_c"),
            ]
        )
        result = executor.execute(chain)
        assert result.success
        assert [r["step_id"] for r in result.step_results] == [
            "step:0000",
            "step:0001",
            "step:0002",
        ]
        # Execution order matches declared order AND result order (stable).
        assert [call[0] for call in invoker.calls] == [
            "tool_a",
            "tool_b",
            "tool_c",
        ]

    def test_step_results_is_total_over_declared_steps(self):
        """Every declared step has an entry (executed or skipped)."""
        invoker = FakeToolInvoker(
            results={"tool_a": _ok("tool_a"), "tool_b": _ok("tool_b")}
        )
        executor = ToolChainExecutor(invoker)
        chain = _chain(
            [
                _step("step:0000", "tool_a"),
                _dep_step("step:0001", "tool_b", "step:nonexistent"),
            ]
        )
        result = executor.execute(chain)
        assert result.success  # skipped dependants are not failures
        assert len(result.step_results) == 2
        assert result.step_results[1]["skipped"] is True


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------


class TestDependencies:
    def test_satisfied_prerequisite_executes(self):
        invoker = FakeToolInvoker(
            results={"tool_a": _ok("tool_a"), "tool_b": _ok("tool_b")}
        )
        executor = ToolChainExecutor(invoker)
        chain = _chain(
            [
                _step("step:0000", "tool_a"),
                _dep_step("step:0001", "tool_b", "step:0000"),
            ]
        )
        result = executor.execute(chain)
        assert result.success
        assert [call[0] for call in invoker.calls] == ["tool_a", "tool_b"]

    def test_unsatisfied_prerequisite_is_never_invoked(self):
        """A step depending on a non-existent/unsatisfied prerequisite is
        skipped deterministically and its tool never runs."""
        invoker = FakeToolInvoker(results={"tool_a": _ok("tool_a")})
        executor = ToolChainExecutor(invoker)
        chain = _chain(
            [
                _dep_step("step:0000", "tool_a", "step:nope"),
                ToolStep(
                    step_id="step:0001",
                    tool_name="tool_b",
                    parameters={},
                    depends_on=("step:0000",),
                ),
            ]
        )
        result = executor.execute(chain)
        assert result.success
        assert len(result.step_results) == 2
        assert result.step_results[0]["skipped"] is True
        assert (
            result.step_results[0]["skipped_reason"]
            == "unsatisfied_prerequisite"
        )
        # Neither tool was invoked.
        assert invoker.calls == []

    def test_failed_prerequisite_never_invokes_dependent(self):
        """A prerequisite whose execution failed does not satisfy the
        dependency, so the dependent step's tool is never invoked."""
        invoker = FakeToolInvoker(
            results={
                "tool_a": FakeToolResult(
                    tool_name="tool_a", success=False, error="boom"
                ),
                "tool_b": _ok("tool_b"),
            }
        )
        executor = ToolChainExecutor(invoker)
        chain = _chain(
            [
                _step("step:0000", "tool_a"),
                _dep_step("step:0001", "tool_b", "step:0000"),
            ]
        )
        result = executor.execute(chain)
        assert not result.success
        assert result.metadata["reason"] == "step_failed"
        assert "step:0000" in result.error
        # tool_b never invoked.
        assert [call[0] for call in invoker.calls] == ["tool_a"]


# ---------------------------------------------------------------------------
# Partial failure
# ---------------------------------------------------------------------------


class TestPartialFailure:
    def test_failure_surfaces_and_preserves_all_sibling_results(self):
        """One failing step fails the overall result while every sibling
        result (including successful siblings after the failure) is kept."""
        invoker = FakeToolInvoker(
            results={
                "tool_a": _ok("tool_a", {"v": 1}),
                "tool_b": FakeToolResult(
                    tool_name="tool_b", success=False, error="boom"
                ),
                "tool_c": _ok("tool_c", {"v": 3}),
            }
        )
        executor = ToolChainExecutor(invoker)
        chain = _chain(
            [
                _step("step:0000", "tool_a"),
                _step("step:0001", "tool_b"),
                _step("step:0002", "tool_c"),
            ]
        )
        result = executor.execute(chain)
        assert not result.success
        assert result.metadata["reason"] == "step_failed"
        assert result.metadata["step_id"] == "step:0001"
        assert "step:0001" in result.error
        assert "tool_b" in result.error
        # Fan-out still executed every eligible sibling exactly once.
        assert [call[0] for call in invoker.calls] == [
            "tool_a",
            "tool_b",
            "tool_c",
        ]
        # All sibling results preserved in declared order; the failed step
        # is NOT converted into a success.
        assert [r["step_id"] for r in result.step_results] == [
            "step:0000",
            "step:0001",
            "step:0002",
        ]
        assert result.step_results[0]["success"] is True
        assert result.step_results[1]["success"] is False
        assert result.step_results[2]["success"] is True

    def test_first_failure_is_deterministic(self):
        """When several steps fail, the surfaced error is the first
        (lowest declared position) failure."""
        invoker = FakeToolInvoker(
            results={
                "tool_a": FakeToolResult(
                    tool_name="tool_a", success=False, error="first-fail"
                ),
                "tool_b": FakeToolResult(
                    tool_name="tool_b", success=False, error="second-fail"
                ),
            }
        )
        executor = ToolChainExecutor(invoker)
        chain = _chain(
            [
                _step("step:0000", "tool_a"),
                _step("step:0001", "tool_b"),
            ]
        )
        result = executor.execute(chain)
        assert not result.success
        assert result.metadata["step_id"] == "step:0000"
        assert "first-fail" in result.error

    def test_no_invoker_fails_closed(self):
        executor = ToolChainExecutor()
        chain = _chain([_step("step:0000", "tool_a")])
        result = executor.execute(chain)
        assert not result.success
        assert result.metadata["reason"] == "no_invoker"

    def test_invoker_exception_preserves_sibling_results(self):
        """A raising invocation is a failed step, not a crash; siblings
        still run and the overall result is a structured failure."""

        class SelectiveRaisingInvoker:
            def __init__(self) -> None:
                self.calls: list[tuple[str, dict[str, Any]]] = []

            def execute_by_name(
                self,
                name: str,
                params: dict[str, Any] | None = None,
            ) -> Any:
                self.calls.append((name, params or {}))
                if name == "tool_b":
                    raise RuntimeError("invoker broken")
                return FakeToolResult(
                    tool_name=name, success=True, output={f"ran_{name}": True}
                )

        invoker = SelectiveRaisingInvoker()
        executor = ToolChainExecutor(invoker)
        chain = _chain(
            [
                _step("step:0000", "tool_a"),
                _step("step:0001", "tool_b"),
                _step("step:0002", "tool_c"),
            ]
        )
        result = executor.execute(chain)
        assert isinstance(result, ToolChainResult)
        assert not result.success
        assert result.metadata["step_id"] == "step:0001"
        assert len(result.step_results) == 3
        assert result.step_results[0]["success"] is True
        assert result.step_results[2]["success"] is True


# ---------------------------------------------------------------------------
# Risk limits
# ---------------------------------------------------------------------------


class TestRiskLimits:
    def test_step_limit_still_applies(self):
        """max_steps is the same pre-flight declared-chain guard as every
        other strategy."""
        invoker = FakeToolInvoker(
            results={f"tool_{i}": _ok(f"tool_{i}") for i in range(5)}
        )
        policy = RiskPolicy(max_steps=2)
        executor = ToolChainExecutor(invoker, policy)
        chain = _chain([_step(f"step:{i:04d}", f"tool_{i}") for i in range(5)])
        result = executor.execute(chain)
        assert not result.success
        assert result.metadata["reason"] == "step_limit_exceeded"

    def test_time_limit_still_applies(self):
        invoker = FakeToolInvoker(results={"tool_a": _ok("tool_a")})
        policy = RiskPolicy(max_execution_time_ms=0.000001)
        executor = ToolChainExecutor(invoker, policy)
        chain = _chain([_step("step:0000", "tool_a")])
        result = executor.execute(chain)
        assert not result.success
        assert result.metadata["reason"] == "time_limit_exceeded"

    def test_deny_policy_still_applies(self):
        """A denied tool is a failed step and never reaches the invoker;
        sibling tools still fan out."""
        invoker = FakeToolInvoker(
            results={"tool_a": _ok("tool_a"), "tool_b": _ok("tool_b")}
        )
        policy = RiskPolicy(deny_list=frozenset({"tool_a"}))
        executor = ToolChainExecutor(invoker, policy)
        chain = _chain(
            [
                _step("step:0000", "tool_a"),
                _step("step:0001", "tool_b"),
            ]
        )
        result = executor.execute(chain)
        assert not result.success
        assert result.metadata["step_id"] == "step:0000"
        assert result.step_results[0].get("denied") is True
        # tool_b still fanned out; tool_a never reached the invoker.
        assert [call[0] for call in invoker.calls] == ["tool_b"]

    def test_allow_policy_still_applies(self):
        invoker = FakeToolInvoker(results={"tool_b": _ok("tool_b")})
        policy = RiskPolicy(allow_list=frozenset({"tool_b"}))
        executor = ToolChainExecutor(invoker, policy)
        chain = _chain(
            [
                _step("step:0000", "tool_a"),
                _step("step:0001", "tool_b"),
            ]
        )
        result = executor.execute(chain)
        assert not result.success
        assert result.step_results[0].get("denied") is True
        assert [call[0] for call in invoker.calls] == ["tool_b"]


# ---------------------------------------------------------------------------
# Determinism / no-concurrency / regression
# ---------------------------------------------------------------------------


class TestDeterminism:
    def test_same_parallel_chain_same_result(self):
        invoker = FakeToolInvoker(
            results={
                "tool_a": _ok("tool_a", {"v": 1}),
                "tool_b": FakeToolResult(
                    tool_name="tool_b", success=False, error="boom"
                ),
                "tool_c": _ok("tool_c", {"v": 3}),
            }
        )
        executor = ToolChainExecutor(invoker)
        chain = _chain(
            [
                _step("step:0000", "tool_a"),
                _step("step:0001", "tool_b"),
                _step("step:0002", "tool_c"),
            ]
        )
        r1 = executor.execute(chain)
        r2 = executor.execute(chain)

        assert r1.success == r2.success
        assert [s["step_id"] for s in r1.step_results] == [
            s["step_id"] for s in r2.step_results
        ]
        for s1, s2 in zip(r1.step_results, r2.step_results):
            assert s1["tool_name"] == s2["tool_name"]
            assert s1["success"] == s2["success"]
            assert s1["output"] == s2["output"]
            assert s1.get("skipped") == s2.get("skipped")
        assert r1.error == r2.error


class TestNoConcurrency:
    def test_no_concurrency_primitives_in_executor_module(self):
        """The executor module must remain free of threads/async/subprocess."""
        from atlas.toolchain import executor as executor_module

        with open(executor_module.__file__, encoding="utf-8") as handle:
            source = handle.read()

        for forbidden in (
            "import threading",
            "import asyncio",
            "import subprocess",
            "Thread(",
            "create_task",
            "concurrent.futures",
            "multiprocessing",
        ):
            assert forbidden not in source

    def test_never_raises_on_parallel_chain(self):
        invoker = FakeToolInvoker()
        executor = ToolChainExecutor(invoker)
        chain = _chain([_step("step:0000", "tool_a")])
        # Must not raise even though tool_a is not registered.
        outcome = executor.execute(chain)
        assert isinstance(outcome, ToolChainResult)
        assert not outcome.success


class TestRegression:
    def test_sequential_fallback_conditional_still_green(self):
        """Spot-checks that the other strategies are untouched by Batch 2."""

        # Sequential: first failure stops the chain.
        seq_invoker = FakeToolInvoker(
            results={
                "tool_a": FakeToolResult(
                    tool_name="tool_a", success=False, error="fail"
                ),
                "tool_b": _ok("tool_b"),
            }
        )
        seq_executor = ToolChainExecutor(seq_invoker)
        seq_chain = ToolChain(
            chain_id="seq",
            goal="g",
            steps=(_step("step:0000", "tool_a"), _step("step:0001", "tool_b")),
            strategy="sequential",
        )
        seq_result = seq_executor.execute(seq_chain)
        assert not seq_result.success
        assert len(seq_result.step_results) == 1

        # Fallback: first success wins.
        fb_invoker = FakeToolInvoker(
            results={
                "tool_a": FakeToolResult(
                    tool_name="tool_a", success=False, error="fail"
                ),
                "tool_b": _ok("tool_b"),
            }
        )
        fb_executor = ToolChainExecutor(fb_invoker)
        fb_chain = ToolChain(
            chain_id="fb",
            goal="g",
            steps=(_step("step:0000", "tool_a"), _step("step:0001", "tool_b")),
            strategy="fallback",
        )
        fb_result = fb_executor.execute(fb_chain)
        assert fb_result.success
        assert fb_result.metadata["winning_tool"] == "tool_b"

        # Conditional: false condition still skips deterministically.
        invoker = FakeToolInvoker(
            results={
                "tool_a": _ok("tool_a", {"status": "fail"}),
                "tool_b": _ok("tool_b"),
            }
        )
        executor = ToolChainExecutor(invoker)
        cond_chain = ToolChain(
            chain_id="cond",
            goal="g",
            steps=(
                _step("step:0000", "tool_a"),
                ToolStep(
                    step_id="step:0001",
                    tool_name="tool_b",
                    parameters={"when": {"key": "status", "equals": "ok"}},
                ),
            ),
            strategy="conditional",
        )
        result = executor.execute(cond_chain)
        assert result.success
        assert [call[0] for call in invoker.calls] == ["tool_a"]
        assert result.step_results[1]["skipped_reason"] == "condition_false"


class TestPlanExecution:
    def test_execute_parallel_plan(self):
        invoker = FakeToolInvoker(
            results={
                "tool_a": _ok("tool_a"),
                "tool_b": _ok("tool_b"),
            }
        )
        executor = ToolChainExecutor(invoker)
        plan = ToolChainPlan(
            plan_id="test-plan",
            goal="g",
            steps=(_step("step:0000", "tool_a"), _step("step:0001", "tool_b")),
            strategy="parallel",
        )
        result = executor.execute(plan)
        assert result.success
        assert result.chain_id == "test-plan"
        assert result.metadata["strategy"] == "parallel"
        assert [call[0] for call in invoker.calls] == ["tool_a", "tool_b"]
