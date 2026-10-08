"""Command 2 (W5/W6) — specialist change discriminator + structural authoring."""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from atlas.evolution.specialist_change_supplier import (  # noqa: E402
    CHANGE_FULL_FILE,
    CHANGE_STRUCTURAL,
    SpecialistChangeSupplier,
)
from atlas.specialists import CODE_GENERATE, SpecialistProposal  # noqa: E402

MODULE_PATH = "pkg/target.py"
MODULE_SOURCE = (
    "import os\n"
    "\n"
    "\n"
    "def kept(value):\n"
    "    return value\n"
    "\n"
    "\n"
    "class Widget:\n"
    "    def render(self):\n"
    "        return kept(1)\n"
)


def _proposal(payload, capability=CODE_GENERATE):
    return SpecialistProposal(
        provider_id="test.provider",
        capability=capability,
        payload=payload,
        confidence=0.6,
    )


def _need(targets=(MODULE_PATH,), metadata=None):
    from atlas.evolution.development_cycle import DevelopmentNeed

    return DevelopmentNeed(
        title="t",
        summary="s",
        target_components=tuple(targets),
        metadata=dict(metadata or {}),
    )


class _Repo:
    """A tiny repository root the structural editor can read."""

    def __init__(self, tmp_path, source=MODULE_SOURCE):
        self.root = tmp_path
        path = tmp_path / MODULE_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")


class TestFullFileForm:
    def test_absent_change_defaults_to_full_file(self, tmp_path):
        supplier = SpecialistChangeSupplier(root=tmp_path)
        supplied = supplier.supply_changes(
            _need(metadata={"specialist_proposal": _proposal(
                {"files": {MODULE_PATH: "X = 1\n"}, "note": "n"}
            )})
        )
        assert supplied is not None
        assert supplied.code_changes == ((MODULE_PATH, "X = 1\n"),)
        assert supplied.origin == "specialist-proposal"

    def test_explicit_full_file_is_accepted(self, tmp_path):
        supplier = SpecialistChangeSupplier(root=tmp_path)
        supplied = supplier.supply_changes(
            _need(metadata={"specialist_proposal": _proposal(
                {"change": CHANGE_FULL_FILE, "files": {MODULE_PATH: "X = 1\n"}}
            )})
        )
        assert supplied is not None

    def test_listed_paths_must_agree(self, tmp_path):
        supplier = SpecialistChangeSupplier(root=tmp_path)
        assert supplier.supply_changes(
            _need(metadata={"specialist_proposal": _proposal(
                {"files": {MODULE_PATH: "X = 1\n"}, "paths": ["other.py"]}
            )})
        ) is None

    def test_structural_fields_reject_a_full_file_proposal(self, tmp_path):
        supplier = SpecialistChangeSupplier(root=tmp_path)
        assert supplier.supply_changes(
            _need(metadata={"specialist_proposal": _proposal(
                {"files": {MODULE_PATH: "X = 1\n"}, "symbol": "kept"}
            )})
        ) is None

    def test_unknown_payload_fields_are_refused(self, tmp_path):
        supplier = SpecialistChangeSupplier(root=tmp_path)
        assert supplier.supply_changes(
            _need(metadata={"specialist_proposal": _proposal(
                {"files": {MODULE_PATH: "X = 1\n"}, "execute": True}
            )})
        ) is None


class TestStructuralForm:
    def test_structural_proposal_is_applied_by_the_existing_editor(self, tmp_path):
        _Repo(tmp_path)
        supplier = SpecialistChangeSupplier(root=tmp_path)
        supplied = supplier.supply_changes(
            _need(metadata={"specialist_proposal": _proposal({
                "change": CHANGE_STRUCTURAL,
                "path": MODULE_PATH,
                "symbol": "kept",
                "kind": "replace",
                "source": "def kept(value):\n    return value * 2\n",
            })})
        )
        assert supplied is not None
        path, content = supplied.code_changes[0]
        assert path == MODULE_PATH
        assert "return value * 2" in content

    def test_every_unrelated_byte_is_preserved(self, tmp_path):
        _Repo(tmp_path)
        supplier = SpecialistChangeSupplier(root=tmp_path)
        supplied = supplier.supply_changes(
            _need(metadata={"specialist_proposal": _proposal({
                "change": CHANGE_STRUCTURAL,
                "path": MODULE_PATH,
                "symbol": "Widget.render",
                "kind": "insert_after",
                "source": "    def extra(self):\n        return 2\n",
            })})
        )
        assert supplied is not None
        content = supplied.code_changes[0][1]
        expected = MODULE_SOURCE.replace(
            "    def render(self):\n        return kept(1)\n",
            "    def render(self):\n        return kept(1)\n"
            "    def extra(self):\n        return 2\n",
        )
        assert content == expected

    def test_delete_kind_works(self, tmp_path):
        _Repo(tmp_path)
        supplier = SpecialistChangeSupplier(root=tmp_path)
        supplied = supplier.supply_changes(
            _need(metadata={"specialist_proposal": _proposal({
                "change": CHANGE_STRUCTURAL,
                "path": MODULE_PATH,
                "symbol": "kept",
                "kind": "delete",
            })})
        )
        assert supplied is not None
        assert "def kept" not in supplied.code_changes[0][1]

    def test_base_source_overrides_the_repository_file(self, tmp_path):
        _Repo(tmp_path)
        supplier = SpecialistChangeSupplier(
            root=tmp_path,
            base_source={MODULE_PATH: "def kept(value):\n    return 0\n"},
        )
        supplied = supplier.supply_changes(
            _need(metadata={"specialist_proposal": _proposal({
                "change": CHANGE_STRUCTURAL,
                "path": MODULE_PATH,
                "symbol": "kept",
                "kind": "replace",
                "source": "def kept(value):\n    return value\n",
            })})
        )
        assert supplied is not None
        assert supplied.code_changes[0][1] == "def kept(value):\n    return value\n"


class TestStructuralRefusals:
    def test_unknown_change_value_is_refused(self, tmp_path):
        supplier = SpecialistChangeSupplier(root=tmp_path)
        for bad in ("search_replace", "patch", "", "FULL_FILE "):
            assert supplier.supply_changes(
                _need(metadata={"specialist_proposal": _proposal(
                    {"change": bad, "path": MODULE_PATH, "symbol": "kept", "source": "x"}
                )})
            ) is None, bad

    def test_non_string_change_is_refused(self, tmp_path):
        supplier = SpecialistChangeSupplier(root=tmp_path)
        assert supplier.supply_changes(
            _need(metadata={"specialist_proposal": _proposal(
                {"change": 1, "path": MODULE_PATH, "symbol": "kept", "source": "x"}
            )})
        ) is None

    def test_invalid_symbol_is_refused(self, tmp_path):
        _Repo(tmp_path)
        supplier = SpecialistChangeSupplier(root=tmp_path)
        assert supplier.supply_changes(
            _need(metadata={"specialist_proposal": _proposal({
                "change": CHANGE_STRUCTURAL,
                "path": MODULE_PATH,
                "symbol": "does_not_exist",
                "kind": "replace",
                "source": "def x():\n    return 1\n",
            })})
        ) is None

    def test_unsupported_kind_is_refused(self, tmp_path):
        _Repo(tmp_path)
        supplier = SpecialistChangeSupplier(root=tmp_path)
        assert supplier.supply_changes(
            _need(metadata={"specialist_proposal": _proposal({
                "change": CHANGE_STRUCTURAL,
                "path": MODULE_PATH,
                "symbol": "kept",
                "kind": "wrap",
                "source": "def x():\n    return 1\n",
            })})
        ) is None

    def test_missing_source_is_refused(self, tmp_path):
        _Repo(tmp_path)
        supplier = SpecialistChangeSupplier(root=tmp_path)
        assert supplier.supply_changes(
            _need(metadata={"specialist_proposal": _proposal({
                "change": CHANGE_STRUCTURAL,
                "path": MODULE_PATH,
                "symbol": "kept",
            })})
        ) is None

    def test_oversized_source_is_refused(self, tmp_path):
        _Repo(tmp_path)
        supplier = SpecialistChangeSupplier(root=tmp_path)
        assert supplier.supply_changes(
            _need(metadata={"specialist_proposal": _proposal({
                "change": CHANGE_STRUCTURAL,
                "path": MODULE_PATH,
                "symbol": "kept",
                "kind": "replace",
                "source": "def kept(value):\n    return value\n" + "# pad\n" * 20000,
            })})
        ) is None

    def test_unparseable_result_is_refused(self, tmp_path):
        _Repo(tmp_path)
        supplier = SpecialistChangeSupplier(root=tmp_path)
        assert supplier.supply_changes(
            _need(metadata={"specialist_proposal": _proposal({
                "change": CHANGE_STRUCTURAL,
                "path": MODULE_PATH,
                "symbol": "kept",
                "kind": "replace",
                "source": "def kept(:\n",
            })})
        ) is None

    def test_architecture_sensitive_target_is_refused(self, tmp_path):
        from atlas.evolution.promotion_gate import ARCHITECTURE_SENSITIVE_PREFIXES

        prefix = sorted(ARCHITECTURE_SENSITIVE_PREFIXES)[0]
        path = prefix.replace(".", "/") + ".py"
        (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / path).write_text("def kept():\n    return 1\n", encoding="utf-8")
        supplier = SpecialistChangeSupplier(root=tmp_path)
        assert supplier.supply_changes(
            _need(
                targets=(path,),
                metadata={"specialist_proposal": _proposal({
                    "change": CHANGE_STRUCTURAL,
                    "path": path,
                    "symbol": "kept",
                    "kind": "replace",
                    "source": "def kept():\n    return 2\n",
                })},
            )
        ) is None

    def test_out_of_target_structural_proposal_is_refused(self, tmp_path):
        _Repo(tmp_path)
        supplier = SpecialistChangeSupplier(root=tmp_path)
        assert supplier.supply_changes(
            _need(
                targets=("pkg/other.py",),
                metadata={"specialist_proposal": _proposal({
                    "change": CHANGE_STRUCTURAL,
                    "path": MODULE_PATH,
                    "symbol": "kept",
                    "kind": "replace",
                    "source": "def kept(value):\n    return value\n",
                })},
            )
        ) is None

    def test_wrong_capability_is_refused(self, tmp_path):
        _Repo(tmp_path)
        supplier = SpecialistChangeSupplier(root=tmp_path)
        assert supplier.supply_changes(
            _need(metadata={"specialist_proposal": _proposal(
                {"change": CHANGE_STRUCTURAL, "path": MODULE_PATH, "symbol": "kept",
                 "source": "def kept(value):\n    return value\n"},
                capability="code.review",
            )})
        ) is None

    def test_no_proposal_is_inert(self, tmp_path):
        supplier = SpecialistChangeSupplier(root=tmp_path)
        assert supplier.supply_changes(_need()) is None
