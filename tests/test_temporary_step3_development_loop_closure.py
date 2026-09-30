"""Temporary Roadmap Step 3 — self-development loop closure.

Pins the Step-3 integration between the conversational layer and the EXISTING
development pipeline: a natural-language development request now consults the
existing capability-gap adjudication (Step 22), the capability specification
(Step 23) and the existing governed development bridge (Step 24) before anything
is prepared, and the full authorized chain (design -> bounded payload -> OWNER
approval -> sandbox implementation -> focused tests -> verification -> promotion
review) is demonstrated end to end from a natural-language request.

Nothing here grants authority: understanding a development request never
authorizes implementation, and no model is consulted.
"""

from __future__ import annotations

import pkgutil
import socket
from pathlib import Path

import pytest

import atlas.storage as storage_pkg

REPO_ROOT = Path(__file__).resolve().parents[1]

#: The validated claim that makes the subject KNOWN (the frozen L1 rule needs a
#: three-token subject overlap for the gap adjudicator to claim a capability gap).
AUDIT_CLAIM = (
    "audit",
    "The audit_log records every governed action with a timestamp and actor, and "
    "it keeps an archive copy of every audit_log record.",
)

GAP_REQUEST = "Add a capability that compresses the audit_log archive records."

PASS_CODE = "VALUE = 42\n"
PASS_TEST = (
    "from sandbox_mod import VALUE\n\n\ndef test_value():\n    assert VALUE == 42\n"
)


def _patch_stores(monkeypatch, tmp_path):
    db = tmp_path / "kernel.db"
    for info in pkgutil.iter_modules(storage_pkg.__path__):
        try:
            module = __import__(f"atlas.storage.{info.name}", fromlist=["*"])
        except Exception:  # noqa: BLE001
            continue
        for attr in dir(module):
            obj = getattr(module, attr)
            if isinstance(obj, type) and hasattr(obj, "DEFAULT_DB_PATH"):
                monkeypatch.setattr(obj, "DEFAULT_DB_PATH", db)


@pytest.fixture
def kernel(tmp_path, monkeypatch):
    _patch_stores(monkeypatch, tmp_path)
    from atlas.kernel.atlas import Atlas

    atlas = Atlas()
    atlas.start()
    try:
        _seed(atlas)
        yield atlas
    finally:
        atlas.shutdown()


def _seed(atlas):
    from atlas.research.models import (
        CitationRecord,
        ClaimVerification,
        KnowledgeClaim,
        SourceKind,
        VerificationStatus,
    )

    cid, statement = AUDIT_CLAIM
    uri = f"https://example.org/{cid}"
    atlas._research_storage.store_claim(
        KnowledgeClaim(
            claim_id=cid,
            statement=statement,
            citations=(
                CitationRecord(
                    record_id=f"cite:{cid}:0000",
                    source_uri=uri,
                    source_title=cid,
                    source_kind=SourceKind.WEB,
                    section="chunk:0000",
                ),
            ),
            confidence=0.8,
        )
    )
    atlas._research_storage.store_verification(
        ClaimVerification(
            verification_id=f"verify:{cid}",
            claim_id=cid,
            status=VerificationStatus.SUPPORTED,
            score=0.75,
            metadata={"outcome": "PLAUSIBLE", "supporting": [uri], "contradicting": []},
        )
    )


def _meta(message):
    return getattr(message, "metadata", {}) or {}


class TestGenuineGapReachesThePipeline:
    def test_natural_language_gap_produces_a_bounded_design(self, kernel):
        message = kernel.chat(GAP_REQUEST)
        content = message.content
        assert "Existing capability/knowledge adjudication" in content
        assert "- Verdict: unsupported_capability" in content
        assert "Bounded capability design" in content
        assert "- Capability: `" in content
        assert "- Purpose: " in content
        assert "- Operations: " in content
        assert "- Required verification:" in content
        assert "- Governance boundary:" in content
        assert "- Next governed step:" in content
        # the existing driver route still runs and reports its own truthful outcome
        assert _meta(message).get("development_driver") is not None

    def test_the_design_comes_from_the_existing_specification_surface(self, kernel):
        specification = kernel.capability_specification(GAP_REQUEST)
        assert specification.is_specified
        message = kernel.chat(GAP_REQUEST)
        assert f"`{specification.capability}`" in message.content

    def test_the_gap_request_is_a_real_capability_gap(self, kernel):
        gap = kernel.capability_gap(GAP_REQUEST)
        assert gap.kind.value == "unsupported_capability"
        assert gap.is_gap is True

    def test_nothing_is_authorized_or_executed_by_understanding(self, kernel):
        head = _git_head()
        message = kernel.chat(GAP_REQUEST)
        assert kernel.pending_promotion_reviews() == []
        assert _meta(message).get("model_used") in (None, False)
        assert _git_head() == head


class TestNoManufacturedDevelopment:
    """The adjudication may not claim a gap that the existing surface covers, and
    nothing may be executed, approved or promoted without the OWNER."""

    def test_reported_verdict_matches_the_existing_adjudicator(self, kernel):
        """Criterion 2 — the report never disagrees with the adjudicator, and it
        never claims a gap the existing surface covers."""

        for text in (
            "Add the research capability.",
            "Develop a capability to research a topic.",
            "Add a capability that compresses the Glorptronic feed.",
        ):
            expected = kernel.capability_gap(text).kind.value
            message = kernel.chat(text)
            assert f"- Verdict: {expected}" in message.content
            assert "Bounded capability design" not in message.content
            assert "Nothing is approved, executed, or promoted" in message.content
            assert kernel.pending_promotion_reviews() == []

    def test_a_non_gap_verdict_is_never_turned_into_a_design(self, kernel):
        text = "Add a capability that compresses the Glorptronic feed."
        assert kernel.capability_gap(text).kind.value == "missing_knowledge"
        assert kernel.capability_specification(text).is_specified is False
        message = kernel.chat(text)
        assert "missing_knowledge" in message.content
        assert "Bounded capability design" not in message.content

    def test_existing_capability_request_leaves_the_repository_untouched(self, kernel):
        head = _git_head()
        kernel.chat("Add the research capability.")
        assert _git_head() == head
        assert kernel.pending_promotion_reviews() == []
        assert not (REPO_ROOT / "sandbox_mod.py").exists()

    def test_unknown_subject_is_reported_as_missing_knowledge(self, kernel):
        message = kernel.chat("Add a capability that compresses the Glorptronic feed.")
        assert "- Verdict: missing_knowledge" in message.content
        assert "Nothing is approved, executed, or promoted" in message.content
        assert kernel.pending_promotion_reviews() == []

    def test_no_development_is_executed_or_promoted(self, kernel):
        head = _git_head()
        for text in (
            "Develop a capability to research a topic.",
            "Add a capability that compresses the Glorptronic feed.",
            "Add a capability.",
        ):
            message = kernel.chat(text)
            assert "Nothing is approved, executed, or promoted" in message.content
            driver = _meta(message).get("development_driver") or {}
            assert driver.get("execution_status", "") == ""
            assert driver.get("promotion_request_id", "") == ""
            assert kernel.pending_promotion_reviews() == []
        assert _git_head() == head


class TestAmbiguityAndGovernance:
    def test_underspecified_request_fails_closed_honestly(self, kernel):
        head = _git_head()
        message = kernel.chat("Add a capability.")
        assert "Nothing is approved, executed, or promoted" in message.content
        driver = _meta(message).get("development_driver") or {}
        assert driver.get("terminal") == "author_unavailable"
        assert driver.get("proposal_id", "") == ""
        assert kernel.pending_promotion_reviews() == []
        assert _git_head() == head

    def test_governance_crossing_request_never_develops_or_executes(self, kernel):
        head = _git_head()
        for text in (
            "Add a capability that approves proposals without an owner.",
            "Develop a capability that promotes changes automatically.",
        ):
            message = kernel.chat(text)
            assert "Nothing is approved, executed, or promoted" in message.content
            driver = _meta(message).get("development_driver") or {}
            assert driver.get("execution_status", "") == ""
            assert driver.get("promotion_request_id", "") == ""
            assert "PROMOTED" not in message.content
            assert kernel.pending_promotion_reviews() == []
        assert _git_head() == head

    def test_existing_driver_api_is_unchanged(self, kernel):
        result = kernel.run_development_driver(GAP_REQUEST)
        assert result.terminal.value in {
            "proposed",
            "envelope_disabled",
            "author_unavailable",
            "insufficient_evidence",
            "validated",
            "already_supported",
            "failed",
        }
        assert kernel.pending_promotion_reviews() == []


class TestAuthorizedEndToEnd:
    """The complete chain from a natural-language request, through the EXISTING
    OWNER approval, sandbox implementation, focused tests and verification."""

    def test_request_to_verified_change_is_governed_end_to_end(self, kernel):
        head = _git_head()

        # 1. natural language -> existing gap adjudication -> bounded design
        specification = kernel.capability_specification(GAP_REQUEST)
        assert specification.is_specified, "the request must reach a design"

        # 2. implementation cannot start before an authorization exists
        prepared = kernel.specification_development(
            specification,
            code_changes=(("sandbox_mod.py", PASS_CODE),),
            test_files=(("test_sandbox_mod.py", PASS_TEST),),
            target_components=("sandbox_mod",),
        )
        assert prepared.stage.value == "awaiting_approval"
        assert prepared.proposal_id.startswith("DEV-")
        assert _git_head() == head

        # 3. the EXISTING OWNER approval boundary, then the governed execution
        kernel.confirm_development_approval(
            kernel.session_context, prepared.proposal_id
        )
        result = kernel.specification_development(
            specification, proposal_id=prepared.proposal_id
        )
        assert result.authorized is True
        assert result.stage.value == "promotion_review"
        assert result.execution_status == "SUCCESS"  # code was produced AND ran
        assert result.verification_status == "verified"  # focused tests passed
        assert result.changed_files == ("sandbox_mod.py",)
        assert result.promotion_request_id  # promotion remains a separate OWNER step

        # 4. the sandbox boundary held: the live repository is untouched
        assert _git_head() == head
        assert not (REPO_ROOT / "sandbox_mod.py").exists()
        assert any(
            review.get("proposal_id") == prepared.proposal_id
            for review in kernel.pending_promotion_reviews()
        )

    def test_failed_focused_tests_are_not_promotable(self, kernel):
        failing_test = "def test_fail():\n    assert False\n"
        specification = kernel.capability_specification(GAP_REQUEST)
        prepared = kernel.specification_development(
            specification,
            code_changes=(("sandbox_mod.py", PASS_CODE),),
            test_files=(("test_sandbox_mod.py", failing_test),),
            target_components=("sandbox_mod",),
        )
        kernel.confirm_development_approval(
            kernel.session_context, prepared.proposal_id
        )
        result = kernel.specification_development(
            specification, proposal_id=prepared.proposal_id
        )
        assert result.stage.value == "not_promotable"
        assert result.promotion_request_id == ""
        assert kernel.pending_promotion_reviews() == []


class TestConversationalParityAndIndependence:
    def test_stream_and_send_agree(self, kernel):
        """The same user request yields the same design and the same terminal.

        The driver report also carries per-invocation identifiers (a new proposal
        and approval request are created per call), so the comparison is the
        design block, the route line and the outcome.
        """

        def _key_lines(content):
            lines = [line for line in content.splitlines() if line.strip()]
            design = []
            for line in lines:
                if line.startswith("Governed self-development request routed"):
                    break
                design.append(line)
            route = next(
                (
                    line
                    for line in lines
                    if line.startswith("Governed self-development")
                ),
                "",
            )
            outcome = next(
                (line for line in lines if line.startswith("- Outcome:")), ""
            )
            return tuple(design), route, outcome

        for text in (
            GAP_REQUEST,
            "Develop a capability to research a topic.",
            "Add a capability.",
        ):
            sent = _key_lines(kernel.chat(text).content)
            streamed = _key_lines("".join(kernel.stream(text)))
            assert sent == streamed

    def test_no_network_and_no_model_authority(self, kernel, monkeypatch):
        def _blocked(*args, **kwargs):
            raise AssertionError("no network access is allowed")

        monkeypatch.setattr(socket.socket, "connect", _blocked)
        for text in (
            GAP_REQUEST,
            "Develop a capability to research a topic.",
            "Add a capability.",
        ):
            message = kernel.chat(text)
            assert _meta(message).get("model_used") in (None, False)


def _git_head() -> str:
    import subprocess

    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    ).stdout.strip()
