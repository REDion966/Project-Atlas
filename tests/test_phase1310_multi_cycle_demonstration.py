"""Phase 13.10 — Bounded multi-cycle demonstration.

A finite, explicitly driven sequence: Cycle 1 runs, terminates, and persists its
outcome; a NEW invocation then loads the durable history, sees what is complete,
selects a different justified subject, and runs Cycle 2. Two cycles, no
self-chaining, no daemon.
"""

from __future__ import annotations

from atlas.evolution.evolution_continuity import (
    EvolutionOpportunityState,
    bounded_multi_cycle_plan,
    continuation_view,
    gate_candidates,
)
from atlas.evolution.evolution_memory import EvolutionMemory
from atlas.evolution.self_evolution import SelfEvolutionTerminal
from tests.phase13_support import candidate, run_cycle, sqlite_memory


class TestPhase1310BoundedMultiCycle:
    def test_cycle_1_terminates_and_persists_before_cycle_2(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()

        # ---------------- Cycle 1: evidence-backed gap -> activate ----------
        memory1, storage1 = sqlite_memory(tmp_path, name="multi.db")
        try:
            cycle1 = run_cycle(
                memory1,
                repo,
                subject="cap.one",
                capability="example.one",
                module="atlas/example/one_handlers.py",
                repo_root=repo,
            )
            assert len(memory1.get_records_by_type("evolution_outcome")) == 1
        finally:
            storage1.close()

        assert cycle1.terminal is SelfEvolutionTerminal.ACTIVATED
        assert cycle1.outcome.value == "successful_evolution"
        assert cycle1.next_cycle_allowed is False
        assert (repo / "atlas/example/one_handlers.py").is_file()

        # ------------- Terminate: nothing started Cycle 2 by itself ---------
        memory_check, storage_check = sqlite_memory(tmp_path, name="multi.db")
        try:
            memory_check.restore()
            assert len(memory_check.get_records_by_type("evolution_outcome")) == 1
        finally:
            storage_check.close()

        # ---------------- Cycle 2: a NEW explicit invocation ---------------
        memory2, storage2 = sqlite_memory(tmp_path, name="multi.db")
        try:
            memory2.restore()
            view = continuation_view(memory2)

            # Cycle 2 loads prior state: subject one is complete.
            assert (
                view.for_subject("cap.one").state
                is EvolutionOpportunityState.COMPLETED
            )
            # …and the gate refuses to repeat it, admitting only the new one.
            gate = gate_candidates(
                [candidate("cap.one")[0], candidate("cap.two")[0]], view
            )
            assert gate.admitted_ids == ("disc:cap.two",)
            assert gate.excluded_subjects == ("cap.one",)

            # A finite plan over what remains attemptable (no scheduler).
            plan = bounded_multi_cycle_plan(view, 2)
            assert plan.cycles_requested <= 2

            cycle2 = run_cycle(
                memory2,
                repo,
                subject=gate.admitted[0].subject,
                capability="example.two",
                module="atlas/example/two_handlers.py",
                repo_root=repo,
            )
        finally:
            storage2.close()

        assert cycle2.terminal is SelfEvolutionTerminal.ACTIVATED
        assert cycle2.cycle_id != cycle1.cycle_id
        assert cycle2.next_cycle_allowed is False

        # ------------- Both cycles are durably recorded --------------------
        memory3, storage3 = sqlite_memory(tmp_path, name="multi.db")
        try:
            memory3.restore()
            outcomes = memory3.get_records_by_type("evolution_outcome")
            assert len(outcomes) == 2
            assert {r.metadata["subject"] for r in outcomes} == {
                "cap.one",
                "cap.two",
            }
            final = continuation_view(memory3)
            assert final.for_subject("cap.one").state is (
                EvolutionOpportunityState.COMPLETED
            )
            assert len(final.completed) == 2
            assert final.attemptable == ()
        finally:
            storage3.close()

    def test_the_sequence_length_is_finite_and_caller_driven(self):
        from atlas.evolution.evolution_continuity import MAX_EXPLICIT_CYCLES

        view = continuation_view(EvolutionMemory())
        assert bounded_multi_cycle_plan(view, 10_000).cycles_requested == (
            MAX_EXPLICIT_CYCLES
        )
        assert bounded_multi_cycle_plan(view, -5).cycles_requested == 0

    def test_no_result_ever_permits_an_automatic_next_cycle(self, tmp_path):
        memory = EvolutionMemory()
        results = [
            run_cycle(
                memory,
                tmp_path,
                subject=f"cap.{name}",
                capability=f"example.{name}",
                module=f"atlas/example/{name}_handlers.py",
                owner_approved=owner_approved,
                promotion_authorized=promotion_authorized,
            )
            for name, owner_approved, promotion_authorized in (
                ("x", True, False),
                ("y", False, False),
            )
        ]
        for result in results:
            assert result.next_cycle_allowed is False
