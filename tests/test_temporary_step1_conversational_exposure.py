"""Temporary Roadmap Step 1 — conversational exposure policy & precedence.

Pins the bounded policy (what internal/self-knowledge state may be exposed
conversationally), the ownership/precedence rules that keep internal-state
questions away from the generic knowledge route, and the fail-closed behaviour of
every surface the policy exposes.

Every answer is projected from an EXISTING read-only seam: nothing here acquires,
authorizes, executes, promotes, configures or mutates anything, and no model is
ever consulted.
"""

from __future__ import annotations

import pkgutil
import socket
from pathlib import Path

import pytest

import atlas.storage as storage_pkg
from atlas.conversation import builtin_response as br
from atlas.conversation.builtin_response import (
    BUILTIN_INTENT_CAPABILITY_DETAIL,
    BUILTIN_INTENT_KNOWLEDGE_STATE,
    BUILTIN_INTENT_SOURCE_AUTHORIZATION,
    BUILTIN_INTENT_UNSUPPORTED,
    EXPOSED_INTERNAL_SURFACES,
    EXPOSURE_POLICY_RULE,
    EXPOSURE_PRECEDENCE,
    BuiltinResponseService,
)

REPO_ROOT = Path(__file__).resolve().parents[1]

MEMORY_CLAIM = (
    "memory_claim",
    "The memory_service stores conversation transcripts and supports archive export.",
)


# ---------------------------------------------------------------------------
# Fakes (pure tests — no kernel): a temporal seam and a capability model
# ---------------------------------------------------------------------------


class _V:
    """Enum-like wrapper (the real model projects ``.value`` objects)."""

    def __init__(self, value):
        self.value = value


class _Entry:
    def __init__(self, name, **kw):
        self.name = name
        self.kind = _V(kw.get("kind", "operational"))
        self.state = kw.get("state", "available")
        self.reason = kw.get("reason", "registered and healthy")
        self.availability = _V(kw.get("availability", "available"))
        self.dependency = _V(kw.get("dependency", "deterministic"))
        self.governing = kw.get("governing", "")
        self.blocked_by = tuple(kw.get("blocked_by", ()))
        self.requires = tuple(kw.get("requires", ()))
        self.inputs = tuple(kw.get("inputs", ()))
        self.operations = tuple(kw.get("operations", ()))
        self.sources = ()
        self.limitations = ()


class _Model:
    def __init__(self, entries=()):
        self.entries = tuple(entries)

    def find(self, name):
        for entry in self.entries:
            if entry.name == name:
                return entry
        return None


class _TemporalEntry:
    def __init__(self, claim_id, status, *, age_days=None, standing="supported"):
        self.claim_id = claim_id
        self.status = status
        self.age_days = age_days
        self.standing = standing


class _Temporal:
    def __init__(self, status, *, entries=(), message=""):
        self.status = status
        self.entries = tuple(entries)
        self.message = message


def _service(*, temporal=None, model=None, provider_wired=True):
    provider = None
    if provider_wired:
        provider = (lambda query: temporal)
    return BuiltinResponseService(
        capability_model_provider=(lambda: model) if model is not None else None,
        knowledge_state_provider=provider,
    )


# ---------------------------------------------------------------------------
# 1. The exposure policy itself (acceptance criteria 1, 4, 5)
# ---------------------------------------------------------------------------


class TestExposurePolicy:
    def test_policy_states_the_bounded_rule(self):
        assert EXPOSURE_POLICY_RULE
        lowered = EXPOSURE_POLICY_RULE.lower()
        for phrase in (
            "existing",
            "read-only",
            "representation",
            "never authority",
            "registered",
            "declined",
            "explanation",
        ):
            assert phrase in lowered

    def test_exposed_surfaces_are_all_in_the_precedence_order(self):
        ids = [surface for surface, _seam in EXPOSED_INTERNAL_SURFACES]
        assert ids
        for surface in ids:
            assert surface in EXPOSURE_PRECEDENCE

    def test_internal_state_precedes_generic_knowledge(self):
        order = list(EXPOSURE_PRECEDENCE)
        internal_state = (
            "capability_detail",
            "capability_state",
            "architecture",
            "self_knowledge",
            "knowledge_state",
            "source_authorization",
        )
        for surface in internal_state:
            # an internal-state question is claimed before BOTH generic
            # knowledge layers (the knowledge-request route and the floor's
            # validated-knowledge surface)
            assert order.index(surface) < order.index("knowledge_request")
            assert order.index(surface) < order.index("validated_knowledge")
        # the governed surfaces keep their own (unchanged) order
        assert order.index("investigation") < order.index("development")
        assert order.index("development") < order.index("unsupported_floor")

    def test_every_exposed_surface_names_a_real_read_only_seam(self):
        import importlib

        for surface, seam in EXPOSED_INTERNAL_SURFACES:
            module = seam.rsplit(".", 2)[0] if seam.count(".") == 2 else seam
            # the named module must exist (no invented surface)
            importlib.import_module(module)
            assert surface

    def test_policy_intents_exist(self):
        assert BUILTIN_INTENT_KNOWLEDGE_STATE == "knowledge_state"
        assert BUILTIN_INTENT_SOURCE_AUTHORIZATION == "source_authorization"

    def test_new_route_is_registered_in_the_operational_catalogue(self):
        from atlas.self_knowledge.operational_capabilities import (
            MAX_OPERATIONAL_CAPABILITIES,
            all_operational_capabilities,
            find_operational_capability,
        )

        caps = all_operational_capabilities()
        assert len(caps) <= MAX_OPERATIONAL_CAPABILITIES
        entry = find_operational_capability("knowledge_freshness")
        assert entry is not None
        assert "atlas.research.temporal" in entry.evidence


# ---------------------------------------------------------------------------
# 2. Knowledge-state (freshness) surface
# ---------------------------------------------------------------------------


class TestKnowledgeStateSurface:
    def _fresh_service(self):
        temporal = _Temporal(
            "ok",
            entries=(
                _TemporalEntry("c1", "current_relative", age_days=2.0),
                _TemporalEntry("c2", "historical", age_days=400.0, standing="verified"),
            ),
            message="2 validated (SUPPORTED) claim(s) matched the query.",
        )
        return _service(temporal=temporal), temporal

    @pytest.mark.parametrize(
        "text",
        [
            "Is your knowledge about the invoice_ledger still current?",
            "Is your knowledge about the invoice_ledger up to date?",
            "Is your knowledge about the invoice_ledger stale?",
            "How current is the invoice_ledger knowledge?",
            "How fresh is the invoice_ledger information?",
            "How fresh is the invoice_ledger information you hold?",
            "Has your knowledge about the invoice_ledger gone stale?",
        ],
    )
    def test_bounded_freshness_forms_are_claimed(self, text):
        service, _ = self._fresh_service()
        message = service.match_knowledge_state_question(text)
        assert message is not None
        assert message.metadata["builtin_intent"] == BUILTIN_INTENT_KNOWLEDGE_STATE
        assert message.metadata["model_used"] is False
        assert "Knowledge state" in message.content

    def test_answer_reports_the_seams_own_verdict(self):
        service, _ = self._fresh_service()
        message = service.match_knowledge_state_question(
            "Is your knowledge about the invoice_ledger still current?"
        )
        assert "current_relative" in message.content
        assert "historical" in message.content
        assert "age ~2 day(s)" in message.content
        assert "standing verified" in message.content
        assert message.metadata["knowledge_state"]["entries"] == 2

    def test_empty_subject_scope_is_reported_honestly(self):
        service, _ = self._fresh_service()
        message = service.match_knowledge_state_question(
            "Is your knowledge about the Zorblax archive still current?"
        )
        # the seam's verdict is what is rendered; the subject is preserved verbatim
        assert message is not None
        assert "zorblax archive" in message.content
        assert message.metadata["knowledge_state"]["subject"] == "zorblax archive"

    def test_no_retained_knowledge_is_not_a_freshness_claim(self):
        service = _service(temporal=_Temporal("empty", message="No query matched."))
        message = service.match_knowledge_state_question(
            "Is your knowledge about the Zorblax archive still current?"
        )
        assert message is not None
        assert "no freshness to report" in message.content
        assert "fresh" not in message.content.split("no freshness to report")[0].lower()

    def test_missing_evidence_never_becomes_freshness(self):
        service = _service(
            temporal=_Temporal("ok", entries=(_TemporalEntry("c1", "undated"),))
        )
        message = service.match_knowledge_state_question(
            "Is your knowledge about the invoice_ledger still current?"
        )
        assert "undated" in message.content
        assert "never treated" in message.content

    def test_unwired_seam_declines(self):
        service = _service(provider_wired=False)
        assert (
            service.match_knowledge_state_question(
                "Is your knowledge about the invoice_ledger still current?"
            )
            is None
        )

    def test_raising_seam_fails_closed_honestly(self):
        def _boom(query):
            raise RuntimeError("seam exploded")

        service = BuiltinResponseService(knowledge_state_provider=_boom)
        message = service.match_knowledge_state_question(
            "Is your knowledge about the invoice_ledger still current?"
        )
        assert message is not None
        assert message.metadata["builtin_intent"] == BUILTIN_INTENT_UNSUPPORTED
        assert "will not claim" in message.content

    @pytest.mark.parametrize(
        "text",
        [
            "What do you know about the invoice_ledger?",
            "Get me the latest information about the invoice_ledger.",
            "Research the invoice_ledger archive format.",
            "What is the latest stable release of PostgreSQL?",
            "Is the deployment pipeline healthy?",
            "Has the deployment_certificate guidance gone stale?",
            "",
            "   ",
        ],
    )
    def test_non_freshness_turns_are_not_claimed(self, text):
        service, _ = self._fresh_service()
        assert service.match_knowledge_state_question(text) is None

    def test_ambiguous_targets_are_not_claimed(self):
        service, _ = self._fresh_service()
        for text in ("Is your knowledge stale?", "Do it.", "Is it current?"):
            result = service.match_knowledge_state_question(text)
            if result is not None:
                # only the bounded subjectless form may answer, honestly
                assert (
                    result.metadata["builtin_intent"] == BUILTIN_INTENT_KNOWLEDGE_STATE
                )


# ---------------------------------------------------------------------------
# 3. Capability requirements (same owner as capability-detail)
# ---------------------------------------------------------------------------


class TestCapabilityRequirements:
    def _service(self):
        model = _Model(
            [
                _Entry(
                    "research",
                    state="governed",
                    reason="governed by the OWNER approval boundary",
                    governing="owner_approval",
                    blocked_by=("approve",),
                    dependency="deterministic",
                    availability="available",
                ),
                _Entry("noop", state="available"),
            ]
        )
        return _service(model=model)

    @pytest.mark.parametrize(
        "text",
        [
            "What does the research capability require?",
            "What does research need?",
            "What does the research capability need?",
            "What are the prerequisites of the research capability?",
            "Which inputs does the research capability accept?",
        ],
    )
    def test_requirement_forms_are_claimed_by_the_detail_surface(self, text):
        message = self._service().match_capability_requirements(text)
        assert message is not None
        assert message.metadata["builtin_intent"] == BUILTIN_INTENT_CAPABILITY_DETAIL
        assert "Requirements for `research`" in message.content
        assert message.metadata["model_used"] is False

    def test_requirements_report_the_contract_fields(self):
        message = self._service().match_capability_requirements(
            "What does the research capability require?"
        )
        assert "Current state: governed" in message.content
        assert "Blocked by: approve" in message.content
        assert "owner_approval" in message.content
        assert "Dependency: deterministic" in message.content
        assert "nothing was executed, authorized or changed" in message.content

    def test_undeclared_prerequisites_are_not_invented(self):
        message = self._service().match_capability_requirements(
            "What does the noop capability require?"
        )
        assert message is not None
        assert "No blocking prerequisite is declared" in message.content

    @pytest.mark.parametrize(
        "text",
        [
            "What does the Frobnitz capability require?",
            "What are the prerequisites of the Zorblax capability?",
            "Research the invoice_ledger archive format.",
            "Explain the research capability.",
            "",
        ],
    )
    def test_unresolvable_or_other_turns_are_not_claimed(self, text):
        assert self._service().match_capability_requirements(text) is None

    def test_plain_detail_phrasing_still_works(self):
        # the pre-existing capability-detail cue family is unchanged
        assert (
            self._service().match_capability_requirements(
                "Explain the research capability."
            )
            is None
        )


# ---------------------------------------------------------------------------
# 4. Source authorization: explain, never change
# ---------------------------------------------------------------------------


class TestSourceAuthorizationExplanation:
    @pytest.mark.parametrize(
        "text",
        [
            "Authorize wikipedia.org as a research source.",
            "Authorize the host docs.python.org for research.",
            "Allow example.net to be used for research.",
            "Add example.org to the allowed research hosts.",
            "Allowlist api.github.com for web research.",
            "Please authorise docs.python.org as a research source.",
        ],
    )
    def test_source_authorization_requests_are_explained(self, text):
        message = _service().match_source_authorization_question(text)
        assert message is not None
        assert message.metadata["builtin_intent"] == BUILTIN_INTENT_SOURCE_AUTHORIZATION
        assert message.metadata["source_authorization"]["changed"] is False
        assert message.metadata["source_authorization"]["authority"] == "none"
        assert "DENY-BY-DEFAULT" in message.content
        assert "OWNER" in message.content
        assert "Nothing was authorized or changed" in message.content

    def test_explanation_discloses_no_configured_value(self):
        message = _service().match_source_authorization_question(
            "Authorize the host docs.python.org for research."
        )
        assert message is not None
        # the policy is explained; configured entries are NOT disclosed
        assert "api.github.com" not in message.content
        assert "raw.githubusercontent.com" not in message.content

    @pytest.mark.parametrize(
        "text",
        [
            "Authorize this proposal.",
            "Approve the pending development proposal now.",
            "I approve this proposal.",
            "Approve the plan.",
            "Accept this proposal.",
            "",
        ],
    )
    def test_development_approval_is_never_claimed(self, text):
        assert _service().match_source_authorization_question(text) is None


# ---------------------------------------------------------------------------
# 5. Real Atlas/kernel: routing, precedence, governance
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
                metadata={
                    "outcome": "PLAUSIBLE",
                    "supporting": [uri],
                    "contradicting": [],
                },
            )
        )


def _intent(message):
    return (getattr(message, "metadata", {}) or {}).get("builtin_intent")


class TestRealKernelRouting:
    def test_freshness_question_reaches_the_internal_state_surface(self, kernel):
        _seed(kernel, (MEMORY_CLAIM,))
        head_before = _git_head()
        message = kernel.chat(
            "Is your knowledge about the memory_service still current?"
        )
        assert _intent(message) == BUILTIN_INTENT_KNOWLEDGE_STATE
        assert "Knowledge state" in message.content
        assert message.metadata["model_used"] is False
        # read-only: nothing acquired, executed, promoted or changed
        assert kernel.pending_promotion_reviews() == []
        assert _git_head() == head_before

    def test_freshness_question_is_not_answered_by_generic_knowledge(self, kernel):
        _seed(kernel, (MEMORY_CLAIM,))
        message = kernel.chat("How fresh is the memory_service information you hold?")
        assert _intent(message) == BUILTIN_INTENT_KNOWLEDGE_STATE
        assert _intent(message) != "validated_knowledge"

    def test_unknown_subject_reports_no_retained_knowledge(self, kernel):
        _seed(kernel, (MEMORY_CLAIM,))
        message = kernel.chat(
            "Is your knowledge about the Glorptronic pipeline still current?"
        )
        assert _intent(message) == BUILTIN_INTENT_KNOWLEDGE_STATE
        assert "no freshness to report" in message.content

    def test_capability_requirements_reach_the_detail_surface(self, kernel):
        message = kernel.chat("What does the research capability require?")
        assert _intent(message) == BUILTIN_INTENT_CAPABILITY_DETAIL
        assert "Requirements for `research`" in message.content

    def test_generic_knowledge_answers_are_unchanged(self, kernel):
        _seed(kernel, (MEMORY_CLAIM,))
        message = kernel.chat("What do you know about the memory_service?")
        assert _intent(message) == "validated_knowledge"

    def test_research_requests_are_not_stolen_by_the_state_surface(self, kernel):
        message = kernel.chat("Get me the latest information about the memory_service.")
        assert _intent(message) != BUILTIN_INTENT_KNOWLEDGE_STATE

    def test_source_authorization_is_explained_not_performed(self, kernel):
        message = kernel.chat("Authorize wikipedia.org as a research source.")
        assert _intent(message) == BUILTIN_INTENT_SOURCE_AUTHORIZATION
        assert kernel.pending_promotion_reviews() == []

    def test_development_approval_is_not_hijacked(self, kernel):
        message = kernel.chat("Authorize this proposal.")
        assert _intent(message) != BUILTIN_INTENT_SOURCE_AUTHORIZATION

    def test_capability_state_and_architecture_ownership_is_unchanged(self, kernel):
        state = kernel.chat("Is the research capability available right now?")
        assert _intent(state) == "capability_state"
        owner = kernel.chat("Who is responsible for the sandbox?")
        assert _intent(owner) == "self_knowledge"

    def test_investigation_and_development_routes_are_unchanged(self, kernel):
        from atlas.conversation.task_intake import TaskIntake, TaskType

        intake = TaskIntake()
        investigation = intake.intake("Investigate the approval flow.")
        assert investigation.task_type is TaskType.INVESTIGATION_REQUEST
        approval = intake.intake("Authorize this proposal.")
        assert approval.task_type is TaskType.APPROVAL

    def test_no_network_is_used(self, kernel, monkeypatch):
        def _blocked(*args, **kwargs):
            raise AssertionError("no network access is allowed")

        monkeypatch.setattr(socket.socket, "connect", _blocked)
        _seed(kernel, (MEMORY_CLAIM,))
        for text in (
            "Is your knowledge about the memory_service still current?",
            "What does the research capability require?",
            "Authorize wikipedia.org as a research source.",
        ):
            message = kernel.chat(text)
            assert message.metadata["model_used"] is False


def _git_head() -> str:
    import subprocess

    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    ).stdout.strip()
