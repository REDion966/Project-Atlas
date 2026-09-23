"""Phase 2.5 — test/verification mapping: evidence contract.

Investigation result (evidence, not aspiration): Atlas already owns the
minimum verification knowledge it needs to reason about whether its
components/capabilities are verified and to validate a controlled development
change. The relationships are either explicitly machine-readable or
deterministically derivable from authoritative repository structure:

* change → relevant tests: ``atlas.evolution.development_test_selection
  .select_relevant_tests`` (Phase 4.2) — deterministic, bounded, name-convention
  based; used by ``SelfDevelopmentLoop`` to choose the sandbox VERIFY target.
* execution → verification evidence: ``DevelopmentOutcome``
  (``verification_passed`` / ``test_outcome``) → ``DevelopmentVerification``
  ``VerificationReport`` (VERIFIED / UNVERIFIED / PARTIAL / UNVERIFIABLE).
* repository structure: ``RepositoryMap`` includes the ``tests/`` tree as
  ordinary modules (tests are evidence, not architecture, so they are never
  classified or hard-coded as architectural truth).
* self-knowledge: ``CapabilityModel`` maps capability → providing component and
  ``ArchitectureModel.locate()`` maps module/component → impact, so
  capability → tests is derivable transitively via the existing selector.

No persistent test/verification registry exists or is warranted: tests are
evidence discovered from authoritative structure at verification time. No
production change was made for Phase 2.5.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from atlas.evolution.development_models import (
    DevelopmentOutcome,
    DevelopmentOutcomeStatus,
)
from atlas.evolution.development_test_selection import select_relevant_tests
from atlas.evolution.development_verification import (
    DevelopmentVerification,
    VerificationStatus,
)
from atlas.lifecycle.component_registry import ComponentRegistry
from atlas.lifecycle.models import ComponentMetadata, ComponentStatus
from atlas.reasoning.execution.registry import CapabilityRegistry
from atlas.research.repository_map import RepositoryMapBuilder
from atlas.self_knowledge.architecture_model import build_architecture_model
from atlas.self_knowledge.capability_model import build_capability_model


class TestPhase25VerificationMappingEvidence:
    def test_repository_map_includes_tests_as_ordinary_modules(self, tmp_path):
        root = tmp_path / "repo"
        (root / "atlas").mkdir(parents=True)
        (root / "atlas" / "__init__.py").write_text("", encoding="utf-8")
        (root / "atlas" / "widget.py").write_text("x = 1\n", encoding="utf-8")
        (root / "tests").mkdir()
        (root / "tests" / "__init__.py").write_text("", encoding="utf-8")
        (root / "tests" / "test_widget.py").write_text(
            "import atlas.widget\n", encoding="utf-8"
        )

        repo_map = RepositoryMapBuilder(root).build()
        info = next(m for m in repo_map.modules if m.module == "tests.test_widget")

        assert info.is_package is False
        assert "atlas.widget" in info.internal_imports
        # Tests are ordinary modules: no test-specific classification exists in
        # the authoritative map (tests are evidence, not architecture).
        assert not hasattr(info, "is_test")
        assert not hasattr(info, "covers_component")

    def test_verification_verdict_is_evidence_based_not_filename_based(self):
        def result(verification_passed: bool) -> SimpleNamespace:
            outcome = DevelopmentOutcome(
                outcome=DevelopmentOutcomeStatus.SUCCESS,
                proposal_id="P-DEMO",
                plan_id="PLAN-DEMO",
                iteration=1,
                message="iteration",
                verification_passed=verification_passed,
                test_outcome="passed" if verification_passed else "failed",
            )
            return SimpleNamespace(
                status=DevelopmentOutcomeStatus.SUCCESS,
                outcomes=[outcome],
                iterations_used=1,
                message="",
            )

        verified = DevelopmentVerification().verify(result(True))
        unverified = DevelopmentVerification().verify(result(False))

        assert verified.status is VerificationStatus.VERIFIED
        assert verified.all_tests_passed is True
        assert unverified.status is VerificationStatus.UNVERIFIED
        assert unverified.all_tests_passed is False

    def test_capability_to_test_relationship_is_transitively_derivable(self):
        registry = ComponentRegistry()
        registry.register(
            ComponentMetadata(
                name="widget_service",
                package="atlas.widget.service",
                module_path="atlas.widget.service.widget_service.WidgetService",
                description="Widget service.",
                status=ComponentStatus.HEALTHY,
                provided_capabilities=["widget_search"],
            )
        )
        capabilities = CapabilityRegistry()
        capabilities.register("widget_search", lambda *_a, **_k: None)
        model = build_architecture_model(
            registry,
            capability_model=build_capability_model(registry, capabilities, None),
        )

        # capability -> providing component (the existing capability join)
        assert dict(model.capability_index)["widget_search"] == ("widget_service",)

        # component -> declared entry module -> module file -> tests (the
        # existing deterministic change->test selector). No registry involved.
        component = next(c for c in model.components if c.name == "widget_service")
        module_dotted = component.module_path.rsplit(".", 1)[0]
        changed_file = module_dotted.replace(".", "/") + ".py"
        selected = select_relevant_tests(
            [changed_file],
            ["tests/test_widget_service.py", "tests/test_other.py"],
        )
        assert selected == ("tests/test_widget_service.py",)

    def test_no_persistent_test_or_verification_registry(self):
        # Phase 2.5 intentionally introduced no test/verification registry in
        # self-knowledge; the existing derivation stays authoritative.
        import atlas.self_knowledge as self_knowledge

        banned = {
            "TestRegistry",
            "VerificationRegistry",
            "TestMap",
            "TestModel",
            "VerificationModel",
        }
        assert banned.isdisjoint(set(dir(self_knowledge)))

        package_dir = Path(self_knowledge.__file__).parent
        module_stems = {p.stem for p in package_dir.glob("*.py")}
        assert {"test_registry", "test_model", "verification_model"}.isdisjoint(
            module_stems
        )
