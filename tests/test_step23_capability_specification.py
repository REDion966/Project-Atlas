"""Step 23 — capability specification and development design.

Measured baseline (real Atlas/kernel, before any change): Step 22 produced a
terminal, read-only `CapabilityGap` and **nothing consumed it** — there was no
`capability_specification` API and no specification/design type anywhere
(`atlas/self_knowledge/capability_specification.py` did not exist). The closest
existing artifact, `AcquisitionStrategy`, is advisory only (mechanism,
prerequisites, verification, failure conditions) and is reachable only from
capability discovery, carrying no architecture grounding and no known-vs-unresolved
split; the EXISTING `DevelopmentPlanner.plan` accepts only an APPROVED proposal, so
a raw gap could not enter it.

Step 23 adds ONE bounded, deterministic, model-free layer that turns a CONFIRMED
genuine gap into a reviewable specification — reconciling the EXISTING Step 22 gap,
the EXISTING advisory acquisition strategy, the EXISTING architecture model and the
EXISTING governance boundary. It generates no implementation and grants no
authority.
"""

from __future__ import annotations

import json

import pytest

from atlas.self_knowledge.capability_gap import (
    CapabilityGap,
    CapabilityGapKind,
)
from atlas.self_knowledge.capability_specification import (
    CapabilitySpecification,
    SpecificationStatus,
    build_capability_specification,
)

_REQUEST = "Convert memory_service archive format"


def _gap(kind=CapabilityGapKind.UNSUPPORTED_CAPABILITY, **kwargs):
    base = dict(
        kind=kind,
        request=_REQUEST,
        boundary="unresolved_target",
        capability="",
        capability_state="",
        matched=(),
        requires=(),
        reason="no existing capability covers this request while its subject is known",
        evidence=("development_gap:missing_capability",),
    )
    base.update(kwargs)
    return CapabilityGap(**base)


class _Component:
    def __init__(self, name, package, module_path, dependencies=(), capabilities=()):
        self.name = name
        self.package = package
        self.module_path = module_path
        self.declared_dependencies = tuple(dependencies)
        self.provided_capabilities = tuple(capabilities)
        self.responsibility = "test component"
        self.status = "HEALTHY"
        self.capability_names = ()
        self.sources = ()
        self.limitations = ()


class _Locate:
    def __init__(self, found, packages=(), module_paths=(), module="", components=()):
        self.found = found
        self.packages = tuple(packages)
        self.module_paths = tuple(module_paths)
        self.module = module
        self.components = tuple(components)


class _Boundary:
    def __init__(self, capability, governing):
        self.capability = capability
        self.governing = governing
        self.reason = "requires the existing OWNER approval boundary"


class _KnowledgeBoundary:
    known = ("36 registered component(s)",)
    unknown = ("Interfaces/contracts are not represented.",)


class _Architecture:
    def __init__(self, resolved=None):
        self.components = (
            _Component(
                "memory_service",
                "atlas.memory.service",
                "atlas.memory.service.memory_manager_service",
                dependencies=("memory_repository", "ranking_engine"),
                capabilities=("memory_search",),
            ),
        )
        self.governance = (_Boundary("approve", "owner_approval"),)
        self.knowledge_boundary = _KnowledgeBoundary()
        self._resolved = resolved if resolved is not None else {
            "memory_service": _Locate(
                True,
                packages=("atlas.memory.service",),
                module_paths=("atlas.memory.service.memory_manager_service",),
                components=("memory_service",),
            ),
            "archive": _Locate(True, packages=("atlas.archive",), module_paths=("atlas.archive.zip",)),
        }

    def locate(self, query):
        return self._resolved.get(query, _Locate(False))


class _CapabilityEntry:
    def __init__(self, name):
        self.name = name


class _CapabilityModel:
    def __init__(self, names=("memory_search", "research")):
        self.entries = tuple(_CapabilityEntry(name) for name in names)


def _build(gap=None, architecture=None, model=None):
    return build_capability_specification(
        gap if gap is not None else _gap(),
        capability_model=model if model is not None else _CapabilityModel(),
        architecture_model=architecture if architecture is not None else _Architecture(),
    )


# ---------------------------------------------------------------------------
# 1. Genuine gap -> specification
# ---------------------------------------------------------------------------


class TestGenuineGap:
    def test_produces_a_specified_design(self):
        spec = _build()
        assert spec.status is SpecificationStatus.SPECIFIED
        assert spec.is_specified is True
        assert spec.request == _REQUEST
        assert spec.purpose == _REQUEST
        assert spec.capability  # a provisional name derived from the request
        assert spec.spec_id.startswith("spec:")

    def test_operations_and_purpose_are_bounded(self):
        spec = _build()
        assert spec.operations
        assert all(len(token) <= 300 for token in spec.operations)
        assert len(spec.operations) <= 6
        assert spec.purpose == _REQUEST

    def test_design_skeleton_reuses_the_existing_advisory_layer(self):
        spec = _build()
        # the EXISTING AcquisitionStrategy supplies mechanism + verification
        assert spec.mechanism == "internal_development"
        assert "DevelopmentVerification" in spec.verification
        assert spec.prerequisites
        assert spec.failure_conditions

    def test_constraints_come_from_the_architecture_scope_boundaries(self):
        spec = _build()
        joined = " ".join(spec.constraints)
        assert "Interfaces/contracts are not represented." in joined
        assert "grants no authority" in joined

    def test_governance_uses_the_existing_boundaries_and_invariants(self):
        spec = _build()
        assert "approve: owner_approval" in spec.governance
        assert any("OWNER approval" in item for item in spec.governance)
        assert any("sandbox-only" in item for item in spec.governance)

    def test_known_facts_and_unresolved_questions_are_separated(self):
        spec = _build()
        assert spec.known_facts
        assert spec.unresolved_questions
        joined_known = " ".join(spec.known_facts)
        joined_unresolved = " ".join(spec.unresolved_questions)
        assert "no existing capability covers this request" in joined_known
        assert "operation signature" in joined_unresolved
        # inputs/outputs are NOT invented
        assert spec.inputs == ()
        assert spec.outputs == ()
        assert "inputs and outputs are not yet established" in joined_unresolved


# ---------------------------------------------------------------------------
# 2. Architecture grounding
# ---------------------------------------------------------------------------


class TestArchitectureGrounding:
    def test_areas_and_dependencies_are_grounded(self):
        spec = _build()
        assert "atlas.memory.service.memory_manager_service" in spec.affected_areas
        assert "memory_repository" in spec.dependencies
        assert "ranking_engine" in spec.dependencies

    def test_multiple_candidate_hosts_are_listed_not_chosen(self):
        spec = _build()
        assert len(spec.options) >= 2
        assert set(spec.options) >= {"atlas.memory.service", "atlas.archive"}
        assert any("more than one candidate host" in item for item in spec.unresolved_questions)

    def test_unresolved_areas_stay_unresolved(self):
        spec = _build(architecture=_Architecture(resolved={}))
        assert spec.affected_areas == ()
        assert spec.dependencies == ()
        assert spec.options == ()
        joined = " ".join(spec.unresolved_questions)
        assert "owning architecture area is unresolved" in joined

    def test_no_architecture_model_is_reported_honestly(self):
        spec = build_capability_specification(
            _gap(), capability_model=_CapabilityModel(), architecture_model=None
        )
        assert spec.status is SpecificationStatus.SPECIFIED
        joined = " ".join(spec.unresolved_questions)
        assert "no architecture model was available" in joined


# ---------------------------------------------------------------------------
# 3. Provenance, determinism and bounds
# ---------------------------------------------------------------------------


class TestProvenanceAndDeterminism:
    def test_gap_provenance_is_preserved_verbatim(self):
        gap = _gap(evidence=("development_gap:missing_capability", "custom:evidence"))
        spec = _build(gap)
        assert spec.gap_kind == "unsupported_capability"
        assert spec.gap_boundary == "unresolved_target"
        assert spec.gap_reason == gap.reason
        assert spec.evidence == ("development_gap:missing_capability", "custom:evidence")

    def test_deterministic_and_serializable(self):
        first = _build()
        second = _build()
        assert first == second
        payload = first.to_dict()
        json.dumps(payload)
        assert payload["is_specified"] is True
        assert payload["status"] == "specified"

    def test_immutable_and_bounded(self):
        spec = _build()
        with pytest.raises(Exception):
            spec.status = SpecificationStatus.REFUSED  # type: ignore[misc]
        assert len(spec.constraints) <= 8
        assert len(spec.governance) <= 8
        assert len(spec.evidence) <= 8
        assert len(spec.unresolved_questions) <= 8
        assert all(len(item) <= 300 for item in spec.known_facts)


# ---------------------------------------------------------------------------
# 4. Refusals (fail-closed)
# ---------------------------------------------------------------------------


class TestRefusals:
    @pytest.mark.parametrize(
        "kind",
        [
            CapabilityGapKind.SUPPORTED,
            CapabilityGapKind.TEMPORARILY_BLOCKED,
            CapabilityGapKind.GOVERNED,
            CapabilityGapKind.MISSING_KNOWLEDGE,
            CapabilityGapKind.AMBIGUOUS,
            CapabilityGapKind.EXECUTION_FAILURE,
            CapabilityGapKind.UNKNOWN,
        ],
    )
    def test_non_gap_kinds_are_refused(self, kind):
        spec = _build(_gap(kind=kind))
        assert spec.status is SpecificationStatus.REFUSED
        assert spec.is_specified is False
        assert spec.reason
        # a refusal carries NO design
        assert spec.operations == ()
        assert spec.known_facts == ()
        assert spec.unresolved_questions == ()
        assert spec.constraints == ()
        assert spec.verification == ()
        assert spec.mechanism == ""

    def test_missing_knowledge_is_not_a_development_target(self):
        spec = _build(_gap(kind=CapabilityGapKind.MISSING_KNOWLEDGE))
        assert spec.status is SpecificationStatus.REFUSED
        assert "knowledge, not capability" in spec.reason

    def test_temporary_block_is_not_a_development_target(self):
        spec = _build(_gap(kind=CapabilityGapKind.TEMPORARILY_BLOCKED))
        assert "temporarily unavailable" in spec.reason

    def test_ambiguity_is_not_a_development_target(self):
        spec = _build(_gap(kind=CapabilityGapKind.AMBIGUOUS))
        assert "clarification precedes" in spec.reason

    def test_governance_is_not_a_development_target(self):
        spec = _build(_gap(kind=CapabilityGapKind.GOVERNED))
        assert "authorization, not design" in spec.reason

    def test_execution_failure_is_not_a_development_target(self):
        spec = _build(_gap(kind=CapabilityGapKind.EXECUTION_FAILURE))
        assert "execution failure" in spec.reason

    def test_supported_is_not_a_development_target(self):
        spec = _build(_gap(kind=CapabilityGapKind.SUPPORTED))
        assert "existing capability can handle" in spec.reason

    def test_ungrounded_input_is_refused(self):
        for bad in (None, "a string", {"kind": "unsupported_capability"}, object()):
            spec = build_capability_specification(
                bad, capability_model=_CapabilityModel(), architecture_model=_Architecture()
            )
            assert spec.status is SpecificationStatus.REFUSED
            assert "no grounded capability gap" in spec.reason

    def test_empty_request_is_refused(self):
        spec = _build(_gap(request=""))
        assert spec.status is SpecificationStatus.REFUSED
        assert "no request" in spec.reason

    def test_refusal_is_serializable(self):
        spec = _build(_gap(kind=CapabilityGapKind.MISSING_KNOWLEDGE))
        json.dumps(spec.to_dict())


# ---------------------------------------------------------------------------
# 5. Real Atlas/kernel validation
# ---------------------------------------------------------------------------


def _tmp_storage(monkeypatch, tmp_path):
    from atlas.storage.evolution_storage import SQLiteEvolutionStorage
    from atlas.storage.research_storage import ResearchSQLiteStorage

    class TmpEvolution(SQLiteEvolutionStorage):
        def __init__(self, db_path=None):  # noqa: D107 - test shim
            super().__init__(db_path=tmp_path / "evolution.db")

    class TmpResearch(ResearchSQLiteStorage):
        def __init__(self, db_path=None):  # noqa: D107 - test shim
            super().__init__(db_path=tmp_path / "research.db")

    monkeypatch.setattr("atlas.kernel.atlas.SQLiteEvolutionStorage", TmpEvolution)
    monkeypatch.setattr("atlas.kernel.atlas.ResearchSQLiteStorage", TmpResearch)


def _started_atlas(monkeypatch, tmp_path):
    _tmp_storage(monkeypatch, tmp_path)
    from atlas.kernel.atlas import Atlas

    atlas = Atlas()
    atlas.start()
    return atlas


def _seed(storage, claim_id, statement):
    from atlas.research.models import (
        CitationRecord,
        ClaimVerification,
        KnowledgeClaim,
        SourceKind,
        VerificationStatus,
    )

    uri = f"https://example.com/{claim_id}"
    storage.store_claim(
        KnowledgeClaim(
            claim_id=claim_id,
            statement=statement,
            citations=(
                CitationRecord(
                    record_id=f"cite:{claim_id}:0000",
                    source_uri=uri,
                    source_title=claim_id,
                    source_kind=SourceKind.WEB,
                    section="chunk:0000",
                ),
            ),
            confidence=0.8,
        )
    )
    storage.store_verification(
        ClaimVerification(
            verification_id=f"verify:{claim_id}",
            claim_id=claim_id,
            status=VerificationStatus.SUPPORTED,
            score=0.75,
            metadata={"outcome": "PLAUSIBLE", "supporting": [uri], "contradicting": []},
        )
    )


class TestRealKernel:
    def test_genuine_gap_produces_a_specification(self, monkeypatch, tmp_path):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            _seed(
                atlas._research_storage,
                "memory",
                "The memory_service convert archive format operation is documented.",
            )
            spec = atlas.capability_specification(_REQUEST)
            assert spec.status is SpecificationStatus.SPECIFIED
            assert spec.gap_kind == "unsupported_capability"
            assert spec.evidence  # the originating gap evidence is preserved
            assert spec.verification  # the existing advisory requirements
            assert spec.governance  # the existing governance boundary
        finally:
            atlas.shutdown()

    def test_non_gaps_are_refused(self, monkeypatch, tmp_path):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            assert atlas.capability_specification(
                "Summarize the Zorblax protocol"
            ).status is SpecificationStatus.REFUSED
            assert atlas.capability_specification(
                "Compress the repository into a zip archive"
            ).status is SpecificationStatus.REFUSED
            assert atlas.capability_specification(
                "Have an open-ended chat", capability="open_conversation"
            ).status is SpecificationStatus.REFUSED
            assert atlas.capability_specification(
                "Verify the development result", capability="verify"
            ).status is SpecificationStatus.REFUSED
            assert atlas.capability_specification(
                "Do it", ambiguous=True
            ).status is SpecificationStatus.REFUSED
            assert atlas.capability_specification(
                "Summarize the Zorblax protocol", execution_failed=True
            ).status is SpecificationStatus.REFUSED
            assert atlas.capability_specification("").status is (
                SpecificationStatus.REFUSED
            )
        finally:
            atlas.shutdown()

    def test_repository_map_grounds_areas_dependencies_and_options(
        self, monkeypatch, tmp_path
    ):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            _seed(
                atlas._research_storage,
                "memory",
                "The memory_service convert archive format operation is documented.",
            )
            _ = atlas.repository_map  # the map is built once, as the planner does
            spec = atlas.capability_specification(_REQUEST)
            assert spec.status is SpecificationStatus.SPECIFIED
            assert any(
                area.startswith("atlas.memory.service") for area in spec.affected_areas
            )
            assert spec.dependencies
            assert len(spec.options) >= 2  # alternatives listed, not chosen
        finally:
            atlas.shutdown()

    def test_no_authority_no_mutation(self, monkeypatch, tmp_path):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            storage = atlas._research_storage
            _seed(storage, "memory", "The memory_service convert archive format operation is documented.")
            before = (
                len(storage.load_claims()),
                len(storage.load_verifications()),
                len(storage.load_citations()),
                len(storage.load_reports()),
            )
            spec = atlas.capability_specification(_REQUEST)
            assert spec.is_specified is True
            after = (
                len(storage.load_claims()),
                len(storage.load_verifications()),
                len(storage.load_citations()),
                len(storage.load_reports()),
            )
            assert after == before
            assert atlas.pending_promotion_reviews() == []
        finally:
            atlas.shutdown()

    def test_deterministic(self, monkeypatch, tmp_path):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            _seed(atlas._research_storage, "memory", "The memory_service convert archive format operation is documented.")
            first = atlas.capability_specification(_REQUEST)
            second = atlas.capability_specification(_REQUEST)
            assert first.to_dict() == second.to_dict()
        finally:
            atlas.shutdown()

    def test_steps_1_to_22_preserved(self, monkeypatch, tmp_path):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            question = "What is the current release of the Zorblax protocol?"
            assert atlas.knowledge_need(question).kind.value == "missing"
            outcome = atlas.research_knowledge_need(question)
            assert atlas.research_provenance(outcome).claims == ()
            assert atlas.knowledge_retention(outcome).records == ()
            assert atlas.retained_knowledge(question).status.value == "empty"
            assert atlas.temporal_knowledge(question).entries == ()
            assert atlas.refresh_requests(question) == ()
            assert atlas.monitor_knowledge(question).observations == ()
            assert atlas.capability_gap(question).is_gap is False
            assert atlas.capability_contract("research")["state"] == "available"
            assert atlas.chat("Is research available?").metadata[
                "builtin_intent"
            ] == "capability_state"
        finally:
            atlas.shutdown()
