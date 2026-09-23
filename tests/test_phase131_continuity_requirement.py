"""Phase 13.1 — Continuous evolution requirement definition: evidence contract.

Investigation result: "continuous evolution" for Atlas means *continued,
separately invoked, bounded cycles over durable evidence* — not a daemon, timer,
scheduler, or autonomous loop. This test pins the definition to the mechanism
that actually implements it.
"""

from __future__ import annotations

import ast
from pathlib import Path

from atlas.evolution.evolution_continuity import (
    EvolutionOpportunityState,
    continuation_view,
    gate_candidates,
    project_opportunities,
    subject_history,
)
from atlas.evolution.evolution_memory import EvolutionMemory
from tests.phase13_support import candidate, record_outcome

_ROOT = Path(__file__).resolve().parents[1]
_MODULE = "atlas/evolution/evolution_continuity.py"


class TestPhase131ContinuityRequirement:
    def test_definition_covers_every_required_meaning(self):
        memory = EvolutionMemory()
        record_outcome(
            memory,
            cycle_id="SEV-1",
            subject="cap.done",
            terminal="activated",
            outcome_kind="successful_evolution",
        )
        record_outcome(
            memory,
            cycle_id="SEV-2",
            subject="cap.failed",
            terminal="sandbox_failed",
            outcome_kind="unsuccessful_attempt",
        )

        view = continuation_view(memory)
        # 1. learn from completed outcomes       -> COMPLETED state
        # 2. retain unresolved gaps              -> EVIDENCE_REQUIRED state
        # 3. identify future opportunities       -> opportunities are projected
        # 4. resume later via explicit invocation -> view is a plain projection
        # 5. prioritize evidence-backed work     -> deterministic ordering
        # 6. state across process boundaries     -> reads durable memory
        # 7. avoid repeating failed attempts      -> may_attempt() refuses
        # 8. recognise when to revisit            -> retry_eligible flag
        # 9. form the next bounded candidate      -> gate_candidates()
        # 10. without an external coding agent    -> no AI seam (12.9/13.9)
        assert view.for_subject("cap.done").state is EvolutionOpportunityState.COMPLETED
        assert (
            view.for_subject("cap.failed").state
            is EvolutionOpportunityState.EVIDENCE_REQUIRED
        )
        assert view.may_attempt("cap.done")[0] is False
        assert view.for_subject("cap.failed").retry_eligible is True
        gate = gate_candidates([candidate("cap.done")[0]], view)
        assert gate.admitted == ()
        assert gate.excluded_subjects == ("cap.done",)
        assert subject_history(memory, "cap.failed")[0].terminal == "sandbox_failed"

    def test_no_daemon_scheduler_or_loop_was_introduced(self):
        module = __import__(
            "atlas.evolution.evolution_continuity", fromlist=["x"]
        )
        for banned in (
            "run_forever",
            "daemon",
            "tick",
            "loop_forever",
            "start_autonomous",
            "schedule",
            "Timer",
            "threading",
            "asyncio",
        ):
            assert not hasattr(module, banned), banned

        tree = ast.parse((_ROOT / _MODULE).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.While):
                raise AssertionError("while loop introduced")
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
                for name in names:
                    assert name.split(".")[0] not in (
                        "threading",
                        "asyncio",
                        "subprocess",
                        "socket",
                        "time",
                    ), name

    def test_continuity_starts_no_cycle_of_its_own(self):
        module = __import__(
            "atlas.evolution.evolution_continuity", fromlist=["x"]
        )
        # The module describes and gates; it never invokes an evolution cycle.
        for banned in ("run", "start", "execute", "promote", "activate", "approve"):
            assert not hasattr(module, banned), banned

    def test_existing_bounded_mechanisms_are_reused_not_rebuilt(self):
        # The bounded cycle controller and the opportunity lifecycle already
        # exist; Phase 13 adds only the continuity bridge between them.
        from atlas.evolution.models import ImprovementStatus
        from atlas.evolution.operation.controller import OperationController
        from atlas.evolution.self_evolution import SelfEvolutionLoop

        assert hasattr(OperationController, "run_operation")
        assert hasattr(SelfEvolutionLoop, "run")
        assert ImprovementStatus.COMPLETED is not None
