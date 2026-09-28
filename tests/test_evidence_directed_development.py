"""Step 3 — evidence-directed development (first vertical slice).

ConcreteGap -> DevelopmentNeed -> resolved source file -> deterministic
evidence-targeted change -> existing DevelopmentCycleController ->
EvolutionProposal + ApprovalRequest + PENDING_APPROVAL -> STOP.

The slice is model-free, deterministic and fail-closed; it never approves,
executes, verifies, promotes or writes to the live repository.
"""

from __future__ import annotations

import posixpath
from datetime import datetime, timezone
from pathlib import Path

import pytest

from atlas.conversation.evidence_gap_analysis import (
    ConcreteGap,
    EvidenceCitation,
    GapAnalysisReport,
    GapCategory,
    GapSufficiency,
)
from atlas.evolution.approval_manager import ApprovalManager
from atlas.evolution.development_cycle import (
    DeterministicChangeSupplier,
    DevelopmentCycleController,
    DevelopmentNeed,
)
from atlas.evolution.development_request_scaffold import scaffold_spec_for_request
from atlas.evolution.development_scaffold_supplier import (
    CompositeChangeSupplier,
    ScaffoldChangeSupplier,
)
from atlas.evolution.evidence_development import (
    EVIDENCE_CHANGE_KEY,
    EVIDENCE_CHANGE_ORIGIN,
    EvidenceChangeSupplier,
    development_need_from_gap,
    resolve_gap_target,
)
from atlas.evolution.models import ProposalStatus
from atlas.evolution.promotion_gate import ARCHITECTURE_SENSITIVE_PREFIXES
from atlas.lifecycle.component_definitions import ComponentMetadata
from atlas.lifecycle.component_registry import ComponentRegistry
from atlas.research.repository_map import ModuleInfo, RepositoryMap
from atlas.self_knowledge.architecture_model import build_architecture_model

COMPONENT = "atlas.goals.dependency_resolver"
SOURCE_PATH = "atlas/goals/dependency_resolver.py"
TEST_PATH = "tests/test_dependency_resolver_evidence_gap.py"

_REPO_ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# harness
# ---------------------------------------------------------------------------


def _architecture(*, modules=(SOURCE_PATH,), components=()):
    """A REAL ``ArchitectureModel`` over a real registry and repository map."""
    registry = ComponentRegistry()
    for metadata in components:
        registry.register(metadata)
    repo_map = RepositoryMap(
        built_at=datetime.now(timezone.utc),
        root_label=".",
        modules=tuple(
            ModuleInfo(
                module=posixpath.splitext(path)[0].replace("/", "."),
                path=path,
                language="python",
                is_package=posixpath.basename(path) == "__init__.py",
                line_count=1,
            )
            for path in modules
        ),
    )
    return build_architecture_model(
        component_registry=registry, capability_model=None, repository_map=repo_map
    )


def _report(*, gaps=(), insufficient=False, target="conversation state handling"):
    return GapAnalysisReport(
        target=target,
        objective=target,
        gaps=tuple(gaps),
        insufficient_evidence=insufficient,
        summary="bounded test summary",
        evidence_basis=("reference", "test"),
        finding_count=5,
        component_count=2,
    )


def _gap(
    *,
    category=GapCategory.UNTESTED_COMPONENT,
    component=COMPONENT,
    gap_id="GAP-0001",
    citations=2,
):
    return ConcreteGap(
        gap_id=gap_id,
        category=category,
        component=component,
        observation=f"the investigation identified '{component}' and found "
        "implementation evidence for it",
        interpretation="no test evidence was found for this component",
        sufficiency=GapSufficiency.SUFFICIENT,
        evidence=tuple(
            EvidenceCitation(
                category="reference",
                description=f"Found 3 reference(s) 'state' in atlas/goals/ ({i})",
                location="atlas/goals/",
                evidence="atlas/goals/dependency_resolver.py",
            )
            for i in range(citations)
        ),
    )


class _RecordingApprovalManager(ApprovalManager):
    """The EXISTING manager, recording the proposals it is handed."""

    def __init__(self) -> None:
        super().__init__()
        self.proposals = []

    def create_approval_request(self, proposal, scope_fingerprint=""):
        self.proposals.append(proposal)
        return super().create_approval_request(proposal, scope_fingerprint)


def _controller():
    manager = _RecordingApprovalManager()
    controller = DevelopmentCycleController(
        approval_manager=manager,
        change_supplier=CompositeChangeSupplier(
            [
                DeterministicChangeSupplier(),
                ScaffoldChangeSupplier(),
                EvidenceChangeSupplier(),
            ]
        ),
    )
    return controller, manager


def _prepare(report=None, *, gap_id=""):
    return development_need_from_gap(
        report if report is not None else _report(gaps=(_gap(),)),
        gap_id=gap_id,
        architecture=_architecture(),
    )


# ---------------------------------------------------------------------------
# 1. ConcreteGap -> DevelopmentNeed
# ---------------------------------------------------------------------------


class TestGapToNeed:
    def test_component_and_citations_are_preserved(self):
        outcome = _prepare()
        assert outcome.status == "prepared"
        need = outcome.need
        assert need.target_components == (COMPONENT,)
        assert need.candidate_id == "evidence-gap::GAP-0001"
        assert need.evidence_change_ids[0] == "evidence-gap::GAP-0001"
        assert len(need.evidence_change_ids) == 3  # gap id + 2 citations
        assert len(set(need.evidence_change_ids)) == 3
        assert COMPONENT in need.rationale
        assert "untested_component" in need.rationale
        assert "Found 3 reference(s) 'state' in atlas/goals/ (0)" in need.rationale
        assert need.has_direct_evidence is True  # existing evidence gate: no research
        assert outcome.source_path == SOURCE_PATH
        assert outcome.test_path == TEST_PATH

    def test_evidence_is_bounded(self):
        outcome = _prepare(_report(gaps=(_gap(citations=40),)))
        assert len(outcome.need.evidence_change_ids) <= 20
        assert len(outcome.need.rationale) <= 4_000

    def test_requested_gap_id_selects_that_gap(self):
        report = _report(
            gaps=(_gap(gap_id="GAP-0001", component="atlas.goals.a"), _gap(gap_id="GAP-0002"))
        )
        chosen = _prepare(report, gap_id="GAP-0002")
        assert chosen.need.candidate_id == "evidence-gap::GAP-0002"
        missing = _prepare(report, gap_id="GAP-9999")
        assert missing.status == "refused" and "GAP-9999" in missing.reason


# ---------------------------------------------------------------------------
# 2. Insufficient evidence
# ---------------------------------------------------------------------------


class TestInsufficientEvidence:
    def test_insufficient_report_creates_no_need(self):
        outcome = development_need_from_gap(
            _report(insufficient=True), architecture=_architecture()
        )
        assert outcome.status == "refused"
        assert outcome.need is None
        assert "insufficient evidence" in outcome.reason

    def test_report_with_no_gaps_creates_no_need(self):
        outcome = development_need_from_gap(_report(), architecture=_architecture())
        assert outcome.status == "refused" and outcome.need is None
        assert "no concrete gaps" in outcome.reason

    def test_non_report_input_creates_no_need(self):
        outcome = development_need_from_gap(None, architecture=_architecture())
        assert outcome.status == "refused" and outcome.need is None


# ---------------------------------------------------------------------------
# 3. Component -> ArchitectureModel path
# ---------------------------------------------------------------------------


class TestResolution:
    def test_module_component_resolves_to_its_real_file(self):
        target, reason = resolve_gap_target(COMPONENT, architecture=_architecture())
        assert reason == ""
        assert target.source_path == SOURCE_PATH
        assert target.module == COMPONENT
        assert target.test_path == TEST_PATH

    def test_registered_component_resolves_via_its_module_path(self):
        architecture = _architecture(
            components=(
                ComponentMetadata(
                    name="dependency_resolver",
                    package="atlas.goals",
                    module_path=SOURCE_PATH,
                    description="resolves goal dependencies",
                ),
            )
        )
        target, reason = resolve_gap_target("dependency_resolver", architecture=architecture)
        assert reason == ""
        assert target.source_path == SOURCE_PATH

    def test_unknown_component_fails_closed(self):
        target, reason = resolve_gap_target("atlas.nope.missing", architecture=_architecture())
        assert target is None
        assert "not known to the architecture model" in reason

    def test_package_target_fails_closed(self):
        architecture = _architecture(modules=("atlas/goals/__init__.py",))
        target, reason = resolve_gap_target("atlas.goals", architecture=architecture)
        assert target is None and reason

    def test_missing_architecture_fails_closed(self):
        target, reason = resolve_gap_target(COMPONENT, architecture=None)
        assert target is None and reason

    def test_empty_component_fails_closed(self):
        target, reason = resolve_gap_target("", architecture=_architecture())
        assert target is None and reason


# ---------------------------------------------------------------------------
# 4. Architecture-sensitive components
# ---------------------------------------------------------------------------


class TestArchitectureSensitive:
    @pytest.mark.parametrize("prefix", ARCHITECTURE_SENSITIVE_PREFIXES)
    def test_every_protected_prefix_fails_closed(self, prefix):
        module = f"{prefix}guarded_module"
        path = module.replace(".", "/") + ".py"
        target, reason = resolve_gap_target(module, architecture=_architecture(modules=(path,)))
        assert target is None
        assert "architecture-sensitive" in reason

    def test_adapter_refuses_a_sensitive_gap_component(self):
        module = f"{ARCHITECTURE_SENSITIVE_PREFIXES[0]}guarded_module"
        path = module.replace(".", "/") + ".py"
        outcome = development_need_from_gap(
            _report(gaps=(_gap(component=module),)),
            architecture=_architecture(modules=(path,)),
        )
        assert outcome.status == "refused" and outcome.need is None

    def test_supplier_refuses_a_sensitive_spec(self):
        need = DevelopmentNeed(
            title="t",
            metadata={
                EVIDENCE_CHANGE_KEY: {
                    "category": "untested_component",
                    "component": "atlas.kernel.atlas",
                    "module": "atlas/kernel/atlas.py",
                    "test_module": "tests/test_atlas_evidence_gap.py",
                }
            },
        )
        with pytest.raises(ValueError, match="architecture-sensitive"):
            EvidenceChangeSupplier().supply_changes(need)


# ---------------------------------------------------------------------------
# 5. Evidence-targeted supplier
# ---------------------------------------------------------------------------


class TestSupplier:
    def _need(self):
        return _prepare().need

    def test_untested_component_produces_a_deterministic_test_change(self):
        supplied = EvidenceChangeSupplier().supply_changes(self._need())
        assert supplied is not None
        (path, content), = supplied.code_changes
        assert path == TEST_PATH
        assert supplied.test_files == ((path, content),)
        assert supplied.origin == EVIDENCE_CHANGE_ORIGIN
        assert supplied.notes
        assert "import pytest" in content
        assert f'"{COMPONENT}"' in content
        assert "def test_evidence_records_the_component():" in content
        assert "def test_component_module_is_importable():" in content

    def test_identical_input_produces_identical_output(self):
        first = EvidenceChangeSupplier().supply_changes(self._need())
        second = EvidenceChangeSupplier().supply_changes(self._need())
        assert first == second

    def test_bounds_are_enforced(self):
        supplied = EvidenceChangeSupplier().supply_changes(self._need())
        path, content = supplied.code_changes[0]
        assert len(content) <= 8_000
        assert len(path) <= 256
        assert len(supplied.code_changes) <= EvidenceChangeSupplier.MAX_FILES

    def test_unrelated_need_is_not_hijacked(self):
        assert EvidenceChangeSupplier().supply_changes(DevelopmentNeed(title="unrelated")) is None

    def test_malformed_spec_raises(self):
        with pytest.raises(ValueError, match="must be an object"):
            EvidenceChangeSupplier().supply_changes(
                DevelopmentNeed(title="t", metadata={EVIDENCE_CHANGE_KEY: "nope"})
            )

    def test_unsupported_gap_category_fails_closed(self):
        refused = development_need_from_gap(
            _report(gaps=(_gap(category=GapCategory.UNCOVERED_COMPONENT),)),
            architecture=_architecture(),
        )
        assert refused.status == "refused" and refused.need is None
        assert "no supported remedy" in refused.reason
        need = DevelopmentNeed(
            title="t",
            metadata={
                EVIDENCE_CHANGE_KEY: {
                    "category": "uncovered_component",
                    "component": COMPONENT,
                    "module": SOURCE_PATH,
                    "test_module": TEST_PATH,
                }
            },
        )
        with pytest.raises(ValueError, match="unsupported gap category"):
            EvidenceChangeSupplier().supply_changes(need)

    def test_missing_module_spec_fails_closed(self):
        need = DevelopmentNeed(
            title="t",
            metadata={
                EVIDENCE_CHANGE_KEY: {
                    "category": "untested_component",
                    "component": COMPONENT,
                }
            },
        )
        with pytest.raises(ValueError, match="'module' is required"):
            EvidenceChangeSupplier().supply_changes(need)


# ---------------------------------------------------------------------------
# 6. Composite compatibility
# ---------------------------------------------------------------------------


class TestCompositeCompatibility:
    def test_scaffold_authoring_is_unchanged(self):
        spec = scaffold_spec_for_request("add a capability for weather reports")
        assert spec is not None
        assert spec["module"].startswith("atlas/reasoning/execution/")
        assert spec["test_module"].startswith("tests/test_")
        assert scaffold_spec_for_request("add a capability for weather reports") == spec

    def test_deterministic_supplier_is_unchanged(self):
        need = DevelopmentNeed(
            title="t",
            metadata={
                "code_changes": [{"path": "atlas/x.py", "content": "x = 1\n"}],
                "test_files": {"tests/test_x.py": "def test_x():\n    assert True\n"},
            },
        )
        supplied = DeterministicChangeSupplier().supply_changes(need)
        assert supplied.code_changes == (("atlas/x.py", "x = 1\n"),)
        assert supplied.test_files == (
            ("tests/test_x.py", "def test_x():\n    assert True\n"),
        )
        assert supplied.origin == "deterministic"

    def test_composite_is_keyed_on_disjoint_metadata(self):
        composite = CompositeChangeSupplier(
            [DeterministicChangeSupplier(), ScaffoldChangeSupplier(), EvidenceChangeSupplier()]
        )
        spec = {
            "category": "untested_component",
            "component": COMPONENT,
            "module": SOURCE_PATH,
            "test_module": TEST_PATH,
        }
        explicit = DevelopmentNeed(
            title="t",
            metadata={
                "code_changes": [{"path": "atlas/x.py", "content": "x = 1\n"}],
                EVIDENCE_CHANGE_KEY: spec,
            },
        )
        assert composite.supply_changes(explicit).origin == "deterministic"
        assert (
            composite.supply_changes(
                DevelopmentNeed(title="t", metadata={EVIDENCE_CHANGE_KEY: spec})
            ).origin
            == EVIDENCE_CHANGE_ORIGIN
        )
        assert composite.supply_changes(DevelopmentNeed(title="t")) is None


# ---------------------------------------------------------------------------
# 7. Development cycle -> PENDING_APPROVAL
# ---------------------------------------------------------------------------


class TestDevelopmentCycle:
    def _prepared(self):
        controller, manager = _controller()
        outcome = _prepare()
        result = controller.run_development_cycle(outcome.need)
        return controller, manager, outcome, result

    def test_real_proposal_reaches_pending_approval_with_the_targeted_path(self):
        _, manager, outcome, result = self._prepared()

        assert result.decision == "prepared"
        assert result.status == "ok"
        assert result.proposal_status == ProposalStatus.PENDING_APPROVAL.name
        assert result.proposal_id.startswith("DEV-")
        assert result.approval_request_id
        assert result.researched is False  # direct evidence: no research invoked
        assert len(manager.proposals) == 1

        proposal = manager.proposals[0]
        metadata = proposal.metadata
        assert [c["path"] for c in metadata["code_changes"]] == [outcome.test_path]
        assert list(metadata["test_files"]) == [outcome.test_path]
        assert metadata["development_cycle"]["change_origin"] == EVIDENCE_CHANGE_ORIGIN
        assert metadata["development_cycle"]["content_status"] == "unverified-draft"
        assert metadata["development_cycle"]["evidence_change_ids"]
        assert proposal.status is ProposalStatus.PENDING_APPROVAL
        assert proposal.approved_at is None

    def test_targeted_test_path_is_derived_from_the_resolved_source_file(self):
        _, manager, outcome, _ = self._prepared()
        stem = posixpath.splitext(posixpath.basename(outcome.source_path))[0]
        assert outcome.source_path == SOURCE_PATH
        assert manager.proposals[0].metadata["code_changes"][0]["path"] == TEST_PATH
        assert TEST_PATH == f"tests/test_{stem}_evidence_gap.py"

    def test_no_execution_or_promotion_surface_is_touched(self):
        controller, manager, _, _ = self._prepared()
        assert not hasattr(controller, "promote")
        assert not hasattr(controller, "execute")
        assert manager.proposals[0].status is ProposalStatus.PENDING_APPROVAL

    def test_refused_gap_never_reaches_the_cycle(self):
        controller, manager = _controller()
        outcome = development_need_from_gap(
            _report(insufficient=True), architecture=_architecture()
        )
        assert outcome.need is None
        assert manager.proposals == []
        assert controller._counter == 0  # noqa: SLF001 - no cycle ran


# ---------------------------------------------------------------------------
# 8. Real kernel: InvestigationService -> EvidenceGapAnalyzer -> proposal
# ---------------------------------------------------------------------------


def _started_atlas(monkeypatch, tmp_path):
    """The established isolated real-kernel pattern (temp EvolutionStorage)."""
    from atlas.storage.evolution_storage import SQLiteEvolutionStorage

    class TmpSQLiteEvolutionStorage(SQLiteEvolutionStorage):
        def __init__(self, db_path=None):  # noqa: D107 - test shim
            super().__init__(db_path=tmp_path / "evolution.db")

    monkeypatch.setattr(
        "atlas.kernel.atlas.SQLiteEvolutionStorage", TmpSQLiteEvolutionStorage
    )
    from atlas.kernel.atlas import Atlas

    atlas = Atlas()
    atlas.start()
    return atlas


class TestRealKernel:
    def _real_analysis(self, atlas):
        from atlas.conversation.evidence_gap_analysis import EvidenceGapAnalyzer
        from atlas.conversation.investigation import InvestigationService

        report = InvestigationService().investigate("the goal plan composer")
        return EvidenceGapAnalyzer().analyze(report)

    def test_real_gap_produces_a_pending_approval_proposal(self, monkeypatch, tmp_path):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            analysis = self._real_analysis(atlas)
            assert analysis.insufficient_evidence is False
            architecture = atlas.architecture_model()
            chosen = None
            for gap in analysis.gaps:
                target, _ = resolve_gap_target(gap.component, architecture=architecture)
                if target is not None:
                    chosen = (gap, target)
                    break
            assert chosen is not None, "no resolvable gap in the real report"
            gap, target = chosen
            assert gap.category is GapCategory.UNTESTED_COMPONENT

            outcome = atlas.propose_development_from_evidence_gap(
                analysis, gap_id=gap.gap_id
            )
            assert outcome.prepared, outcome.reason
            summary = outcome.to_dict()
            assert summary["proposal_status"] == ProposalStatus.PENDING_APPROVAL.name
            assert summary["proposal_id"].startswith("DEV-")
            assert summary["approval_request_id"]
            assert summary["component"] == gap.component
            assert summary["source_path"] == target.source_path
            assert (tmp_path / "evolution.db").exists()  # persisted, not executed

            # The resolved file is a real repository file; the targeted test
            # module is deterministic and bounded.
            assert (_REPO_ROOT / target.source_path).exists()
            stem = posixpath.splitext(posixpath.basename(target.source_path))[0]
            assert outcome.test_path == f"tests/test_{stem}_evidence_gap.py"
            assert len(outcome.test_path) <= 256

            # No promotion, no review, no automatic approval.
            assert not atlas.pending_promotion_reviews()
        finally:
            atlas.shutdown()

    def test_failure_paths_fail_closed_with_truthful_reasons(self, monkeypatch, tmp_path):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            insufficient = atlas.propose_development_from_evidence_gap(
                _report(insufficient=True)
            )
            assert insufficient.status == "refused" and insufficient.need is None
            assert "insufficient evidence" in insufficient.reason

            unknown = atlas.propose_development_from_evidence_gap(
                _report(gaps=(_gap(component="atlas.nope.missing"),))
            )
            assert unknown.status == "refused" and unknown.need is None
            assert "architecture model" in unknown.reason

            unsupported = atlas.propose_development_from_evidence_gap(
                _report(gaps=(_gap(category=GapCategory.UNCOVERED_COMPONENT),))
            )
            assert unsupported.status == "refused" and unsupported.need is None
            assert "no supported remedy" in unsupported.reason

            assert not atlas.pending_promotion_reviews()
        finally:
            atlas.shutdown()
