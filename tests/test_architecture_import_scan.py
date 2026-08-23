"""Architecture import-scan regression tests.

Protects three AI-subsystem boundaries with AST/static source inspection
(no production package is imported by these tests):

  1. ``atlas/cognition/``          -- must not import AI providers or the AI
     router.  ``atlas.ai.routing.models`` is an allowed pure-data seam.
  2. ``atlas/runtime/``            -- must not import AI providers or the AI
     router.  The runtime's existing routing.models data import stays
     allowed.
  3. ``atlas/evolution/autonomy/`` -- must not import the AI subsystem at
     all; any module path beginning with ``atlas.ai`` is forbidden.

Both forbidden forms are detected:

    import atlas.ai.providers.foo
    from atlas.ai.providers import Foo

The recursive AST scan pattern is reused from
``tests/test_advanced_reasoning_import_scan.py``.
"""

from __future__ import annotations

import ast
import pathlib
import unittest

_ROOT = pathlib.Path(__file__).resolve().parents[1]

# Boundary directories.
_COGNITION_DIR: pathlib.Path = _ROOT / "atlas" / "cognition"
_RUNTIME_DIR: pathlib.Path = _ROOT / "atlas" / "runtime"
_AUTONOMY_DIR: pathlib.Path = _ROOT / "atlas" / "evolution" / "autonomy"

# Boundary 1 / 2 forbidden prefixes.
_AI_BOUNDARY_FORBIDDEN: tuple[str, ...] = (
    "atlas.ai.providers",
    "atlas.ai.router",
)
# Boundary 3 forbids the entire AI subsystem.
_AUTONOMY_FORBIDDEN: tuple[str, ...] = ("atlas.ai",)

# The pure-data routing.models seam is allowed in cognition and runtime.
_ALLOWED_DATA_SEAM: tuple[str, ...] = ("atlas.ai.routing.models",)


# ---------------------------------------------------------------------------
# Scan helpers (AST / static source inspection only)
# ---------------------------------------------------------------------------


def _python_files(directory: pathlib.Path) -> list[pathlib.Path]:
    """Return every ``*.py`` file under ``directory`` recursively."""
    return sorted(
        path
        for path in directory.rglob("*.py")
        if "__pycache__" not in path.parts
    )


def _imported_modules(tree: ast.AST) -> set[str]:
    """Collect every module path referenced by an import statement."""
    imported: set[str] = set()

    def _walk(node: ast.AST) -> None:
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imported.add(node.module)
        for child in ast.iter_child_nodes(node):
            _walk(child)

    _walk(tree)
    return imported


def _matches(module: str, prefixes: tuple[str, ...]) -> bool:
    """True when ``module`` equals a prefix or lives beneath it."""
    return any(
        module == prefix or module.startswith(prefix + ".")
        for prefix in prefixes
    )


def _violations(
    source: str,
    forbidden: tuple[str, ...],
    allowed: tuple[str, ...],
) -> list[str]:
    """Return the forbidden module paths imported by ``source``."""
    tree = ast.parse(source)
    return sorted(
        module
        for module in _imported_modules(tree)
        if not _matches(module, allowed) and _matches(module, forbidden)
    )


def _scan_directory(
    directory: pathlib.Path,
    forbidden: tuple[str, ...],
    allowed: tuple[str, ...],
) -> list[str]:
    """Return ``file: import`` violations for a package directory."""
    violations: list[str] = []
    for path in _python_files(directory):
        tree = ast.parse(
            path.read_text(encoding="utf-8"),
            filename=str(path),
        )
        for module in _imported_modules(tree):
            if not _matches(module, allowed) and _matches(module, forbidden):
                violations.append(f"{path.relative_to(_ROOT)}: {module}")
    return sorted(violations)


# ---------------------------------------------------------------------------
# Boundary 1 — cognition
# ---------------------------------------------------------------------------


class TestCognitionAIBoundary(unittest.TestCase):
    """atlas/cognition must not depend on AI providers or the AI router."""

    def test_package_files_exist(self):
        files = _python_files(_COGNITION_DIR)
        self.assertTrue(files, "no Python files found under atlas/cognition")
        names = {path.name for path in files}
        for expected in (
            "__init__.py",
            "api.py",
            "engine.py",
            "models.py",
            "pipeline.py",
        ):
            self.assertIn(expected, names)

    def test_no_forbidden_ai_imports(self):
        violations = _scan_directory(
            _COGNITION_DIR,
            _AI_BOUNDARY_FORBIDDEN,
            _ALLOWED_DATA_SEAM,
        )
        self.assertEqual(violations, [])

    def test_routing_models_data_seam_remains_allowed(self):
        """The pure-data routing seam must not be rejected by the scanner."""
        self.assertEqual(
            _violations(
                "from atlas.ai.routing.models import RoutingRequest\n",
                _AI_BOUNDARY_FORBIDDEN,
                _ALLOWED_DATA_SEAM,
            ),
            [],
        )


# ---------------------------------------------------------------------------
# Boundary 2 — runtime
# ---------------------------------------------------------------------------


class TestRuntimeAIBoundary(unittest.TestCase):
    """atlas/runtime must not depend on AI providers or the AI router."""

    def test_package_files_exist(self):
        files = _python_files(_RUNTIME_DIR)
        self.assertTrue(files, "no Python files found under atlas/runtime")
        names = {path.name for path in files}
        for expected in (
            "__init__.py",
            "runtime.py",
            "runtime_coordinator.py",
        ):
            self.assertIn(expected, names)

    def test_no_forbidden_ai_imports(self):
        violations = _scan_directory(
            _RUNTIME_DIR,
            _AI_BOUNDARY_FORBIDDEN,
            _ALLOWED_DATA_SEAM,
        )
        self.assertEqual(violations, [])

    def test_existing_routing_models_import_remains_allowed(self):
        """The runtime's existing RoutingRequest data import stays permitted."""
        coordinator = _RUNTIME_DIR / "runtime_coordinator.py"
        imported = _imported_modules(
            ast.parse(coordinator.read_text(encoding="utf-8"))
        )
        self.assertIn("atlas.ai.routing.models", imported)
        violations = [
            module
            for module in imported
            if not _matches(module, _ALLOWED_DATA_SEAM)
            and _matches(module, _AI_BOUNDARY_FORBIDDEN)
        ]
        self.assertEqual(violations, [])


# ---------------------------------------------------------------------------
# Boundary 3 — evolution autonomy
# ---------------------------------------------------------------------------


class TestEvolutionAutonomyAIBoundary(unittest.TestCase):
    """atlas/evolution/autonomy must not import the AI subsystem at all."""

    def test_package_files_exist(self):
        files = _python_files(_AUTONOMY_DIR)
        self.assertTrue(
            files,
            "no Python files found under atlas/evolution/autonomy",
        )
        names = {path.name for path in files}
        for expected in (
            "__init__.py",
            "dispatcher.py",
            "application_engine.py",
            "schedule_store.py",
        ):
            self.assertIn(expected, names)
        # The adapters subpackage is part of the same boundary.
        self.assertTrue((_AUTONOMY_DIR / "adapters").is_dir())
        self.assertTrue(
            (_AUTONOMY_DIR / "adapters" / "__init__.py").is_file()
        )

    def test_no_ai_imports(self):
        violations = _scan_directory(
            _AUTONOMY_DIR,
            _AUTONOMY_FORBIDDEN,
            (),
        )
        self.assertEqual(violations, [])


# ---------------------------------------------------------------------------
# Scanner self-checks (detection forms + allow-list behaviour)
# ---------------------------------------------------------------------------


class TestScannerDetection(unittest.TestCase):
    """The scanner detects both forbidden forms and honours the allow list."""

    def test_detects_autonomy_import_module_form(self):
        for source in (
            "import atlas.ai\n",
            "import atlas.ai.providers.foo\n",
            "import atlas.ai.router.ai_router\n",
        ):
            with self.subTest(source=source):
                self.assertTrue(
                    _violations(source, _AUTONOMY_FORBIDDEN, ())
                )

    def test_detects_autonomy_from_import_form(self):
        for source in (
            "from atlas.ai import providers\n",
            "from atlas.ai.providers import OpenAIProvider\n",
            "from atlas.ai.router import AIRouter\n",
        ):
            with self.subTest(source=source):
                self.assertTrue(
                    _violations(source, _AUTONOMY_FORBIDDEN, ())
                )

    def test_detects_cognition_boundary_both_forms(self):
        for source in (
            "import atlas.ai.providers.openai_provider\n",
            "from atlas.ai.providers import OpenAIProvider\n",
            "import atlas.ai.router.ai_router\n",
            "from atlas.ai.router import AIRouter\n",
        ):
            with self.subTest(source=source):
                self.assertTrue(
                    _violations(
                        source,
                        _AI_BOUNDARY_FORBIDDEN,
                        _ALLOWED_DATA_SEAM,
                    )
                )

    def test_allows_routing_models_data_seam(self):
        self.assertEqual(
            _violations(
                "from atlas.ai.routing.models import RoutingRequest\n",
                _AI_BOUNDARY_FORBIDDEN,
                _ALLOWED_DATA_SEAM,
            ),
            [],
        )

    def test_router_prefix_does_not_swallow_routing_models(self):
        """``atlas.ai.routing.models`` must not match ``atlas.ai.router``."""
        self.assertFalse(
            _matches("atlas.ai.routing.models", ("atlas.ai.router",))
        )


if __name__ == "__main__":
    unittest.main()