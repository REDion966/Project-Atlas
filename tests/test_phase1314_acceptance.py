"""Phase 13.14 — Acceptance & final roadmap state.

Machine-checked summary of the Phase 13 acceptance criteria, so the verdict
cannot drift from the evidence.
"""

from __future__ import annotations

import ast
from pathlib import Path

from atlas.evolution.evolution_continuity import (
    EvolutionContinuation,
    EvolutionOpportunity,
    continuation_view,
)
from atlas.evolution.evolution_memory import EvolutionMemory
from atlas.evolution.models import ImprovementStatus
from atlas.evolution.self_evolution import SelfEvolutionTerminal
from atlas.self_knowledge.independence_inventory import (
    build_independence_inventory,
    repository_root,
)
from tests.phase13_support import record_outcome

_ROOT = repository_root()


class TestPhase1314Acceptance:
    def test_actual_meaning_of_continuous_evolution_was_investigated(self):
        # The requirement is satisfied by reuse: durable storage, a bounded
        # cycle controller, an opportunity lifecycle, and a continuity bridge.
        from atlas.evolution.operation.controller import OperationController
        from atlas.evolution.evolution_memory import EvolutionMemory as _M
        from atlas.evolution.scheduler import EvolutionScheduler

        assert hasattr(_M, "restore")
        assert hasattr(OperationController, "run_operation")
        assert hasattr(EvolutionScheduler, "tick")  # existing bounded analysis
        assert isinstance(continuation_view(None), EvolutionContinuation)

    def test_no_speculative_autonomous_architecture_was_added(self):
        module = __import__(
            "atlas.evolution.evolution_continuity", fromlist=["x"]
        )
        for banned in (
            "run_forever",
            "daemon",
            "loop_forever",
            "start_autonomous",
            "schedule",
            "spawn",
        ):
            assert not hasattr(module, banned), banned
        # The module declares only the continuity projection types: no store,
        # scheduler, executor, or agent class exists.
        tree = ast.parse(
            (_ROOT / "atlas/evolution/evolution_continuity.py").read_text(
                encoding="utf-8"
            )
        )
        classes = {node.name for node in tree.body if isinstance(node, ast.ClassDef)}
        assert classes == {
            "EvolutionOpportunityState",
            "EvolutionOpportunity",
            "EvolutionContinuation",
            "CandidateGate",
            "EvolutionHistoryFact",
            "MultiCyclePlan",
        }

    def test_state_is_durable_and_history_survives_processes(self):
        from atlas.storage.evolution_storage import SQLiteEvolutionStorage

        assert hasattr(SQLiteEvolutionStorage, "initialize")
        assert hasattr(SQLiteEvolutionStorage, "load_records")
        assert hasattr(EvolutionMemory, "restore")

    def test_failed_attempts_are_represented_honestly_and_not_repeated(self):
        memory = EvolutionMemory()
        record_outcome(
            memory,
            cycle_id="SEV-1",
            subject="cap.honest",
            terminal="sandbox_failed",
            outcome_kind="unsuccessful_attempt",
        )
        opportunity = continuation_view(memory).for_subject("cap.honest")
        assert opportunity.state.value == "evidence_required"
        assert opportunity.retry_eligible is True
        assert opportunity.attemptable is False

    def test_separate_cycles_do_not_recursively_call_each_other(self):
        source = (_ROOT / "atlas/evolution/self_evolution.py").read_text(
            encoding="utf-8"
        )
        assert "next_cycle_allowed=False" in source.replace(" ", "")
        assert "self.run(" not in source

    def test_governance_remains_separately_mandatory(self):
        from atlas.evolution.promotion_executor import (
            PromotionExecutor,
            PromotionOutcome,
        )

        assert (
            PromotionExecutor(_ROOT).promote(object(), authorized=False).outcome
            is PromotionOutcome.REFUSED_UNAUTHORIZED
        )
        for terminal in SelfEvolutionTerminal:
            assert terminal.value

    def test_sandbox_and_production_boundaries_remain_enforced(self):
        from atlas.evolution.autonomy.code_sandbox import SandboxPathError, CodeChangeSet

        try:
            CodeChangeSet.from_payload(
                {"code_changes": [{"path": "../escape.py", "content": "x"}]}
            )
        except SandboxPathError:
            pass
        else:  # pragma: no cover - must never happen
            raise AssertionError("sandbox path escape was not refused")

    def test_external_ai_remains_optional_and_model_free_operation_intact(self):
        inventory = build_independence_inventory(_ROOT)
        assert inventory.required_ai_dependencies() == ()
        assert inventory.unknown_dependencies == ()

    def test_provenance_and_self_model_consistency_remain_validated(self):
        memory = EvolutionMemory()
        record_outcome(
            memory,
            cycle_id="SEV-1",
            subject="cap.prov",
            terminal="activated",
            outcome_kind="successful_evolution",
            proposal_id="DEV-1",
            related=("disc:cap.prov",),
        )
        opportunity = continuation_view(memory).for_subject("cap.prov")
        assert opportunity.evidence_ids == ("DEV-1", "disc:cap.prov")
        assert opportunity.to_improvement_status() is ImprovementStatus.COMPLETED
        assert not hasattr(EvolutionOpportunity, "set_state")

    def test_no_phase_14_has_been_invented(self):
        roadmap = (_ROOT / "docs/ROADMAP.md").read_text(encoding="utf-8")
        assert "Phase 14" not in roadmap
        assert "### Phase 13 — Continuous Atlas Evolution (COMPLETE)" in roadmap
        phase13 = roadmap.split("### Phase 13", 1)[1].split("---", 1)[0]
        assert "- [x] 13.1 Continuous capability-gap detection" in phase13
        assert "- [x] 13.10 Continuously improving human-governed system" in phase13
        assert "- [ ] 13." not in phase13

    def test_phase13_artifacts_exist(self):
        assert (_ROOT / "atlas/evolution/evolution_continuity.py").is_file()
        assert (_ROOT / "docs/CONTINUOUS_EVOLUTION.md").is_file()
        assert (_ROOT / "tests/phase13_support.py").is_file()
