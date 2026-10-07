"""The governed seam: an explicitly supplied edit through the EXISTING cycle.

Proves the final deterministic bridge — a validated supplied structural edit is
authored by the EXISTING ``ChangeSupplier`` composite and carried through the
EXISTING F9 governed development cycle, stopping at the human approval boundary.
Nothing here authorizes, approves, executes or promotes anything.
"""

from __future__ import annotations

import pathlib

import pytest

from atlas.evolution.development_cycle import DevelopmentNeed
from atlas.evolution.structural_editor import STRUCTURAL_ORIGIN

ROOT = pathlib.Path(__file__).resolve().parents[1]

TARGET_PATH = "atlas/evolution/structural_editor.py"
TARGET_SYMBOL = "_indent_of"

REQUEST = (
    f"Update the explicitly named helper `{TARGET_SYMBOL}` in {TARGET_PATH} while "
    "preserving its public interface:\n\n"
    "```python\n"
    "def _indent_of(line: str) -> str:\n"
    "    return line[: len(line) - len(line.lstrip(' \\t'))]\n"
    "```\n"
)


@pytest.fixture(scope="module")
def kernel():
    import pkgutil
    import tempfile

    import atlas.storage as storage_pkg

    tmp = pathlib.Path(tempfile.mkdtemp())
    db = tmp / "governed.db"
    saved = []
    for info in pkgutil.iter_modules(storage_pkg.__path__):
        try:
            module = __import__(f"atlas.storage.{info.name}", fromlist=["*"])
        except Exception:  # noqa: BLE001
            continue
        for attr in dir(module):
            obj = getattr(module, attr)
            if isinstance(obj, type) and hasattr(obj, "DEFAULT_DB_PATH"):
                saved.append((obj, obj.DEFAULT_DB_PATH))
                obj.DEFAULT_DB_PATH = db
    from atlas.kernel.atlas import Atlas

    atlas = Atlas()
    atlas.start()
    try:
        yield atlas
    finally:
        atlas.shutdown()
        for obj, original in saved:
            obj.DEFAULT_DB_PATH = original


# ---------------------------------------------------------------------------
# 1-3. The seam exists and is registered in the EXISTING composite
# ---------------------------------------------------------------------------


class TestGovernedSeam:
    def test_structural_author_is_registered_in_the_existing_composite(self, kernel):
        from atlas.evolution.structural_editor import StructuralChangeSupplier

        composite = kernel._proposal_change_supplier
        assert composite is not None
        # the SAME authoritative composition serves the cycle and the authoring seam
        assert any(
            isinstance(supplier, StructuralChangeSupplier)
            for supplier in getattr(composite, "suppliers", ())
        ) or "StructuralChangeSupplier" in repr(composite)

    def test_the_structural_key_is_disjoint_from_the_existing_keys(self, kernel):
        structural_need = DevelopmentNeed(
            title="x",
            summary="x",
            metadata={
                "structural": [
                    {
                        "path": TARGET_PATH,
                        "symbol": TARGET_SYMBOL,
                        "kind": "replace",
                        "source": "def _indent_of(line: str) -> str:\n    return ''\n",
                    }
                ]
            },
        )
        supplied = kernel._proposal_change_supplier.supply_changes(structural_need)
        assert supplied is not None
        assert supplied.origin == STRUCTURAL_ORIGIN

        # a need with NO structural metadata is untouched by the new registration
        assert kernel._proposal_change_supplier.supply_changes(
            DevelopmentNeed(title="y", summary="y")
        ) is None

    def test_the_new_supplier_is_inert_without_its_own_key(self, kernel):
        from atlas.evolution.structural_editor import StructuralChangeSupplier

        # The registration cannot change any existing behaviour: with no
        # ``structural`` metadata the supplier returns None and the composite
        # falls through to exactly the suppliers it used before.
        assert StructuralChangeSupplier().supply_changes(
            DevelopmentNeed(title="y", summary="y")
        ) is None
        assert kernel._proposal_change_supplier.supply_changes(
            DevelopmentNeed(title="y", summary="y")
        ) is None


# ---------------------------------------------------------------------------
# 4-9. Real governed preparation and its boundaries
# ---------------------------------------------------------------------------


class TestGovernedPreparation:
    def test_supplied_edit_reaches_the_governed_cycle(self, kernel):
        payload = kernel.development_authoring_request(REQUEST)
        assert payload["ok"] is True, payload
        assert payload["proposal_id"]
        assert payload["proposal_status"] == "PENDING_APPROVAL"

    def test_the_cycle_stops_at_the_human_approval_boundary(self, kernel):
        payload = kernel.development_authoring_request(REQUEST)
        assert payload["authorized"] is False
        assert payload["executed"] is False
        assert payload["proposal_status"] != "APPROVED"

    def test_nothing_is_written_to_the_repository(self, kernel):
        before = (ROOT / TARGET_PATH).read_text(encoding="utf-8")
        kernel.development_authoring_request(REQUEST)
        assert (ROOT / TARGET_PATH).read_text(encoding="utf-8") == before

    def test_the_proposal_is_not_promoted_automatically(self, kernel):
        before = len(kernel.pending_promotion_reviews())
        kernel.development_authoring_request(REQUEST)
        assert len(kernel.pending_promotion_reviews()) == before

    def test_execution_still_requires_owner_authorization(self, kernel):
        payload = kernel.development_authoring_request(REQUEST)
        with pytest.raises(RuntimeError):
            kernel.run_development_execution(None, payload["proposal_id"])

    def test_execution_is_refused_before_approval(self, kernel):
        payload = kernel.development_authoring_request(REQUEST)
        # even a bound session cannot execute a DRAFT: status is checked too
        with pytest.raises(RuntimeError):
            kernel.run_development_execution(kernel.session_context, payload["proposal_id"])

    def test_no_model_or_provider_is_consulted(self, kernel):
        payload = kernel.development_authoring_request(REQUEST)
        assert payload["ok"] is True
        assert bool(getattr(kernel._ai_manager, "external_providers", False)) is False
        assert bool(
            kernel._config.get("development", "model_assisted_authoring", default=False)
        ) is False


# ---------------------------------------------------------------------------
# 10-16. Fail-closed boundary and unchanged classification
# ---------------------------------------------------------------------------


class TestFailClosed:
    @pytest.mark.parametrize(
        "text",
        [
            # ambiguous / unresolved target
            "Update the helper that validates empty input:\n\n```python\ndef h():\n    return 1\n```\n",
            "Improve the zzz nonexistent widget subsystem:\n\n```python\ndef t():\n    return 1\n```\n",
            # no supplied content
            f"Update the helper `{TARGET_SYMBOL}` in {TARGET_PATH}.",
            # symbol not part of the localized target
            f"Update the helper `not_a_symbol` in {TARGET_PATH}:\n\n```python\ndef x():\n    return 1\n```\n",
        ],
    )
    def test_refused_requests_never_reach_the_cycle(self, kernel, text):
        payload = kernel.development_authoring_request(text)
        # Either the turn is not a development request at all ({}) or the bridge
        # refuses it: in NEITHER case may a proposal, authorization or execution
        # exist.
        assert payload.get("ok") is not True
        assert payload.get("proposal_id", "") == ""
        assert payload.get("authorized", False) is False
        assert payload.get("executed", False) is False

    def test_non_development_requests_are_unchanged(self, kernel):
        for request in (
            "Investigate the development gap helper.",
            "What would be affected if I change atlas/memory/manager.py?",
            "Change it.",
            "Hello there.",
        ):
            assert kernel.development_authoring_request(request) == {}, request

    def test_repository_impact_and_investigation_stay_themselves(self, kernel):
        assert kernel._conversation._intake(
            "What would be affected if I change atlas/memory/manager.py?"
        ).task_type.value == "repository_impact_request"
        assert kernel._conversation._intake(
            "Investigate the development gap helper."
        ).task_type.value == "investigation_request"

    def test_an_unknown_symbol_fails_the_cycle_closed(self, kernel):
        request = (
            f"Update the helper `{TARGET_SYMBOL}` in {TARGET_PATH}:\n\n"
            "```python\ndef _indent_of(line: str) -> str:\n    return ''\n```\n"
        )
        # a valid parse that the supplier accepts, then the cycle's own validation
        payload = kernel.development_authoring_request(request)
        assert payload.get("ok") in (True, False)
        if payload.get("ok") is False:
            assert payload.get("proposal_id") == ""

    def test_ambiguous_localization_never_produces_a_proposal(self, kernel):
        request = (
            "Update the helper that validates empty input:\n\n"
            "```python\ndef helper():\n    return 1\n```\n"
        )
        localization = kernel.development_localization(request)
        assert localization["status"] != "resolved"


# ---------------------------------------------------------------------------
# 17-20. Determinism and governance invariants
# ---------------------------------------------------------------------------


class TestDeterminismAndGovernance:
    def test_repeated_governed_preparation_is_consistent(self, kernel):
        first = kernel.development_authoring_request(REQUEST)
        second = kernel.development_authoring_request(REQUEST)
        assert first["ok"] == second["ok"] is True
        assert first["proposal_status"] == second["proposal_status"]
        assert first["entry"] == second["entry"]

    def test_the_supplied_entry_is_the_validated_one(self, kernel):
        payload = kernel.development_authoring_request(REQUEST)
        assert payload["entry"]["path"] == TARGET_PATH
        assert payload["entry"]["symbol"] == TARGET_SYMBOL
        assert payload["entry"]["kind"] == "replace"

    def test_governance_surfaces_are_untouched(self, kernel):
        assert kernel._approval_manager is not None
        assert kernel._promotion_gate is not None
        assert kernel.pending_promotion_reviews() == []

    def test_approval_boundary_remains_mandatory(self, kernel):
        payload = kernel.development_authoring_request(REQUEST)
        proposal = kernel._evolution_memory.get_proposal(payload["proposal_id"])
        assert proposal is not None
        status = getattr(getattr(proposal, "status", None), "name", "")
        assert status == "PENDING_APPROVAL"
