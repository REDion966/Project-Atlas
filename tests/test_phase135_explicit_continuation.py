"""Phase 13.5 — Explicit continuation across cycles: evidence contract.

Validation result: a cycle terminates and returns to the caller; the next cycle
is a NEW explicit invocation that loads prior state. Nothing self-calls, chains,
or schedules — ``next_cycle_allowed`` remains False, and the continuity module
is a pure projection.
"""

from __future__ import annotations

import inspect

from atlas.evolution.evolution_continuity import (
    EvolutionOpportunityState,
    MAX_EXPLICIT_CYCLES,
    bounded_multi_cycle_plan,
    continuation_view,
)
from atlas.evolution.evolution_memory import EvolutionMemory
from atlas.evolution.self_evolution import SelfEvolutionLoop, SelfEvolutionTerminal
from tests.phase13_support import run_cycle

_MODULE = "atlas/example/continuation_handlers.py"
_CAPABILITY = "example.continuation"


class TestPhase135ExplicitContinuation:
    def test_a_cycle_terminates_and_returns_to_the_caller(self, tmp_path):
        memory = EvolutionMemory()
        result = run_cycle(
            memory,
            tmp_path,
            subject="cap.first",
            capability=_CAPABILITY,
            module=_MODULE,
        )
        assert result.terminal is SelfEvolutionTerminal.ACTIVATED
        assert result.next_cycle_allowed is False

        # Nothing ran a second cycle: exactly one outcome record exists.
        outcomes = memory.get_records_by_type("evolution_outcome")
        assert len(outcomes) == 1

    def test_a_second_cycle_is_a_new_explicit_invocation(self, tmp_path):
        memory = EvolutionMemory()
        first = run_cycle(
            memory,
            tmp_path,
            subject="cap.a",
            capability=_CAPABILITY,
            module=_MODULE,
            promotion_authorized=False,
        )
        second = run_cycle(
            memory,
            tmp_path,
            subject="cap.b",
            capability="example.continuation_b",
            module="atlas/example/continuation_b_handlers.py",
            promotion_authorized=False,
        )
        assert first.cycle_id != second.cycle_id
        assert first.next_cycle_allowed is False
        assert second.next_cycle_allowed is False
        assert len(memory.get_records_by_type("evolution_outcome")) == 2

    def test_the_loop_never_calls_itself(self):
        source = inspect.getsource(SelfEvolutionLoop)
        # No recursive self-invocation anywhere in the bounded cycle.
        assert "self.run(" not in source
        assert "SelfEvolutionLoop().run" not in source

    def test_continuation_view_bounds_the_sequence_and_never_starts_it(self):
        view = continuation_view(None)
        plan = bounded_multi_cycle_plan(view, 99)
        assert plan.cycles_requested <= MAX_EXPLICIT_CYCLES
        assert plan.subjects == ()  # nothing READY without evidence
        assert "explicit invocations only" in plan.note
        # A descriptive plan only: it holds no callable and no scheduler.
        for attr in ("run", "start", "tick", "next"):
            assert not hasattr(plan, attr)

    def test_multi_cycle_plan_respects_an_injected_policy_bound(self):
        from atlas.evolution.operation.policy import OperationPolicy

        view = continuation_view(None)
        policy = OperationPolicy(max_cycles_per_invocation=2, max_budget_cycles=2)
        plan = bounded_multi_cycle_plan(view, 4, policy=policy)
        assert plan.cycles_requested == 2

    def test_prior_state_is_visible_to_the_next_invocation(self, tmp_path):
        memory = EvolutionMemory()
        run_cycle(
            memory,
            tmp_path,
            subject="cap.first",
            capability=_CAPABILITY,
            module=_MODULE,
            promotion_authorized=False,
        )
        view = continuation_view(memory)
        opportunity = view.for_subject("cap.first")
        assert opportunity is not None
        assert opportunity.state is EvolutionOpportunityState.DEFERRED
        # The next invocation can see exactly why a repeat is inappropriate.
        allowed, reason = view.may_attempt("cap.first")
        assert allowed is False
        assert "human governance decision" in reason
