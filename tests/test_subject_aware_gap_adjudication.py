"""Subject-aware capability-gap adjudication — post-roadmap L1 fix.

Reproduces and pins the authorized improvement to
``atlas.evolution.development_gap``: the knowledge half of the gap decision now
asks whether validated knowledge is held about the request's SUBJECT (strict
whole-request retrieval first, then a bounded fallback probe) instead of requiring
the request as a whole to restate a claim.

Every test here is a regression for one promise of that change:
short known-subject forms and their natural full-sentence equivalents must reach
the SAME verdict, unknown subjects must stay protected, nothing may fail less
closed than before, and the strict retrieval path must be byte-compatible.
"""

from __future__ import annotations

import pkgutil
from pathlib import Path

import pytest

import atlas.storage as storage_pkg
from atlas.evolution import development_gap as dg
from atlas.evolution.development_gap import (
    MAX_SUBJECT_PROBES,
    MIN_SUBJECT_SHARED_TOKENS,
    DevelopmentGapAssessment,
    DevelopmentGapKind,
    _probe_tokens,
    assess_development_gap,
)
from atlas.research.validated_retrieval import ValidatedKnowledgeRetriever

REPO_ROOT = Path(__file__).resolve().parents[1]

# The validated claims used throughout (the investigation's store).
MEMORY_CLAIM = (
    "c1_memory",
    "The memory_service stores conversation transcripts and supports archive export.",
)
AUDIT_CLAIM = (
    "c2_audit",
    "The audit_log records every governed action with a timestamp and actor.",
)
GENERIC_CLAIM = (
    "c3_generic",
    "The conversion format for generated reports is documented in the reporting guide.",
)

#: The exact previously-failing natural-language request from the investigation.
SENTENCE = "Convert the memory_service archive to parquet format."

#: Known subject + no matching capability -> the genuine gap.
KNOWN_SUBJECT_REQUESTS = [
    ("short form", "memory_service archive"),
    ("short form", "memory_service"),
    ("sentence", SENTENCE),
    (
        "sentence + filler",
        "Please convert my memory_service archive into a parquet file for me.",
    ),
    ("sentence", "Export the memory_service transcripts to PDF."),
]

#: Unknown or adversarial subjects -> never a capability gap.
UNKNOWN_SUBJECT_REQUESTS = [
    "What is the latest stable release of PostgreSQL?",
    "Summarize the documentation for the Frobnitz scheduler.",
    "Convert the Zorblax archive to parquet format.",
    "Tell me about the Glorptronic pipeline.",
    "Convert the Glorptronic reports format to PDF.",
]


# ---------------------------------------------------------------------------
# Harness: a real retriever over a controlled, WRITE-INTOLERANT storage
# ---------------------------------------------------------------------------


class _Storage:
    """Read-only storage stub; records any unexpected (write) attribute access."""

    def __init__(self, claims=(), *, available=True, error=None):
        from atlas.research.models import (
            ClaimVerification,
            KnowledgeClaim,
            VerificationStatus,
        )

        self.unexpected: list[str] = []
        self._claims = [
            KnowledgeClaim(
                claim_id=cid, statement=statement, citations=(), confidence=0.8
            )
            for cid, statement in claims
        ]
        self._verifications = [
            ClaimVerification(
                verification_id=f"verify:{cid}",
                claim_id=cid,
                status=VerificationStatus.SUPPORTED,
                score=0.75,
            )
            for cid, _statement in claims
        ]
        self._available = available
        self._error = error

    def is_available(self):
        return self._available

    def load_claims(self):
        if self._error is not None:
            raise self._error
        return list(self._claims)

    def load_verifications(self):
        if self._error is not None:
            raise self._error
        return list(self._verifications)

    def __getattr__(self, name):
        # Any attribute other than the three read methods is an attempted write.
        object.__getattribute__(self, "unexpected").append(name)
        raise AttributeError(name)


class _RecordingRetriever:
    """Wraps a real retriever and records every query it is asked."""

    def __init__(self, inner):
        self.inner = inner
        self.queries: list[str] = []

    def retrieve(self, query):
        self.queries.append(query)
        return self.inner.retrieve(query)


class _StrictRetriever:
    """Fails the whole-request lookup, so the fallback path is exercised."""

    def retrieve(self, query):
        raise AssertionError(f"unexpected strict query {query!r}")


def _retriever(claims=(MEMORY_CLAIM, AUDIT_CLAIM, GENERIC_CLAIM), **kwargs):
    return ValidatedKnowledgeRetriever(_Storage(claims, **kwargs))


class _Entry:
    def __init__(self, name, state="available", requires=()):
        self.name = name
        self.state = state
        self.requires = tuple(requires)


class _Model:
    def __init__(self, entries):
        self.entries = tuple(entries)

    def find(self, name):
        for entry in self.entries:
            if entry.name == name:
                return entry
        return None


def _base(kind: DevelopmentGapKind, matched=()):
    return DevelopmentGapAssessment(kind=kind, matched=tuple(matched))


# ---------------------------------------------------------------------------
# 1. The strict path is unchanged (behaviour and evidence string)
# ---------------------------------------------------------------------------


class TestStrictPathUnchanged:
    def test_strict_match_still_wins_and_uses_the_legacy_evidence_string(self):
        retriever = _RecordingRetriever(_retriever())
        present, evidence = dg._knowledge_present(retriever, "memory_service archive")
        assert present is True
        assert evidence == "validated knowledge matches=1 status=ok"
        assert retriever.queries == ["memory_service archive"]  # no probe needed

    def test_strict_match_short_circuits_the_fallback_probe(self):
        retriever = _RecordingRetriever(_retriever())
        dg._knowledge_present(retriever, "audit_log")
        assert len(retriever.queries) == 1

    def test_no_retriever_wired_is_unchanged(self):
        assert dg._knowledge_present(None, "anything") == (
            False,
            "no knowledge retriever wired",
        )

    def test_retriever_exception_is_unchanged(self):
        class _Boom:
            def retrieve(self, query):
                raise RuntimeError("store exploded")

        present, evidence = dg._knowledge_present(_Boom(), "anything")
        assert present is False
        assert evidence == "knowledge lookup failed (RuntimeError)"


# ---------------------------------------------------------------------------
# 2. Known subject: short form and full sentence now agree
# ---------------------------------------------------------------------------


class TestKnownSubject:
    @pytest.mark.parametrize("label, text", KNOWN_SUBJECT_REQUESTS)
    def test_short_and_sentence_forms_both_report_missing_capability(self, label, text):
        assessment = assess_development_gap(text, knowledge_retriever=_retriever())
        assert assessment.kind is DevelopmentGapKind.MISSING_CAPABILITY, label

    def test_sentence_evidence_records_the_probe_and_shared_tokens(self):
        retriever = _RecordingRetriever(_retriever())
        present, evidence = dg._knowledge_present(
            retriever, "Convert the memory_service archive to parquet format."
        )
        assert present is True
        assert evidence.startswith("subject probe=")
        assert "shared_tokens=" in evidence
        # the strict whole-request probe is always first
        assert retriever.queries[0] == SENTENCE

    def test_identifier_normalization_matches_underscored_and_spaced_forms(self):
        # The request writes `audit_log`; the claim writes `audit log`.
        claims = [("c", "The audit log archive entries are documented.")]
        present, evidence = dg._knowledge_present(
            _retriever(claims), "Compress the audit_log archive entries."
        )
        assert present is True
        assert "shared_tokens=" in evidence

    def test_subject_known_needs_three_shared_tokens_not_two(self):
        # Exactly two shared tokens is NOT enough evidence of a known subject.
        two = [("c", "The archive format guide is documented.")]
        three = [("c", "The archive format parquet guide is documented.")]
        not_known, _ = dg._knowledge_present(
            _retriever(two), "Convert archive format zip."
        )
        known, _ = dg._knowledge_present(
            _retriever(three), "Convert archive format parquet."
        )
        assert not_known is False
        assert known is True

    def test_threshold_constant_is_the_conservative_one(self):
        assert MIN_SUBJECT_SHARED_TOKENS == 3


# ---------------------------------------------------------------------------
# 3. Unknown / adversarial subjects remain protected
# ---------------------------------------------------------------------------


class TestUnknownSubjectProtection:
    @pytest.mark.parametrize("text", UNKNOWN_SUBJECT_REQUESTS)
    def test_unknown_subjects_stay_missing_knowledge(self, text):
        assessment = assess_development_gap(text, knowledge_retriever=_retriever())
        assert assessment.kind is DevelopmentGapKind.MISSING_KNOWLEDGE

    @pytest.mark.parametrize("text", UNKNOWN_SUBJECT_REQUESTS)
    def test_unknown_subjects_never_become_a_gap(self, text):
        assessment = assess_development_gap(text, knowledge_retriever=_retriever())
        assert assessment.kind is not DevelopmentGapKind.MISSING_CAPABILITY

    def test_unknown_subject_evidence_records_the_probes(self):
        assessment = assess_development_gap(
            "Convert the Glorptronic reports format to PDF.",
            knowledge_retriever=_retriever(),
        )
        assert "probes=[" in assessment.evidence

    def test_empty_store_is_missing_knowledge(self):
        assessment = assess_development_gap(
            "Convert the memory_service archive to parquet format.",
            knowledge_retriever=_retriever(()),
        )
        assert assessment.kind is DevelopmentGapKind.MISSING_KNOWLEDGE


# ---------------------------------------------------------------------------
# 4. Boundedness and determinism of the fallback probe
# ---------------------------------------------------------------------------


class TestBoundedProbe:
    def test_probe_order_is_longest_then_alphabetical_and_capped(self):
        probes = _probe_tokens(
            "Convert the memory_service archive to parquet format please quickly"
        )
        assert len(probes) == MAX_SUBJECT_PROBES
        assert probes == tuple(
            sorted(probes, key=lambda t: (-len(t), t))
        )
        assert probes[0] == "memory_service"  # longest wins

    def test_probe_tokens_are_deduplicated_and_short_requests_yield_fewer(self):
        assert len(_probe_tokens("archive archive ARCHIVE")) == 1
        assert len(_probe_tokens("zip")) <= MAX_SUBJECT_PROBES

    def test_fallback_performs_at_most_three_extra_lookups(self):
        retriever = _RecordingRetriever(_retriever())
        dg._knowledge_present(
            retriever,
            "Please convert my memory_service archive into a parquet file for me today",
        )
        assert len(retriever.queries) <= 1 + MAX_SUBJECT_PROBES

    def test_verdict_and_evidence_are_stable_across_calls(self):
        request = "Convert the memory_service archive to parquet format."
        first = assess_development_gap(request, knowledge_retriever=_retriever())
        second = assess_development_gap(request, knowledge_retriever=_retriever())
        assert first.kind is second.kind
        assert first.evidence == second.evidence

    def test_the_lookup_is_read_only(self):
        storage = _Storage([MEMORY_CLAIM])
        dg._knowledge_present(
            ValidatedKnowledgeRetriever(storage),
            "Convert the memory_service archive to parquet format.",
        )
        assert storage.unexpected == []

    def test_a_failing_probe_is_simply_not_evidence(self):
        class _Flaky:
            def __init__(self):
                self.calls = 0

            def retrieve(self, query):
                self.calls += 1
                if self.calls == 1:  # strict lookup succeeds but finds nothing
                    return ValidatedKnowledgeRetriever(_Storage(())).retrieve(query)
                raise RuntimeError("probe failed")

        present, evidence = dg._knowledge_present(
            _Flaky(), "Convert the memory_service archive to parquet format."
        )
        assert present is False
        assert "probes=[" in evidence


# ---------------------------------------------------------------------------
# 5. Fail-closed behaviour is unchanged
# ---------------------------------------------------------------------------


class TestFailClosed:
    @pytest.mark.parametrize("bad", ["", "   ", None, 42, [], {}])
    def test_malformed_or_empty_request_is_unclear(self, bad):
        assert (
            assess_development_gap(bad, knowledge_retriever=_retriever()).kind
            is DevelopmentGapKind.UNCLEAR
        )

    @pytest.mark.parametrize("bad", ["", "   ", None, 42])
    def test_no_significant_tokens_is_unclear(self, bad):
        assessment = assess_development_gap(bad, knowledge_retriever=_retriever())
        assert assessment.kind is DevelopmentGapKind.UNCLEAR

    def test_store_unavailable_is_missing_knowledge(self):
        assessment = assess_development_gap(
            "Convert the memory_service archive to parquet format.",
            knowledge_retriever=_retriever(available=False),
        )
        assert assessment.kind is DevelopmentGapKind.MISSING_KNOWLEDGE

    def test_store_error_is_missing_knowledge(self):
        assessment = assess_development_gap(
            "Convert the memory_service archive to parquet format.",
            knowledge_retriever=_retriever(error=RuntimeError("io")),
        )
        assert assessment.kind is DevelopmentGapKind.MISSING_KNOWLEDGE

    def test_no_retriever_at_all_is_missing_knowledge(self):
        assessment = assess_development_gap(
            "Convert the memory_service archive to parquet format.",
            knowledge_retriever=None,
        )
        assert assessment.kind is DevelopmentGapKind.MISSING_KNOWLEDGE

    def test_capability_absence_is_still_required(self):
        """A matched capability still wins — the probe cannot manufacture a gap."""
        with_capability = assess_development_gap(
            "research memory_service",
            capability_names=("research",),
            knowledge_retriever=_retriever(),
        )
        assert with_capability.kind is DevelopmentGapKind.ALREADY_SUPPORTED


# ---------------------------------------------------------------------------
# 6. Step 22 precedence is preserved
# ---------------------------------------------------------------------------


class TestStep22Precedence:
    def _assess(self, **kwargs):
        from atlas.self_knowledge.capability_gap import assess_capability_gap

        model = kwargs.pop("model", None) or _Model(
            [
                _Entry("investigate", "partially_supported"),
                _Entry("verify", "governed"),
                _Entry("execute", "blocked", ("approve",)),
            ]
        )
        return assess_capability_gap(
            "Convert the memory_service archive to parquet format.",
            capability_model=model,
            knowledge_retriever=_retriever(),
            **kwargs,
        )

    def test_known_subject_reaches_unsupported_capability(self):
        gap = self._assess()
        assert gap.kind.value == "unsupported_capability"
        assert gap.boundary == "unresolved_target"

    def test_ambiguous_outranks_the_subject_escalation(self):
        gap = self._assess(ambiguous=True)
        assert gap.kind.value == "ambiguous"

    def test_governed_capability_outranks_the_subject_escalation(self):
        gap = self._assess(
            development_gap=_base(DevelopmentGapKind.ALREADY_SUPPORTED, ("verify",))
        )
        assert gap.kind.value == "governed"

    def test_blocked_capability_outranks_the_subject_escalation(self):
        gap = self._assess(
            development_gap=_base(DevelopmentGapKind.ALREADY_SUPPORTED, ("execute",))
        )
        assert gap.kind.value == "temporarily_blocked"
        assert gap.requires == ("approve",)

    def test_partially_supported_capability_is_unavailability(self):
        base = _base(DevelopmentGapKind.ALREADY_SUPPORTED, ("investigate",))
        gap = self._assess(development_gap=base)
        assert gap.kind.value == "temporarily_blocked"

    def test_execution_failure_outranks_the_subject_escalation(self):
        from atlas.self_knowledge.capability_gap import assess_capability_gap

        model = _Model([_Entry("research", "available")])
        gap = assess_capability_gap(
            "Convert the memory_service archive to parquet format.",
            capability_model=model,
            knowledge_retriever=_retriever(),
            development_gap=_base(DevelopmentGapKind.ALREADY_SUPPORTED, ("research",)),
            execution_failed=True,
        )
        assert gap.kind.value == "execution_failure"

    def test_unknown_subject_stays_missing_knowledge(self):
        gap = self._assess(development_gap=_base(DevelopmentGapKind.MISSING_KNOWLEDGE))
        assert gap.kind.value == "missing_knowledge"

    def test_no_capability_model_is_unknown(self):
        from atlas.self_knowledge.capability_gap import assess_capability_gap

        gap = assess_capability_gap(SENTENCE, capability_model=None)
        assert gap.kind.value == "unknown"

    def test_empty_request_is_unknown(self):
        from atlas.self_knowledge.capability_gap import assess_capability_gap

        gap = assess_capability_gap("", capability_model=_Model([_Entry("x")]))
        assert gap.kind.value == "unknown"


# ---------------------------------------------------------------------------
# 7. Real Atlas/kernel: the exact previously failing requests
# ---------------------------------------------------------------------------


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
        yield atlas
    finally:
        atlas.shutdown()


def _seed(atlas, claims):
    from atlas.research.models import (
        CitationRecord,
        ClaimVerification,
        KnowledgeClaim,
        SourceKind,
        VerificationStatus,
    )

    for cid, statement in claims:
        uri = f"https://example.com/{cid}"
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
                metadata={
                    "outcome": "PLAUSIBLE",
                    "supporting": [uri],
                    "contradicting": [],
                },
            )
        )


SEED = (MEMORY_CLAIM, AUDIT_CLAIM, GENERIC_CLAIM)
SENTENCE = "Convert the memory_service archive to parquet format."


class TestRealKernel:
    def test_sentence_now_reaches_the_step22_gap_path(self, kernel):
        _seed(kernel, SEED)
        gap = kernel.capability_gap(SENTENCE)
        assert gap.kind.value == "unsupported_capability"
        assert gap.boundary == "unresolved_target"

    def test_short_form_still_reaches_the_step22_gap_path(self, kernel):
        _seed(kernel, SEED)
        assert kernel.capability_gap("memory_service archive").kind.value == (
            "unsupported_capability"
        )

    @pytest.mark.parametrize(
        "phrase",
        [
            "memory_service archive",
            SENTENCE,
            "Please convert my memory_service archive into a parquet file for me.",
            "Export the memory_service transcripts to PDF.",
        ],
    )
    def test_short_and_sentence_forms_agree_through_the_kernel(self, kernel, phrase):
        _seed(kernel, SEED)
        assert kernel.capability_gap(phrase).kind.value == "unsupported_capability"

    @pytest.mark.parametrize("phrase", UNKNOWN_SUBJECT_REQUESTS)
    def test_unknown_subjects_stay_missing_through_the_kernel(self, kernel, phrase):
        _seed(kernel, SEED)
        assert kernel.capability_gap(phrase).kind.value == "missing_knowledge"

    def test_step23_specification_only_for_the_genuine_gap(self, kernel):
        _seed(kernel, SEED)
        assert kernel.capability_specification(SENTENCE).status.value == "specified"
        for phrase in UNKNOWN_SUBJECT_REQUESTS:
            assert kernel.capability_specification(phrase).status.value == "refused"

    def test_step25_reaches_the_existing_waiting_state(self, kernel):
        _seed(kernel, SEED)
        loop = kernel.integrated_loop(SENTENCE)
        assert loop.status.value == "awaiting_input"
        assert loop.action.value == "provide_change_payload"
        assert loop.specification is not None
        assert loop.specification.is_specified

    def test_step25_never_executes_or_authorizes_from_the_escalation(self, kernel):
        _seed(kernel, SEED)
        head = _git_head()
        loop = kernel.integrated_loop(SENTENCE)
        assert loop.executed is False
        assert loop.verified is False
        assert loop.promotable is False
        assert loop.proposal_id == ""  # no proposal without an explicit payload
        assert kernel.pending_promotion_reviews() == []
        assert _git_head() == head

    def test_step25_unknown_subject_is_answered_without_development(self, kernel):
        _seed(kernel, SEED)
        loop = kernel.integrated_loop("Convert the Zorblax archive to parquet format.")
        assert loop.status.value == "answered"
        assert loop.specification is None
        assert loop.executed is False

    def test_driver_consumer_uses_the_same_classification(self, kernel):
        _seed(kernel, SEED)
        names = tuple(e.name for e in kernel.capability_model().entries)
        retriever = ValidatedKnowledgeRetriever(kernel._research_storage)
        for phrase in ("memory_service archive", SENTENCE):
            assessment = assess_development_gap(
                phrase, capability_names=names, knowledge_retriever=retriever
            )
            assert assessment.kind is DevelopmentGapKind.MISSING_CAPABILITY

    def test_driver_run_stays_fail_closed_and_creates_no_execution(self, kernel):
        _seed(kernel, SEED)
        head = _git_head()
        result = kernel.run_development_driver(SENTENCE)
        assert result.terminal.value in {
            "author_unavailable",
            "proposed",
            "envelope_disabled",
            "failed",
        }
        assert kernel.pending_promotion_reviews() == []
        assert _git_head() == head

    def test_knowledge_answer_surface_is_unchanged(self, kernel):
        _seed(kernel, SEED)
        # the strict, contract-bound retrieval must behave exactly as before
        strict = kernel.validated_knowledge("memory_service archive")
        assert strict.status.value == "ok" and len(strict.items) == 1
        empty = kernel.validated_knowledge(SENTENCE)
        assert empty.status.value == "empty" and len(empty.items) == 0


def _git_head() -> str:
    import subprocess

    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    ).stdout.strip()
