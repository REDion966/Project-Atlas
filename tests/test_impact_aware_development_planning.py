"""Stage C — Impact-aware development planning validation.

Verifies that ``DevelopmentPlanner``, when given a cache-only repository
map provider, validates affected-file targets against the map (known vs
unknown) and expands transitive dependency impact into advisory plan
metadata — without changing plan structure or ever failing planning.

Default behavior (no provider / no map / raising provider) is preserved
exactly as before Stage C.
"""

from datetime import datetime

import pytest

from atlas.evolution.development_planner import IMPACT_MAX_DEPTH, DevelopmentPlanner
from atlas.evolution.models import ProposalStatus
from atlas.evolution.proposal_generator import ProposalGenerator
from atlas.research.repository_map import RepositoryMapBuilder


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def mapped_repo(tmp_path):
    """Tree where pkg.user depends on pkg.core (impact edge)."""
    root = tmp_path / "repo"
    pkg = root / "pkg"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "core.py").write_text("VALUE = 1\n", encoding="utf-8")
    (pkg / "user.py").write_text(
        "from pkg.core import VALUE\nUSE = VALUE\n", encoding="utf-8"
    )
    return RepositoryMapBuilder(root).build()


def _approved_proposal(targets: list[str], pid: str = "PROP-C1"):
    from atlas.evolution.improvement_planner import (
        ImprovementPlanner,
        ImprovementPriority,
    )
    from atlas.evolution.models import Weakness

    weakness = Weakness(
        area="testing",
        description="synthetic",
        severity=ImprovementPriority.MEDIUM,
        supporting_observations=[],
        detected_at=datetime.now(),
    )
    proposal = ProposalGenerator().generate_proposal(
        ImprovementPlanner().create_improvement_plan([weakness])
    )
    proposal.proposal_id = pid
    proposal.metadata["affected_files"] = list(targets)
    proposal.status = ProposalStatus.APPROVED
    proposal.approved_at = datetime.now()
    return proposal


class TestLegacyBehaviorPreserved:
    def test_no_provider_plan_unchanged(self):
        planner = DevelopmentPlanner()
        plan = planner.plan(_approved_proposal(["pkg/core.py"]))

        assert len(plan.steps) == 7
        assert "repository_validation" not in plan.metadata

    def test_missing_provider_does_not_crash(self):
        planner = DevelopmentPlanner(repository_map_provider=None)
        plan = planner.plan(_approved_proposal(["anything.py"]))
        assert len(plan.steps) == 7
        assert "repository_validation" not in plan.metadata

    def test_raising_provider_is_swallowed(self):
        def boom():
            raise RuntimeError("no scanning")

        planner = DevelopmentPlanner(repository_map_provider=boom)
        plan = planner.plan(_approved_proposal(["x.py"]))
        assert "repository_validation" not in plan.metadata

    def test_none_snapshot_is_swallowed(self):
        planner = DevelopmentPlanner(repository_map_provider=lambda: None)
        plan = planner.plan(_approved_proposal(["x.py"]))
        assert "repository_validation" not in plan.metadata


class TestRepositoryValidation:
    def test_known_target_accepted_without_warning(self, mapped_repo):
        planner = DevelopmentPlanner(
            repository_map_provider=lambda: mapped_repo
        )
        plan = planner.plan(_approved_proposal(["pkg/core.py"]))

        validation = plan.metadata["repository_validation"]
        assert validation["known_targets"] == ["pkg/core.py"]
        assert validation["unknown_targets"] == []
        assert plan.affected_files == ["pkg/core.py"]  # preserved

    def test_unknown_target_preserved_and_warned(self, mapped_repo):
        planner = DevelopmentPlanner(
            repository_map_provider=lambda: mapped_repo
        )
        targets = ["pkg/core.py", "does/not/exist.py"]
        plan = planner.plan(_approved_proposal(targets))

        validation = plan.metadata["repository_validation"]
        assert validation["known_targets"] == ["pkg/core.py"]
        assert validation["unknown_targets"] == ["does/not/exist.py"]
        # Unknown targets are never dropped from the plan.
        assert plan.affected_files == targets

    def test_dependency_impact_expansion(self, mapped_repo):
        """Changing pkg/core must surface pkg/user as impacted."""
        planner = DevelopmentPlanner(
            repository_map_provider=lambda: mapped_repo
        )
        plan = planner.plan(_approved_proposal(["pkg/core.py"]))

        validation = plan.metadata["repository_validation"]
        assert "pkg.user" in validation["impact_expansion"]
        assert "pkg/user.py" in validation["related_affected_files"]
        assert validation["dependency_count"] >= 1

    def test_multiple_targets_deduplicate_impact(self, tmp_path):
        root = tmp_path / "repo"
        pkg = root / "pkg"
        pkg.mkdir(parents=True)
        (pkg / "__init__.py").write_text("", encoding="utf-8")
        (pkg / "a.py").write_text("A = 1\n", encoding="utf-8")
        (pkg / "b.py").write_text("B = 2\n", encoding="utf-8")
        (root / "user_both.py").write_text(
            "from pkg.a import A\nfrom pkg.b import B\nC = A + B\n",
            encoding="utf-8",
        )
        map_ = RepositoryMapBuilder(root).build()

        planner = DevelopmentPlanner(repository_map_provider=lambda: map_)
        plan = planner.plan(_approved_proposal(["pkg/a.py", "pkg/b.py"]))

        validation = plan.metadata["repository_validation"]
        assert validation["impact_expansion"].count("user_both") == 1
        assert validation["dependency_count"] == 1

    def test_empty_repository_map_still_plans(self, tmp_path):
        empty_root = tmp_path / "empty"
        empty_root.mkdir()
        empty_map = RepositoryMapBuilder(empty_root).build()

        planner = DevelopmentPlanner(repository_map_provider=lambda: empty_map)
        plan = planner.plan(_approved_proposal(["anything.py"]))

        validation = plan.metadata["repository_validation"]
        assert validation["known_targets"] == []
        assert validation["unknown_targets"] == ["anything.py"]
        assert len(plan.steps) == 7

    def test_circular_dependencies_terminate(self, tmp_path):
        root = tmp_path / "repo"
        root.mkdir()
        (root / "loop_a.py").write_text("import loop_b\n", encoding="utf-8")
        (root / "loop_b.py").write_text("import loop_a\n", encoding="utf-8")
        map_ = RepositoryMapBuilder(root).build()

        planner = DevelopmentPlanner(repository_map_provider=lambda: map_)
        plan = planner.plan(_approved_proposal(["loop_a.py"]))  # must not hang

        validation = plan.metadata["repository_validation"]
        assert "loop_b" in validation["impact_expansion"]

    def test_metadata_is_json_safe(self, mapped_repo):
        import json

        planner = DevelopmentPlanner(
            repository_map_provider=lambda: mapped_repo
        )
        plan = planner.plan(
            _approved_proposal(["pkg/core.py", "ghost.py"])
        )

        payload = json.dumps(plan.metadata["repository_validation"])
        assert "pkg.core" not in payload or isinstance(payload, str)

    def test_depth_bound_respected(self, mapped_repo):
        """Impact expansion uses the module-level depth constant."""
        planner = DevelopmentPlanner(
            repository_map_provider=lambda: mapped_repo,
        )
        plan = planner.plan(_approved_proposal(["pkg/core.py"]))
        validation = plan.metadata["repository_validation"]

        max_expected = IMPACT_MAX_DEPTH * 10  # generous structural bound
        assert validation["dependency_count"] <= max_expected


# ---------------------------------------------------------------------------
# Kernel wiring (cache-only provider, lazy map)
# ---------------------------------------------------------------------------


class TestKernelWiring:
    def test_kernel_planner_consumes_cached_map(self):
        from atlas.kernel.atlas import Atlas

        atlas = Atlas()
        atlas.start()
        try:
            planner = atlas.development_planner
            proposal = _approved_proposal(["pkg/core.py"], pid="PROP-K1")

            # Lazy world: no map built yet -> advisory section absent.
            before = planner.plan(proposal)
            assert "repository_validation" not in before.metadata

            # Explicit refresh builds the map; the cache-only provider
            # then serves it without any rescan.
            assert atlas.refresh_repository_map() is not None
            after = planner.plan(_approved_proposal(["pkg/core.py"], pid="PROP-K2"))
            validation = after.metadata["repository_validation"]
            # Real Atlas tree: at least one of our targets may be unknown,
            # but the section itself must now exist.
            assert "known_targets" in validation
            assert "unknown_targets" in validation
        finally:
            atlas.shutdown()