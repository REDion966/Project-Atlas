"""Atlas Evolution — Deterministic Scaffold Change Supplier (Phase 5.2).

A MODEL-INDEPENDENT :class:`~atlas.evolution.development_cycle.ChangeSupplier`
that authors a bounded, well-understood change class deterministically: a new
capability-handler factory module plus a sandbox-self-verifying test, rendered
from a fixed template driven by a structured spec carried in the need.

It reuses the EXISTING change-validation and bounds surfaces
(:meth:`CodeChangeSet.validate_path`, ``ARCHITECTURE_SENSITIVE_PREFIXES`) and
never authors novel logic, structural edits to existing modules, or diffs.

Spec (in ``need.metadata["scaffold"]``)::

    {
        "module": "atlas/example/example_handlers.py",   # required, in a package dir
        "test_module": "tests/test_example_handlers.py",  # optional (defaults)
        "capability_name": "example.run",                # required
        "class_name": "ExampleHandlersFactory",           # optional (defaults)
        "handler_name": "_run_handler"                    # optional (defaults)
    }

Deterministic: identical spec -> identical bytes. Stdlib only. No AI.
"""

from __future__ import annotations

import posixpath
from dataclasses import dataclass

from atlas.evolution.autonomy.code_sandbox import CodeChangeSet
from atlas.evolution.development_cycle import DevelopmentNeed, SuppliedChanges
from atlas.evolution.promotion_gate import ARCHITECTURE_SENSITIVE_PREFIXES

#: Maximum authored files (bounded; the controller additionally bounds these).
MAX_SCAFFOLD_FILES: int = 2

_MODULE_TEMPLATE = '''"""{docstring}

Generated deterministically by the Phase 5.2 scaffold author. Data-only
capability registration; contains no external dependencies and no AI.
"""

from __future__ import annotations

from typing import Any, Callable

#: Handler signature matches the existing CapabilityHandler convention.
CapabilityHandler = Callable[[dict], Any]

CAPABILITY_NAME = "{capability_name}"


class {class_name}:
    """A minimal capability-handler factory (deterministic scaffold)."""

    def __init__(self, collaborator: Any | None = None) -> None:
        self._collaborator = collaborator

    def handlers(self) -> dict[str, CapabilityHandler]:
        """Return the dotted capability name -> handler mapping."""
        return {{CAPABILITY_NAME: self.{handler_name}}}

    def register(self, registry: Any) -> None:
        """Register every handler on the supplied registry (additive)."""
        for name, handler in self.handlers().items():
            registry.register(name, handler)

    def {handler_name}(self, params: dict) -> dict:
        """Deterministic handler body (no side effects, no AI)."""
        if not isinstance(params, dict):
            return {{"capability": CAPABILITY_NAME, "status": "invalid"}}
        return {{"capability": CAPABILITY_NAME, "status": "ok"}}
'''

_TEST_TEMPLATE = '''"""Sandbox self-verification for the scaffolded capability (Phase 5.2).

Loads the generated module by relative path so the test runs inside the
disposable sandbox without requiring package ``__init__`` seeding.
"""

from __future__ import annotations

import importlib.util
import pathlib

_MODULE_PATH = pathlib.Path(__file__).resolve().parent.parent / "{module_rel}"
_spec = importlib.util.spec_from_file_location("{module_stem}", _MODULE_PATH)
assert _spec is not None and _spec.loader is not None
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)


def test_scaffold_registers_capability():
    factory = _module.{class_name}()
    handlers = factory.handlers()
    assert "{capability_name}" in handlers
    result = handlers["{capability_name}"]({{}})
    assert result["status"] == "ok"


def test_scaffold_register_is_additive():
    class _Registry:
        def __init__(self):
            self.names = []

        def register(self, name, handler):
            self.names.append(name)

    registry = _Registry()
    _module.{class_name}().register(registry)
    assert registry.names == ["{capability_name}"]
'''


@dataclass(frozen=True, slots=True)
class ScaffoldSpec:
    """Validated scaffold specification (pure data)."""

    module: str
    test_module: str
    capability_name: str
    class_name: str
    handler_name: str


class ScaffoldChangeSupplier:
    """Deterministic ChangeSupplier for the capability-handler change class."""

    def __init__(self, max_files: int = MAX_SCAFFOLD_FILES) -> None:
        if max_files < 1:
            raise ValueError("max_files must be >= 1")
        self._max_files = max_files

    @property
    def origin(self) -> str:
        """Provenance marker stamped on authored changes."""
        return "deterministic-scaffold"

    def supply_changes(self, need: DevelopmentNeed) -> SuppliedChanges | None:
        """Author the scaffold for ``need`` (or ``None`` when unspecified)."""
        metadata = getattr(need, "metadata", None)
        if not isinstance(metadata, dict):
            return None
        raw = metadata.get("scaffold")
        if raw is None:
            return None
        if not isinstance(raw, dict):
            raise ValueError("malformed 'scaffold' spec (must be an object)")

        spec = self._validate(raw)
        module_content = _MODULE_TEMPLATE.format(
            docstring=f"Atlas capability scaffold: {spec.capability_name}.",
            capability_name=spec.capability_name,
            class_name=spec.class_name,
            handler_name=spec.handler_name,
        )
        test_content = _TEST_TEMPLATE.format(
            module_rel=spec.module,
            module_stem=posixpath.splitext(posixpath.basename(spec.module))[0],
            class_name=spec.class_name,
            capability_name=spec.capability_name,
        )
        return SuppliedChanges(
            code_changes=((spec.module, module_content),),
            test_files=((spec.test_module, test_content),),
            origin=self.origin,
            confidence=1.0,
            notes="deterministic capability-handler scaffold",
        )

    # -- validation --------------------------------------------------------

    def _validate(self, raw: dict) -> ScaffoldSpec:
        module = raw.get("module")
        capability_name = raw.get("capability_name")
        if not isinstance(module, str) or not module.strip():
            raise ValueError("scaffold 'module' is required")
        if not isinstance(capability_name, str) or not capability_name.strip():
            raise ValueError("scaffold 'capability_name' is required")
        module = module.strip().replace("\\", "/")

        # Path confinement + bounds (reuse the existing validator).
        CodeChangeSet.validate_path(module)
        if "/" not in module:
            raise ValueError(
                "scaffold 'module' must live in a package directory"
            )
        if not module.endswith(".py"):
            raise ValueError("scaffold 'module' must be a .py file")

        stem = posixpath.splitext(posixpath.basename(module))[0]
        if not stem or not stem.replace("_", "").isalnum():
            raise ValueError("scaffold module stem must be alphanumeric")

        dotted = posixpath.splitext(module)[0].replace("/", ".")
        if any(dotted.startswith(prefix) for prefix in ARCHITECTURE_SENSITIVE_PREFIXES):
            raise ValueError(
                "scaffold cannot target an architecture-sensitive module"
            )

        test_module = raw.get("test_module", f"tests/test_{stem}.py")
        if not isinstance(test_module, str) or not test_module.strip():
            raise ValueError("scaffold 'test_module' must be a non-empty string")
        test_module = test_module.strip().replace("\\", "/")
        CodeChangeSet.validate_path(test_module)
        if not test_module.startswith("tests/") or not test_module.endswith(".py"):
            raise ValueError(
                "scaffold 'test_module' must be a tests/<name>.py path"
            )

        class_name = raw.get("class_name") or (
            "".join(part.capitalize() for part in stem.split("_")) + "Factory"
        )
        handler_name = raw.get("handler_name") or "_execute_handler"
        for name, label in ((class_name, "class_name"), (handler_name, "handler_name")):
            if not isinstance(name, str) or not name.replace("_", "").isalnum():
                raise ValueError(f"scaffold '{label}' must be an identifier")

        return ScaffoldSpec(
            module=module,
            test_module=test_module,
            capability_name=capability_name.strip(),
            class_name=class_name,
            handler_name=handler_name,
        )


class CompositeChangeSupplier:
    """Try a bounded, ordered list of suppliers; return the first non-None.

    Orchestration glue over the existing ``ChangeSupplier`` seam: it never
    fabricates content and never changes any supplier's own fail-closed
    contract (a raising supplier still fails the cycle closed).
    """

    def __init__(self, suppliers: object) -> None:
        ordered = tuple(
            supplier for supplier in (suppliers or ()) if supplier is not None
        )
        if not ordered:
            raise ValueError("CompositeChangeSupplier requires >= 1 supplier")
        self._suppliers = ordered

    @property
    def suppliers(self) -> tuple:
        """The ordered suppliers (read-only)."""
        return self._suppliers

    def supply_changes(self, need: DevelopmentNeed) -> SuppliedChanges | None:
        """Return the first supplier's non-None result, else ``None``."""
        for supplier in self._suppliers:
            supplied = supplier.supply_changes(need)
            if supplied is not None:
                return supplied
        return None
