"""Phase 9.1 — Self-development capability inventory: evidence contract.

Investigation result: no deterministic development-capability inventory existed,
so the smallest read-only catalogue was added at
``atlas/evolution/self_development_inventory.py``. It classifies each governed
development-lifecycle stage by ownership (Atlas-owned / governed-only /
human-dependent / external-optional / missing) and availability.
"""

from __future__ import annotations

import json

from atlas.evolution.self_development_inventory import (
    Availability,
    OwnershipKind,
    build_inventory,
)


class TestPhase91SelfDevelopmentInventory:
    def test_inventory_classifies_each_lifecycle_stage(self):
        inventory = build_inventory()
        assert (
            inventory.by_key("planning").ownership is OwnershipKind.ATLAS_OWNED
        )
        assert (
            inventory.by_key("change_generation").ownership
            is OwnershipKind.ATLAS_OWNED
        )
        assert (
            inventory.by_key("approval").ownership is OwnershipKind.GOVERNED_ONLY
        )
        assert (
            inventory.by_key("promotion").ownership is OwnershipKind.HUMAN_DEPENDENT
        )
        assert (
            inventory.by_key("model_assisted_authoring").ownership
            is OwnershipKind.EXTERNAL_OPTIONAL
        )

    def test_required_capabilities_are_present(self):
        inventory = build_inventory()
        assert inventory.missing_required() == ()
        for key in inventory.atlas_owned():
            assert inventory.by_key(key).availability is Availability.AVAILABLE

    def test_no_required_external_dependency(self):
        inventory = build_inventory()
        assert inventory.external_dependencies() == ()
        assert inventory.self_sufficient is True
        # The external model is optional, never required.
        assert "model_assisted_authoring" in inventory.external_optional()
        assert inventory.by_key("model_assisted_authoring").required is False

    def test_inventory_records_honest_limitations(self):
        inventory = build_inventory()
        assert inventory.by_key("change_generation").limitation
        assert inventory.by_key("promotion").limitation

    def test_inventory_is_deterministic_and_json_safe(self):
        first = build_inventory().to_dict()
        second = build_inventory().to_dict()
        assert first == second
        json.dumps(first, sort_keys=True)
