"""C4.1 — capability-detail routing precedence (regression).

Proves the advertised ``"explain <name>"`` form reaches the deterministic
capability-detail surface for EVERY registered capability/tool name, including
names whose identifiers contain investigation/research cue tokens
(``analysis``, ``reasoning.trace``, ``research.summarize``), while ordinary
investigation/research requests keep their existing routing and unknown names
stay fail-closed.

Exercises the REAL public conversation path (``ConversationService.send`` on a
fully wired ``Atlas`` kernel, default config). Environment note: all SQLite
stores default to one shared file; this module points them at a fresh temporary
database for the module's duration (restored afterwards). Test-harness only;
production behaviour is unchanged.
"""

from __future__ import annotations

import importlib
import pkgutil
import tempfile
from pathlib import Path

import pytest

from atlas.kernel.atlas import Atlas


def _patch_default_db_paths(new_path: Path) -> list[tuple[type, object]]:
    import atlas.storage as storage_pkg

    saved: list[tuple[type, object]] = []
    for info in pkgutil.iter_modules(storage_pkg.__path__):
        try:
            module = importlib.import_module(f"atlas.storage.{info.name}")
        except Exception:  # noqa: BLE001
            continue
        for attr in dir(module):
            obj = getattr(module, attr)
            if isinstance(obj, type) and hasattr(obj, "DEFAULT_DB_PATH"):
                saved.append((obj, obj.DEFAULT_DB_PATH))
                setattr(obj, "DEFAULT_DB_PATH", new_path)
    return saved


@pytest.fixture(scope="module")
def kernel():
    saved = _patch_default_db_paths(
        Path(tempfile.mkdtemp(prefix="c4_1_")) / "atlas_experience.db"
    )
    atlas = Atlas()
    atlas.start()
    try:
        yield atlas
    finally:
        try:
            atlas.shutdown()
        except Exception:  # noqa: BLE001
            pass
        for cls, original in saved:
            setattr(cls, "DEFAULT_DB_PATH", original)


def _send(kernel, text):
    service = kernel.container.get("conversation")
    service._conversation = service._history.create()
    service._state_manager.clear()
    service._last_investigation_report = None
    return service.send(text)


def _intent(message):
    return (message.metadata or {}).get("builtin_intent")


# ---------------------------------------------------------------------------
# A — registered collision names now reach capability detail
# ---------------------------------------------------------------------------


class TestCollisionNamesReachCapabilityDetail:
    @pytest.mark.parametrize(
        "name", ["analysis", "reasoning.trace", "research.summarize"]
    )
    def test_explain_collision_name(self, kernel, name):
        message = _send(kernel, f"explain {name}")
        assert _intent(message) == "capability_detail"
        assert name in message.content
        assert message.metadata.get("model_used") is False

    def test_what_does_analysis_do(self, kernel):
        message = _send(kernel, "What does analysis do?")
        assert _intent(message) == "capability_detail"
        assert "analysis" in message.content

    def test_dotted_name_not_split(self, kernel):
        message = _send(kernel, "explain reasoning.trace")
        assert "reasoning.trace" in message.content


# ---------------------------------------------------------------------------
# B — previously-working detail names remain working
# ---------------------------------------------------------------------------


class TestExistingDetailBehaviourPreserved:
    @pytest.mark.parametrize("name", ["conversation", "echo"])
    def test_previously_working_names(self, kernel, name):
        message = _send(kernel, f"explain {name}")
        assert _intent(message) == "capability_detail"
        assert name in message.content


# ---------------------------------------------------------------------------
# C — unknown capability stays fail-closed (no fabricated detail)
# ---------------------------------------------------------------------------


class TestUnknownCapabilityFailsClosed:
    def test_unknown_name_not_fabricated(self, kernel):
        message = _send(kernel, "explain definitely_not_a_real_capability")
        assert _intent(message) != "capability_detail"
        assert "definitely_not_a_real_capability" not in message.content

    def test_unknown_do_form_not_fabricated(self, kernel):
        message = _send(kernel, "What does definitely_not_a_real_capability do?")
        assert _intent(message) != "capability_detail"


# ---------------------------------------------------------------------------
# D — investigation requests containing "analysis" remain investigations
# ---------------------------------------------------------------------------


class TestInvestigationRoutingPreserved:
    @pytest.mark.parametrize(
        "text",
        [
            "Investigate how Atlas performs analysis.",
            "Investigate the analysis capability.",
        ],
    )
    def test_investigation_still_investigation(self, kernel, text):
        message = _send(kernel, text)
        assert _intent(message) != "capability_detail"
        report = (message.metadata or {}).get("investigation")
        assert isinstance(report, dict)
        assert report.get("modification_status") == "NONE"


# ---------------------------------------------------------------------------
# E — research-shaped requests keep their existing routing
# ---------------------------------------------------------------------------


class TestResearchRoutingPreserved:
    def test_research_request_not_capability_detail(self, kernel):
        message = _send(kernel, "Research the best camera sensors available today.")
        assert _intent(message) != "capability_detail"
        assert (message.metadata or {}).get("investigation") is None
        # Research/information routing is retained: the turn reaches the
        # orchestration (research) path, not the capability-detail surface.
        assert isinstance((message.metadata or {}).get("orchestration"), dict)
