"""Temporary Roadmap Step 5 — self-architecture understanding.

Pins the Step-5 integration: Atlas exposes the architecture facts its EXISTING
architecture model already records — declared dependencies (forward and reverse),
component/subsystem structure and responsibility, and the model's OWN knowledge
boundary for contracts/extension points — always fail-closed on an unresolvable
target; and a missing architectural fact travels the EXISTING governed
research/learning path (Step 4) so the retained knowledge can inform the EXISTING
capability specification and reach the governed development boundary.

No new architecture model, knowledge store or planner is involved: every answer
is a read-only projection of the existing model, and every acquisition goes
through the authorized host policy used by Step 4.
"""

from __future__ import annotations

import pkgutil
import socket
from pathlib import Path

import pytest

import atlas.storage as storage_pkg

REPO_ROOT = Path(__file__).resolve().parents[1]

GOOD_URL = "https://example.com/pipeline"
PAGE = (
    "The conversation pipeline keeps the deployment telemetry conversation history "
    "for each environment and flushes the conversation archive every hour."
)
PAGES = {GOOD_URL: ("text/plain", PAGE)}
RESEARCH_TURN = f"research {GOOD_URL} about the conversation history architecture"
DEVELOPMENT_REQUEST = (
    "Add a capability that summarises the conversation history archive."
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


class TestExistingArchitectureAnswers:
    """Criterion 1/3 — bounded answers from the authoritative existing model."""

    def test_responsibility_and_structure_are_answered(self, kernel):
        responsibility = kernel.chat(
            "what is the responsibility of the conversation service?"
        )
        assert _meta(responsibility)["builtin_intent"] == "architecture"
        assert "Responsibility:" in responsibility.content
        structure = kernel.chat("how is the conversation service structured?")
        assert "Entry module:" in structure.content
        assert "Declared dependencies" in structure.content

    def test_known_and_missing_architecture_are_distinguished(self, kernel):
        boundary = kernel.chat("what architecture information do you not know?")
        assert "not represented" in boundary.content
        unknown = kernel.chat(
            "what is the responsibility of the unknown_widget service?"
        )
        assert "no registered component named" in unknown.content


class TestDeclaredDependencies:
    """Criterion 2 — modules/dependencies of the architecture, forward and reverse."""

    def test_forward_dependencies_come_from_the_model(self, kernel):
        expected = None
        for entry in kernel.architecture_model().components:
            if entry.name == "conversation_service":
                expected = entry.declared_dependencies
        assert expected, "the model must record the component's declared dependencies"
        message = kernel.chat("what does the conversation service depend on?")
        assert "Declared dependencies of component" in message.content
        assert "`conversation_service`" in message.content
        for dependency in expected:
            assert f"`{dependency}`" in message.content
        recorded = _meta(message)["architecture_dependencies"]["dependencies"]
        assert recorded == list(expected)

    def test_subsystem_dependencies_use_the_subsystem_entry(self, kernel):
        message = kernel.chat("what does the evolution subsystem depend on?")
        assert "subsystem `atlas.evolution`" in message.content
        assert _meta(message)["builtin_intent"] == "architecture"

    def test_reverse_dependencies_are_walked_from_the_model(self, kernel):
        message = kernel.chat("which components depend on the conversation service?")
        metadata = _meta(message)["architecture_dependents"]
        assert metadata["target"] == "conversation service"
        assert isinstance(metadata["dependents"], list)
        assert "None declared" in message.content or metadata["dependents"]

    def test_reverse_dependencies_reflect_a_registered_edge(self, kernel):
        model = kernel.architecture_model()
        target = ""
        resolver = kernel._builtin_response._find_component_entry  # noqa: SLF001
        for component in model.components:
            for dependency in component.declared_dependencies:
                if resolver(dependency) is not None:
                    target = dependency
                    break
            if target:
                break
        assert target, "the model must record at least one resolvable declared edge"
        message = kernel.chat(f"what depends on the {target} component?")
        assert f"`{target}`" in message.content
        assert "None declared" not in message.content


class TestContractsAndExtensionPoints:
    """Criterion 3 — contracts/extension points answered honestly, never invented."""

    def test_extension_points_report_the_real_boundary(self, kernel):
        message = kernel.chat("what are the extension points for adding a capability?")
        assert "Interfaces/contracts are NOT represented" in message.content
        assert "registry is the extension mechanism" in message.content
        assert _meta(message)["model_used"] is False

    def test_contracts_question_never_invents_a_contract(self, kernel):
        message = kernel.chat("what contracts does the capability model expose?")
        assert "NOT represented" in message.content
        assert "nothing was changed" in message.content.lower()

    def test_unresolvable_dependency_target_is_reported_honestly(self, kernel):
        message = kernel.chat("which components depend on the unknown_widget service?")
        assert "no registered component named" in message.content


class TestMissingArchitecturalFact:
    """Criterion 4/5/6 — a missing fact uses the existing governed research path."""

    def test_missing_fact_is_researched_and_retained_with_provenance(self, kernel):
        message = kernel.chat(RESEARCH_TURN)
        assert _meta(message)["builtin_intent"] == "external_research"
        assert "- Acquisition: researched" in message.content
        evidence = _meta(message)["external_research"]
        assert evidence["provenance"]["standings"] == ["supported"]
        assert evidence["retention"]["retained"] == 1

    def test_retained_fact_is_reused_without_repeating_research(self, kernel):
        kernel.chat(RESEARCH_TURN)
        message = kernel.chat(
            "what validated facts do you have about conversation history?"
        )
        assert "SUPPORTED" in message.content
        assert _meta(message).get("external_research") is None

    def test_unauthorized_architecture_source_stays_blocked(self, kernel):
        message = kernel.chat(
            "research https://evil.example.net/architecture about the "
            "conversation history"
        )
        assert _meta(message)["external_research"]["research_status"] == (
            "no_authorized_source"
        )


class TestInformsDevelopment:
    """Criterion 7/8/9 — architecture-derived specification, governed development."""

    def test_specification_is_derived_from_the_architecture_model(self, kernel):
        kernel.chat(RESEARCH_TURN)
        specification = kernel.capability_specification(DEVELOPMENT_REQUEST)
        assert specification.is_specified
        architecture_derived = bool(specification.affected_areas) or any(
            "architecture area" in question
            for question in specification.unresolved_questions
        )
        assert architecture_derived, "the spec must carry architecture grounding"

    def test_architecture_grounding_matches_the_model(self, kernel):
        kernel.chat(RESEARCH_TURN)
        specification = kernel.capability_specification(DEVELOPMENT_REQUEST)
        model = kernel.architecture_model()
        names = {entry.name for entry in model.components} | {
            entry.package for entry in model.subsystems
        }
        for area in specification.affected_areas:
            assert any(
                area in name or name in area or area.split(".")[-1] in name
                for name in names
            ), f"affected area {area!r} is not grounded in the architecture model"

    def test_design_block_is_reported_conversationally(self, kernel):
        kernel.chat(RESEARCH_TURN)
        message = kernel.chat(DEVELOPMENT_REQUEST)
        assert "Bounded capability design" in message.content
        assert "- Affected areas:" in message.content or "- Still unresolved:" in (
            message.content
        )

    def test_development_remains_behind_the_owner_approval(self, kernel):
        head = _git_head()
        kernel.chat(RESEARCH_TURN)
        specification = kernel.capability_specification(DEVELOPMENT_REQUEST)
        prepared = kernel.specification_development(
            specification,
            code_changes=(("sandbox_mod.py", "VALUE = 1\n"),),
            test_files=(("sandbox_mod.py", "VALUE = 1\n"),),
            target_components=("sandbox_mod",),
        )
        assert prepared.stage.value == "awaiting_approval"
        assert prepared.authorized is False
        assert kernel.pending_promotion_reviews() == []
        assert not (REPO_ROOT / "sandbox_mod.py").exists()
        assert _git_head() == head

    def test_architecture_answers_grant_no_authority(self, kernel):
        for text in (
            "what does the conversation service depend on?",
            "what depends on the conversation service?",
            "what are the extension points for adding a capability?",
        ):
            message = kernel.chat(text)
            assert "Nothing was changed" in message.content
            assert _meta(message).get("model_used") is False
        assert kernel.pending_promotion_reviews() == []


class TestCompatibilityAndIsolation:
    """Criterion 10/11/12 — model independence, compatibility, store isolation."""

    def test_unrelated_turns_keep_their_existing_route(self, kernel):
        message = kernel.chat("research the telemetry_spool deployment events")
        assert _meta(message).get("architecture_dependencies") is None
        assert _meta(message).get("architecture_dependents") is None

    def test_dependent_forms_implement_a_word_boundary(self, kernel):
        # "what depends on that?" is not an architecture question.
        message = kernel.chat("what depends on that?")
        assert _meta(message).get("architecture_dependents") is None

    def test_stream_and_send_agree_on_architecture_answers(self, kernel):
        for text in (
            "what does the conversation service depend on?",
            "what depends on the conversation service?",
            "what are the extension points for adding a capability?",
        ):
            sent = kernel.chat(text).content.strip()
            streamed = "".join(kernel.stream(text)).strip()
            assert sent == streamed

    def test_no_network_and_no_model_authority(self, kernel, monkeypatch):
        def _blocked(*args, **kwargs):
            raise AssertionError("no network access is allowed")

        monkeypatch.setattr(socket.socket, "connect", _blocked)
        for text in (
            "what does the conversation service depend on?",
            "what are the extension points for adding a capability?",
            RESEARCH_TURN,
        ):
            message = kernel.chat(text)
            assert _meta(message).get("model_used") is False

    def test_probes_use_isolated_stores(self, kernel, tmp_path):
        from atlas.storage.research_storage import ResearchSQLiteStorage

        assert str(tmp_path) in str(ResearchSQLiteStorage.DEFAULT_DB_PATH)
        assert kernel.pending_promotion_reviews() == []
