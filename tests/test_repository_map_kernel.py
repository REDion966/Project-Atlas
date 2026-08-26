"""Stage A1.2 — kernel integration of the repository self-knowledge map.

Verifies that ``Atlas`` exposes a read-only repository map with lazy,
cached, fail-soft build semantics and an explicit refresh entry point —
without any automatic rebuilding loops.
"""

from atlas.kernel.atlas import Atlas
from atlas.research.repository_map import RepositoryMapBuilder


class _FailingBuilder:
    """Builder stand-in whose build always fails."""

    def build(self):
        raise RuntimeError("map build exploded")


class TestKernelRepositoryMap:
    def test_property_returns_cached_map(self):
        atlas = Atlas()
        first = atlas.repository_map
        second = atlas.repository_map

        assert first is not None          # fail-soft: real repo builds fine
        assert first is second            # built once, cached
        assert first.module_count() > 0   # the Atlas tree is non-trivial
        assert any(
            info.module.startswith("atlas.") for info in first.modules
        )

    def test_refresh_rebuilds_and_returns_fresh_snapshot(self):
        atlas = Atlas()
        original = atlas.repository_map
        refreshed = atlas.refresh_repository_map()

        assert refreshed is not None
        assert refreshed is not original  # new snapshot object
        # Cached access after refresh serves the refreshed snapshot.
        assert atlas.repository_map is refreshed

    def test_missing_builder_returns_none_without_crash(self):
        atlas = Atlas()
        atlas._repository_map_builder = None
        atlas._repository_map = None

        assert atlas.repository_map is None
        assert atlas.refresh_repository_map() is None

    def test_builder_failure_is_fail_soft(self):
        atlas = Atlas()
        atlas._repository_map_builder = _FailingBuilder()
        atlas._repository_map = None

        assert atlas.repository_map is None  # never raises

    def test_builder_construction_uses_real_repository_root(self):
        from pathlib import Path

        atlas = Atlas()
        builder = atlas._repository_map_builder

        assert isinstance(builder, RepositoryMapBuilder)
        # Repository root = two levels above atlas/kernel/atlas.py.
        assert builder._root == Path(__file__).resolve().parents[1]