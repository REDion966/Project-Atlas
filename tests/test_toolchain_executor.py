"""Phase 18.5 — ToolChainExecutor tests."""

from dataclasses import dataclass, field
from typing import Any

import pytest

from atlas.toolchain.executor import (
    RiskPolicy,
    SUPPORTED_STRATEGIES,
    ToolChainExecutor,
    ToolInvoker,
    UNSUPPORTED_STRATEGIES,
)
from atlas.toolchain.models import (
    ToolChain,
    ToolChainPlan,
    ToolChainResult,
    ToolStep,
)


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


@dataclass
class FakeToolResult:
    """Minimal tool-result-like object (duck-typed)."""

    tool_name: str = ""
    success: bool = False
    output: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    execution_time_ms: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


class _NoDefault:
    """Sentinel for 'no default result configured'."""


_NO_DEFAULT = _NoDefault()


class FakeToolInvoker:
    """Fake tool invoker implementing the ToolInvoker protocol."""

    def __init__(
        self,
        results: dict[str, Any] | None = None,
        default_result: Any = _NO_DEFAULT,
    ) -> None:
        self._results: dict[str, Any] = results or {}
        self._default: Any = default_result
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def execute_by_name(
        self,
        name: str,
        params: dict[str, Any] | None = None,
    ) -> Any:
        self.calls.append((name, params or {}))
        if name in self._results:
            result = self._results[name]
            if callable(result):
                return result(params or {})
            return result
        if self._default is not _NO_DEFAULT:
            return self._default
        # Unknown tool — return a failed result
        return FakeToolResult(
            tool_name=name,
            success=False,
            error=f"Tool '{name}' is not registered.",
        )


class RaisingInvoker:
    """Invoker that always raises."""

    def execute_by_name(
        self,
        name: str,
        params: dict[str, Any] | None = None,
    ) -> Any:
        raise RuntimeError("invoker broken")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _step(step_id: str, tool_name: str, **params: Any) -> ToolStep:
    """Build a ToolStep with optional parameters."""
    return ToolStep(
        step_id=step_id,
        tool_name=tool_name,
        parameters=params,
    )


def _chain(
    steps: list[ToolStep],
    strategy: str = "sequential",
    chain_id: str = "test-chain",
) -> ToolChain:
    """Build a ToolChain."""
    return ToolChain(
        chain_id=chain_id,
        goal="test goal",
        steps=tuple(steps),
        strategy=strategy,
    )


def _plan(
    steps: list[ToolStep],
    strategy: str = "sequential",
    plan_id: str = "test-plan",
) -> ToolChainPlan:
    """Build a ToolChainPlan."""
    return ToolChainPlan(
        plan_id=plan_id,
        goal="test goal",
        steps=tuple(steps),
        strategy=strategy,
    )


# ---------------------------------------------------------------------------
# Protocol tests
# ---------------------------------------------------------------------------


class TestProtocol:
    def test_fake_invoker_satisfies_protocol(self):
        invoker = FakeToolInvoker()
        assert isinstance(invoker, ToolInvoker)

    def test_real_tool_executor_satisfies_protocol(self):
        from atlas.tools.executor import ToolExecutor
        from atlas.tools.registry import ToolRegistry

        executor = ToolExecutor(ToolRegistry())
        assert isinstance(executor, ToolInvoker)


# ---------------------------------------------------------------------------
# Construction tests
# ---------------------------------------------------------------------------


class TestConstruction:
    def test_no_invoker(self):
        executor = ToolChainExecutor()
        assert not executor.has_invoker

    def test_with_invoker(self):
        executor = ToolChainExecutor(FakeToolInvoker())
        assert executor.has_invoker

    def test_default_risk_policy(self):
        executor = ToolChainExecutor()
        policy = executor.risk_policy
        assert isinstance(policy, RiskPolicy)
        assert policy.allow_list == frozenset()
        assert policy.deny_list == frozenset()

    def test_custom_risk_policy(self):
        policy = RiskPolicy(allow_list=frozenset({"tool_a"}))
        executor = ToolChainExecutor(risk_policy=policy)
        assert executor.risk_policy is policy


# ---------------------------------------------------------------------------
# RiskPolicy tests
# ---------------------------------------------------------------------------


class TestRiskPolicy:
    def test_permissive_policy_allows_all(self):
        policy = RiskPolicy()
        assert policy.is_allowed("any_tool")

    def test_allow_list_permits_listed(self):
        policy = RiskPolicy(allow_list=frozenset({"tool_a", "tool_b"}))
        assert policy.is_allowed("tool_a")
        assert policy.is_allowed("tool_b")

    def test_allow_list_denies_unlisted(self):
        policy = RiskPolicy(allow_list=frozenset({"tool_a"}))
        assert not policy.is_allowed("tool_c")

    def test_deny_list_denies_listed(self):
        policy = RiskPolicy(deny_list=frozenset({"bad_tool"}))
        assert not policy.is_allowed("bad_tool")

    def test_deny_list_allows_unlisted(self):
        policy = RiskPolicy(deny_list=frozenset({"bad_tool"}))
        assert policy.is_allowed("good_tool")

    def test_deny_wins_over_allow(self):
        """Fail-closed: when a tool is in both lists, it is denied."""
        policy = RiskPolicy(
            allow_list=frozenset({"tool_a"}),
            deny_list=frozenset({"tool_a"}),
        )
        assert not policy.is_allowed("tool_a")

    def test_empty_deny_list_allows_all(self):
        policy = RiskPolicy(deny_list=frozenset())
        assert policy.is_allowed("anything")

    def test_has_step_limit(self):
        assert RiskPolicy(max_steps=5).has_step_limit
        assert not RiskPolicy(max_steps=0).has_step_limit

    def test_has_time_limit(self):
        assert RiskPolicy(max_execution_time_ms=1000.0).has_time_limit
        assert not RiskPolicy(max_execution_time_ms=0.0).has_time_limit


# ---------------------------------------------------------------------------
# Sequential execution tests
# ---------------------------------------------------------------------------


class TestSequentialExecution:
    def test_successful_sequential(self):
        invoker = FakeToolInvoker(
            results={
                "tool_a": FakeToolResult(tool_name="tool_a", success=True),
                "tool_b": FakeToolResult(tool_name="tool_b", success=True),
            }
        )
        executor = ToolChainExecutor(invoker)
        chain = _chain(
            [_step("step:0000", "tool_a"), _step("step:0001", "tool_b")],
            strategy="sequential",
        )
        result = executor.execute(chain)

        assert result.success
        assert result.chain_id == "test-chain"
        assert len(result.step_results) == 2
        assert result.metadata["strategy"] == "sequential"

    def test_sequential_stops_on_first_failure(self):
        invoker = FakeToolInvoker(
            results={
                "tool_a": FakeToolResult(
                    tool_name="tool_a", success=False, error="boom"
                ),
                "tool_b": FakeToolResult(tool_name="tool_b", success=True),
            }
        )
        executor = ToolChainExecutor(invoker)
        chain = _chain(
            [_step("step:0000", "tool_a"), _step("step:0001", "tool_b")],
            strategy="sequential",
        )
        result = executor.execute(chain)

        assert not result.success
        assert len(result.step_results) == 1
        assert "step:0000" in result.error
        assert "tool_a" in result.error
        # tool_b should not have been called
        assert len(invoker.calls) == 1

    def test_sequential_single_step_success(self):
        invoker = FakeToolInvoker(
            results={"tool_a": FakeToolResult(tool_name="tool_a", success=True)}
        )
        executor = ToolChainExecutor(invoker)
        chain = _chain([_step("step:0000", "tool_a")], strategy="sequential")
        result = executor.execute(chain)

        assert result.success
        assert len(result.step_results) == 1

    def test_sequential_preserves_step_order(self):
        invoker = FakeToolInvoker(
            results={
                f"tool_{i}": FakeToolResult(
                    tool_name=f"tool_{i}", success=True
                )
                for i in range(3)
            }
        )
        executor = ToolChainExecutor(invoker)
        chain = _chain(
            [
                _step("step:0000", "tool_0"),
                _step("step:0001", "tool_1"),
                _step("step:0002", "tool_2"),
            ],
            strategy="sequential",
        )
        result = executor.execute(chain)

        assert result.success
        called_names = [call[0] for call in invoker.calls]
        assert called_names == ["tool_0", "tool_1", "tool_2"]


# ---------------------------------------------------------------------------
# Fallback execution tests
# ---------------------------------------------------------------------------


class TestFallbackExecution:
    def test_fallback_first_success_wins(self):
        invoker = FakeToolInvoker(
            results={
                "tool_a": FakeToolResult(
                    tool_name="tool_a", success=False, error="fail"
                ),
                "tool_b": FakeToolResult(tool_name="tool_b", success=True),
                "tool_c": FakeToolResult(tool_name="tool_c", success=True),
            }
        )
        executor = ToolChainExecutor(invoker)
        chain = _chain(
            [
                _step("step:0000", "tool_a"),
                _step("step:0001", "tool_b"),
                _step("step:0002", "tool_c"),
            ],
            strategy="fallback",
        )
        result = executor.execute(chain)

        assert result.success
        assert result.metadata["winning_step"] == "step:0001"
        assert result.metadata["winning_tool"] == "tool_b"
        assert result.metadata["attempts"] == 2
        # tool_c should not have been called
        assert len(invoker.calls) == 2

    def test_fallback_all_fail(self):
        invoker = FakeToolInvoker(
            results={
                "tool_a": FakeToolResult(
                    tool_name="tool_a", success=False, error="fail"
                ),
                "tool_b": FakeToolResult(
                    tool_name="tool_b", success=False, error="fail"
                ),
            }
        )
        executor = ToolChainExecutor(invoker)
        chain = _chain(
            [_step("step:0000", "tool_a"), _step("step:0001", "tool_b")],
            strategy="fallback",
        )
        result = executor.execute(chain)

        assert not result.success
        assert "All fallback steps failed." in result.error
        assert len(result.step_results) == 2

    def test_fallback_first_tool_succeeds(self):
        invoker = FakeToolInvoker(
            results={
                "tool_a": FakeToolResult(tool_name="tool_a", success=True),
                "tool_b": FakeToolResult(tool_name="tool_b", success=True),
            }
        )
        executor = ToolChainExecutor(invoker)
        chain = _chain(
            [_step("step:0000", "tool_a"), _step("step:0001", "tool_b")],
            strategy="fallback",
        )
        result = executor.execute(chain)

        assert result.success
        assert result.metadata["winning_tool"] == "tool_a"
        assert result.metadata["attempts"] == 1


# ---------------------------------------------------------------------------
# Parallel execution tests
# ---------------------------------------------------------------------------


class TestParallelExecution:
    def test_parallel_executes_all_tools_in_declared_order(self):
        invoker = FakeToolInvoker(
            results={
                "tool_a": FakeToolResult(tool_name="tool_a", success=True),
                "tool_b": FakeToolResult(tool_name="tool_b", success=True),
            }
        )
        executor = ToolChainExecutor(invoker)
        chain = _chain(
            [_step("step:0000", "tool_a"), _step("step:0001", "tool_b")],
            strategy="parallel",
        )
        result = executor.execute(chain)

        assert result.success
        assert result.metadata["strategy"] == "parallel"
        assert len(result.step_results) == 2
        # Fan-out invokes every eligible tool exactly once, in declared order.
        assert [call[0] for call in invoker.calls] == ["tool_a", "tool_b"]

    def test_parallel_single_step_success(self):
        invoker = FakeToolInvoker(
            results={"tool_a": FakeToolResult(tool_name="tool_a", success=True)}
        )
        executor = ToolChainExecutor(invoker)
        chain = _chain(
            [_step("step:0000", "tool_a")],
            strategy="parallel",
        )
        result = executor.execute(chain)

        assert result.success
        assert len(result.step_results) == 1

    def test_parallel_never_raises_on_unknown_tools(self):
        invoker = FakeToolInvoker()
        executor = ToolChainExecutor(invoker)
        chain = _chain(
            [_step("step:0000", "tool_a")],
            strategy="parallel",
        )
        # Must not raise even though tool_a is not registered.
        result = executor.execute(chain)
        assert isinstance(result, ToolChainResult)
        assert not result.success

    def test_conditional_strategy_is_supported(self):
        """Phase 22 Batch 1: conditional is no longer a fail-closed strategy."""
        invoker = FakeToolInvoker(
            results={"tool_a": FakeToolResult(tool_name="tool_a", success=True)}
        )
        executor = ToolChainExecutor(invoker)
        chain = _chain(
            [_step("step:0000", "tool_a")],
            strategy="conditional",
        )
        result = executor.execute(chain)
        assert result.success
        assert result.metadata["strategy"] == "conditional"


# ---------------------------------------------------------------------------
# Unknown tool tests
# ---------------------------------------------------------------------------


class TestUnknownTool:
    def test_unknown_tool_returns_failed_step(self):
        invoker = FakeToolInvoker()  # no results configured
        executor = ToolChainExecutor(invoker)
        chain = _chain([_step("step:0000", "nonexistent")])
        result = executor.execute(chain)

        assert not result.success
        assert len(result.step_results) == 1
        assert not result.step_results[0]["success"]

    def test_unknown_tool_never_raises(self):
        invoker = FakeToolInvoker()
        executor = ToolChainExecutor(invoker)
        chain = _chain([_step("step:0000", "nonexistent")])
        # Must not raise
        result = executor.execute(chain)
        assert isinstance(result, ToolChainResult)

    def test_unknown_tool_in_fallback(self):
        invoker = FakeToolInvoker(
            results={
                "tool_b": FakeToolResult(tool_name="tool_b", success=True),
            }
        )
        executor = ToolChainExecutor(invoker)
        chain = _chain(
            [_step("step:0000", "unknown"), _step("step:0001", "tool_b")],
            strategy="fallback",
        )
        result = executor.execute(chain)

        assert result.success
        assert result.metadata["winning_tool"] == "tool_b"


# ---------------------------------------------------------------------------
# Allow list tests
# ---------------------------------------------------------------------------


class TestAllowList:
    def test_allow_list_permits_listed_tools(self):
        invoker = FakeToolInvoker(
            results={
                "tool_a": FakeToolResult(tool_name="tool_a", success=True),
            }
        )
        policy = RiskPolicy(allow_list=frozenset({"tool_a"}))
        executor = ToolChainExecutor(invoker, policy)
        chain = _chain([_step("step:0000", "tool_a")])
        result = executor.execute(chain)

        assert result.success

    def test_allow_list_denies_unlisted_tools(self):
        invoker = FakeToolInvoker(
            results={
                "tool_b": FakeToolResult(tool_name="tool_b", success=True),
            }
        )
        policy = RiskPolicy(allow_list=frozenset({"tool_a"}))
        executor = ToolChainExecutor(invoker, policy)
        chain = _chain([_step("step:0000", "tool_b")])
        result = executor.execute(chain)

        assert not result.success
        assert "denied" in result.error.lower() or "denied" in result.step_results[0].get("error", "").lower()

    def test_allow_list_with_multiple_tools(self):
        invoker = FakeToolInvoker(
            results={
                "tool_a": FakeToolResult(tool_name="tool_a", success=True),
                "tool_b": FakeToolResult(tool_name="tool_b", success=True),
            }
        )
        policy = RiskPolicy(allow_list=frozenset({"tool_a", "tool_b"}))
        executor = ToolChainExecutor(invoker, policy)
        chain = _chain(
            [_step("step:0000", "tool_a"), _step("step:0001", "tool_b")],
            strategy="sequential",
        )
        result = executor.execute(chain)

        assert result.success


# ---------------------------------------------------------------------------
# Deny list tests
# ---------------------------------------------------------------------------


class TestDenyList:
    def test_deny_list_blocks_tool(self):
        invoker = FakeToolInvoker(
            results={
                "tool_a": FakeToolResult(tool_name="tool_a", success=True),
            }
        )
        policy = RiskPolicy(deny_list=frozenset({"tool_a"}))
        executor = ToolChainExecutor(invoker, policy)
        chain = _chain([_step("step:0000", "tool_a")])
        result = executor.execute(chain)

        assert not result.success
        assert result.step_results[0].get("denied") is True

    def test_deny_list_allows_others(self):
        invoker = FakeToolInvoker(
            results={
                "tool_a": FakeToolResult(tool_name="tool_a", success=True),
                "tool_b": FakeToolResult(tool_name="tool_b", success=True),
            }
        )
        policy = RiskPolicy(deny_list=frozenset({"tool_a"}))
        executor = ToolChainExecutor(invoker, policy)
        chain = _chain([_step("step:0000", "tool_b")])
        result = executor.execute(chain)

        assert result.success

    def test_deny_wins_over_allow(self):
        invoker = FakeToolInvoker(
            results={
                "tool_a": FakeToolResult(tool_name="tool_a", success=True),
            }
        )
        policy = RiskPolicy(
            allow_list=frozenset({"tool_a"}),
            deny_list=frozenset({"tool_a"}),
        )
        executor = ToolChainExecutor(invoker, policy)
        chain = _chain([_step("step:0000", "tool_a")])
        result = executor.execute(chain)

        assert not result.success
        assert result.step_results[0].get("denied") is True


# ---------------------------------------------------------------------------
# Fail-closed tests
# ---------------------------------------------------------------------------


class TestFailClosed:
    def test_no_invoker_fails_closed(self):
        executor = ToolChainExecutor()
        chain = _chain([_step("step:0000", "tool_a")])
        result = executor.execute(chain)

        assert not result.success
        assert result.metadata["reason"] == "no_invoker"

    def test_no_invoker_never_raises(self):
        executor = ToolChainExecutor()
        chain = _chain([_step("step:0000", "tool_a")])
        result = executor.execute(chain)
        assert isinstance(result, ToolChainResult)

    def test_invoker_exception_fails_closed(self):
        invoker = RaisingInvoker()
        executor = ToolChainExecutor(invoker)
        chain = _chain([_step("step:0000", "tool_a")])
        result = executor.execute(chain)

        assert not result.success
        assert "invoker raised" in result.error.lower() or "invoker raised" in result.step_results[0].get("error", "").lower()

    def test_invoker_exception_never_raises(self):
        invoker = RaisingInvoker()
        executor = ToolChainExecutor(invoker)
        chain = _chain([_step("step:0000", "tool_a")])
        result = executor.execute(chain)
        assert isinstance(result, ToolChainResult)

    def test_none_result_fails_closed(self):
        invoker = FakeToolInvoker(default_result=None)
        executor = ToolChainExecutor(invoker)
        chain = _chain([_step("step:0000", "tool_a")])
        result = executor.execute(chain)

        assert not result.success
        assert "None" in result.step_results[0].get("error", "")

    def test_step_limit_exceeded_fails_closed(self):
        invoker = FakeToolInvoker(
            results={
                f"tool_{i}": FakeToolResult(
                    tool_name=f"tool_{i}", success=True
                )
                for i in range(5)
            }
        )
        policy = RiskPolicy(max_steps=2)
        executor = ToolChainExecutor(invoker, policy)
        chain = _chain(
            [_step(f"step:{i:04d}", f"tool_{i}") for i in range(5)]
        )
        result = executor.execute(chain)

        assert not result.success
        assert result.metadata["reason"] == "step_limit_exceeded"


# ---------------------------------------------------------------------------
# Malformed input tests
# ---------------------------------------------------------------------------


class TestMalformedInput:
    def test_none_input_fails_closed(self):
        executor = ToolChainExecutor(FakeToolInvoker())
        result = executor.execute(None)  # type: ignore[arg-type]
        assert not result.success
        assert result.metadata["reason"] == "malformed_input"

    def test_dict_input_fails_closed(self):
        executor = ToolChainExecutor(FakeToolInvoker())
        result = executor.execute({"steps": []})  # type: ignore[arg-type]
        assert not result.success
        assert result.metadata["reason"] == "malformed_input"

    def test_empty_steps_fails_closed(self):
        invoker = FakeToolInvoker()
        executor = ToolChainExecutor(invoker)
        chain = _chain([])
        result = executor.execute(chain)

        assert not result.success
        assert result.metadata["reason"] == "empty_chain"

    def test_empty_strategy_defaults_to_sequential(self):
        """A chain with empty strategy should be treated as sequential."""
        invoker = FakeToolInvoker(
            results={"tool_a": FakeToolResult(tool_name="tool_a", success=True)}
        )
        executor = ToolChainExecutor(invoker)
        chain = ToolChain(
            chain_id="test",
            goal="test",
            steps=(_step("step:0000", "tool_a"),),
            strategy="",
        )
        result = executor.execute(chain)
        assert result.success


# ---------------------------------------------------------------------------
# Determinism tests
# ---------------------------------------------------------------------------


class TestDeterminism:
    def test_same_chain_same_success(self):
        invoker = FakeToolInvoker(
            results={
                "tool_a": FakeToolResult(tool_name="tool_a", success=True),
                "tool_b": FakeToolResult(tool_name="tool_b", success=True),
            }
        )
        executor = ToolChainExecutor(invoker)
        chain = _chain(
            [_step("step:0000", "tool_a"), _step("step:0001", "tool_b")],
            strategy="sequential",
        )
        r1 = executor.execute(chain)
        r2 = executor.execute(chain)

        assert r1.success == r2.success
        assert len(r1.step_results) == len(r2.step_results)
        for s1, s2 in zip(r1.step_results, r2.step_results):
            assert s1["success"] == s2["success"]
            assert s1["tool_name"] == s2["tool_name"]

    def test_same_chain_same_failure(self):
        invoker = FakeToolInvoker(
            results={
                "tool_a": FakeToolResult(
                    tool_name="tool_a", success=False, error="fail"
                ),
            }
        )
        executor = ToolChainExecutor(invoker)
        chain = _chain([_step("step:0000", "tool_a")])
        r1 = executor.execute(chain)
        r2 = executor.execute(chain)

        assert r1.success == r2.success
        assert not r1.success
        assert r1.error == r2.error

    def test_deterministic_step_results_content(self):
        invoker = FakeToolInvoker(
            results={
                "tool_a": FakeToolResult(
                    tool_name="tool_a",
                    success=True,
                    output={"key": "value"},
                ),
            }
        )
        executor = ToolChainExecutor(invoker)
        chain = _chain([_step("step:0000", "tool_a")])
        r1 = executor.execute(chain)
        r2 = executor.execute(chain)

        assert r1.step_results[0]["output"] == r2.step_results[0]["output"]
        assert r1.step_results[0]["success"] == r2.step_results[0]["success"]


# ---------------------------------------------------------------------------
# Protocol injection tests
# ---------------------------------------------------------------------------


class TestProtocolInjection:
    def test_works_with_dict_returning_invoker(self):
        """The executor should handle dict results from the invoker."""

        class DictInvoker:
            def execute_by_name(self, name, params=None):
                return {
                    "tool_name": name,
                    "success": True,
                    "output": {"result": "ok"},
                    "error": "",
                    "execution_time_ms": 1.0,
                }

        executor = ToolChainExecutor(DictInvoker())
        chain = _chain([_step("step:0000", "tool_a")])
        result = executor.execute(chain)

        assert result.success
        assert result.step_results[0]["output"] == {"result": "ok"}

    def test_works_with_object_returning_invoker(self):
        """The executor should handle object results from the invoker."""

        class ObjectInvoker:
            def execute_by_name(self, name, params=None):
                return FakeToolResult(
                    tool_name=name, success=True, output={"data": 42}
                )

        executor = ToolChainExecutor(ObjectInvoker())
        chain = _chain([_step("step:0000", "tool_a")])
        result = executor.execute(chain)

        assert result.success
        assert result.step_results[0]["output"] == {"data": 42}

    def test_parameters_merged_into_step(self):
        captured: list[dict] = []

        class CapturingInvoker:
            def execute_by_name(self, name, params=None):
                captured.append(params or {})
                return FakeToolResult(tool_name=name, success=True)

        executor = ToolChainExecutor(CapturingInvoker())
        chain = _chain(
            [_step("step:0000", "tool_a", specific="val")],
        )
        executor.execute(chain, parameters={"shared": "ctx"})

        assert captured[0] == {"shared": "ctx", "specific": "val"}

    def test_step_parameters_override_shared(self):
        captured: list[dict] = []

        class CapturingInvoker:
            def execute_by_name(self, name, params=None):
                captured.append(params or {})
                return FakeToolResult(tool_name=name, success=True)

        executor = ToolChainExecutor(CapturingInvoker())
        chain = _chain(
            [_step("step:0000", "tool_a", shared="override")],
        )
        executor.execute(chain, parameters={"shared": "original"})

        assert captured[0]["shared"] == "override"


# ---------------------------------------------------------------------------
# ToolChainPlan execution tests
# ---------------------------------------------------------------------------


class TestPlanExecution:
    def test_execute_plan(self):
        invoker = FakeToolInvoker(
            results={
                "tool_a": FakeToolResult(tool_name="tool_a", success=True),
            }
        )
        executor = ToolChainExecutor(invoker)
        plan = _plan([_step("step:0000", "tool_a")])
        result = executor.execute(plan)

        assert result.success
        assert result.chain_id == "test-plan"

    def test_execute_plan_fallback(self):
        invoker = FakeToolInvoker(
            results={
                "tool_a": FakeToolResult(
                    tool_name="tool_a", success=False, error="fail"
                ),
                "tool_b": FakeToolResult(tool_name="tool_b", success=True),
            }
        )
        executor = ToolChainExecutor(invoker)
        plan = _plan(
            [_step("step:0000", "tool_a"), _step("step:0001", "tool_b")],
            strategy="fallback",
        )
        result = executor.execute(plan)

        assert result.success
        assert result.metadata["winning_tool"] == "tool_b"


# ---------------------------------------------------------------------------
# Strategy constants tests
# ---------------------------------------------------------------------------


class TestStrategyConstants:
    def test_supported_strategies_contains_sequential(self):
        assert "sequential" in SUPPORTED_STRATEGIES

    def test_supported_strategies_contains_fallback(self):
        assert "fallback" in SUPPORTED_STRATEGIES

    def test_supported_strategies_contains_parallel(self):
        """Phase 22 Batch 2: parallel is now a supported strategy."""
        assert "parallel" in SUPPORTED_STRATEGIES
        assert "parallel" not in UNSUPPORTED_STRATEGIES

    def test_supported_strategies_contains_conditional(self):
        """Phase 22 Batch 1: conditional is now a supported strategy."""
        assert "conditional" in SUPPORTED_STRATEGIES
        assert "conditional" not in UNSUPPORTED_STRATEGIES

    def test_supported_and_unsupported_disjoint(self):
        assert not (SUPPORTED_STRATEGIES & UNSUPPORTED_STRATEGIES)
