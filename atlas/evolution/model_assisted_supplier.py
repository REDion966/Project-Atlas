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

#: Bound applied to ``notes`` (the model's rationale). Matches the downstream
#: ``_build_proposal`` truncation of ``supplier_notes``.
_MAX_NOTES_CHARS: int = 500

#: The only fields the model contract accepts. Any other key is an unsupported
#: field and rejects the whole response (fail-closed, no silent repair).
_SUPPORTED_FIELDS: frozenset[str] = frozenset(
    {"code_changes", "test_files", "rationale", "confidence"}
)


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
    """

    def __init__(self, authoring_model: Callable[[str], Any] | None = None) -> None:
        self._authoring_model = authoring_model
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
        """Render a bounded authoring prompt from the need."""
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
        parts.append(
            "Return ONLY one JSON object with exactly these keys: "
            '"code_changes" (list of {"path": "relative/path", "content": '
            '"..."} objects), "test_files" (object mapping relative test '
            'path -> content), "rationale" (string), "confidence" (number '
            "0.0..1.0). No prose, no markdown fences, no extra keys."
        )
        return "\n".join(parts)

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
