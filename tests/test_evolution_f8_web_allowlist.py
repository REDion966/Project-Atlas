"""Phase F8 - Web host allowlist configuration tests.

Focused coverage of the additive ``research.web_allowed_hosts`` surface:

  * empty/default configuration keeps the web adapter deny-by-default;
  * configured hosts are propagated into the web host policy;
  * an allowed host can be fetched through the existing resolvers using a
    fake transport (never live network);
  * an unlisted host remains rejected;
  * SSRF protections remain mandatory even for allowlisted hosts.

No live network: every retrieval path uses an injected fake transport and
a fake DNS resolver.
"""

import pytest

import atlas.research.capability_handlers as cap_mod
import atlas.research.sources as sources_mod
from atlas.config.configuration import Configuration
from atlas.config.configuration_models import (
    AISettings,
    ApplicationSettings,
    AtlasSettings,
    ConversationSettings,
    LoggingSettings,
    ResearchSettings,
)
from atlas.evolution.models import ResearchQuery
from atlas.research.capability_handlers import ResearchCapabilityFactory
from atlas.research.coordinator import ConcreteResearchCoordinator
from atlas.research.sources.web import (
    WebHostPolicy,
    WebSourceAdapter as RealWebSourceAdapter,
    web_host_policy_from_hosts,
)

GLOBAL_IP = "93.184.216.34"


def ok_transport(body=b"Atlas is deterministic. It preserves provenance."):
    """Fake single-hop HTTP GET handler (no live network)."""

    class _Handler:
        def get(self, url, timeout, max_bytes):
            return 200, [("Content-Type", "text/plain")], body

    return _Handler()


class _Resolver:
    """Fake DNS resolver returning a fixed address tuple."""

    def __init__(self, addresses):
        self._addresses = tuple(addresses)

    def __call__(self, host):
        return self._addresses


GLOBAL_RESOLVER = _Resolver((GLOBAL_IP,))
PRIVATE_RESOLVER = _Resolver(("10.0.0.5",))


def make_adapter_factory(resolver=None, transport=None):
    """Return a callable usable as a WebSourceAdapter substitute.

    Injects a fake transport and a fake DNS resolver so no live network is
    ever touched. The real :class:`WebSourceAdapter` is used, so all SSRF /
    bound / fail-closed logic is genuinely exercised.
    """

    def _factory(*, host_policy=None):
        return RealWebSourceAdapter(
            transport=transport or ok_transport(),
            host_policy=host_policy,
            resolver=resolver if resolver is not None else GLOBAL_RESOLVER,
        )

    return _factory


def minimal_config(tmp_path, research_block=""):
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        '[application]\nname="Atlas"\nversion="0.1.0"\n'
        '[ai]\nprovider="Ollama"\nmodel="m"\ntemperature=0.7\ntimeout=1\n'
        '[conversation]\nhistory_limit=1\n'
        '[logging]\nlevel="INFO"\n' + research_block,
        encoding="utf-8",
    )
    return str(cfg)


# ---------------------------------------------------------------------------
# Configuration parsing
# ---------------------------------------------------------------------------


class TestConfigurationParsing:
    def test_default_empty_when_research_section_absent(self, tmp_path):
        configuration = Configuration(minimal_config(tmp_path))
        configuration.load()
        assert configuration.get("research", "web_allowed_hosts", default=()) == ()
        assert configuration.settings.research.web_allowed_hosts == ()

    def test_configured_hosts_parsed_and_stripped(self, tmp_path):
        configuration = Configuration(
            minimal_config(
                tmp_path,
                '[research]\n'
                'web_allowed_hosts = ["example.com", " docs.example.org "]\n',
            )
        )
        configuration.load()
        assert (
            configuration.get("research", "web_allowed_hosts", default=())
            == ("example.com", "docs.example.org")
        )

    def test_research_settings_generic_type_default(self):
        assert ResearchSettings().web_allowed_hosts == ()

    def test_atlas_settings_default_research(self):
        # Existing constructors that omit ``research`` still work (backward
        # compatibility thanks to the default_factory).
        settings = AtlasSettings(
            application=ApplicationSettings(name="Atlas", version="1"),
            ai=AISettings(provider="p", model="m", temperature=0.0, timeout=1),
            conversation=ConversationSettings(history_limit=1),
            logging=LoggingSettings(level="INFO"),
        )
        assert settings.research.web_allowed_hosts == ()


# ---------------------------------------------------------------------------
# Policy helper
# ---------------------------------------------------------------------------


class TestWebHostPolicyFromHosts:
    def test_empty_hosts_deny_all(self):
        policy = web_host_policy_from_hosts(())
        assert policy.allow_unlisted is False
        assert not policy.allowed_hosts
        assert not policy.permits("example.com")

    def test_configured_hosts_allowed(self):
        policy = web_host_policy_from_hosts(("example.com", "Example.com.", "docs.atlas.io"))
        assert policy.permits("example.com")
        assert policy.permits("docs.atlas.io")
        assert not policy.permits("unlisted.org")

    def test_blank_entries_ignored(self):
        policy = web_host_policy_from_hosts(("example.com", "   ", ""))
        assert policy.permits("example.com")
        assert policy.allowed_hosts == frozenset({"example.com"})


# ---------------------------------------------------------------------------
# ResearchCapabilityFactory wiring
# ---------------------------------------------------------------------------


class TestFactoryWiring:
    def test_default_factory_deny_all(self, monkeypatch):
        monkeypatch.setattr(cap_mod, "WebSourceAdapter", make_adapter_factory())
        factory = ResearchCapabilityFactory()
        assert factory._resolve_sources(["https://example.com/x"]) == []

    def test_configured_host_fetched_with_fake_transport(self, monkeypatch):
        monkeypatch.setattr(cap_mod, "WebSourceAdapter", make_adapter_factory())
        factory = ResearchCapabilityFactory(web_hosts=("example.com",))
        from atlas.research.models import SourceProfile

        resolved = factory._resolve_sources(
            ["https://example.com/x", "https://unlisted.org/x"]
        )
        assert len(resolved) == 1
        assert isinstance(resolved[0], SourceProfile)
        assert resolved[0].uri == "https://example.com/x"
        assert resolved[0].text == "Atlas is deterministic. It preserves provenance."

    def test_unlisted_host_rejected(self, monkeypatch):
        monkeypatch.setattr(cap_mod, "WebSourceAdapter", make_adapter_factory())
        factory = ResearchCapabilityFactory(web_hosts=("example.com",))
        assert factory._resolve_sources(["https://unlisted.org/x"]) == []

    def test_allowlisted_host_with_private_resolution_blocked(self, monkeypatch):
        monkeypatch.setattr(
            cap_mod,
            "WebSourceAdapter",
            make_adapter_factory(resolver=PRIVATE_RESOLVER),
        )
        factory = ResearchCapabilityFactory(web_hosts=("example.com",))
        assert factory._resolve_sources(["https://example.com/x"]) == []

    def test_allowlisted_private_literal_still_blocked(self, monkeypatch):
        monkeypatch.setattr(cap_mod, "WebSourceAdapter", make_adapter_factory())
        factory = ResearchCapabilityFactory(web_hosts=("127.0.0.1", "169.254.169.254"))
        assert factory._resolve_sources(
            ["http://127.0.0.1/x", "http://169.254.169.254/meta"]
        ) == []


# ---------------------------------------------------------------------------
# Coordinator fallback resolver wiring
# ---------------------------------------------------------------------------


class TestCoordinatorFallback:
    def test_default_coordinator_deny_all(self, monkeypatch):
        monkeypatch.setattr(sources_mod, "WebSourceAdapter", make_adapter_factory())
        coordinator = ConcreteResearchCoordinator()
        result = coordinator.run(
            ResearchQuery(
                query_id="q",
                question="re-research x",
                context={"sources": ["https://example.com/x"]},
            )
        )
        assert result.sources == []

    def test_configured_coordinator_fetches_web(self, monkeypatch):
        monkeypatch.setattr(sources_mod, "WebSourceAdapter", make_adapter_factory())
        coordinator = ConcreteResearchCoordinator(web_hosts=("example.com",))
        result = coordinator.run(
            ResearchQuery(
                query_id="q",
                question="re-research x",
                context={"sources": ["https://example.com/x"]},
            )
        )
        assert "https://example.com/x" in result.sources

    def test_unlisted_coordinator_rejected(self, monkeypatch):
        monkeypatch.setattr(sources_mod, "WebSourceAdapter", make_adapter_factory())
        coordinator = ConcreteResearchCoordinator(web_hosts=("example.com",))
        result = coordinator.run(
            ResearchQuery(
                query_id="q",
                question="re-research x",
                context={"sources": ["https://unlisted.org/x"]},
            )
        )
        assert result.sources == []
