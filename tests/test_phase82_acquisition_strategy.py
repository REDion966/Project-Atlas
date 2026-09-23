"""Phase 8.2 — Acquisition strategy determination: evidence contract.

Investigation result: no deterministic acquisition-strategy layer existed (the
DevelopmentDriver hard-codes the research+authoring path). The smallest
deterministic strategy layer was added at
``atlas/evolution/capability_acquisition.py``.

It selects only mechanisms Atlas genuinely supports (existing capability/tool,
internal governed development, researched internalization) and fails closed to
``NONE`` on ambiguous/unauthorized/dependency-blocked needs. It never asserts
authority — the strategy records the authorization/validation requirements.
"""

from __future__ import annotations

import json

from atlas.evolution.capability_acquisition import (
    AcquisitionMechanism,
    AcquisitionNeed,
    determine_acquisition_strategy,
)


def _need(**kw) -> AcquisitionNeed:
    kw.setdefault("request", "acquire a vector-search capability")
    kw.setdefault("target_capability", "widget.search")
    return AcquisitionNeed(**kw)


class TestPhase82AcquisitionStrategy:
    def test_internal_development_strategy_records_requirements(self):
        strategy = determine_acquisition_strategy(_need(knowledge_available=True))
        assert strategy.mechanism is AcquisitionMechanism.INTERNAL_DEVELOPMENT
        assert strategy.acquirable is True
        assert strategy.authorization_required is True
        assert strategy.prerequisites
        assert strategy.validation_required
        assert strategy.failure_conditions
        assert strategy.expected_resulting_capability == "widget.search"

    def test_researched_internalization_when_knowledge_is_missing(self):
        strategy = determine_acquisition_strategy(_need(knowledge_available=False))
        assert strategy.mechanism is AcquisitionMechanism.RESEARCHED_INTERNALIZATION
        assert "bounded research evidence" in strategy.prerequisites

    def test_existing_capability_needs_no_acquisition(self):
        strategy = determine_acquisition_strategy(
            _need(), capability_names=["widget.search"]
        )
        assert strategy.mechanism is AcquisitionMechanism.EXISTING_CAPABILITY
        assert strategy.authorization_required is False

    def test_existing_tool_mechanism(self):
        strategy = determine_acquisition_strategy(
            _need(target_capability="echo"), tool_names=["echo"]
        )
        assert strategy.mechanism is AcquisitionMechanism.EXISTING_TOOL

    def test_ambiguous_and_unauthorized_fail_closed(self):
        assert (
            determine_acquisition_strategy(AcquisitionNeed(request="do the thing")).mechanism
            is AcquisitionMechanism.NONE
        )
        assert (
            determine_acquisition_strategy(
                _need(authorized=False, knowledge_available=True)
            ).mechanism
            is AcquisitionMechanism.NONE
        )

    def test_dependency_blockers_fail_closed(self):
        unavailable = determine_acquisition_strategy(
            _need(required_dependencies=("libx",), available_dependencies=())
        )
        assert unavailable.mechanism is AcquisitionMechanism.NONE
        assert unavailable.failure_conditions

        incompatible = determine_acquisition_strategy(
            _need(incompatible_dependencies=("libx",), knowledge_available=True)
        )
        assert incompatible.mechanism is AcquisitionMechanism.NONE

    def test_strategy_is_json_safe(self):
        json.dumps(
            determine_acquisition_strategy(_need(knowledge_available=True)).to_dict(),
            sort_keys=True,
        )
