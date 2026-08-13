"""Phase 22 Batch 1 — CONDITIONAL tool-chain execution.

Covers the Phase 22 design §3 / §8 Batch 1 acceptance criteria:

  - ``conditional`` is now a supported strategy (no longer fail-closed).
  - Deterministic predicate evaluation over prior step ``output`` dicts
    (``when`` / ``step_when`` condition specs).
  - True condition executes the eligible step; false condition skips it
    deterministically.
  - Dependency/prior-output handling via ``ToolStep.depends_on``.
  - Failed prerequisite produces a deterministic chain failure.
  - Stable result ordering (skips keep their declared position).
  - ``RiskPolicy.max_steps`` / ``max_execution_time_ms`` still apply.
  - No threading / async / subprocess behaviour.
  - Existing sequential + fallback behaviour remains green (spot checks).
  - Unsupported/invalid conditional input fails safely (no tool execution).
"""

from dataclasses import dataclass, field
from typing import Any

from atlas.toolchain.conditional import (
    evaluate_condition,
    extract_condition,
    is_supported_condition,
)
from atlas.toolchain.executor import (
    RiskPolicy,
    SUPPORTED_STRATEGIES,
    ToolChainExecutor,
    UNSUPPORTED_STRATEGIES,
)
from atlas.toolchain.models import ToolChain, ToolChainResult, ToolStep


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


def _chain(steps: list[ToolStep], strategy: str = "conditional") -> ToolChain:
    return ToolChain(
        chain_id="test-chain",
        goal="test goal",
        steps=tuple(steps),
        strategy=strategy,
    )


def _ok(tool_name: str, output: dict[str, Any] | None = None) -> FakeToolResult:
    return FakeToolResult(
        tool_name=tool_name, success=True, output=output or {}
    )


def _run_sequential_and_fallback_spot_checks() -> None:
    """Regression spot-check: sequential + fallback semantics are preserved.

    Helper used by the Batch 1 acceptance regression test. Keeps the
    conditional executor's own tests focused while proving the existing
    strategies did not change behaviour.
    """
    invoker = FakeToolInvoker(
        results={
            "tool_a": FakeToolResult(
                tool_name="tool_a", success=False, error="fail"
            ),
            "tool_b": _ok("tool_b"),
        }
    )
    executor = ToolChainExecutor(invoker)

    # Sequential: first failure stops the chain.
    seq_chain = ToolChain(
        chain_id="seq",
        goal="g",
        steps=(_step("step:0000", "tool_a"), _step("step:0001", "tool_b")),
        strategy="sequential",
    )
    seq_result = executor.execute(seq_chain)
    assert not seq_result.success
    assert len(seq_result.step_results) == 1

    # Fallback: first success wins.
    fb_chain = ToolChain(
        chain_id="fb",
        goal="g",
        steps=(_step("step:0000", "tool_a"), _step("step:0001", "tool_b")),
        strategy="fallback",
    )
    fb_result = executor.execute(fb_chain)
    assert fb_result.success
    assert fb_result.metadata["winning_tool"] == "tool_b"


# ---------------------------------------------------------------------------
# Supported-strategy surface
# ---------------------------------------------------------------------------


class TestSupportedStrategy:
    def test_conditional_is_supported(self):
        assert "conditional" in SUPPORTED_STRATEGIES

    def test_conditional_no_longer_unsupported(self):
        assert "conditional" not in UNSUPPORTED_STRATEGIES

    def test_parallel_is_supported_by_batch_2(self):
        """parallel became a supported strategy in Phase 22 Batch 2.

        Batch 1 acceptance only required that conditional no longer fails
        closed; the parallel surface is owned by Batch 2 and therefore no
        longer fails closed either.
        """
        invoker = FakeToolInvoker(results={"tool_a": _ok("tool_a")})
        executor = ToolChainExecutor(invoker)
        chain = _chain([_step("step:0000", "tool_a")], strategy="parallel")
        result = executor.execute(chain)
        assert result.success
        assert result.metadata["strategy"] == "parallel"

    def test_conditional_chain_succeeds_without_conditions(self):
        """Unconditional steps under the conditional strategy behave like an
        ordered walk and succeed."""
        invoker = FakeToolInvoker(
            results={
                "tool_a": _ok("tool_a", {"stage": "done"}),
                "tool_b": _ok("tool_b"),
            }
        )
        executor = ToolChainExecutor(invoker)
        chain = _chain(
            [_step("step:0000", "tool_a"), _step("step:0001", "tool_b")]
        )
        result = executor.execute(chain)
        assert result.success
        assert result.metadata["strategy"] == "conditional"
        assert len(result.step_results) == 2
        assert [c[0] for c in invoker.calls] == ["tool_a", "tool_b"]


# ---------------------------------------------------------------------------
# Deterministic predicate evaluation
# ---------------------------------------------------------------------------


class TestPredicateEvaluation:
    def test_equals_true(self):
        assert (
            evaluate_condition({"key": "status", "equals": "ok"}, {"status": "ok"})
            is True
        )

    def test_equals_false(self):
        assert (
            evaluate_condition({"key": "status", "equals": "ok"}, {"status": "fail"})
            is False
        )

    def test_truthy_true(self):
        assert (
            evaluate_condition({"key": "found", "truthy": True}, {"found": 1})
            is True
        )

    def test_truthy_false(self):
        assert (
            evaluate_condition({"key": "found", "truthy": True}, {"found": None})
            is False
        )

    def test_missing_key_false(self):
        assert (
            evaluate_condition({"key": "missing", "equals": "x"}, {"other": "x"})
            is False
        )

    def test_none_condition_is_true(self):
        assert evaluate_condition(None, {}) is True

    def test_unsupported_condition_false(self):
        assert (
            evaluate_condition({"key": "a", "contains": "x"}, {"a": "xyz"})
            is False
        )

    def test_non_dict_output_false(self):
        assert (
            evaluate_condition({"key": "a", "truthy": True}, None)  # type: ignore[arg-type]
            is False
        )

    def test_extract_condition_primary_key(self):
        assert extract_condition({"when": {"key": "a", "equals": 1}}) == {
            "key": "a",
            "equals": 1,
        }

    def test_extract_condition_legacy_key(self):
        assert extract_condition({"step_when": {"key": "a", "equals": 1}}) == {
            "key": "a",
            "equals": 1,
        }

    def test_extract_condition_absent(self):
        assert extract_condition({"x": 1}) is None

    def test_is_supported_condition(self):
        assert is_supported_condition({"key": "a", "equals": 1})
        assert is_supported_condition({"key": "a", "truthy": True})
        assert not is_supported_condition({"key": "a", "contains": "x"})
        assert not is_supported_condition({"without_key": True})
        assert not is_supported_condition("not a dict")  # type: ignore[arg-type]
        # An absent condition is always eligible.
        assert is_supported_condition(None) is True


# ---------------------------------------------------------------------------
# Conditional execution semantics
# ---------------------------------------------------------------------------


class TestConditionalExecution:
    def test_true_condition_executes_step(self):
        invoker = FakeToolInvoker(
            results={
                "tool_a": _ok("tool_a", {"status": "ok"}),
                "tool_b": _ok("tool_b"),
            }
        )
        executor = ToolChainExecutor(invoker)
        chain = _chain(
            [
                _step("step:0000", "tool_a"),
                _step(
                    "step:0001",
                    "tool_b",
                    when={"key": "status", "equals": "ok"},
                ),
            ]
        )
        result = executor.execute(chain)
        assert result.success
        assert [c[0] for c in invoker.calls] == ["tool_a", "tool_b"]
        assert len(result.step_results) == 2

    def test_false_condition_skips_step_deterministically(self):
        invoker = FakeToolInvoker(
            results={
                "tool_a": _ok("tool_a", {"status": "fail"}),
                "tool_b": _ok("tool_b"),
            }
        )
        executor = ToolChainExecutor(invoker)
        chain = _chain(
            [
                _step("step:0000", "tool_a"),
                _step(
                    "step:0001",
                    "tool_b",
                    when={"key": "status", "equals": "ok"},
                ),
            ]
        )
        result = executor.execute(chain)
        assert result.success
        # tool_b was NOT executed
        assert [c[0] for c in invoker.calls] == ["tool_a"]
        assert len(result.step_results) == 2
        skipped = result.step_results[1]
        assert skipped["skipped"] is True
        assert skipped["skipped_reason"] == "condition_false"
        assert skipped["success"] is False

    def test_legacy_step_when_key(self):
        invoker = FakeToolInvoker(
            results={
                "tool_a": _ok("tool_a", {"ok": True}),
                "tool_b": _ok("tool_b"),
            }
        )
        executor = ToolChainExecutor(invoker)
        chain = _chain(
            [
                _step("step:0000", "tool_a"),
                _step("step:0001", "tool_b", step_when={"key": "ok", "truthy": True}),
            ]
        )
        result = executor.execute(chain)
        assert result.success
        assert [c[0] for c in invoker.calls] == ["tool_a", "tool_b"]

    def test_condition_only_sees_last_successful_output(self):
        """Conditions evaluate against the most recent successful step
        output, not an earlier one."""
        invoker = FakeToolInvoker(
            results={
                "tool_a": _ok("tool_a", {"stage": "first"}),
                "tool_b": _ok("tool_b", {"stage": "second"}),
                "tool_c": _ok("tool_c"),
            }
        )
        executor = ToolChainExecutor(invoker)
        chain = _chain(
            [
                _step("step:0000", "tool_a"),
                _step("step:0001", "tool_b"),
                _step(
                    "step:0002",
                    "tool_c",
                    when={"key": "stage", "equals": "second"},
                ),
            ]
        )
        result = executor.execute(chain)
        assert result.success
        assert [c[0] for c in invoker.calls] == ["tool_a", "tool_b", "tool_c"]

    def test_skipped_step_keeps_ordering(self):
        """A skipped step keeps its declared position in step_results."""
        invoker = FakeToolInvoker(
            results={"tool_a": _ok("tool_a", {"v": 0}), "tool_b": _ok("tool_b")}
        )
        executor = ToolChainExecutor(invoker)
        chain = _chain(
            [
                _step("step:0000", "tool_a"),
                _step("step:0001", "tool_b", when={"key": "v", "equals": 99}),
            ]
        )
        result = executor.execute(chain)
        assert result.success
        assert [r["step_id"] for r in result.step_results] == [
            "step:0000",
            "step:0001",
        ]

    def test_unsupported_condition_skips_safely(self):
        """A malformed/unsupported condition never executes the tool."""
        invoker = FakeToolInvoker(
            results={
                "tool_a": _ok("tool_a", {"status": "ok"}),
                "tool_b": _ok("tool_b"),
            }
        )
        executor = ToolChainExecutor(invoker)
        chain = _chain(
            [
                _step("step:0000", "tool_a"),
                _step("step:0001", "tool_b", when={"key": "status", "contains": "x"}),
            ]
        )
        result = executor.execute(chain)
        assert result.success
        assert [c[0] for c in invoker.calls] == ["tool_a"]
        skipped = result.step_results[1]
        assert skipped["skipped"] is True
        assert skipped["skipped_reason"] == "unsupported_condition"


# ---------------------------------------------------------------------------
# Dependency / prior-output handling
# ---------------------------------------------------------------------------


class TestDependencies:
    def test_satisfied_prerequisite_executes(self):
        invoker = FakeToolInvoker(
            results={
                "tool_a": _ok("tool_a", {"ok": True}),
                "tool_b": _ok("tool_b"),
            }
        )
        executor = ToolChainExecutor(invoker)
        chain = _chain(
            [
                _step("step:0000", "tool_a"),
                ToolStep(
                    step_id="step:0001",
                    tool_name="tool_b",
                    depends_on=("step:0000",),
                ),
            ]
        )
        result = executor.execute(chain)
        assert result.success
        assert [c[0] for c in invoker.calls] == ["tool_a", "tool_b"]

    def test_failed_prerequisite_produces_chain_failure(self):
        """A dependent step must never execute when its prerequisite is
        unsatisfied; the chain fails deterministically."""
        invoker = FakeToolInvoker(
            results={"tool_b": _ok("tool_b")}
        )
        executor = ToolChainExecutor(invoker)
        chain = _chain(
            [
                _step("step:0000", "tool_a"),
                ToolStep(
                    step_id="step:0001",
                    tool_name="tool_b",
                    depends_on=("step:0000",),
                ),
            ]
        )
        # step:0000 fails (not registered), so step:0001 must not run.
        result = executor.execute(chain)
        assert not result.success
        assert result.metadata["reason"] in (
            "step_failed",
            "unsatisfied_prerequisite",
        )
        # tool_b never invoked
        assert all(c[0] != "tool_b" for c in invoker.calls)

    def test_unsatisfied_prerequisite_mid_chain(self):
        """A prerequisite that does not exist anywhere fails closed."""
        invoker = FakeToolInvoker(results={"tool_a": _ok("tool_a")})
        executor = ToolChainExecutor(invoker)
        chain = _chain(
            [
                ToolStep(
                    step_id="step:0000",
                    tool_name="tool_a",
                    depends_on=("step:nonexistent",),
                )
            ]
        )
        result = executor.execute(chain)
        assert not result.success
        assert result.metadata["reason"] == "unsatisfied_prerequisite"

    def test_prerequisite_satisfied_by_earlier_step(self):
        """A step can depend on an earlier successful step by ID."""
        invoker = FakeToolInvoker(
            results={
                "tool_a": _ok("tool_a"),
                "tool_b": _ok("tool_b", {"ready": True}),
                "tool_c": _ok("tool_c"),
            }
        )
        executor = ToolChainExecutor(invoker)
        chain = _chain(
            [
                _step("step:0000", "tool_a"),
                _step("step:0001", "tool_b"),
                ToolStep(
                    step_id="step:0002",
                    tool_name="tool_c",
                    depends_on=("step:0001",),
                ),
            ]
        )
        result = executor.execute(chain)
        assert result.success
        assert [c[0] for c in invoker.calls] == ["tool_a", "tool_b", "tool_c"]


# ---------------------------------------------------------------------------
# Failure behavior
# ---------------------------------------------------------------------------


class TestFailureBehavior:
    def test_failed_step_breaks_chain(self):
        invoker = FakeToolInvoker(
            results={
                "tool_a": _ok("tool_a"),
                "tool_b": FakeToolResult(
                    tool_name="tool_b", success=False, error="boom"
                ),
                "tool_c": _ok("tool_c"),
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
        assert "step:0001" in result.error
        # tool_c never runs after the failure
        assert [c[0] for c in invoker.calls] == ["tool_a", "tool_b"]


# ---------------------------------------------------------------------------
# Risk limits
# ---------------------------------------------------------------------------


class TestRiskLimits:
    def test_step_limit_still_applies(self):
        invoker = FakeToolInvoker(
            results={f"tool_{i}": _ok(f"tool_{i}") for i in range(5)}
        )
        policy = RiskPolicy(max_steps=2)
        executor = ToolChainExecutor(invoker, policy)
        chain = _chain(
            [_step(f"step:{i:04d}", f"tool_{i}") for i in range(5)]
        )
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

    def test_risk_policy_deny_still_applies(self):
        invoker = FakeToolInvoker(results={"tool_a": _ok("tool_a")})
        policy = RiskPolicy(deny_list=frozenset({"tool_a"}))
        executor = ToolChainExecutor(invoker, policy)
        chain = _chain([_step("step:0000", "tool_a")])
        result = executor.execute(chain)
        assert not result.success
        assert result.step_results[0].get("denied") is True


# ---------------------------------------------------------------------------
# Determinism / regression / concurrency
# ---------------------------------------------------------------------------


class TestDeterminism:
    def test_same_conditional_chain_same_result(self):
        invoker = FakeToolInvoker(
            results={
                "tool_a": _ok("tool_a", {"status": "fail"}),
                "tool_b": _ok("tool_b"),
            }
        )
        executor = ToolChainExecutor(invoker)
        chain = _chain(
            [
                _step("step:0000", "tool_a"),
                _step("step:0001", "tool_b", when={"key": "status", "equals": "ok"}),
            ]
        )
        r1 = executor.execute(chain)
        r2 = executor.execute(chain)
        assert r1.success == r2.success
        # Compare deterministic content only (execution_time_ms varies).
        assert len(r1.step_results) == len(r2.step_results)
        for s1, s2 in zip(r1.step_results, r2.step_results):
            assert s1["step_id"] == s2["step_id"]
            assert s1["tool_name"] == s2["tool_name"]
            assert s1["success"] == s2["success"]
            assert s1["output"] == s2["output"]
            assert s1.get("skipped") == s2.get("skipped")
            assert s1.get("skipped_reason") == s2.get("skipped_reason")


class TestRegressionAndNoConcurrency:
    def test_sequential_and_fallback_semantics_preserved(self):
        """Existing sequential + fallback behaviour remains green."""
        _run_sequential_and_fallback_spot_checks()

    def test_no_concurrency_primitives_in_executor_module(self):
        """The executor module must remain free of threading/async/subprocess."""
        from atlas.toolchain import executor as executor_module

        source = ""
        with open(executor_module.__file__, encoding="utf-8") as handle:
            source = handle.read()

        for forbidden in (
            "import threading",
            "import asyncio",
            "import subprocess",
            "Thread(",
            "create_task",
        ):
            assert forbidden not in source

    def test_never_raises_on_conditional_chain(self):
        invoker = FakeToolInvoker()
        executor = ToolChainExecutor(invoker)
        chain = _chain([_step("step:0000", "tool_a")])
        # Must not raise even though tool_a is not registered.
        outcome = executor.execute(chain)
        assert isinstance(outcome, ToolChainResult)
