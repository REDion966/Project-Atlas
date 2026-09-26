"""G3 — Governed Self-Development (target-state gate).

Evidence-based acceptance tests for the documented gap "No conversational routing of
DEVELOPMENT_REQUESTs through ``DevelopmentDriver``":

* a conversational development request reaches the EXISTING bounded
  ``DevelopmentDriver`` exactly once and its own honest terminal is reported;
* the bounded capability-handler scaffold SPECIFICATION is derived deterministically
  from the request's own words and is accepted by the EXISTING
  ``ScaffoldChangeSupplier`` (a request naming no capability is refused honestly);
* the Development Envelope is honoured unchanged: disabled by default -> nothing
  executes; enabled by the OWNER -> the bounded sandbox phase may run and a promotion
  request may be prepared, while promotion itself stays OWNER-only;
* nothing is ever approved, executed outside the envelope, or promoted by the
  conversational route, and no sandbox change reaches the live repository;
* the conversation layer keeps no ``atlas.evolution`` import, model independence is
  preserved, and ``tick()`` never invokes the route.
"""

from __future__ import annotations

import inspect
import socket
from pathlib import Path

import pytest

from atlas.conversation.conversation_service import ConversationService
from atlas.evolution.development_cycle import DevelopmentNeed
from atlas.evolution.development_envelope import (
    DevelopmentAuthority,
    DevelopmentEnvelope,
)
from atlas.evolution.development_gap import (
    DevelopmentGapKind,
    assess_development_gap,
)
from atlas.evolution.development_request_scaffold import (
    SCAFFOLD_PACKAGE,
    capability_slug,
    scaffold_spec_for_request,
)
from atlas.evolution.development_scaffold_supplier import ScaffoldChangeSupplier
from atlas.evolution.models import ProposalStatus
from atlas.evolution.promotion_gate import ARCHITECTURE_SENSITIVE_PREFIXES

_REPO_ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# Deterministic scaffold derivation (pure, no kernel)
# ---------------------------------------------------------------------------


class TestScaffoldDerivation:
    @pytest.mark.parametrize(
        ("text", "slug"),
        (
            ("add a new capability to Atlas for scheduling", "scheduling"),
            ("add a capability that summarizes documents", "summarizes_documents"),
            ("Atlas needs a capability that reads PDFs.", "reads_pdfs"),
            ("Please create a capability that batches widgets", "batches_widgets"),
        ),
    )
    def test_slug_is_deterministic_and_bounded(self, text, slug):
        assert capability_slug(text) == slug

    @pytest.mark.parametrize(
        "text",
        (
            "Can you add a new capability to Atlas?",
            "Hello there.",
            "What is your status?",
            "",
            None,
            12345,
        ),
    )
    def test_no_capability_named_yields_nothing(self, text):
        assert capability_slug(text) is None
        assert scaffold_spec_for_request(text) is None

    def test_spec_is_accepted_by_the_existing_supplier(self):
        spec = scaffold_spec_for_request("add a new capability to Atlas for scheduling")
        assert spec is not None
        supplied = ScaffoldChangeSupplier().supply_changes(
            DevelopmentNeed(title="t", metadata={"scaffold": spec})
        )
        assert supplied is not None
        paths = tuple(path for path, _content in supplied.code_changes)
        assert paths == (f"{SCAFFOLD_PACKAGE}/scheduling.py",)
        assert supplied.origin == "deterministic-scaffold"

    def test_derived_module_is_not_architecture_sensitive(self):
        spec = scaffold_spec_for_request("add a new capability to Atlas for scheduling")
        dotted = spec["module"][:-3].replace("/", ".")
        assert not any(
            dotted.startswith(prefix) for prefix in ARCHITECTURE_SENSITIVE_PREFIXES
        )
        assert spec["module"].endswith(".py") and "/" in spec["module"]
        assert spec["test_module"].startswith("tests/")

    def test_registered_capability_is_not_re_developed(self):
        assert (
            scaffold_spec_for_request(
                "add a new capability to Atlas for scheduling",
                registered_names=("scheduling",),
            )
            is None
        )

    def test_derivation_is_pure_and_repeatable(self):
        request = "add a capability that summarizes documents"
        first = scaffold_spec_for_request(request)
        second = scaffold_spec_for_request(request)
        assert first == second


# ---------------------------------------------------------------------------
# Capability-gap adjudication evidence (G3 defect fix)
# ---------------------------------------------------------------------------


class TestCapabilityGapEvidence:
    """Lexical overlap is NECESSARY but not SUFFICIENT for ALREADY_SUPPORTED.

    A registered capability is honoured only when the overlap accounts for a
    substantial share of the request's own words. An incidental shared token
    inside a longer development request must not be read as functional
    equivalence, so a legitimate new-capability request still reaches the
    governed development path.
    """

    def test_genuine_existing_capability_request_is_already_supported(self):
        gap = assess_development_gap(
            "export the conversation history as markdown",
            capability_names=["conversation_history_export"],
        )
        assert gap.kind is DevelopmentGapKind.ALREADY_SUPPORTED
        assert gap.matched == ("conversation_history_export",)

    def test_incidental_capability_token_overlap_is_not_already_supported(self):
        gap = assess_development_gap(
            "Add a capability that lets me export the conversation history "
            "as markdown.",
            capability_names=["conversation"],
        )
        assert gap.kind is not DevelopmentGapKind.ALREADY_SUPPORTED
        assert gap.matched == ()

    def test_short_invocation_shaped_overlap_is_still_supported(self):
        # The existing (stricter) contract for short invocation-shaped requests
        # is preserved.
        gap = assess_development_gap(
            "run the research pipeline", capability_names=["research.query"]
        )
        assert gap.kind is DevelopmentGapKind.ALREADY_SUPPORTED

    def test_gap_adjudication_is_deterministic(self):
        request = (
            "Add a capability that lets me export the conversation history "
            "as markdown."
        )
        first = assess_development_gap(request, capability_names=["conversation"])
        second = assess_development_gap(request, capability_names=["conversation"])
        assert first == second


# ---------------------------------------------------------------------------
# Kernel route
# ---------------------------------------------------------------------------


def _started_atlas(monkeypatch, tmp_path):
    import atlas.kernel.atlas as kernel_mod
    from atlas.storage.research_storage import ResearchSQLiteStorage
    from tests.test_durable_guided_improvement import _storage_class

    monkeypatch.setattr(
        "atlas.kernel.atlas.SQLiteEvolutionStorage", _storage_class(tmp_path)
    )

    class _TmpResearch(ResearchSQLiteStorage):
        def __init__(self, db_path=None):  # noqa: D107
            super().__init__(db_path=tmp_path / "research.db")

    monkeypatch.setattr("atlas.kernel.atlas.ResearchSQLiteStorage", _TmpResearch)
    atlas = kernel_mod.Atlas()
    atlas.start()
    return atlas


class _FakeAcquisition:
    """Duck-typed F8 acquisition result (no network)."""

    status = "ok"

    def to_dict(self):
        return {
            "acquisition_id": "ACQ-G3-000001",
            "status": "ok",
            "report_id": "report:g3",
            "sources": ("https://example.test/a",),
            "confidence": 0.8,
            "claim_count": 1,
        }


def _stub_research(atlas):
    """Replace the controller's F8 researcher to avoid any network access."""
    controller = atlas.development_controller
    controller._researcher = lambda **kwargs: _FakeAcquisition()  # noqa: SLF001


class _ConcreteSupplier:
    """Deterministic supplier producing one concrete sandbox change."""

    def supply_changes(self, need):
        from atlas.evolution.development_cycle import SuppliedChanges

        return SuppliedChanges(
            code_changes=(("docs/g3_note.md", "# g3\n"),),
            origin="deterministic",
        )


def _disable_network(monkeypatch):
    def _no_network(*args, **kwargs):
        raise RuntimeError("network access is forbidden in this test")

    monkeypatch.setattr(socket, "create_connection", _no_network)
    monkeypatch.setattr(socket.socket, "connect", _no_network)


class TestConversationalGovernedSelfDevelopment:
    def test_request_reaches_the_driver_once_with_the_derived_scaffold(
        self, monkeypatch, tmp_path
    ):
        atlas = _started_atlas(monkeypatch, tmp_path)
        calls: list[tuple[str, object]] = []
        original = atlas.run_development_driver

        def _spy(request, metadata=None):
            calls.append((request, metadata))
            return original(request, metadata=metadata)

        atlas.run_development_driver = _spy
        try:
            _stub_research(atlas)
            message = atlas.chat("add a new capability to Atlas for scheduling")
            driver = dict(message.metadata or {}).get("development_driver") or {}
        finally:
            atlas.shutdown()

        assert len(calls) == 1
        _request, metadata = calls[0]
        assert metadata and metadata.get("scaffold")
        assert metadata["scaffold"]["capability_name"] == "scheduling"
        assert driver.get("terminal") == "envelope_disabled"
        assert "Outcome: envelope_disabled" in message.content

    def test_conversation_history_export_reaches_the_governed_path(
        self, monkeypatch, tmp_path
    ):
        """The Claude-reported request is not silently rejected as supported.

        "conversation" overlaps a registered capability name, but the request is
        for a NEW capability (markdown export of conversation history), so the
        gap is MISSING_KNOWLEDGE and the governed driver prepares it instead of
        terminating as ``already_supported``.
        """
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            _stub_research(atlas)
            message = atlas.chat(
                "Add a capability that lets me export the conversation history "
                "as markdown."
            )
            driver = dict(message.metadata or {}).get("development_driver") or {}
            pending = atlas.pending_promotion_reviews()
        finally:
            atlas.shutdown()

        assert driver.get("terminal") == "envelope_disabled"
        assert driver.get("terminal") != "already_supported"
        assert driver.get("proposal_id")
        assert "PENDING_APPROVAL" in message.content
        assert "Nothing is approved, executed, or promoted" in message.content
        assert tuple(pending) == ()

    def test_default_envelope_executes_nothing_and_writes_nothing(
        self, monkeypatch, tmp_path
    ):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            _stub_research(atlas)
            message = atlas.chat("add a new capability to Atlas for scheduling")
            driver = dict(message.metadata or {}).get("development_driver") or {}
            proposals = tuple(atlas._evolution_memory.get_all_proposals())
            pending_promotions = tuple(atlas.pending_promotion_reviews())
        finally:
            atlas.shutdown()

        assert driver.get("terminal") == "envelope_disabled"
        assert not driver.get("execution_status")
        assert not driver.get("verification_status")
        assert not driver.get("promotion_request_id")
        assert not pending_promotions
        assert all(p.status is not ProposalStatus.APPROVED for p in proposals)
        # The derived sandbox change never reached the live repository.
        assert not (_REPO_ROOT / f"{SCAFFOLD_PACKAGE}/scheduling.py").exists()
        assert not (_REPO_ROOT / "tests" / "test_scheduling.py").exists()

    def test_enabled_envelope_runs_the_bounded_sandbox_and_never_promotes(
        self, monkeypatch, tmp_path
    ):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            _stub_research(atlas)
            repo = tmp_path / "live_repo"
            (repo / "pkg").mkdir(parents=True, exist_ok=True)
            (repo / "pkg" / "mod.py").write_text("VALUE = 1\n", encoding="utf-8")
            atlas._promotion_repo_root = lambda: repo
            envelope = DevelopmentEnvelope(
                enabled=True, max_runs_per_window=3, window_seconds=3600
            )
            atlas._development_envelope = envelope
            atlas._development_authority = DevelopmentAuthority(
                envelope, usage_provider=lambda: atlas._development_envelope_usage
            )

            message = atlas.chat("add a new capability to Atlas for scheduling")
            driver = dict(message.metadata or {}).get("development_driver") or {}
            proposals = tuple(atlas._evolution_memory.get_all_proposals())
            pending_promotions = tuple(atlas.pending_promotion_reviews())
        finally:
            atlas.shutdown()

        assert driver.get("terminal") == "validated", driver
        assert driver.get("verification_status") == "verified"
        assert driver.get("promotion_request_id")
        # Sandbox authorization is NEVER the OWNER-approved state.
        assert proposals
        assert all(p.status is not ProposalStatus.APPROVED for p in proposals)
        # A promotion REQUEST exists, but nothing was promoted by the conversation,
        # and the live (temporary) repository was not written.
        assert pending_promotions
        assert (repo / "pkg" / "mod.py").read_text(encoding="utf-8") == "VALUE = 1\n"
        assert not (_REPO_ROOT / f"{SCAFFOLD_PACKAGE}/scheduling.py").exists()

    def test_explanatory_question_stays_self_knowledge(self, monkeypatch, tmp_path):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            message = atlas.chat("How would you add a new capability?")
            driver = dict(message.metadata or {}).get("development_driver")
        finally:
            atlas.shutdown()

        assert driver is None
        assert message.metadata.get("builtin_intent") == "self_knowledge"

    def test_under_specified_request_still_clarifies(self, monkeypatch, tmp_path):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            message = atlas.chat("Could you add a capability to Atlas that tracks releases")
            driver = dict(message.metadata or {}).get("development_driver")
        finally:
            atlas.shutdown()

        assert driver is None
        assert "more detail" in message.content.lower()

    def test_development_route_is_model_free(self, monkeypatch, tmp_path):
        import atlas.ai.ai_service as ai_service

        calls = {"n": 0}

        def _boom(*args, **kwargs):
            calls["n"] += 1
            raise RuntimeError("provider contacted")

        monkeypatch.setattr(ai_service.AIService, "chat", _boom)
        monkeypatch.setattr(ai_service.AIService, "complete", _boom)
        _disable_network(monkeypatch)

        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            _stub_research(atlas)
            message = atlas.chat("add a new capability to Atlas for scheduling")
            driver = dict(message.metadata or {}).get("development_driver") or {}
        finally:
            atlas.shutdown()

        assert calls["n"] == 0
        assert driver.get("terminal") == "envelope_disabled"
        assert "deterministic; no external AI model used" in message.content

    def test_conversation_layer_does_not_import_the_driver(self):
        import ast

        source = (
            _REPO_ROOT / "atlas" / "conversation" / "conversation_service.py"
        ).read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
            elif isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
        # G3 — the governed self-development route is DUCK-TYPED: the conversation
        # layer never imports the driver or the scaffold derivation.
        assert "atlas.evolution.development_driver" not in imported
        assert "atlas.evolution.development_request_scaffold" not in imported
        assert "_development_driver_bridge" in source

    def test_tick_never_invokes_the_route(self):
        from atlas.kernel.atlas import Atlas

        tick_source = inspect.getsource(Atlas.tick)
        assert "_development_driver_bridge" not in tick_source
        assert "run_development_driver" not in tick_source
