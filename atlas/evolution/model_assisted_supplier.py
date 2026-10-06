"""Atlas Evolution — Model-Assisted Change Supplier (B4, authoring-only).

A second, OPTIONAL implementation of the existing :class:`ChangeSupplier`
protocol. It turns a bounded :class:`DevelopmentNeed` plus a duck-typed
authoring model into a bounded, unverified-draft :class:`SuppliedChanges`
payload — WITHOUT executing, approving, applying, promoting, or writing
anything.

This module is a pure authoring/data adapter. It closes the authoring gap
left by :class:`DeterministicChangeSupplier` (which only reads already-supplied
``metadata["code_changes"]``) while preserving every existing governance
boundary:

  * The result is ``SuppliedChanges`` (draft content only) with
    ``origin="model-assisted-draft"``. The downstream proposal builder already
    stamps ``content_status="unverified-draft"`` and requires owner approval
    before anything reaches the sandbox.
  * The supplier is injectable and OFF by default: ``authoring_model=None``
    means no authoring (returns ``None``).
  * Fail-closed: any model, parsing, structure, size, path, or policy failure
    returns ``None`` — never partial changes, never fabricated changes, never
    repaired output.

ARCHITECTURE CONTRACT:
  * No ``atlas.ai`` import (the model is duck-typed).
  * No kernel, runtime, gateway, dispatcher, approval, execution, promotion,
    self-development-loop, or other governance/execution imports.
  * No repository mutation, no EventBus, no storage, no scheduler.
  * Reuses the existing ``CodeChangeSet.validate_path``,
    ``DevelopmentCyclePolicy`` bounds, and
    ``PromotionGate.ARCHITECTURE_SENSITIVE_PREFIXES`` — this module never
    redefines them.
"""

from __future__ import annotations

import json
from typing import Any, Callable

from atlas.evolution.autonomy.code_sandbox import CodeChangeSet
from atlas.evolution.development_cycle import (
    DevelopmentCyclePolicy,
    DevelopmentNeed,
    SuppliedChanges,
)
from atlas.evolution.promotion_gate import ARCHITECTURE_SENSITIVE_PREFIXES

#: Provenance marker for everything this supplier produces. Downstream, the
#: proposal builder copies this into ``metadata["development_cycle"]
#: ["change_origin"]`` and stamps ``content_status="unverified-draft"``.
ORIGIN_MODEL_ASSISTED_DRAFT: str = "model-assisted-draft"

# --- Bounded authoring context -------------------------------------------
# The verified Goal-2 bottleneck: the prompt carried only development metadata
# and target NAMES, so a draft author was asked to write code it could not see.
# These caps keep the repository context small, deterministic and safe to place
# in a prompt. They are fixed module constants, never per-request.
MAX_CONTEXT_MODULES: int = 5
#: How many ranked modules are requested before the production/test preference is
#: applied. A test module may legitimately outrank a production one lexically,
#: so a wider slice is taken first and then narrowed.
MAX_CONTEXT_RANK_LIMIT: int = 12
MAX_CONTEXT_SYMBOLS: int = 40
MAX_CONTEXT_SIGNATURE_CHARS: int = 160
MAX_CONTEXT_QUERY_CHARS: int = 200
#: GLOBAL budget for SOURCE content across the whole authoring context. The
#: change contract asks for full replacement content, so a symbol list alone is
#: not authorable; bounded source is included instead of an unbounded dump. The
#: target module is served first, so a large target cannot be starved by
#: secondary modules.
MAX_CONTEXT_SOURCE_CHARS: int = 16000
#: Bounded internal-import evidence per module (dependency context).
MAX_CONTEXT_IMPORTS: int = 12
#: Bounded declared-architecture items (declared dependencies / provided
#: capabilities) exposed for the target module's owning component.
MAX_CONTEXT_CONTRACT_ITEMS: int = 8
#: Bounded relevant-test modules exposed for the target module.
MAX_CONTEXT_TESTS: int = 8

#: Bound applied to ``notes`` (the model's rationale). Matches the downstream
#: ``_build_proposal`` truncation of ``supplier_notes``.
_MAX_NOTES_CHARS: int = 500

#: The only fields the model contract accepts. Any other key is an unsupported
#: field and rejects the whole response (fail-closed, no silent repair).
_SUPPORTED_FIELDS: frozenset[str] = frozenset(
    {"code_changes", "test_files", "rationale", "confidence"}
)


def _is_test_module(module: str) -> bool:
    """True for a test module, by module name or file path."""
    if not isinstance(module, str) or not module:
        return False
    normalized = module.replace("/", ".").replace("\\", ".")
    parts = [p for p in normalized.split(".") if p]
    return any(
        part == "tests"
        or part == "test"
        or part.startswith("test_")
        or part.endswith("_test")
        for part in parts
    )


def _prefer_production(ranked: object) -> tuple:
    """Order a ranking so production modules come before test modules.

    Purely an ordering preference over the EXISTING ranking (stable within each
    group, so the ranker's own ordering is preserved). Drafting code benefits
    from the implementation; tests are still included afterwards when there is
    room, because they show the contract.
    """
    entries = tuple(ranked or ())
    if not entries:
        return ()
    production = [e for e in entries if not _is_test_module(str(getattr(e, "module", "") or ""))]
    tests = [e for e in entries if _is_test_module(str(getattr(e, "module", "") or ""))]
    return tuple(production) + tuple(tests)


def _owning_component(architecture_model: Any, module: str) -> Any | None:
    """The registered component that owns ``module``, or ``None``.

    Read-only and deterministic: a component owns a module when its declared
    ``package`` equals the module or is a dotted prefix of it, or when its
    declared ``module_path`` is the module. The MOST SPECIFIC (longest package)
    match wins; ties break on the component name. Nothing is inferred — an
    unowned module yields ``None`` and the caller omits the boundary block.
    """
    if architecture_model is None or not module:
        return None
    candidates: list[tuple[int, str, Any]] = []
    for component in getattr(architecture_model, "components", ()) or ():
        package = str(getattr(component, "package", "") or "")
        declared_path = str(getattr(component, "module_path", "") or "")
        specificity = -1
        if package and (module == package or module.startswith(package + ".")):
            specificity = len(package)
        elif declared_path and declared_path == module:
            specificity = len(declared_path)
        if specificity >= 0:
            candidates.append(
                (specificity, str(getattr(component, "name", "") or ""), component)
            )
    if not candidates:
        return None
    candidates.sort(key=lambda item: (-item[0], item[1]))
    return candidates[0][2]


def _prioritise_declared_target(ranked: object, need: DevelopmentNeed) -> tuple:
    """Move a DECLARED target component to the front of the ranking.

    The need already names the target(s) it is about; the ranking is evidence,
    not instruction, so honouring the declared target first is safe and keeps the
    shared source budget pointed at the thing being changed. Purely an ordering
    step over the EXISTING ranking: the ranker's order is preserved within each
    group and no module is added or removed.
    """
    entries = tuple(ranked or ())
    if not entries:
        return ()
    declared = {
        c for c in (getattr(need, "target_components", ()) or ())
        if isinstance(c, str) and c.strip()
    }
    if not declared:
        return entries
    targets = [e for e in entries if str(getattr(e, "module", "") or "") in declared]
    rest = [e for e in entries if str(getattr(e, "module", "") or "") not in declared]
    return tuple(targets) + tuple(rest)


def _context_query(need: DevelopmentNeed) -> str:
    """The lexical query used to rank repository modules for a need.

    Built ONLY from fields the need already carries (title, summary, rationale,
    target components). No language interpretation and no extra vocabulary: the
    ranking layer decides relevance, this only supplies the text to rank.
    """
    parts: list[str] = []
    for value in (
        getattr(need, "title", ""),
        getattr(need, "summary", ""),
        getattr(need, "rationale", ""),
    ):
        text = value.strip() if isinstance(value, str) else ""
        if text:
            parts.append(text)
    for component in getattr(need, "target_components", ()) or ():
        text = component.strip() if isinstance(component, str) else ""
        if text:
            parts.append(text)
    return " ".join(parts)[:MAX_CONTEXT_QUERY_CHARS].strip()


class ModelAssistedChangeSupplier:
    """Optional model-assisted authoring over the existing ChangeSupplier seam.

    Args:
        authoring_model: Optional duck-typed callable. It is invoked with a
            single prompt string and may return:
              * a ``str`` containing exactly one JSON object, or
              * a ``dict`` (the already-decoded JSON object), or
              * any object exposing a ``.text`` attribute whose value is a
                string containing exactly one JSON object (the existing
                ``AIResponse`` shape, without importing ``atlas.ai``).
            ``None`` (the default) means no authoring is available, so
            :meth:`supply_changes` returns ``None``.
        repository_map: Optional duck-typed ``RepositoryMap``-like object
            exposing ``rank_modules(query, limit)`` and
            ``symbols_in_module(module)``. Optional: with no map the prompt is
            byte-identical to what it was before, so every existing caller keeps
            its current behaviour.
    """

    def __init__(
        self,
        authoring_model: Callable[[str], Any] | None = None,
        repository_map: Any | None = None,
        architecture_model: Any | None = None,
    ) -> None:
        self._authoring_model = authoring_model
        self._repository_map = repository_map
        self._architecture_model = architecture_model
        self._policy = DevelopmentCyclePolicy()

    # -- ChangeSupplier protocol ---------------------------------------------

    def supply_changes(self, need: DevelopmentNeed) -> SuppliedChanges | None:
        """Author bounded draft changes for ``need``, or ``None`` (fail-closed).

        The entire response is atomic: if any single change, test file, path,
        or field is invalid, the whole response is rejected and ``None`` is
        returned. No partial changes, no fabricated changes.
        """
        if self._authoring_model is None:
            return None
        if not isinstance(need, DevelopmentNeed):
            return None

        try:
            raw = self._authoring_model(self._build_prompt(need))
        except Exception:
            return None

        payload = _extract_payload(raw)
        if payload is None:
            return None

        return self._validate_and_build(payload)

    # -- internals -----------------------------------------------------------

    def _build_prompt(self, need: DevelopmentNeed) -> str:
        """Render a bounded authoring prompt from the need.

        When a repository map is available the prompt also carries a BOUNDED,
        deterministically-ranked slice of the repository (modules, paths and
        bounded symbol signatures the map already records). The context is
        evidence only: it never asserts where a change belongs, never
        authorizes anything, and is omitted entirely when no ranking exists.
        """
        parts: list[str] = [
            "Author bounded code changes for a governed development request.",
            f"Title: {need.title}",
            f"Summary: {need.summary or need.title}",
        ]
        if need.rationale:
            parts.append(f"Rationale: {need.rationale}")
        if need.expected_benefit:
            parts.append(f"Expected benefit: {need.expected_benefit}")
        if need.target_components:
            parts.append(
                "Target components: " + ", ".join(need.target_components)
            )
        context = self._build_authoring_context(need)
        if context:
            parts.append("")
            parts.append(context)
        parts.append(
            "Return ONLY one JSON object with exactly these keys: "
            '"code_changes" (list of {"path": "relative/path", "content": '
            '"..."} objects), "test_files" (object mapping relative test '
            'path -> content), "rationale" (string), "confidence" (number '
            "0.0..1.0). No prose, no markdown fences, no extra keys."
        )
        return "\n".join(parts)

    def _build_authoring_context(self, need: DevelopmentNeed) -> str:
        """Bounded repository context for the prompt, or ``""``.

        Read-only and deterministic: candidates come from the EXISTING
        ``RepositoryMap.rank_modules`` lexical ranking, and symbols from
        ``symbols_in_module``. Nothing is read from disk here, nothing is
        invented, and an absent/blank/raising map yields ``""`` so the prompt is
        exactly what it was before this capability existed.
        """
        repository_map = self._repository_map
        if repository_map is None:
            return ""
        rank = getattr(repository_map, "rank_modules", None)
        if not callable(rank):
            return ""
        query = _context_query(need)
        if not query:
            return ""
        try:
            ranked = rank(query, limit=MAX_CONTEXT_RANK_LIMIT)
        except Exception:
            return ""
        ranked = _prioritise_declared_target(
            _prefer_production(ranked), need
        )[:MAX_CONTEXT_MODULES]
        if not ranked:
            return ""

        symbols_in_module = getattr(repository_map, "symbols_in_module", None)
        module_index = {
            str(getattr(info, "module", "") or ""): info
            for info in (getattr(repository_map, "modules", ()) or ())
        }
        lines = [
            "Repository context (bounded, ranked; evidence only, not an "
            "instruction about where to change anything):"
        ]
        source_budget = MAX_CONTEXT_SOURCE_CHARS
        for index, entry in enumerate(ranked, start=1):
            module = str(getattr(entry, "module", "") or "")
            path = str(getattr(entry, "path", "") or "")
            if not module:
                continue
            lines.append(f"- {index}. {module} ({path})")
            info = module_index.get(module)

            # Dependency evidence: the module's own resolved internal imports.
            dependencies = tuple(
                getattr(info, "internal_imports", ()) or ()
            )[:MAX_CONTEXT_IMPORTS]
            if dependencies:
                lines.append("    internal imports: " + ", ".join(dependencies))

            # Bounded SOURCE. The target is ranked first, so it is served from
            # the budget before any secondary module. Truncation is stated
            # explicitly rather than silently cutting the excerpt.
            excerpt = str(getattr(info, "source_excerpt", "") or "")
            if excerpt and source_budget > 0:
                allowed = min(len(excerpt), source_budget)
                piece = excerpt[:allowed]
                source_budget -= allowed
                cut = bool(getattr(info, "source_truncated", False)) or (
                    allowed < len(excerpt)
                )
                total_lines = getattr(info, "line_count", 0) or 0
                shown_lines = len(piece.splitlines())
                header = "    source"
                if cut:
                    header += (
                        f" (truncated: first {shown_lines} of {total_lines} lines)"
                    )
                lines.append(header + ":")
                lines.extend("        " + line for line in piece.splitlines())

            if not callable(symbols_in_module):
                continue
            try:
                symbols = tuple(symbols_in_module(module) or ())[:MAX_CONTEXT_SYMBOLS]
            except Exception:
                continue
            if symbols:
                lines.append("    symbols:")
            for symbol in symbols:
                name = str(getattr(symbol, "name", "") or "")
                if not name:
                    continue
                kind = getattr(getattr(symbol, "kind", None), "value", "")
                signature = str(getattr(symbol, "signature", "") or "")
                line = f"        - {kind} {name}".rstrip()
                if signature:
                    line += f"{signature[:MAX_CONTEXT_SIGNATURE_CHARS]}"
                lines.append(line)
        lines.extend(self._target_boundary_lines(ranked[0]))
        if len(lines) == 1:
            return ""
        return "\n".join(lines)

    def _target_boundary_lines(self, entry: Any) -> list[str]:
        """Bounded DECLARED-BOUNDARY and RELEVANT-TEST evidence for the target.

        Both are deterministic PROJECTIONS of data Atlas already holds — the
        owning component's declared boundary from the architecture model, and
        the test modules that actually import the target from the repository
        map's reverse-import index. Nothing is inferred, nothing is invented,
        and an unresolvable component (or an absent map/model) simply omits its
        block rather than guessing.
        """
        lines: list[str] = []
        module = str(getattr(entry, "module", "") or "")
        if not module:
            return lines

        component = _owning_component(self._architecture_model, module)
        if component is not None:
            name = str(getattr(component, "name", "") or "")
            responsibility = str(getattr(component, "responsibility", "") or "")
            dependencies = tuple(
                str(d) for d in (getattr(component, "declared_dependencies", ()) or ())
                if str(d)
            )[:MAX_CONTEXT_CONTRACT_ITEMS]
            provided = tuple(
                str(c) for c in (getattr(component, "provided_capabilities", ()) or ())
                if str(c)
            )[:MAX_CONTEXT_CONTRACT_ITEMS]
            if name or responsibility or dependencies or provided:
                lines.append(
                    f"    declared boundary for {name or module} "
                    "(existing architecture metadata; evidence only):"
                )
                if responsibility:
                    lines.append(f"        responsibility: {responsibility[:200]}")
                if dependencies:
                    lines.append(
                        "        declared dependencies: " + ", ".join(dependencies)
                    )
                if provided:
                    lines.append(
                        "        provided capabilities: " + ", ".join(provided)
                    )

        repository_map = self._repository_map
        tests_for_module = getattr(repository_map, "tests_for_module", None)
        if callable(tests_for_module):
            try:
                tests = tuple(tests_for_module(module) or ())
            except Exception:
                tests = ()
            if tests:
                shown = tests[:MAX_CONTEXT_TESTS]
                cut = len(tests) > len(shown)
                header = (
                    "    relevant test modules (import-derived repository "
                    "evidence, not a guarantee of behavioural coverage"
                )
                header += (
                    f"; truncated: first {len(shown)} of {len(tests)})"
                    if cut
                    else ")"
                )
                lines.append(header + ":")
                lines.extend(f"        {test}" for test in shown)
        return lines

    def _validate_and_build(self, payload: dict[str, Any]) -> SuppliedChanges | None:
        """Structurally validate, bound, and path/policy-check the payload."""
        policy = self._policy

        # Fail-closed on any unsupported field (operation semantics, prose, etc.).
        if not set(payload.keys()) <= _SUPPORTED_FIELDS:
            return None

        # 1. code_changes: required non-empty list of {path, content}.
        raw_changes = payload.get("code_changes")
        if not isinstance(raw_changes, list) or not raw_changes:
            return None
        if len(raw_changes) > policy.max_code_changes:
            return None

        changes: list[tuple[str, str]] = []
        for item in raw_changes:
            if not isinstance(item, dict):
                return None
            path = item.get("path")
            content = item.get("content")
            if not isinstance(path, str) or not path:
                return None
            if not isinstance(content, str):
                return None
            if len(content) > policy.max_content_chars:
                return None
            if not self._safe_path(path):
                return None
            changes.append((path, content))

        if not changes:
            return None

        # 2. test_files: optional, must be a dict[str, str] and bounded.
        test_files: tuple[tuple[str, str], ...] = ()
        if "test_files" in payload:
            raw_tests = payload["test_files"]
            if not isinstance(raw_tests, dict):
                return None
            if len(raw_tests) > policy.max_test_files:
                return None
            tests: list[tuple[str, str]] = []
            for path, content in raw_tests.items():
                if not isinstance(path, str) or not isinstance(content, str):
                    return None
                if len(content) > policy.max_content_chars:
                    return None
                if not self._safe_path(path):
                    return None
                tests.append((path, content))
            test_files = tuple(tests)

        # 3. rationale -> notes (bounded).
        notes = ""
        if "rationale" in payload:
            rationale = payload["rationale"]
            if not isinstance(rationale, str):
                return None
            notes = rationale[:_MAX_NOTES_CHARS]

        # 4. confidence -> clamped [0.0, 1.0].
        confidence = _clamp01(payload.get("confidence", 0.0))

        return SuppliedChanges(
            code_changes=tuple(changes),
            test_files=test_files,
            origin=ORIGIN_MODEL_ASSISTED_DRAFT,
            confidence=confidence,
            notes=notes,
        )

    def _safe_path(self, path: str) -> bool:
        """Reuse existing validators to reject unsafe/forbidden paths."""
        if len(path) > self._policy.max_path_chars:
            return False
        try:
            CodeChangeSet.validate_path(path)
        except Exception:
            return False
        module = _path_to_module(path)
        return not any(
            module.startswith(prefix) for prefix in ARCHITECTURE_SENSITIVE_PREFIXES
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_payload(raw: Any) -> dict[str, Any] | None:
    """Normalize a model response into a decoded dict, or ``None``."""
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        return _parse_json(raw)
    text = getattr(raw, "text", None)
    if isinstance(text, str):
        return _parse_json(text)
    return None


def _parse_json(text: str) -> dict[str, Any] | None:
    """Strictly parse exactly one JSON object; reject anything else."""
    if not isinstance(text, str):
        return None
    stripped = text.strip()
    if not stripped:
        return None
    try:
        obj = json.loads(stripped)
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(obj, dict):
        return None
    return obj


def _clamp01(value: Any) -> float:
    """Coerce a value into [0.0, 1.0]; malformed/NaN -> 0.0."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if number != number:  # NaN guard
        return 0.0
    return max(0.0, min(1.0, number))


def _path_to_module(path: str) -> str:
    """Convert a relative path to a dotted module name (pure lexical)."""
    normalized = str(path).replace("\\", "/")
    if normalized.endswith(".py"):
        normalized = normalized[:-3]
    return normalized.replace("/", ".")
