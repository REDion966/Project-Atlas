"""Atlas Self-Knowledge — Runtime Independence Inventory (Phase 12.1).

A deterministic, READ-ONLY inventory of Atlas's *external* runtime
dependencies, each classified as exactly one of:

* ``REQUIRED_RUNTIME``   — must be installed for Atlas to run
* ``OPTIONAL_RUNTIME``   — used only behind an explicit opt-in seam
* ``DEVELOPMENT_ONLY``   — used only by tests/sandbox tooling
* ``INFORMATION_SOURCE`` — exists to perform ordinary authorized information
                           retrieval (NOT an AI/model dependency)
* ``UNKNOWN``            — not yet classified (a build-failing condition)

Static analysis only: it parses Python source with ``ast`` and reads the
declared requirement files. It never imports the audited modules, performs no
network I/O, runs no subprocess, and mutates nothing. It is NOT wired into the
kernel; the tests and the independence report consume it directly.

Critical invariant: ``required_ai_dependencies()`` must be empty — Atlas may
not require an external AI model, provider SDK, or coding agent at runtime.
"""

from __future__ import annotations

import ast
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Iterable

#: Top-level module names that constitute an external AI/model/provider or
#: external coding-agent ecosystem. Importing ANY of these from ``atlas/**``
#: would be a prohibited runtime dependency.
PROHIBITED_AI_MODULES: tuple[str, ...] = (
    "openai",
    "anthropic",
    "google.generativeai",
    "google.ai",
    "genai",
    "gemini",
    "ollama",
    "llama_cpp",
    "llamacpp",
    "transformers",
    "torch",
    "litellm",
    "mistralai",
    "cohere",
    "vllm",
    "dashscope",
    "qwen",
    "vertexai",
    "langchain",
    "langchain_core",
    "huggingface_hub",
    "sentence_transformers",
    "cline",
    "copilot",
    "commandcode",
    "command_code",
    "cursor",
)

#: Runtime entry modules (repository-relative POSIX paths) whose transitive
#: imports define what is REQUIRED to boot Atlas.
RUNTIME_ENTRY_PATHS: tuple[str, ...] = (
    "main.py",
    "atlas/cli/main.py",
    "atlas/cli/cli.py",
    "atlas/kernel/atlas.py",
)

#: Optional model-assisted seams (never required, never authoritative).
OPTIONAL_MODEL_SEAMS: tuple[tuple[str, str], ...] = (
    (
        "atlas.evolution.model_assisted_supplier.ModelAssistedChangeSupplier",
        "injectable change authoring; OFF by default; output is unverified "
        "draft content requiring approval + sandbox verification",
    ),
    (
        "atlas.ai.providers.* (OpenAI/Ollama/LMStudio/Anthropic/OpenRouter)",
        "inert provider objects; the ACTIVE provider is the local no-network "
        "tier unless [ai].external_providers is explicitly true",
    ),
    (
        "atlas.evolution.development_cycle.ChangeSupplier (protocol)",
        "protocol seam; the default implementation is deterministic",
    ),
)

#: Development-only tooling (tests, sandbox test runner, repository search).
DEVELOPMENT_ONLY_MODULES: tuple[str, ...] = ("pytest",)

#: External executables invoked as bounded local tools (never AI agents).
LOCAL_TOOL_EXECUTABLES: tuple[tuple[str, str], ...] = (
    ("pytest", "sandbox verification runner (atlas/evolution/autonomy)"),
    ("rg", "bounded repository pattern search (atlas/conversation/investigation)"),
)


class DependencyClass(str, Enum):
    """Classification of one external runtime dependency."""

    REQUIRED_RUNTIME = "required_runtime"
    OPTIONAL_RUNTIME = "optional_runtime"
    DEVELOPMENT_ONLY = "development_only"
    INFORMATION_SOURCE = "information_source"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class DependencyRecord:
    """One classified external dependency with provenance."""

    name: str
    classification: DependencyClass
    imported_by: tuple[str, ...] = ()
    imported_at_boot: bool = False
    ai_related: bool = False
    evidence: str = ""

    @property
    def required(self) -> bool:
        return self.classification is DependencyClass.REQUIRED_RUNTIME

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "classification": self.classification.value,
            "imported_by": list(self.imported_by),
            "imported_at_boot": self.imported_at_boot,
            "ai_related": self.ai_related,
            "evidence": self.evidence,
        }


@dataclass(frozen=True, slots=True)
class IndependenceInventory:
    """Bounded, JSON-safe independence inventory (evidence-backed)."""

    external_dependencies: tuple[DependencyRecord, ...] = ()
    declared_requirements: tuple[str, ...] = ()
    prohibited_ai_imports: tuple[tuple[str, str], ...] = ()
    unknown_dependencies: tuple[str, ...] = ()
    boot_entry_paths: tuple[str, ...] = ()

    # -- invariants ------------------------------------------------------

    def required_ai_dependencies(self) -> tuple[str, ...]:
        """External AI/model/provider dependencies required at runtime."""
        return tuple(
            record.name
            for record in self.external_dependencies
            if record.ai_related and record.required
        )

    def by_classification(
        self, classification: DependencyClass
    ) -> tuple[DependencyRecord, ...]:
        return tuple(
            record
            for record in self.external_dependencies
            if record.classification is classification
        )

    @property
    def independent(self) -> bool:
        """True when no prohibited AI import and no UNKNOWN classification exists."""
        return not self.prohibited_ai_imports and not self.unknown_dependencies

    def to_dict(self) -> dict[str, Any]:
        return {
            "external_dependencies": [r.to_dict() for r in self.external_dependencies],
            "declared_requirements": list(self.declared_requirements),
            "prohibited_ai_imports": [list(x) for x in self.prohibited_ai_imports],
            "unknown_dependencies": list(self.unknown_dependencies),
            "boot_entry_paths": list(self.boot_entry_paths),
            "required_ai_dependencies": list(self.required_ai_dependencies()),
            "independent": self.independent,
        }

    def to_markdown(self) -> str:
        """Render the inventory deterministically as markdown."""
        lines = [
            "# Atlas External Runtime Dependency Inventory",
            "",
            "Deterministic, read-only static analysis (Phase 12.1). Nothing "
            "was imported, executed, or modified.",
            "",
            "## External (non-stdlib) dependencies actually imported",
            "",
            "| module | classification | boot | AI-related | imported by |",
            "| --- | --- | --- | --- | --- |",
        ]
        for record in self.external_dependencies:
            lines.append(
                f"| `{record.name}` | {record.classification.value} | "
                f"{'yes' if record.imported_at_boot else 'no'} | "
                f"{'yes' if record.ai_related else 'no'} | "
                f"{', '.join(record.imported_by) or '-'} |"
            )
        if not self.external_dependencies:
            lines.append("| (none) | - | - | - | - |")

        lines += [
            "",
            f"- Declared requirements: "
            f"{', '.join(self.declared_requirements) or '(none)'}",
            f"- Required external AI dependencies: "
            f"{', '.join(self.required_ai_dependencies()) or '(none)'}",
            f"- Prohibited AI imports found: "
            f"{len(self.prohibited_ai_imports)}",
            f"- Unclassified dependencies: "
            f"{', '.join(self.unknown_dependencies) or '(none)'}",
            "",
            "## Optional model seams (never required, never authoritative)",
            "",
        ]
        for name, note in OPTIONAL_MODEL_SEAMS:
            lines.append(f"- `{name}` — {note}")
        lines += ["", "## Local tool executables (not AI agents)", ""]
        for name, note in LOCAL_TOOL_EXECUTABLES:
            lines.append(f"- `{name}` — {note}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Static scanning
# ---------------------------------------------------------------------------


def _stdlib_names() -> frozenset[str]:
    return frozenset(sys.stdlib_module_names)


def scan_atlas_imports(root: str | Path) -> dict[str, tuple[str, ...]]:
    """Return ``{external_top_level_module: (importing file, ...)}``.

    Walks ``<root>/atlas/**/*.py``, AST-parses each file, and reports every
    imported top-level module that is neither stdlib nor first-party Atlas.
    Read-only; the audited modules are never imported.
    """
    root_path = Path(root)
    stdlib = _stdlib_names()
    found: dict[str, set[str]] = {}
    for path in sorted((root_path / "atlas").rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, OSError, UnicodeDecodeError):
            continue
        rel = path.relative_to(root_path).as_posix()
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and not node.level:
                names = [node.module or ""]
            for dotted in names:
                top = dotted.split(".")[0]
                if not top or top == "atlas" or top in stdlib:
                    continue
                found.setdefault(top, set()).add(rel)
    return {name: tuple(sorted(files)) for name, files in sorted(found.items())}


def _module_paths(root: Path) -> dict[str, str]:
    """Map dotted Atlas module names to repository-relative file paths."""
    mapping: dict[str, str] = {}
    for path in (root / "atlas").rglob("*.py"):
        rel = path.relative_to(root).as_posix()
        if path.name == "__init__.py":
            dotted = rel[: -len("/__init__.py")].replace("/", ".")
        else:
            dotted = rel[: -len(".py")].replace("/", ".")
        mapping[dotted] = rel
    return mapping


def scan_boot_imports(root: str | Path) -> tuple[str, ...]:
    """Return external modules imported transitively from the runtime entries.

    Breadth-first over first-party ``atlas.*`` imports starting from
    :data:`RUNTIME_ENTRY_PATHS`. Read-only static analysis (no execution).
    """
    root_path = Path(root)
    stdlib = _stdlib_names()
    modules = _module_paths(root_path)

    roots: list[str] = []
    for rel in RUNTIME_ENTRY_PATHS:
        candidate = root_path / rel
        if candidate.is_file():
            dotted = rel[: -len(".py")].replace("/", ".")
            roots.append(dotted)

    seen: set[str] = set()
    external: set[str] = set()
    queue = list(roots)
    while queue:
        dotted = queue.pop()
        if dotted in seen:
            continue
        seen.add(dotted)
        rel = modules.get(dotted)
        if rel is None:
            continue
        try:
            tree = ast.parse((root_path / rel).read_text(encoding="utf-8"))
        except (SyntaxError, OSError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            targets: list[str] = []
            if isinstance(node, ast.Import):
                targets = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and not node.level:
                targets = [node.module or ""]
            for target in targets:
                top = target.split(".")[0]
                if not top or top in stdlib:
                    continue
                if top == "atlas":
                    queue.append(target)
                    continue
                external.add(top)
    return tuple(sorted(external))


def _declared_requirements(root: Path) -> tuple[str, ...]:
    """Read declared requirement names (evidence for the classification)."""
    names: list[str] = []
    requirements = root / "requirements.txt"
    if requirements.is_file():
        for line in requirements.read_text(encoding="utf-8").splitlines():
            entry = line.strip()
            if not entry or entry.startswith("#"):
                continue
            name = entry.split(">=")[0].split("==")[0].split("[")[0].strip()
            if name:
                names.append(name)
    return tuple(sorted(set(names)))


def _classify(
    name: str,
    *,
    imported_by: tuple[str, ...],
    at_boot: bool,
) -> DependencyRecord:
    """Classify one external module (never guesses without evidence)."""
    for prohibited in PROHIBITED_AI_MODULES:
        if name == prohibited or name.startswith(prohibited + "."):
            return DependencyRecord(
                name=name,
                classification=DependencyClass.REQUIRED_RUNTIME,
                imported_by=imported_by,
                imported_at_boot=at_boot,
                ai_related=True,
                evidence=(
                    "imported by Atlas source; external AI/model/provider or "
                    "coding-agent ecosystem (prohibited as a runtime dependency)"
                ),
            )
    if name in DEVELOPMENT_ONLY_MODULES:
        return DependencyRecord(
            name=name,
            classification=DependencyClass.DEVELOPMENT_ONLY,
            imported_by=imported_by,
            imported_at_boot=at_boot,
            evidence="development/sandbox tooling only",
        )
    if name == "requests":
        return DependencyRecord(
            name=name,
            classification=DependencyClass.INFORMATION_SOURCE,
            imported_by=imported_by,
            imported_at_boot=at_boot,
            evidence=(
                "generic HTTP client; used by the authorized research web "
                "source adapter and by the OPTIONAL external-provider seam "
                "(inactive unless [ai].external_providers is true)"
            ),
        )
    return DependencyRecord(
        name=name,
        classification=DependencyClass.UNKNOWN,
        imported_by=imported_by,
        imported_at_boot=at_boot,
        evidence="not yet classified",
    )


def build_independence_inventory(root: str | Path) -> IndependenceInventory:
    """Build the independence inventory for the repository at ``root``."""
    root_path = Path(root)
    imported = scan_atlas_imports(root_path)
    boot_modules = set(scan_boot_imports(root_path))

    records: list[DependencyRecord] = []
    prohibited: list[tuple[str, str]] = []
    unknown: list[str] = []
    for name, files in imported.items():
        record = _classify(
            name, imported_by=files, at_boot=name in boot_modules
        )
        records.append(record)
        if record.ai_related:
            prohibited.extend((name, f) for f in files)
        if record.classification is DependencyClass.UNKNOWN:
            unknown.append(name)

    return IndependenceInventory(
        external_dependencies=tuple(records),
        declared_requirements=_declared_requirements(root_path),
        prohibited_ai_imports=tuple(prohibited),
        unknown_dependencies=tuple(sorted(unknown)),
        boot_entry_paths=tuple(
            rel for rel in RUNTIME_ENTRY_PATHS if (root_path / rel).is_file()
        ),
    )


def repository_root() -> Path:
    """Return the Atlas repository root (the parent of the ``atlas`` package)."""
    return Path(__file__).resolve().parents[2]
