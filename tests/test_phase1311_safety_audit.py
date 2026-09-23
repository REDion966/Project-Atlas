"""Phase 13.11 — Continuous evolution safety audit.

Audits the completed evolution architecture for duplicate attempts, stale
artifacts and authorizations, replayed records, invalid transitions, evidence or
provenance loss, unauthorized activation, automatic chaining, unbounded retry,
recursive self-invocation, hidden subprocess execution, external AI dependence,
production mutation outside promotion, and governance bypass.
"""

from __future__ import annotations

import ast
from pathlib import Path

from atlas.evolution.approval_manager import ApprovalManager
from atlas.evolution.development_cycle import (
    DevelopmentCycleController,
    DevelopmentNeed,
)
from atlas.evolution.development_scaffold_supplier import ScaffoldChangeSupplier
from atlas.evolution.evolution_continuity import (
    _STATE_BY_TERMINAL,
    EvolutionOpportunityState,
    continuation_view,
    gate_candidates,
    project_opportunities,
)
from atlas.evolution.evolution_memory import EvolutionMemory
from atlas.evolution.promotion_artifact import capture_promotion_artifact
from atlas.evolution.promotion_executor import PromotionExecutor, PromotionOutcome
from atlas.evolution.self_evolution import SelfEvolutionTerminal
from tests.phase13_support import candidate, record_outcome, run_cycle

_ROOT = Path(__file__).resolve().parents[1]
_MODULE = "atlas/evolution/evolution_continuity.py"


def _replayed(memory: EvolutionMemory, *, subject: str, terminal: str) -> None:
    """Write the SAME durable record id twice (a literal replay)."""
    record_outcome(
        memory,
        cycle_id="SEV-000001",
        subject=subject,
        terminal=terminal,
        outcome_kind="x",
        record_id="EVO-fixed",
    )


class TestPhase1311SafetyAudit:
    def test_duplicate_and_replayed_records_are_counted_once(self):
        memory = EvolutionMemory()
        _replayed(memory, subject="cap.dup", terminal="activated")
        _replayed(memory, subject="cap.dup", terminal="activated")
        opportunities = project_opportunities(memory)
        assert len(opportunities) == 1
        assert opportunities[0].attempts == 1  # literal replay collapsed

    def test_duplicate_attempts_are_gated_out_repeatedly(self):
        memory = EvolutionMemory()
        record_outcome(
            memory,
            cycle_id="SEV-1",
            subject="cap.tried",
            terminal="activated",
            outcome_kind="successful_evolution",
        )
        view = continuation_view(memory)
        for _ in range(3):  # idempotent refusal
            gate = gate_candidates([candidate("cap.tried")[0]], view)
            assert gate.admitted == ()

    def test_stale_repository_target_is_refused_without_overwrite(self, tmp_path):
        target = tmp_path / "atlas/example/stale_handlers.py"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("ORIGINAL = 1\n", encoding="utf-8")
        artifact = capture_promotion_artifact(
            [{"path": "atlas/example/stale_handlers.py", "content": "NEW = 2\n"}],
            proposal_id="P",
            repo_root=tmp_path,
        )
        target.write_text("DRIFTED = 3\n", encoding="utf-8")
        result = PromotionExecutor(tmp_path).promote(artifact, authorized=True)
        assert result.outcome is PromotionOutcome.REFUSED_STALE
        assert target.read_text(encoding="utf-8") == "DRIFTED = 3\n"

    def test_stale_approval_cannot_authorize_a_later_cycle(self, tmp_path):
        store_a, store_b = _CapturingStore(), _CapturingStore()
        manager = ApprovalManager()
        first = DevelopmentCycleController(
            approval_manager=manager,
            change_supplier=ScaffoldChangeSupplier(),
            proposal_store=store_a,
            approval_request_store=store_a,
        ).run_development_cycle(
            DevelopmentNeed(
                title="one",
                evidence_knowledge_ids=("k",),
                metadata={
                    "scaffold": {
                        "module": "atlas/example/stale_a_handlers.py",
                        "capability_name": "example.stale_a",
                    }
                },
            )
        )
        assert first.proposal_status == "PENDING_APPROVAL"
        # A later, unrelated cycle gets its own pending request.
        second = DevelopmentCycleController(
            approval_manager=manager,
            change_supplier=ScaffoldChangeSupplier(),
            proposal_store=store_b,
            approval_request_store=store_b,
        ).run_development_cycle(
            DevelopmentNeed(
                title="two",
                evidence_knowledge_ids=("k",),
                metadata={
                    "scaffold": {
                        "module": "atlas/example/stale_b_handlers.py",
                        "capability_name": "example.stale_b",
                    }
                },
            )
        )
        assert second.proposal_status == "PENDING_APPROVAL"
        assert store_a.requests[0].request_id != store_b.requests[0].request_id
        assert store_b.requests[0].decision.name == "PENDING"

    def test_provenance_and_evidence_survive_the_projection(self):
        memory = EvolutionMemory()
        record_outcome(
            memory,
            cycle_id="SEV-1",
            subject="cap.prov",
            terminal="promotion_failed",
            outcome_kind="unsuccessful_attempt",
            proposal_id="DEV-9",
            related=("disc:cap.prov",),
        )
        opportunity = project_opportunities(memory)[0]
        assert opportunity.evidence_ids == ("DEV-9", "disc:cap.prov")
        assert opportunity.record_ids

    def test_no_module_level_state_is_mutated_by_the_projection(self):
        snapshot = dict(_STATE_BY_TERMINAL)
        memory = EvolutionMemory()
        record_outcome(
            memory,
            cycle_id="SEV-1",
            subject="cap.x",
            terminal="activated",
            outcome_kind="successful_evolution",
        )
        continuation_view(memory)
        assert _STATE_BY_TERMINAL == snapshot

    def test_unauthorized_activation_and_production_mutation_are_impossible(
        self, tmp_path
    ):
        memory = EvolutionMemory()
        result = run_cycle(
            memory,
            tmp_path,
            subject="cap.noauth",
            capability="example.noauth",
            module="atlas/example/noauth_handlers.py",
            promotion_authorized=False,
        )
        assert result.terminal is SelfEvolutionTerminal.PENDING_PROMOTION_REVIEW
        assert result.activated_capabilities == ()
        assert not list(tmp_path.rglob("*.py"))

    def test_self_model_inconsistency_is_represented_not_ignored(self):
        memory = EvolutionMemory()
        record_outcome(
            memory,
            cycle_id="SEV-1",
            subject="cap.inconsistent",
            terminal="self_model_inconsistent",
            outcome_kind="partial_result",
        )
        opportunity = continuation_view(memory).for_subject("cap.inconsistent")
        assert opportunity.state is EvolutionOpportunityState.BLOCKED
        assert opportunity.retry_eligible is False

    def test_registry_inconsistency_is_refused_and_rolled_back(self, tmp_path):
        from atlas.evolution.self_evolution import SelfEvolutionLoop
        from atlas.lifecycle.component_registry import ComponentRegistry
        from atlas.reasoning.execution.registry import CapabilityRegistry

        registry = CapabilityRegistry()
        registry.register("example.dupe", lambda params: None)

        memory = EvolutionMemory()
        loop = SelfEvolutionLoop(
            evolution_memory=memory,
            component_registry=ComponentRegistry(),
            capability_registry=registry,
            repo_root=tmp_path,
        )
        discovery, assessment = candidate("cap.dupe")
        result = loop.run(
            discovery,
            assessment,
            target_module="atlas/example/dupe_handlers.py",
            capability_name="example.dupe",
            capability_names=(),
            owner_approved=True,
            promotion_authorized=True,
        )
        assert result.terminal is SelfEvolutionTerminal.PROMOTION_FAILED
        assert result.activated_capabilities == ()
        assert not [
            p for p in tmp_path.rglob("*") if p.is_file() and p.suffix != ".pyc"
        ]

    def test_no_hidden_subprocess_recursion_or_unbounded_retry(self):
        tree = ast.parse((_ROOT / _MODULE).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name.split(".")[0] not in (
                        "subprocess",
                        "os",
                        "socket",
                        "threading",
                        "asyncio",
                        "time",
                    ), alias.name
            if isinstance(node, ast.While):
                raise AssertionError("loop introduced in the continuity module")

    def test_continuity_module_holds_no_authority_surface(self):
        module = __import__(
            "atlas.evolution.evolution_continuity", fromlist=["x"]
        )
        for banned in ("approve", "authorize", "promote", "activate", "execute", "write"):
            assert not hasattr(module, banned), banned

    def test_governed_boundaries_are_still_the_only_path(self, tmp_path):
        # Promotion still refuses without explicit OWNER authorization, and the
        # approval manager remains the sole approval surface.
        refused = PromotionExecutor(tmp_path).promote(object(), authorized=False)
        assert refused.outcome is PromotionOutcome.REFUSED_UNAUTHORIZED
        assert hasattr(ApprovalManager, "approve")


class _CapturingStore:
    def __init__(self):
        self.proposals = []
        self.requests = []

    def store_proposal(self, proposal):
        self.proposals.append(proposal)

    def store_approval_request(self, request):
        self.requests.append(request)
