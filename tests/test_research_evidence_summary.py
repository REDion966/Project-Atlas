"""Stage F1 — research evidence summarizer unit tests.

Pure-logic coverage for ``atlas/research/evidence_summary.py``:
determinism, bounding, fail-soft handling of malformed inputs, JSON
safety, and the import boundary (stdlib + existing research modules only).
"""

import json

import pytest

from atlas.research.acquisition import (
    AcquisitionResult,
    SourceEvidence,
)
from atlas.research.evidence_summary import (
    empty_summary,
    summarize_acquisition,
)


def _acquisition(**overrides):
    base = dict(
        acquisition_id="ACQ-1",
        decision="research",
        status="ok",
        query_id="Q-1",
        question="How does the ranking engine work?",
        findings="Ranking uses recency + confidence. " * 40,
        sources=("code://atlas/memory/ranking.py", "https://example.com/a"),
        confidence=0.82,
        report_ids=("RPT-1",),
        claim_count=7,
        verification_count=5,
        verification_statuses=("verified", "verified"),
        source_evidence=(
            SourceEvidence(
                source_uri="code://atlas/memory/ranking.py",
                total_claims=4,
                supporting_claims=3,
            ),
        ),
        failures=(("web", "timeout"),),
        elapsed_seconds=1.234,
        completed_at=datetime(2026, 8, 26, 12, 0, 0),
    )
    base.update(overrides)
    return AcquisitionResult(**base)


from datetime import datetime  # noqa: E402


class TestNormalSummary:
    def test_normal_summary_shape(self):
        summary = summarize_acquisition(_acquisition())
        assert summary["acquisition_id"] == "ACQ-1"
        assert summary["status"] == "ok"
        assert summary["decision"] == "research"
        assert summary["question"] == "How does the ranking engine work?"
        assert summary["confidence"] == pytest.approx(0.82)
        assert summary["claim_count"] == 7
        assert len(summary["sources"]) == 2
        assert summary["completed_at"] == "2026-08-26T12:00:00"

    def test_findings_truncation(self):
        summary = summarize_acquisition(
            _acquisition(), max_findings_chars=50
        )
        assert len(summary["findings"]) == 50
        full = summarize_acquisition(_acquisition())
        assert summary["findings"] == full["findings"][:50]

    def test_source_cap(self):
        sources = tuple(f"src://{i}" for i in range(12))
        summary = summarize_acquisition(
            _acquisition(sources=sources), max_sources=3
        )
        assert summary["sources"] == ["src://0", "src://1", "src://2"]
        assert summary["truncated_sources"] is True

    def test_no_truncation_flags_when_under_caps(self):
        summary = summarize_acquisition(_acquisition())
        assert summary["truncated_sources"] is False


class TestDeterminismAndSafety:
    def test_deterministic_output(self):
        first = summarize_acquisition(_acquisition())
        second = summarize_acquisition(_acquisition())
        assert first == second

    def test_malformed_object_returns_empty_summary(self):
        class _Junk:
            def to_dict(self):
                raise RuntimeError("junk")

        summary = summarize_acquisition(_Junk())
        assert summary == empty_summary()

    def test_none_input_returns_empty_summary(self):
        assert summarize_acquisition(None) == empty_summary()

    def test_to_dict_returning_non_dict(self):
        class _Weird:
            def to_dict(self):
                return ["not", "a", "dict"]

        summary = summarize_acquisition(_Weird())
        assert summary["status"] == ""

    def test_invalid_bounds_fall_back_safely(self):
        summary = summarize_acquisition(_acquisition(), max_sources=-1)
        assert summary == empty_summary()

    def test_partial_fields_tolerated(self):
        class _Partial:
            def to_dict(self):
                return {"status": "noop"}  # most keys missing

        summary = summarize_acquisition(_Partial())
        assert summary["status"] == "noop"
        assert summary["claim_count"] == 0
        assert summary["confidence"] == 0.0


class TestEmptySummaryAndJson:
    def test_empty_summary_shape(self):
        empty = empty_summary("some question")
        assert empty == {
            "question": "some question",
            "status": "",
            "decision": "",
            "confidence": 0.0,
            "findings": "",
            "sources": [],
            "claim_count": 0,
            "report_id": "",
            "truncated_sources": False,
        }

    def test_summary_is_json_serializable(self):
        payload = json.dumps(summarize_acquisition(_acquisition()))
        data = json.loads(payload)
        assert data["acquisition_id"] == "ACQ-1"


# ---------------------------------------------------------------------------
# Import boundary — stdlib + existing research models only
# ---------------------------------------------------------------------------


def test_import_boundary():
    """Only stdlib + existing research modules may be imported."""
    import ast
    import inspect

    import atlas.research.evidence_summary as module

    tree = ast.parse(inspect.getsource(module))
    imported_roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_roots.add(node.module.split(".")[0])

    allowed = {
        "__future__",
        "dataclasses",
        "typing",
        "atlas",  # atlas.research.* only — enforced below
    }
    unexpected = imported_roots - allowed
    assert not unexpected, f"forbidden imports: {sorted(unexpected)}"

    # Within atlas, only atlas.research may be touched.
    from atlas.research.repository_map import RepositoryMap  # noqa: F401

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.module.startswith("atlas."):
                assert node.module.startswith("atlas.research."), node.module