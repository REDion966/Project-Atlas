"""Phase 12.1 — Independence inventory & dependency graph: evidence contract.

Validation result: Atlas imports exactly ONE external (non-stdlib) module —
``requests`` — a generic HTTP client used by the authorized research web source
and by the OPTIONAL external-provider seam. No AI/model/provider SDK, and no
external coding agent, is imported anywhere in ``atlas/**``.
"""

from __future__ import annotations

import json

from atlas.self_knowledge.independence_inventory import (
    LOCAL_TOOL_EXECUTABLES,
    OPTIONAL_MODEL_SEAMS,
    RUNTIME_ENTRY_PATHS,
    DependencyClass,
    build_independence_inventory,
    repository_root,
    scan_atlas_imports,
    scan_boot_imports,
)

_INVENTORY = build_independence_inventory(repository_root())


class TestPhase121IndependenceInventory:
    def test_exactly_one_external_module_is_imported(self):
        names = {record.name for record in _INVENTORY.external_dependencies}
        assert names == {"requests"}

    def test_requests_is_an_information_source_not_an_ai_dependency(self):
        record = next(
            r for r in _INVENTORY.external_dependencies if r.name == "requests"
        )
        assert record.classification is DependencyClass.INFORMATION_SOURCE
        assert record.ai_related is False
        assert record.required is False

    def test_no_prohibited_ai_import_exists_anywhere(self):
        assert _INVENTORY.prohibited_ai_imports == ()
        assert _INVENTORY.required_ai_dependencies() == ()

    def test_no_dependency_remains_unclassified(self):
        assert _INVENTORY.unknown_dependencies == ()
        assert all(
            record.classification is not DependencyClass.UNKNOWN
            for record in _INVENTORY.external_dependencies
        )
        assert _INVENTORY.independent is True

    def test_declared_requirements_match_the_scan(self):
        assert _INVENTORY.declared_requirements == ("requests",)
        imported = set(scan_atlas_imports(repository_root()))
        assert set(_INVENTORY.declared_requirements) <= imported

    def test_only_requests_is_needed_to_boot(self):
        boot = scan_boot_imports(repository_root())
        assert boot == ("requests",)
        assert _INVENTORY.boot_entry_paths  # the runtime entries exist
        assert _INVENTORY.boot_entry_paths == tuple(
            rel for rel in RUNTIME_ENTRY_PATHS if (repository_root() / rel).is_file()
        )
        assert _INVENTORY.boot_entry_paths == (
            "main.py",
            "atlas/cli/main.py",
            "atlas/cli/cli.py",
            "atlas/kernel/atlas.py",
        )

    def test_inventory_is_deterministic_and_json_safe(self):
        first = build_independence_inventory(repository_root()).to_dict()
        second = build_independence_inventory(repository_root()).to_dict()
        assert first == second
        json.dumps(first, sort_keys=True)

    def test_report_is_deterministic_and_names_the_seams_and_tools(self):
        report = _INVENTORY.to_markdown()
        assert report == build_independence_inventory(repository_root()).to_markdown()
        for _, note in OPTIONAL_MODEL_SEAMS:
            assert note[:20] in report
        for name, _ in LOCAL_TOOL_EXECUTABLES:
            assert f"`{name}`" in report

    def test_optional_model_seams_are_declared_as_such(self):
        names = " ".join(name for name, _ in OPTIONAL_MODEL_SEAMS)
        assert "ModelAssistedChangeSupplier" in names
        assert "atlas.ai.providers" in names
