"""Phase 8.1 — Acquisition need interpretation: evidence contract.

Investigation result: the Phase-3/5/6 gap adjudicator (``assess_development_gap``)
distinguishes supported / missing-capability / missing-knowledge / unclear, but
does NOT distinguish dependency blockers or authorization. The smallest
deterministic acquisition-need classifier was therefore added at
``atlas/evolution/capability_acquisition.py`` (no second framework — it reuses
the existing capability/dependency/authorization surfaces).

It never infers a missing capability from vague text: a blank request or an
unbounded target is AMBIGUOUS.
"""

from __future__ import annotations

from atlas.evolution.capability_acquisition import (
    AcquisitionNeed,
    AcquisitionNeedKind,
    classify_acquisition_need,
)


def _need(**kw) -> AcquisitionNeed:
    kw.setdefault("request", "acquire a vector-search capability")
    kw.setdefault("target_capability", "widget.search")
    return AcquisitionNeed(**kw)


class TestPhase81AcquisitionNeed:
    def test_already_available(self):
        assert (
            classify_acquisition_need(_need(), capability_names=["widget.search"])
            is AcquisitionNeedKind.ALREADY_AVAILABLE
        )
        assert (
            classify_acquisition_need(
                _need(target_capability="echo"), tool_names=["echo"]
            )
            is AcquisitionNeedKind.ALREADY_AVAILABLE
        )

    def test_missing_implementation_when_know_how_exists(self):
        assert (
            classify_acquisition_need(_need(knowledge_available=True))
            is AcquisitionNeedKind.MISSING_IMPLEMENTATION
        )

    def test_missing_knowledge_when_no_validated_knowledge(self):
        assert (
            classify_acquisition_need(_need(knowledge_available=False))
            is AcquisitionNeedKind.MISSING_KNOWLEDGE
        )

    def test_missing_capability_when_undetermined(self):
        assert (
            classify_acquisition_need(_need())
            is AcquisitionNeedKind.MISSING_CAPABILITY
        )

    def test_unavailable_and_incompatible_dependencies(self):
        assert (
            classify_acquisition_need(
                _need(required_dependencies=("libx",), available_dependencies=())
            )
            is AcquisitionNeedKind.UNAVAILABLE_DEPENDENCY
        )
        # Incompatibility outranks unavailability.
        assert (
            classify_acquisition_need(
                _need(
                    required_dependencies=("libx",),
                    incompatible_dependencies=("libx",),
                    knowledge_available=True,
                )
            )
            is AcquisitionNeedKind.INCOMPATIBLE_DEPENDENCY
        )

    def test_unauthorized(self):
        assert (
            classify_acquisition_need(_need(authorized=False, knowledge_available=True))
            is AcquisitionNeedKind.UNAUTHORIZED
        )

    def test_ambiguous_requirements_fail_closed(self):
        assert (
            classify_acquisition_need(AcquisitionNeed(request="   "))
            is AcquisitionNeedKind.AMBIGUOUS
        )
        assert (
            classify_acquisition_need(AcquisitionNeed(request="do the thing"))
            is AcquisitionNeedKind.AMBIGUOUS
        )
