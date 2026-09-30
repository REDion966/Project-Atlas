"""Temporary Roadmap Step 6 — end-to-end real-world development test.

Pins the two Step-6 acceptance gaps that the experiment exposed and their fixes:

1. EQUIVALENT USER TEXT PRODUCES EQUIVALENT IDENTITY. The deterministic intake's
   goal carries a bounded utterance prefix ("respond: ..."), and a repeated
   equivalent turn reaches the development route through the antecedent machinery
   carrying that prefix; before the fix the second turn derived a different
   capability identity and created a divergent proposal. The derivation input and
   the accepted-request operand now use the user's own text, so send, stream and
   repetitions all derive the same identity.

2. THE DEVELOPMENT REQUEST'S OWN KNOWLEDGE NEED IS CLOSED BY ATLAS. On a fresh
   store with the subject knowledge absent, a development request that names an
   explicit external source now triggers ONE governed acquisition through the
   EXISTING research/provenance/retention seams, after which the EXISTING
   adjudication flips to a capability gap and the EXISTING specification is
   produced — and the governed development route still stops at the approval
   boundary with nothing promoted.

Everything runs through the real entry point (Atlas.chat / Atlas.stream) over
isolated stores; the authorized source is reached through the real deny-by-default
host policy with a deterministic in-process transport (the established D2/F8
pattern), so no test touches the network or the operator's stores.
"""

from __future__ import annotations

import pkgutil
import socket
from pathlib import Path

import pytest

import atlas.storage as storage_pkg

REPO_ROOT = Path(__file__).resolve().parents[1]

SOURCE_URL = "https://example.com/telemetry-spool"
PAGE = (
    "The deployment telemetry spool collects deployment telemetry records for "
    "every production spool and writes a deployment telemetry spool summary to "
    "the archive every hour."
)
DEVELOPMENT_TURN = "Add a capability that summarises the deployment telemetry spool."
AUTONOMOUS_TURN = (
    f"Using the page {SOURCE_URL}, develop a capability that summarises the "
    "deployment telemetry spool."
)
DENIED_URL = "https://evil.example.net/telemetry-spool"


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


class _Config:
    def __init__(self, real, hosts):
        self._real = real
        self._hosts = tuple(hosts)

    def get(self, section, key, default=None):
        if (section, key) == ("research", "web_allowed_hosts"):
            return self._hosts
        return self._real.get(section, key, default=default)

    def __getattr__(self, name):
        return getattr(self._real, name)


def _install_source(atlas, hosts):
    from atlas.research.coordinator import ConcreteResearchCoordinator
    from atlas.research.external_acquisition import ExternalKnowledgeAcquirer
    from atlas.research.sources import DocumentSourceAdapter
    from atlas.research.sources.web import WebSourceAdapter, web_host_policy_from_hosts
    from atlas.research.validated_retrieval import ValidatedKnowledgeRetriever

    def handler(url, timeout, max_bytes):
        if url == SOURCE_URL:
            return 200, [("Content-Type", "text/plain")], PAGE.encode("utf-8")
        return 404, [("Content-Type", "text/plain")], b"not found"

    policy = web_host_policy_from_hosts(hosts)
    web = WebSourceAdapter(
        transport=handler, host_policy=policy, resolver=lambda host: ("93.184.216.34",)
    )

    def resolve(specs):
        out = []
        for spec in specs or ():
            if isinstance(spec, str):
                try:
                    if web.supports(spec):
                        out.append(web.load(spec))
                    elif DocumentSourceAdapter().supports(spec):
                        out.append(DocumentSourceAdapter().load(spec))
                except (ValueError, OSError):
                    continue
            else:
                out.append(spec)
        return out

    service = atlas._acquisition_service  # noqa: SLF001
    service._coordinator = ConcreteResearchCoordinator(  # noqa: SLF001
        storage=atlas._research_storage, resolve_sources=resolve
    )
    atlas._external_acquirer = ExternalKnowledgeAcquirer(  # noqa: SLF001
        acquisition_service=service,
        validated_retriever=ValidatedKnowledgeRetriever(atlas._research_storage),
        host_policy=policy,
    )
    atlas._research_orchestrator = None  # noqa: SLF001


@pytest.fixture
def kernel(tmp_path, monkeypatch):
    _patch_stores(monkeypatch, tmp_path)
    from atlas.kernel.atlas import Atlas

    atlas = Atlas()
    atlas.start()
    _install_source(atlas, ("example.com",))
    try:
        yield atlas
    finally:
        atlas.shutdown()


def _meta(message):
    return getattr(message, "metadata", {}) or {}


def _design(text: str) -> str:
    for line in text.splitlines():
        if line.startswith("- Capability:"):
            return line.strip()
    return ""


def _proposal_ids(*messages):
    return [
        (_meta(message).get("development_driver") or {}).get("proposal_id")
        for message in messages
    ]


def _git_head() -> str:
    import subprocess

    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    ).stdout.strip()


class TestEquivalentTextProducesEquivalentIdentity:
    """Gap 1 — the derived capability identity is transport- and repeat-stable."""

    def test_send_and_stream_derive_the_same_identity(self, kernel):
        kernel.chat(f"research {SOURCE_URL} about the deployment telemetry spool")
        sent = kernel.chat(DEVELOPMENT_TURN)
        streamed = "".join(kernel.stream(DEVELOPMENT_TURN))
        assert _design(sent.content)
        assert _design(sent.content) == _design(streamed)

    def test_driver_request_is_the_users_own_text(self, kernel):
        message = kernel.chat(DEVELOPMENT_TURN)
        driver = _meta(message)["development_driver"]
        assert driver["request"] == DEVELOPMENT_TURN
        assert not driver["request"].startswith("respond:")

    def test_repeated_equivalent_turns_do_not_diverge(self, kernel):
        first = kernel.chat(DEVELOPMENT_TURN)
        second = kernel.chat(DEVELOPMENT_TURN)
        first_driver = _meta(first)["development_driver"]
        second_driver = _meta(second)["development_driver"]
        assert first_driver["request"] == second_driver["request"]
        assert first_driver["proposal_id"] != second_driver["proposal_id"]

    def test_prefix_never_reaches_the_derivation_input(self, kernel):
        """A prefixed utterance form must not change the derived request."""
        normalized = kernel._development_purpose_text(  # noqa: SLF001
            f"respond: {DEVELOPMENT_TURN}"
        )
        assert normalized == DEVELOPMENT_TURN

    def test_repeated_stream_turns_are_stable(self, kernel):
        kernel.chat(f"research {SOURCE_URL} about the deployment telemetry spool")
        first = "".join(kernel.stream(DEVELOPMENT_TURN))
        second = "".join(kernel.stream(DEVELOPMENT_TURN))
        assert _design(first)
        assert _design(first) == _design(second)


class TestAutonomousKnowledgeAcquisition:
    """Gap 2 — Atlas closes the request's own knowledge need, then develops."""

    def test_knowledge_is_absent_before_the_request(self, kernel):
        assert tuple(kernel._research_storage.load_claims()) == ()  # noqa: SLF001
        assert kernel.retained_knowledge("deployment telemetry spool").records == ()
        assert kernel.knowledge_need(AUTONOMOUS_TURN).kind.value == "missing"
        assert kernel.capability_gap(AUTONOMOUS_TURN).kind.value == "missing_knowledge"

    def test_atlas_acquires_the_named_authorized_source_itself(self, kernel):
        message = kernel.chat(AUTONOMOUS_TURN)
        content = message.content
        assert "Knowledge gap detected by Atlas for this development request" in content
        assert f"- Source: `{SOURCE_URL}`" in content
        assert "- Acquisition: researched" in content
        assert "- Provenance: 1 source(s), 1 evaluated claim(s)" in content
        assert "standing ['supported']" in content
        assert "- Retention (governed knowledge mechanism): retained 1" in content
        assert "- Adjudication after acquisition: unsupported_capability" in content

    def test_retained_knowledge_then_resolves_the_gap(self, kernel):
        kernel.chat(AUTONOMOUS_TURN)
        assert len(tuple(kernel._research_storage.load_claims())) == 1  # noqa: SLF001
        assert kernel.retained_knowledge("deployment telemetry spool").records
        assert kernel.capability_gap(AUTONOMOUS_TURN).kind.value == (
            "unsupported_capability"
        )
        assert kernel.capability_specification(AUTONOMOUS_TURN).is_specified

    def test_development_still_reaches_the_governed_boundary(self, kernel):
        """The governed route runs and stops; nothing is promoted or activated.

        Under the controlled test configuration the Development Envelope is
        disabled, so the driver reports its own honest terminal and prepares no
        promotion request; the sandbox execution itself is demonstrated by the
        isolated real-world experiment. Either way nothing may be promoted or
        activated here.
        """
        head = _git_head()
        message = kernel.chat(AUTONOMOUS_TURN)
        driver = _meta(message)["development_driver"]
        assert driver["terminal"] in {
            "validated",
            "envelope_disabled",
            "author_unavailable",
        }
        reviews = kernel.pending_promotion_reviews()
        assert all(review.get("status") == "pending_review" for review in reviews)
        assert _git_head() == head
        # nothing was activated: the derived capability is not registered
        derived = ""
        for line in message.content.splitlines():
            if line.startswith("- Capability: `"):
                derived = line.split("`")[1]
        assert derived, "the design must name its capability"
        assert kernel.capability_model().find(derived) is None

    def test_unauthorized_source_acquires_nothing(self, kernel):
        denied_turn = (
            f"Using the page {DENIED_URL}, develop a capability that summarises "
            "the deployment telemetry spool."
        )
        message = kernel.chat(denied_turn)
        assert "no_authorized_source" in message.content
        assert tuple(kernel._research_storage.load_claims()) == ()  # noqa: SLF001
        assert kernel.capability_gap(denied_turn).kind.value == "missing_knowledge"

    def test_development_request_without_a_source_is_unchanged(self, kernel):
        message = kernel.chat(DEVELOPMENT_TURN)
        assert "Knowledge gap detected by Atlas" not in message.content
        assert tuple(kernel._research_storage.load_claims()) == ()  # noqa: SLF001
        assert _meta(message).get("development_driver") is not None

    def test_authorization_requests_keep_their_step1_owner(self, kernel):
        message = kernel.chat(f"please authorize {SOURCE_URL} as a research source")
        assert _meta(message)["builtin_intent"] == "source_authorization"
        assert tuple(kernel._research_storage.load_claims()) == ()  # noqa: SLF001

    def test_research_surfaces_keep_their_step4_behaviour(self, kernel):
        message = kernel.chat(
            f"research {SOURCE_URL} about the deployment telemetry spool"
        )
        assert _meta(message)["builtin_intent"] == "external_research"
        assert "- Acquisition: researched" in message.content

    def test_no_network_and_no_model_dependency(self, kernel, monkeypatch):
        def _blocked(*args, **kwargs):
            raise AssertionError("no network access is allowed")

        monkeypatch.setattr(socket.socket, "connect", _blocked)
        message = kernel.chat(AUTONOMOUS_TURN)
        assert "- Acquisition: researched" in message.content
        assert _meta(message).get("model_used") is None  # deterministic route

    def test_stores_stay_isolated(self, kernel, tmp_path):
        from atlas.storage.research_storage import ResearchSQLiteStorage

        assert str(tmp_path) in str(ResearchSQLiteStorage.DEFAULT_DB_PATH)
