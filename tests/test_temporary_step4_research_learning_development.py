"""Temporary Roadmap Step 4 — research → learning → development.

Pins the Step-4 integration: a natural-language request that names an explicit
external source is carried through the EXISTING governed mechanisms (deny-by-
default host policy → Step-16 research → Step-17 provenance → Step-18 retention
→ Step-19/21 retained knowledge), the retained knowledge then resolves the
original knowledge gap through the EXISTING Step-22/23 adjudication, and the
resolved request reaches the EXISTING specification/development boundary without
bypassing any approval, execution, verification or promotion boundary.

The external source is an OPERATOR-AUTHORIZED host reached through the real
policy/storage path with a deterministic in-process transport (the established
D2/F8 pattern), so no test touches the network or the operator's stores.
"""

from __future__ import annotations

import pkgutil
import socket
from pathlib import Path

import pytest

import atlas.storage as storage_pkg

REPO_ROOT = Path(__file__).resolve().parents[1]

GOOD_URL = "https://example.com/telemetry"
DENIED_URL = "https://evil.example.net/telemetry"
CONTRADICTING_URL = "https://example.com/telemetry-contradiction"
GITHUB_URL = "https://github.com/psf/requests"

STATEMENT = (
    "The telemetry_spool keeps deployment telemetry events for each environment "
    "and flushes them to the archive every hour."
)
CONTRADICTION = (
    "The telemetry_spool does not keep deployment telemetry events and never "
    "flushes them to the archive."
)
PAGES = {
    GOOD_URL: ("text/plain", STATEMENT),
    CONTRADICTING_URL: ("text/plain", CONTRADICTION),
}
RESEARCH_TURN = f"research {GOOD_URL} about the telemetry deployment events"
DEVELOPMENT_REQUEST = (
    "Add a capability that summarises the telemetry deployment events."
)
SUBJECT_QUERY = "telemetry_spool"


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
    """An OWNER-style allowlist view over the real config (bounded, read-only)."""

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
    """Wire the real acquisition path to a deterministic in-process transport."""
    from atlas.research.coordinator import ConcreteResearchCoordinator
    from atlas.research.external_acquisition import ExternalKnowledgeAcquirer
    from atlas.research.sources import DocumentSourceAdapter
    from atlas.research.sources.web import WebSourceAdapter, web_host_policy_from_hosts
    from atlas.research.validated_retrieval import ValidatedKnowledgeRetriever

    def handler(url, timeout, max_bytes):
        entry = PAGES.get(url)
        if entry is None:
            return 404, [("Content-Type", "text/plain")], b"not found"
        ctype, body = entry
        return 200, [("Content-Type", ctype)], body.encode("utf-8")

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
    return policy


def _authorize(atlas, hosts):
    atlas._config = _Config(atlas._config, hosts)  # noqa: SLF001


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


def _git_head() -> str:
    import subprocess

    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    ).stdout.strip()


class TestGapIdentification:
    def test_genuine_knowledge_gap_is_identified(self, kernel):
        need = kernel.knowledge_need(DEVELOPMENT_REQUEST)
        assert need.kind.value == "missing"
        assert kernel.capability_gap(DEVELOPMENT_REQUEST).kind.value == (
            "missing_knowledge"
        )

    def test_gap_request_does_not_manufacture_a_capability_gap(self, kernel):
        gap = kernel.capability_gap(DEVELOPMENT_REQUEST)
        assert gap.is_gap is False
        specification = kernel.capability_specification(DEVELOPMENT_REQUEST)
        assert specification.is_specified is False


class TestGovernedResearch:
    def test_authorized_source_is_acquired_evaluated_and_retained(self, kernel):
        message = kernel.chat(RESEARCH_TURN)
        assert _meta(message)["builtin_intent"] == "external_research"
        content = message.content
        assert f"- Source: `{GOOD_URL}`" in content
        assert "- Acquisition: researched" in content
        assert "- Provenance: 1 source(s), 1 evaluated claim(s)" in content
        assert "standing ['supported']" in content
        assert "- Retention (governed knowledge mechanism): retained 1" in content
        evidence = _meta(message)["external_research"]
        assert evidence["research_status"] == "researched"
        assert evidence["retention"]["retained"] == 1
        assert evidence["provenance"]["standings"] == ["supported"]

    def test_authorized_research_is_model_free_and_writes_no_repository(self, kernel):
        head = _git_head()
        message = kernel.chat(RESEARCH_TURN)
        assert _meta(message).get("model_used") is False
        assert _git_head() == head
        assert kernel.pending_promotion_reviews() == []

    def test_denied_host_stays_blocked(self, kernel):
        message = kernel.chat(f"research {DENIED_URL} about the telemetry spool")
        evidence = _meta(message)["external_research"]
        assert evidence["research_status"] == "no_authorized_source"
        assert evidence["report_ids"] == []
        assert evidence["retention"]["retained"] == 0
        assert "no_authorized_source" in message.content
        assert "deny-by-default" in message.content

    def test_denied_source_acquires_nothing(self, kernel):
        kernel.chat(f"research {DENIED_URL} about the telemetry spool")
        assert tuple(kernel._research_storage.load_claims()) == ()  # noqa: SLF001
        assert kernel.retained_knowledge(SUBJECT_QUERY).records == ()

    def test_github_target_uses_the_existing_repository_mechanism(self, kernel):
        message = kernel.chat(f"please research {GITHUB_URL}")
        assert _meta(message)["builtin_intent"] == "external_research"
        assert _meta(message)["external_research"]["kind"] == "github"
        assert "Repository acquisition" in message.content
        assert "treated as DATA only" in message.content
        assert kernel.pending_promotion_reviews() == []


class TestLearningAndReuse:
    def test_retained_knowledge_is_retrievable_afterwards(self, kernel):
        kernel.chat(RESEARCH_TURN)
        kept = kernel.retained_knowledge(SUBJECT_QUERY)
        assert kept.records
        assert kernel.research_provenance(
            kernel.research_knowledge_need("telemetry deployment events")
        ) is not None

    def test_retained_knowledge_resolves_the_original_gap(self, kernel):
        kernel.chat(RESEARCH_TURN)
        gap = kernel.capability_gap(DEVELOPMENT_REQUEST)
        assert gap.kind.value == "unsupported_capability"
        assert gap.is_gap is True
        assert gap.boundary == "unresolved_target"

    def test_follow_up_uses_retained_knowledge_without_re_research(self, kernel):
        kernel.chat(RESEARCH_TURN)
        message = kernel.chat("what validated facts do you have about telemetry_spool?")
        assert "SUPPORTED" in message.content
        assert "telemetry_spool" in message.content
        assert _meta(message).get("external_research") is None

    def test_single_source_knowledge_is_never_called_established(self, kernel):
        message = kernel.chat(RESEARCH_TURN)
        evidence = _meta(message)["external_research"]
        assert evidence["retention"]["established"] == 0
        assert "multi-source corroboration" in message.content


class TestUntrustedAndContradicted:
    def test_contradicted_claim_is_not_trusted(self, kernel):
        kernel.chat(RESEARCH_TURN)
        message = kernel.chat(
            f"research {CONTRADICTING_URL} about the telemetry deployment events"
        )
        retention = _meta(message)["external_research"]["retention"]
        # the contradicting source is either refused or explicitly not established
        assert retention["retained"] == 0 or retention["established"] == 0
        assert kernel.pending_promotion_reviews() == []

    def test_external_text_is_data_not_instruction(self, kernel):
        message = kernel.chat(RESEARCH_TURN)
        assert "Nothing was authorized, allowlisted, configured, approved" in (
            message.content
        )
        # the acquired page never becomes a command surface
        assert not (REPO_ROOT / "sandbox_mod.py").exists()


class TestDevelopmentStaysGoverned:
    def test_resolved_gap_reaches_the_specification_surface(self, kernel):
        kernel.chat(RESEARCH_TURN)
        specification = kernel.capability_specification(DEVELOPMENT_REQUEST)
        assert specification.is_specified
        message = kernel.chat(DEVELOPMENT_REQUEST)
        assert "Bounded capability design" in message.content
        assert "- Required verification:" in message.content

    def test_research_does_not_authorize_development(self, kernel):
        head = _git_head()
        kernel.chat(RESEARCH_TURN)
        message = kernel.chat(DEVELOPMENT_REQUEST)
        driver = _meta(message).get("development_driver") or {}
        assert driver.get("execution_status", "") == ""
        assert driver.get("promotion_request_id", "") == ""
        assert kernel.pending_promotion_reviews() == []
        assert _git_head() == head

    def test_implementation_still_needs_the_owner_approval(self, kernel):
        kernel.chat(RESEARCH_TURN)
        specification = kernel.capability_specification(DEVELOPMENT_REQUEST)
        prepared = kernel.specification_development(
            specification,
            code_changes=(("sandbox_mod.py", "VALUE = 1\n"),),
            test_files=(("test_sandbox_mod.py", "def test_ok():\n    assert True\n"),),
            target_components=("sandbox_mod",),
        )
        assert prepared.stage.value == "awaiting_approval"
        assert prepared.authorized is False
        assert not (REPO_ROOT / "sandbox_mod.py").exists()


class TestBoundariesAndIndependence:
    def test_non_research_turns_keep_their_existing_route(self, kernel):
        for text in (
            "research the telemetry_spool deployment events",
            "what is the telemetry_spool?",
        ):
            message = kernel.chat(text)
            assert _meta(message).get("external_research") is None

    def test_authorization_changes_keep_their_step1_owner(self, kernel):
        message = kernel.chat(f"please authorize {DENIED_URL} as a research source")
        assert _meta(message)["builtin_intent"] == "source_authorization"
        assert _meta(message).get("external_research") is None

    def test_a_turn_without_a_target_is_never_acquired(self, kernel):
        kernel.chat("research the telemetry spool")
        assert tuple(kernel._research_storage.load_claims()) == ()  # noqa: SLF001

    def test_stream_and_send_agree(self, kernel):
        streamed = "".join(kernel.stream(RESEARCH_TURN))
        assert "Governed external research" in streamed
        assert "- Acquisition: researched" in streamed

    def test_no_network_is_contacted(self, kernel, monkeypatch):
        def _blocked(*args, **kwargs):
            raise AssertionError("no network access is allowed")

        monkeypatch.setattr(socket.socket, "connect", _blocked)
        message = kernel.chat(RESEARCH_TURN)
        assert "- Acquisition: researched" in message.content
        assert _meta(message).get("model_used") is False

    def test_owner_allowlist_is_what_authorizes_a_host(self, kernel):
        # The SAME turn against the SAME source is denied when the OWNER allowlist
        # does not name the host: the allowlist, not the request, is the authority.
        _install_source(kernel, ())
        message = kernel.chat(RESEARCH_TURN)
        assert _meta(message)["external_research"]["research_status"] == (
            "no_authorized_source"
        )
        assert tuple(kernel._research_storage.load_claims()) == ()  # noqa: SLF001
