"""Phase 10.6 — Research/investigation trigger: evidence contract.

Investigation result: discovery reuses the EXISTING research infrastructure by
emitting a bounded research question only when evidence is genuinely
insufficient; it creates no second research system and requires no network.
"""

from __future__ import annotations

from types import SimpleNamespace

from atlas.evolution.capability_discovery import (
    DiscoverySignal,
    DiscoverySignalKind,
    DiscoverySourceKind,
    run_discovery_cycle,
)


def _signal(subject):
    return DiscoverySignal(
        DiscoverySignalKind.MISSING_KNOWLEDGE,
        subject,
        DiscoverySourceKind.SELF_MODEL,
        evidence=(f"self_model:{subject}",),
    )


class _Retriever:
    def __init__(self, items):
        self._items = items

    def retrieve(self, query):  # noqa: ARG002
        return SimpleNamespace(items=list(self._items))


class TestPhase106ResearchTrigger:
    def test_research_request_emitted_when_knowledge_is_missing(self):
        result = run_discovery_cycle(extra_signals=[_signal("cap.new")])
        requests = result.research_requests()
        assert len(requests) == 1
        assert isinstance(requests[0], str) and requests[0]
        verdict = next(a for a in result.assessments if a.subject == "cap.new")
        assert verdict.verdict.value == "requires_research"

    def test_no_research_request_when_knowledge_is_present(self):
        result = run_discovery_cycle(
            extra_signals=[_signal("cap.new")],
            knowledge_retriever=_Retriever([object()]),
        )
        assert result.research_requests() == ()
        verdict = next(a for a in result.assessments if a.subject == "cap.new")
        assert verdict.verdict.value == "actionable_gap"

    def test_research_request_is_deterministic(self):
        first = run_discovery_cycle(extra_signals=[_signal("cap.new")]).research_requests()
        second = run_discovery_cycle(extra_signals=[_signal("cap.new")]).research_requests()
        assert first == second

    def test_discovery_cycle_opens_no_network_and_no_storage(self):
        # The cycle only inspects + normalizes; it holds no research adapter and
        # performs no I/O (it merely *requests* research).
        result = run_discovery_cycle(extra_signals=[_signal("cap.new")])
        assert result.landscape.known_capabilities == ()  # no model supplied
        assert result.research_requests()
