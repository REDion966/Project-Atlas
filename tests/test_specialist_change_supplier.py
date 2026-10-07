"""The specialist -> authoring bridge (Command 3A): bounded, fail-closed, inert.

Proves that an UNTRUSTED :class:`SpecialistProposal` carried on a
:class:`DevelopmentNeed` becomes ONLY the EXISTING bounded ``code_changes``
representation, that every malformed/unsafe/unauthorized proposal is refused,
and that the deterministic / structural / scaffold / supplied-edit paths are
completely unchanged when no proposal is present.

No model, network, filesystem write, execution, approval or promotion occurs.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

from atlas.evolution.approval_manager import ApprovalManager
from atlas.evolution.development_cycle import (
    ChangeSupplier,
    DevelopmentCycleController,
    DevelopmentNeed,
    DeterministicChangeSupplier,
    SuppliedChanges,
)
from atlas.evolution.development_scaffold_supplier import (
    CompositeChangeSupplier,
    ScaffoldChangeSupplier,
)
from atlas.evolution.models import ProposalStatus
from atlas.evolution.specialist_change_supplier import (
    SPECIALIST_ORIGIN,
    SPECIALIST_PROPOSAL_KEY,
    SpecialistChangeSupplier,
)
from atlas.specialists import CODE_GENERATE, CODE_REVIEW, SpecialistProposal

ROOT = pathlib.Path(__file__).resolve().parents[1]
TARGET = "atlas/evolution/structural_editor.py"
CONTENT = "def _indent_of(line: str) -> str:\n    return ''\n"


# ---------------------------------------------------------------------------
# Builders (real repository contracts only)
# ---------------------------------------------------------------------------


def _proposal(
    files=None,
    *,
    paths=None,
    capability=CODE_GENERATE,
    provider_id="http.code",
    payload_extra=None,
    confidence=0.5,
    note="proposed",
):
    payload: dict = {}
    if files is not None:
        payload["files"] = files
        payload["paths"] = sorted(files) if paths is None else paths
    if note is not None:
        payload["note"] = note
    if payload_extra:
        payload.update(payload_extra)
    return SpecialistProposal(
        provider_id=provider_id,
        capability=capability,
        payload=payload,
        confidence=confidence,
    )


def _need(proposal=None, *, metadata=None, target=TARGET):
    md = dict(metadata or {})
    if proposal is not None:
        md[SPECIALIST_PROPOSAL_KEY] = proposal
    return DevelopmentNeed(
        title="Change the helper",
        target_components=(target,) if target else (),
        metadata=md,
    )


def _supply(proposal=None, **need_kw):
    return SpecialistChangeSupplier().supply_changes(_need(proposal, **need_kw))


# ---------------------------------------------------------------------------
# 1-4. The happy path produces the EXISTING code-change representation
# ---------------------------------------------------------------------------


class TestValidProposal:
    def test_valid_proposal_yields_supplied_changes(self):
        supplied = _supply(_proposal({TARGET: CONTENT}))
        assert supplied is not None
        assert supplied.code_changes == ((TARGET, CONTENT),)
        assert supplied.origin == SPECIALIST_ORIGIN
        assert supplied.confidence == pytest.approx(0.5)
        assert supplied.notes == "proposed"

    def test_exact_declared_target_is_accepted(self):
        assert _supply(_proposal({TARGET: CONTENT}), target=TARGET) is not None

    def test_dotted_module_form_of_the_target_is_accepted(self):
        dotted = "atlas.evolution.structural_editor"
        assert _supply(_proposal({TARGET: CONTENT}), target=dotted) is not None

    def test_generated_supplied_changes_shape(self):
        supplied = _supply(_proposal({TARGET: CONTENT}))
        assert isinstance(supplied, SuppliedChanges)
        assert supplied.test_files == ()
        assert supplied.repository_context == ()
        assert 0.0 <= supplied.confidence <= 1.0

    def test_code_changes_representation(self):
        supplied = _supply(_proposal({TARGET: CONTENT}))
        assert isinstance(supplied.code_changes, tuple)
        assert len(supplied.code_changes) == 1
        path, content = supplied.code_changes[0]
        assert (path, content) == (TARGET, CONTENT)

    def test_it_is_a_change_supplier(self):
        assert isinstance(SpecialistChangeSupplier(), ChangeSupplier)


# ---------------------------------------------------------------------------
# 5-16. Fail-closed refusals (every refusal returns None, never raises)
# ---------------------------------------------------------------------------


class TestFailClosed:
    def test_missing_proposal_is_inert(self):
        assert SpecialistChangeSupplier().supply_changes(
            DevelopmentNeed(title="t", metadata={})
        ) is None
        assert SpecialistChangeSupplier().supply_changes(
            DevelopmentNeed(title="t")
        ) is None

    @pytest.mark.parametrize(
        "malformed",
        ["not a proposal", 123, ["a"], {"provider_id": "p"}, object()],
    )
    def test_malformed_proposal_is_refused(self, malformed):
        assert _supply(None, metadata={SPECIALIST_PROPOSAL_KEY: malformed}) is None

    def test_malformed_payload_is_refused(self):
        proposal = SpecialistProposal(
            provider_id="p", capability=CODE_GENERATE, payload="nope"
        )
        assert _supply(proposal) is None

    def test_wrong_capability_is_refused(self):
        assert _supply(_proposal({TARGET: CONTENT}, capability=CODE_REVIEW)) is None

    def test_missing_provider_identity_is_refused(self):
        assert _supply(_proposal({TARGET: CONTENT}, provider_id="   ")) is None

    def test_missing_files_is_refused(self):
        assert _supply(_proposal(None)) is None
        assert _supply(_proposal({})) is None

    def test_zero_files_is_refused(self):
        assert _supply(_proposal({})) is None

    def test_multiple_files_is_refused(self):
        files = {TARGET: CONTENT, "atlas/other.py": "x = 1\n"}
        assert _supply(_proposal(files)) is None

    def test_target_mismatch_is_refused(self):
        """The proposal's own declared paths must agree with its files."""
        proposal = _proposal({TARGET: CONTENT}, paths=["atlas/other.py"])
        assert _supply(proposal) is None

    def test_absolute_path_is_refused(self):
        assert _supply(_proposal({"/etc/passwd": CONTENT}), target=None) is None

    def test_windows_drive_path_is_refused(self):
        assert _supply(_proposal({"C:/Windows/x.py": CONTENT}), target=None) is None

    def test_traversal_is_refused(self):
        assert _supply(_proposal({"../outside.py": CONTENT}), target=None) is None

    def test_out_of_target_path_is_refused(self):
        assert _supply(_proposal({"atlas/kernel/atlas.py": CONTENT})) is None

    @pytest.mark.parametrize("content", [123, None, "", "   \n"])
    def test_invalid_content_is_refused(self, content):
        proposal = SpecialistProposal(
            provider_id="p",
            capability=CODE_GENERATE,
            payload={"files": {TARGET: content}, "paths": [TARGET]},
        )
        assert _supply(proposal) is None

    def test_non_string_path_is_refused(self):
        proposal = SpecialistProposal(
            provider_id="p",
            capability=CODE_GENERATE,
            payload={"files": {42: CONTENT}, "paths": [42]},
        )
        assert _supply(proposal) is None

    @pytest.mark.parametrize(
        "extra",
        [
            {"action": "execute"},
            {"execute": True},
            {"approve": True},
            {"promote": True},
            {"command": "rm -rf /"},
        ],
    )
    def test_unauthorized_action_metadata_is_refused(self, extra):
        assert _supply(_proposal({TARGET: CONTENT}, payload_extra=extra)) is None

    def test_unsupported_payload_field_is_refused(self):
        assert _supply(
            _proposal({TARGET: CONTENT}, payload_extra={"unexpected": "x"})
        ) is None

    def test_oversized_content_is_refused(self):
        big = "x = 1\n" * 10_000
        assert _supply(_proposal({TARGET: big})) is None


# ---------------------------------------------------------------------------
# 17. Deterministic / provider-disabled compatibility
# ---------------------------------------------------------------------------


class TestDeterministicCompatibility:
    def test_absent_proposal_leaves_the_deterministic_path_unchanged(self):
        composite = CompositeChangeSupplier(
            [DeterministicChangeSupplier(), SpecialistChangeSupplier()]
        )
        need = _need(
            metadata={"code_changes": [{"path": TARGET, "content": CONTENT}]}
        )
        supplied = composite.supply_changes(need)
        assert supplied is not None
        assert supplied.origin == "deterministic"
        assert supplied.code_changes == ((TARGET, CONTENT),)

    def test_a_need_with_no_evidence_still_yields_none(self):
        composite = CompositeChangeSupplier(
            [DeterministicChangeSupplier(), SpecialistChangeSupplier()]
        )
        assert composite.supply_changes(DevelopmentNeed(title="t")) is None

    def test_specialist_member_is_inert_without_a_proposal(self):
        assert SpecialistChangeSupplier().supply_changes(
            DevelopmentNeed(title="t", metadata={"code_changes": []})
        ) is None

    def test_a_valid_proposal_flows_through_the_composite(self):
        composite = CompositeChangeSupplier(
            [DeterministicChangeSupplier(), SpecialistChangeSupplier()]
        )
        supplied = composite.supply_changes(_need(_proposal({TARGET: CONTENT})))
        assert supplied is not None
        assert supplied.origin == SPECIALIST_ORIGIN

    def test_a_malformed_proposal_does_not_shadow_the_deterministic_author(self):
        """A bad proposal is refused, so the existing author still wins."""
        composite = CompositeChangeSupplier(
            [DeterministicChangeSupplier(), SpecialistChangeSupplier()]
        )
        need = _need(
            metadata={
                SPECIALIST_PROPOSAL_KEY: "broken",
                "code_changes": [{"path": TARGET, "content": CONTENT}],
            }
        )
        supplied = composite.supply_changes(need)
        assert supplied is not None
        assert supplied.origin == "deterministic"


# ---------------------------------------------------------------------------
# 18. Existing authoring regression
# ---------------------------------------------------------------------------


def _scaffold_need():
    return DevelopmentNeed(
        title="Add a capability",
        metadata={
            "scaffold": {
                "module": "atlas/example/example_handlers.py",
                "capability_name": "example.run",
            }
        },
    )


class TestExistingAuthoringRegression:
    def test_scaffold_route_is_unaffected(self):
        composite = CompositeChangeSupplier(
            [
                DeterministicChangeSupplier(),
                ScaffoldChangeSupplier(),
                SpecialistChangeSupplier(),
            ]
        )
        supplied = composite.supply_changes(_scaffold_need())
        assert supplied is not None
        assert supplied.origin == "deterministic-scaffold"

    def test_composite_still_requires_a_supplier(self):
        with pytest.raises(ValueError):
            CompositeChangeSupplier([])

    def test_kernel_composes_the_specialist_bridge(self):
        source = (ROOT / "atlas" / "kernel" / "atlas.py").read_text(
            encoding="utf-8"
        )
        assert "from atlas.evolution.specialist_change_supplier import" in source
        assert "SpecialistChangeSupplier()," in source


# ---------------------------------------------------------------------------
# Governed-pipeline consumption (the whole point of the seam)
# ---------------------------------------------------------------------------


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
            [DeterministicChangeSupplier(), SpecialistChangeSupplier()]
        ),
    )
    return controller, manager


class TestGovernedPipelineConsumption:
    def test_proposal_reaches_pending_approval(self):
        controller, _ = _controller()
        need = DevelopmentNeed(
            title="Change the helper",
            target_components=(TARGET,),
            evidence_change_ids=("ev::1",),  # direct evidence -> no research
            metadata={SPECIALIST_PROPOSAL_KEY: _proposal({TARGET: CONTENT})},
        )
        result = controller.run_development_cycle(need)
        assert result.decision == "prepared"
        assert result.proposal_status == ProposalStatus.PENDING_APPROVAL.name

    def test_draft_carries_specialist_origin_and_unverified_status(self):
        controller, manager = _controller()
        need = DevelopmentNeed(
            title="Change the helper",
            target_components=(TARGET,),
            evidence_change_ids=("ev::1",),
            metadata={SPECIALIST_PROPOSAL_KEY: _proposal({TARGET: CONTENT})},
        )
        controller.run_development_cycle(need)
        proposal = manager.proposals[-1]
        assert proposal.status is ProposalStatus.PENDING_APPROVAL
        assert proposal.metadata["code_changes"] == [
            {"path": TARGET, "content": CONTENT}
        ]
        cycle = proposal.metadata["development_cycle"]
        assert cycle["change_origin"] == SPECIALIST_ORIGIN
        assert cycle["content_status"] == "unverified-draft"

    def test_malformed_proposal_fails_the_cycle_closed(self):
        controller, _ = _controller()
        need = DevelopmentNeed(
            title="Change the helper",
            target_components=(TARGET,),
            evidence_change_ids=("ev::1",),
            metadata={SPECIALIST_PROPOSAL_KEY: {"files": {TARGET: CONTENT}}},
        )
        result = controller.run_development_cycle(need)
        assert result.decision == "failed"
        assert result.failures[0][0] == "supplier"


# ---------------------------------------------------------------------------
# Boundaries: no I/O, no governance surface, no repository mutation
# ---------------------------------------------------------------------------


class TestBoundaries:
    def test_module_imports_no_model_network_or_process_client(self):
        source = (
            ROOT / "atlas" / "evolution" / "specialist_change_supplier.py"
        ).read_text(encoding="utf-8")
        imported: set[str] = set()
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Import):
                imported.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        for forbidden in (
            "openai", "anthropic", "requests", "httpx", "socket",
            "subprocess", "shutil", "torch", "transformers",
        ):
            assert forbidden not in imported

    def test_module_touches_no_execution_or_governance_surface(self):
        source = (
            ROOT / "atlas" / "evolution" / "specialist_change_supplier.py"
        ).read_text(encoding="utf-8")
        for forbidden in (
            "approval_manager", "promotion_gate", "dispatcher",
            "execution_gateway", "self_development_loop", "code_execution",
        ):
            assert f"import {forbidden}" not in source

    def test_supplier_cannot_approve_promote_or_execute(self):
        supplier = SpecialistChangeSupplier()
        for forbidden in (
            "apply", "approve", "promote", "authorize", "execute", "run_tests",
        ):
            assert not hasattr(supplier, forbidden)

    def test_supplying_changes_does_not_touch_the_repository(self):
        before = (ROOT / TARGET).read_text(encoding="utf-8")
        _supply(_proposal({TARGET: CONTENT}))
        assert (ROOT / TARGET).read_text(encoding="utf-8") == before

    def test_the_proposal_is_never_a_decision(self):
        proposal = _proposal({TARGET: CONTENT})
        for forbidden in ("apply", "approve", "promote", "authorize", "execute"):
            assert not hasattr(proposal, forbidden)
