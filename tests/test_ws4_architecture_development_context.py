"""WS4 — ArchitectureModel evidence in development planning (advisory).

Verifies the additive ``architecture_model_provider`` seam on
``DevelopmentPlanner``: when an already-built ``ArchitectureModel`` is
supplied, bounded architectural evidence for the plan's affected targets is
attached as advisory plan metadata. Default behavior (no provider / None /
non-model / raising provider) is preserved exactly, the model and repository
are never mutated, and the evidence can never authorize or execute anything.
"""

from __future__ import annotations

import json
from datetime import datetime

import pytest

from atlas.evolution.development_planner import (
    DevelopmentPlanner,
    DevelopmentPlannerError,
)
from atlas.evolution.models import ProposalStatus
from atlas.evolution.proposal_generator import ProposalGenerator
from atlas.lifecycle.component_registry import ComponentRegistry
from atlas.lifecycle.models import ComponentMetadata, ComponentStatus
from atlas.reasoning.execution.registry import CapabilityRegistry
from atlas.research.repository_map import RepositoryMapBuilder
from atlas.self_knowledge.architecture_model import build_architecture_model
from atlas.self_knowledge.capability_model import build_capability_model

_TARGET = "atlas/memory/service/memory_manager_service.py"


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _repo_map(tmp_path):
    """Small repo where the memory service imports the knowledge package."""
    root = tmp_path / "repo"
    files = {
        "atlas/__init__.py": "",
        "atlas/memory/__init__.py": "",
        "atlas/memory/service/__init__.py": "",
        "atlas/memory/service/memory_manager_service.py": "import atlas.knowledge\n",
        "atlas/knowledge/__init__.py": "",
        "atlas/knowledge/knowledge_manager.py": "import os\n",
    }
    for relative, text in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return RepositoryMapBuilder(root).build()


def _architecture_model(tmp_path):
    """Build a real, already-existing ArchitectureModel over a small repo."""
    registry = ComponentRegistry()
    registry.register(
        ComponentMetadata(
            name="memory_service",
            package="atlas.memory.service",
            module_path=(
                "atlas.memory.service.memory_manager_service.MemoryManagerService"
            ),
            description="Memory retrieval, search, ranking, and storage.",
            status=ComponentStatus.HEALTHY,
            dependencies=["knowledge_manager"],
            provided_capabilities=["memory_search", "memory_store"],
        )
    )
    registry.register(
        ComponentMetadata(
            name="knowledge_manager",
            package="atlas.knowledge",
            module_path="atlas.knowledge.knowledge_manager.KnowledgeManager",
            description="Knowledge base querying and management.",
            status=ComponentStatus.HEALTHY,
            provided_capabilities=["knowledge_query"],
        )
    )
    capabilities = CapabilityRegistry()
    capabilities.register("memory_search", lambda *_a, **_k: None)
    capability_model = build_capability_model(registry, capabilities, None)
    return build_architecture_model(
        registry,
        capability_model=capability_model,
        repository_map=_repo_map(tmp_path),
    )


def _approved_proposal(targets: list[str], pid: str = "PROP-WS4"):
    from atlas.evolution.improvement_planner import (
        ImprovementPlanner,
        ImprovementPriority,
    )
    from atlas.evolution.models import Weakness

    weakness = Weakness(
        area="testing",
        description="synthetic",
        severity=ImprovementPriority.MEDIUM,
        supporting_observations=[],
        detected_at=datetime.now(),
    )
    proposal = ProposalGenerator().generate_proposal(
        ImprovementPlanner().create_improvement_plan([weakness])
    )
    proposal.proposal_id = pid
    proposal.metadata["affected_files"] = list(targets)
    proposal.status = ProposalStatus.APPROVED
    proposal.approved_at = datetime.now()
    return proposal


# ---------------------------------------------------------------------------
# A. Provider present — bounded architecture evidence is attached
# ---------------------------------------------------------------------------


class TestProviderPresent:
    def test_module_target_yields_architecture_evidence(self, tmp_path):
        model = _architecture_model(tmp_path)
        planner = DevelopmentPlanner(architecture_model_provider=lambda: model)

        plan = planner.plan(_approved_proposal([_TARGET]))

        evidence = plan.metadata["architecture_evidence"]
        assert evidence["unresolved_targets"] == []
        assert len(evidence["targets"]) == 1
        entry = evidence["targets"][0]
        assert entry["target"] == _TARGET
        assert entry["matched_kind"] == "module"
        assert entry["module"] == (
            "atlas.memory.service.memory_manager_service"
        )
        assert entry["packages"] == ["atlas.memory.service"]
        assert entry["components"] == ["memory_service"]
        assert entry["dependencies"] == ["atlas.knowledge"]

    def test_component_target_resolves_component(self, tmp_path):
        model = _architecture_model(tmp_path)
        planner = DevelopmentPlanner(architecture_model_provider=lambda: model)

        plan = planner.plan(_approved_proposal(["memory_service"]))

        entry = plan.metadata["architecture_evidence"]["targets"][0]
        assert entry["matched_kind"] == "component"
        assert entry["packages"] == ["atlas.memory.service"]
        assert entry["module_paths"]

    def test_capability_target_resolves_subsystem(self, tmp_path):
        model = _architecture_model(tmp_path)
        planner = DevelopmentPlanner(architecture_model_provider=lambda: model)

        plan = planner.plan(_approved_proposal(["memory_search"]))

        entry = plan.metadata["architecture_evidence"]["targets"][0]
        assert entry["matched_kind"] == "capability"
        assert entry["components"] == ["memory_service"]

    def test_unknown_target_is_reported_unresolved(self, tmp_path):
        model = _architecture_model(tmp_path)
        planner = DevelopmentPlanner(architecture_model_provider=lambda: model)

        plan = planner.plan(_approved_proposal([_TARGET, "does/not/exist.py"]))

        evidence = plan.metadata["architecture_evidence"]
        assert evidence["unresolved_targets"] == ["does/not/exist.py"]
        assert [t["target"] for t in evidence["targets"]] == [_TARGET]

    def test_all_unknown_targets_yield_no_section(self, tmp_path):
        model = _architecture_model(tmp_path)
        planner = DevelopmentPlanner(architecture_model_provider=lambda: model)

        plan = planner.plan(_approved_proposal(["ghost.py"]))

        # Nothing architectural resolved: mirror the historical absence.
        assert "architecture_evidence" not in plan.metadata


# ---------------------------------------------------------------------------
# B. Provider absent — existing behavior unchanged
# ---------------------------------------------------------------------------


class TestProviderAbsent:
    def test_no_provider_plan_unchanged(self):
        planner = DevelopmentPlanner()
        plan = planner.plan(_approved_proposal([_TARGET]))

        assert len(plan.steps) == 7
        assert "architecture_evidence" not in plan.metadata

    def test_explicit_none_provider_unchanged(self):
        planner = DevelopmentPlanner(architecture_model_provider=None)
        plan = planner.plan(_approved_proposal([_TARGET]))

        assert len(plan.steps) == 7
        assert "architecture_evidence" not in plan.metadata

    def test_existing_seams_still_coexist(self, tmp_path):
        model = _architecture_model(tmp_path)
        planner = DevelopmentPlanner(
            repository_map_provider=lambda: _repo_map(tmp_path),
            architecture_model_provider=lambda: model,
        )
        plan = planner.plan(_approved_proposal([_TARGET]))

        assert "repository_validation" in plan.metadata
        assert "architecture_evidence" in plan.metadata


# ---------------------------------------------------------------------------
# C. Fail-soft — planning continues without architecture evidence
# ---------------------------------------------------------------------------


class TestFailSoft:
    def test_raising_provider_is_swallowed(self):
        def boom():
            raise RuntimeError("no model from here")

        planner = DevelopmentPlanner(architecture_model_provider=boom)
        plan = planner.plan(_approved_proposal([_TARGET]))

        assert len(plan.steps) == 7
        assert "architecture_evidence" not in plan.metadata

    def test_none_snapshot_is_swallowed(self):
        planner = DevelopmentPlanner(
            architecture_model_provider=lambda: None
        )
        plan = planner.plan(_approved_proposal([_TARGET]))

        assert len(plan.steps) == 7
        assert "architecture_evidence" not in plan.metadata

    def test_non_model_return_value_ignored(self):
        planner = DevelopmentPlanner(
            architecture_model_provider=lambda: "not an architecture model"
        )
        plan = planner.plan(_approved_proposal([_TARGET]))

        assert "architecture_evidence" not in plan.metadata

    def test_empty_targets_yield_no_section(self, tmp_path):
        model = _architecture_model(tmp_path)
        planner = DevelopmentPlanner(architecture_model_provider=lambda: model)
        plan = planner.plan(_approved_proposal([]))

        assert "architecture_evidence" not in plan.metadata


# ---------------------------------------------------------------------------
# D. Read-only — evidence cannot mutate the model or repository
# ---------------------------------------------------------------------------


class TestReadOnly:
    def test_planning_does_not_mutate_model(self, tmp_path):
        model = _architecture_model(tmp_path)
        before = model.to_dict()
        planner = DevelopmentPlanner(architecture_model_provider=lambda: model)

        planner.plan(_approved_proposal([_TARGET, "memory_service"]))

        assert model.to_dict() == before

    def test_planner_has_no_execution_or_authorization_surface(self):
        planner = DevelopmentPlanner()
        for banned in ("execute", "apply", "approve", "promote", "activate"):
            assert not hasattr(planner, banned)


# ---------------------------------------------------------------------------
# E. Governance isolation — evidence never authorizes or executes
# ---------------------------------------------------------------------------


class TestGovernanceIsolation:
    def test_evidence_does_not_change_proposal_status(self, tmp_path):
        model = _architecture_model(tmp_path)
        proposal = _approved_proposal([_TARGET])
        planner = DevelopmentPlanner(architecture_model_provider=lambda: model)

        plan = planner.plan(proposal)

        assert plan.metadata["architecture_evidence"]
        assert proposal.status is ProposalStatus.APPROVED

    def test_unapproved_proposal_still_rejected_with_provider(self, tmp_path):
        model = _architecture_model(tmp_path)
        proposal = _approved_proposal([_TARGET])
        proposal.status = ProposalStatus.DRAFT
        planner = DevelopmentPlanner(architecture_model_provider=lambda: model)

        with pytest.raises(DevelopmentPlannerError):
            planner.plan(proposal)

    def test_evidence_contains_no_authorization_vocabulary(self, tmp_path):
        model = _architecture_model(tmp_path)
        planner = DevelopmentPlanner(architecture_model_provider=lambda: model)
        plan = planner.plan(_approved_proposal([_TARGET]))

        payload = json.dumps(plan.metadata["architecture_evidence"])
        for banned in (
            "authoriz",
            "approved",
            "execute",
            "promote",
            "activat",
            "schedule",
        ):
            assert banned not in payload


# ---------------------------------------------------------------------------
# F. Determinism
# ---------------------------------------------------------------------------


class TestDeterminism:
    def test_same_inputs_same_semantic_evidence(self, tmp_path):
        model = _architecture_model(tmp_path)
        planner = DevelopmentPlanner(architecture_model_provider=lambda: model)

        first = planner.plan(_approved_proposal([_TARGET])).metadata[
            "architecture_evidence"
        ]
        second = planner.plan(_approved_proposal([_TARGET])).metadata[
            "architecture_evidence"
        ]
        assert first == second

    def test_evidence_is_json_safe(self, tmp_path):
        model = _architecture_model(tmp_path)
        planner = DevelopmentPlanner(architecture_model_provider=lambda: model)
        plan = planner.plan(_approved_proposal([_TARGET, "memory_search"]))

        json.dumps(plan.metadata["architecture_evidence"], sort_keys=True)


# ---------------------------------------------------------------------------
# G. Kernel wiring — cache-only provider, no scan triggered
# ---------------------------------------------------------------------------


class TestKernelWiring:
    def test_kernel_architecture_provider_is_cache_only(self):
        from atlas.kernel.atlas import Atlas

        atlas = Atlas()
        atlas.start()
        try:
            planner = atlas.development_planner
            provider = planner._architecture_model_provider
            assert provider is not None

            # Lazy world: no repository map built yet -> no model, no scan.
            assert provider() is None

            assert atlas.refresh_repository_map() is not None
            model = provider()
            assert model is not None

            # Evidence flows through the kernel-wired planner.
            plan = planner.plan(
                _approved_proposal(
                    ["atlas/evolution/development_planner.py"], pid="PROP-WS4-K"
                )
            )
            evidence = plan.metadata["architecture_evidence"]
            assert any(
                t["matched_kind"] == "module" for t in evidence["targets"]
            )
        finally:
            atlas.shutdown()
