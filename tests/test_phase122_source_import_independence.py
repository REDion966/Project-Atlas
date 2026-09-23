"""Phase 12.2 — Source & import independence audit: evidence contract.

AST-based audit of the whole ``atlas/**`` runtime tree. Validation result: no
direct or indirect dependence on an external AI/model/provider ecosystem or an
external coding agent; network use is confined to the optional provider seam and
the authorized research web source; subprocess use is confined to two bounded
local tools with fixed argument lists.
"""

from __future__ import annotations

import ast

from atlas.self_knowledge.independence_inventory import (
    PROHIBITED_AI_MODULES,
    repository_root,
    scan_boot_imports,
)

_ROOT = repository_root()
_ATLAS = _ROOT / "atlas"

_AI_KEY_ENV_VARS = (
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "OPENROUTER_API_KEY",
    "GOOGLE_API_KEY",
    "GEMINI_API_KEY",
    "QWEN_API_KEY",
    "DASHSCOPE_API_KEY",
)


def _sources() -> list[tuple[str, ast.Module]]:
    out: list[tuple[str, ast.Module]] = []
    for path in sorted(_ATLAS.rglob("*.py")):
        rel = path.relative_to(_ROOT).as_posix()
        out.append((rel, ast.parse(path.read_text(encoding="utf-8"))))
    return out


def _imported_names(tree: ast.Module) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name.lower() for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module.lower())
    return names


class TestPhase122SourceImportIndependence:
    def test_no_ai_or_coding_agent_ecosystem_is_imported(self):
        offenders: list[str] = []
        for rel, tree in _sources():
            for name in _imported_names(tree):
                for prefix in PROHIBITED_AI_MODULES:
                    if name == prefix or name.startswith(prefix + "."):
                        offenders.append(f"{rel} -> {name}")
        assert offenders == []

    def test_no_provider_sdk_appears_in_sys_modules_after_import(self):
        import sys

        leaked = [
            name
            for name in sys.modules
            if any(
                name == p or name.startswith(p + ".")
                for p in ("openai", "anthropic", "google.generativeai", "ollama",
                          "llama_cpp", "transformers", "torch", "litellm")
            )
        ]
        assert leaked == []

    def test_concrete_provider_modules_are_referenced_only_by_the_manager(self):
        referencing: set[str] = set()
        for rel, tree in _sources():
            for name in _imported_names(tree):
                if name.startswith("atlas.ai.providers"):
                    referencing.add(rel)
        assert referencing == {"atlas/ai/ai_manager.py"}

    def test_ai_api_key_env_vars_are_read_only_inside_provider_modules(self):
        offenders: list[str] = []
        for rel, tree in _sources():
            for node in ast.walk(tree):
                if not isinstance(node, ast.Constant) or not isinstance(
                    node.value, str
                ):
                    continue
                if node.value in _AI_KEY_ENV_VARS and not rel.startswith(
                    "atlas/ai/providers/"
                ):
                    offenders.append(f"{rel}:{node.lineno} {node.value}")
        assert offenders == []

    def test_network_use_is_confined_to_providers_and_the_research_source(self):
        allowed_ai = "atlas/ai/providers/"
        allowed_research = "atlas/research/sources/web.py"
        offenders: list[str] = []
        for rel, tree in _sources():
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                if not isinstance(func, ast.Attribute):
                    continue
                value = func.value
                base = value.id if isinstance(value, ast.Name) else ""
                if base in ("requests", "socket", "httpx") or (
                    base == "urllib" and func.attr in ("urlopen", "build_opener")
                ):
                    if not (rel.startswith(allowed_ai) or rel == allowed_research):
                        offenders.append(f"{rel}:{node.lineno} {base}.{func.attr}")
        assert offenders == []

    def test_subprocess_use_is_confined_and_shell_free(self):
        sites: dict[str, list[tuple[list | None, bool | None]]] = {}
        for rel, tree in _sources():
            for node in ast.walk(tree):
                if not (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "subprocess"
                ):
                    continue
                argv = node.args[0] if node.args else None
                literal = (
                    [
                        elt.value if isinstance(elt, ast.Constant) else "?"
                        for elt in argv.elts
                    ]
                    if isinstance(argv, ast.List)
                    else None
                )
                shell = None
                for kw in node.keywords:
                    if kw.arg == "shell" and isinstance(kw.value, ast.Constant):
                        shell = bool(kw.value.value)
                sites.setdefault(rel, []).append((literal, shell))

        assert set(sites) == {
            "atlas/conversation/investigation.py",
            "atlas/evolution/autonomy/sandbox_tools.py",
        }
        # Repository search: a fixed literal argv for `rg` (no shell).
        assert (["rg", "--no-heading", "-n", "-l", "?", "?"], None) in sites[
            "atlas/conversation/investigation.py"
        ]
        # Sandbox test runner: built argv executed with an explicit shell=False.
        assert sites["atlas/evolution/autonomy/sandbox_tools.py"] == [(None, False)]

    def test_no_shell_string_execution_or_dynamic_code_execution(self):
        offenders: list[str] = []
        for rel, tree in _sources():
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    func = node.func
                    if isinstance(func, ast.Name) and func.id in ("eval", "exec"):
                        offenders.append(f"{rel}:{node.lineno} {func.id}")
                    if isinstance(func, ast.Attribute) and func.attr in (
                        "system",
                        "popen",
                    ):
                        offenders.append(f"{rel}:{node.lineno} {func.attr}")
                    if isinstance(func, ast.Attribute) and func.attr == "run":
                        for kw in node.keywords:
                            if (
                                kw.arg == "shell"
                                and isinstance(kw.value, ast.Constant)
                                and kw.value.value is True
                            ):
                                offenders.append(f"{rel}:{node.lineno} shell=True")
        assert offenders == []

    def test_dynamic_imports_resolve_only_to_first_party_modules(self):
        literals: list[str] = []
        for _, tree in _sources():
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "import_module"
                    and node.args
                    and isinstance(node.args[0], ast.Constant)
                    and isinstance(node.args[0].value, str)
                ):
                    literals.append(node.args[0].value)
        assert literals  # the dynamic imports exist
        assert all(name.startswith("atlas.") for name in literals), literals

    def test_boot_closure_contains_no_prohibited_module(self):
        boot = scan_boot_imports(_ROOT)
        for name in boot:
            for prefix in PROHIBITED_AI_MODULES:
                assert not (name == prefix or name.startswith(prefix + ".")), name

    def test_documentation_references_are_not_runtime_dependencies(self):
        # Prose mentions (README/docs/comments) never create a dependency: the
        # AST audit above is authoritative and finds none. This asserts the
        # audit covers the whole runtime tree.
        audited = {rel for rel, _ in _sources()}
        assert len(audited) > 200
        assert all(
            rel.endswith(".py") and not rel.startswith("tests/") for rel in audited
        )
