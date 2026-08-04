"""Phase 17.7 — Research capability handler tests."""

import pytest

from atlas.reasoning.execution.registry import CapabilityRegistry
from atlas.research.capability_handlers import ResearchCapabilityFactory
from atlas.research.models import (
    ClaimVerification,
    KnowledgeClaim,
    ResearchReport,
    SourceProfile,
    SourceKind,
    VerificationStatus,
)


def make_profile(text="Atlas uses SQLite for persistent storage."):
    return SourceProfile(
        uri="docs/guide.md",
        kind=SourceKind.DOCUMENT,
        text=text,
        title="guide.md",
        language="markdown",
    )


def make_claim():
    return KnowledgeClaim(
        claim_id="claim:test:0001",
        statement="Atlas uses SQLite for persistent storage.",
    )


def make_report():
    claim = make_claim()
    verification = ClaimVerification(
        verification_id="verify:claim:test:0001",
        claim_id=claim.claim_id,
        status=VerificationStatus.SUPPORTED,
        score=0.85,
        metadata={"outcome": "VERIFIED", "supporting": ["s1"]},
    )
    return ResearchReport(
        report_id="report:test:1",
        plan_id="plan::test",
        query_id="test",
        question="What storage does Atlas use?",
        findings="verification summary: VERIFIED=1",
        confidence=0.85,
        claims=(claim,),
        verifications=(verification,),
    )


class TestRegistration:
    def test_three_capabilities_registered(self):
        factory = ResearchCapabilityFactory()
        registry = CapabilityRegistry()
        factory.register(registry)
        assert set(registry.registered_names) == {
            "research.query",
            "research.verify",
            "research.summarize",
        }

    def test_handlers_are_callables(self):
        handlers = ResearchCapabilityFactory().handlers()
        for name, handler in handlers.items():
            result = handler({"x": 1})
            assert result is not None


class TestResearchQuery:
    def test_requires_question(self):
        handler = ResearchCapabilityFactory().handlers()["research.query"]
        result = handler({})
        assert not result.success
        assert "'question' is required" in result.error

    def test_full_pipeline_with_profile_source(self, tmp_path):
        doc = tmp_path / "guide.md"
        doc.write_text(
            "Atlas uses SQLite for persistent storage across sessions.",
            encoding="utf-8",
        )
        factory = ResearchCapabilityFactory()
        handler = factory.handlers()["research.query"]
        result = handler(
            {
                "question": "What storage does Atlas use?",
                "query_id": "test-1",
                "sources": [str(doc)],
            }
        )
        assert result.success
        report = result.output["report"]
        assert report["question"] == "What storage does Atlas use?"
        assert len(report["claims"]) >= 1

    def test_deterministic_outputs(self):
        factory = ResearchCapabilityFactory()
        handler = factory.handlers()["research.query"]
        params = {
            "question": "What storage does Atlas use?",
            "query_id": "test-2",
            "sources": [],
        }
        first = handler(params)
        second = handler(params)
        assert first.success == second.success
        assert first.output["report"]["claims"] == second.output["report"]["claims"]


class TestResearchVerify:
    def test_requires_claims_list(self):
        handler = ResearchCapabilityFactory().handlers()["research.verify"]
        result = handler({"sources": []})
        assert not result.success

    def test_verify_runs(self):
        factory = ResearchCapabilityFactory()
        handler = factory.handlers()["research.verify"]
        profile = make_profile()
        result = handler(
            {
                "claims": [make_claim()],
                "sources": [profile],
            }
        )
        assert result.success
        assert len(result.output["verifications"]) == 1


class TestResearchSummarize:
    def test_requires_report(self):
        handler = ResearchCapabilityFactory().handlers()["research.summarize"]
        result = handler({})
        assert not result.success
        assert "ResearchReport" in result.error

    def test_summarize_report(self):
        factory = ResearchCapabilityFactory()
        handler = factory.handlers()["research.summarize"]
        result = handler({"report": make_report()})
        assert result.success
        assert "VERIFIED=1" in result.output["summary"]


class TestDependencyInjection:
    def test_custom_components_injected(self):
        from atlas.research.extractor import KnowledgeExtractor
        from atlas.research.planner import ResearchPlanner
        from atlas.research.verifier import ClaimVerifier

        factory = ResearchCapabilityFactory(
            planner=ResearchPlanner(),
            extractor=KnowledgeExtractor(),
            verifier=ClaimVerifier(),
        )
        assert factory.planner is not None
