"""Atlas Evolution — the specialist -> authoring bridge (Command 3A).

The one missing consumer of :class:`~atlas.specialists.SpecialistProposal`.

The preceding steps established the Atlas-owned specialist seam and a real
``code.generate`` provider that yields an UNTRUSTED
:class:`~atlas.specialists.SpecialistProposal`. Nothing consumed it: a proposal
could not reach the EXISTING governed development pipeline. This module is that
consumer, and it is deliberately the smallest possible bridge:

    SpecialistProposal
        -> SpecialistChangeSupplier
        -> existing SuppliedChanges / code_changes contract
        -> existing CompositeChangeSupplier
        -> existing governed development pipeline

Placement
---------
This is a NEW sibling of the existing authoring suppliers
(:mod:`atlas.evolution.structural_editor`,
:mod:`atlas.evolution.development_scaffold_supplier`,
:mod:`atlas.evolution.model_assisted_supplier`) in the same ``atlas/evolution``
authoring area. It is not placed inside ``structural_editor`` because a full-file
replacement authored by an untrusted provider is a different change class from an
AST-anchored structural edit, and mixing them would blur both modules' stated
responsibility. It mirrors the dedicated, optional ``model_assisted_supplier``
module exactly.

Contract
--------
It reads ``need.metadata["specialist_proposal"]`` (a dedicated key, disjoint
from the existing ``code_changes`` / ``structural`` / ``scaffold`` /
``evidence_change`` conventions) and produces ONLY the existing bounded
``SuppliedChanges`` representation: exactly one ``code_changes`` entry plus,
when the need carries them, the same plan-derived ``test_files`` /
``repository_context`` every sibling supplier forwards (so the governed
verification leg stays bounded). It is fail-closed: absent,
malformed, wrong-capability, identity-less, missing/zero/multiple-file,
invalid-content, internally-inconsistent, unsafe-path or out-of-target
proposals all yield ``None``. It NEVER raises, so it can never change the
outcome of any pre-existing deterministic / structural / supplied-edit path:
when no valid proposal is present it is completely inert.

It does NOT execute, run tests, approve, promote, call a model, read the
filesystem, or decide whether a provider is trustworthy. The produced draft
still passes the unchanged ``CodeChangeSet`` validation, the sandbox,
verification, approval and promotion boundaries. Standard library only.
"""

from __future__ import annotations

from typing import Any

from atlas.evolution.autonomy.code_sandbox import CodeChangeSet
from atlas.evolution.development_cycle import (
    DevelopmentCyclePolicy,
    DevelopmentNeed,
    SuppliedChanges,
)
from atlas.specialists import CODE_GENERATE, SpecialistProposal

#: The dedicated metadata key this supplier consumes. Disjoint from the existing
#: ``code_changes`` / ``structural`` / ``scaffold`` / ``evidence_change`` keys,
#: so existing authoring behaviour is untouched.
SPECIALIST_PROPOSAL_KEY: str = "specialist_proposal"

#: Provenance marker stamped on specialist-authoring drafts (unverified draft).
SPECIALIST_ORIGIN: str = "specialist-proposal"

#: The FULL-FILE proposal form (Command 2 keeps ``"full_file"`` as the
#: backward-compatible default when ``change`` is absent).
CHANGE_FULL_FILE: str = "full_file"

#: The STRUCTURAL proposal form (Command 2, W5): an AST-anchored edit of an
#: existing module's named symbol, applied by the EXISTING structural editor.
CHANGE_STRUCTURAL: str = "structural"

#: The change forms this bridge understands. Any other value is refused
#: fail-closed rather than guessed.
SUPPORTED_CHANGES: frozenset[str] = frozenset({CHANGE_FULL_FILE, CHANGE_STRUCTURAL})

#: The ONLY proposal payload fields each form may carry. Any other key (an
#: action, an execution directive, an approval claim, ...) rejects the whole
#: proposal — the adapter never honours an unauthorized field.
_FULL_FILE_FIELDS: frozenset[str] = frozenset(
    {"paths", "files", "note", "change"}
)
_STRUCTURAL_FIELDS: frozenset[str] = frozenset(
    {"change", "path", "symbol", "kind", "source", "note"}
)

#: The structural transformations the EXISTING editor already implements.
_STRUCTURAL_KINDS: frozenset[str] = frozenset(
    {"replace", "insert_after", "delete"}
)

#: Bound applied to ``notes`` (the provider's own note). Matches the downstream
#: ``_build_proposal`` truncation of ``supplier_notes``.
_MAX_NOTES_CHARS: int = 500


def _declared_targets(need: DevelopmentNeed) -> tuple[str, ...]:
    """The need's DECLARED target(s), normalized to repository-relative form.

    ``DevelopmentNeed.target_components`` is Atlas's authoritative statement of
    what the request is about. Entries are normalized to POSIX separators only;
    nothing is inferred. An empty declaration means no containment claim is made
    (the other checks still apply).
    """
    out: list[str] = []
    for raw in getattr(need, "target_components", ()) or ():
        text = str(raw or "").strip().replace("\\", "/")
        if text:
            out.append(text)
    return tuple(out)


def _matches_declared_target(path: str, declared: str) -> bool:
    """Whether ``path`` names the DECLARED target, exactly.

    Accepts the two canonical forms Atlas already uses for a module: the
    repository-relative path (``atlas/x.py``) and its dotted module name
    (``atlas.x``). No fuzzy matching, so a near-miss can never be accepted.
    """
    if path == declared:
        return True
    if path.endswith(".py"):
        module = path[:-3].replace("/", ".")
    else:
        module = path.replace("/", ".")
    return declared == module


def _clamp01(value: Any) -> float:
    """Coerce a value into [0.0, 1.0]; malformed/NaN -> 0.0."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if number != number:  # NaN guard
        return 0.0
    return max(0.0, min(1.0, number))


class SpecialistChangeSupplier:
    """Fail-closed ``ChangeSupplier`` bridge over an untrusted proposal.

    Reads ``need.metadata["specialist_proposal"]`` and returns a bounded
    :class:`~atlas.evolution.development_cycle.SuppliedChanges` carrying exactly
    one ``code_changes`` entry, or ``None`` for every refusal. It never raises
    and never escalates authority.
    """

    def __init__(
        self,
        policy: DevelopmentCyclePolicy | None = None,
        *,
        root: Any | None = None,
        base_source: Any | None = None,
    ) -> None:
        self._policy = policy or DevelopmentCyclePolicy()
        #: Command 2 (W6) — the repository root and an optional explicit base
        #: source per path, forwarded UNCHANGED to the EXISTING structural
        #: editor. Both default to ``None``, which is exactly today's behaviour
        #: (the editor's own repository root and the on-disk source). A repair
        #: passes the CURRENT failing content as ``base_source`` so an anchored
        #: edit is applied to what actually failed.
        self._root = root
        self._base_source = base_source if isinstance(base_source, dict) else None

    @property
    def origin(self) -> str:
        """Provenance marker stamped on specialist-authored drafts."""
        return SPECIALIST_ORIGIN

    def supply_changes(self, need: DevelopmentNeed) -> SuppliedChanges | None:
        """Bridge the proposal carried by ``need``, or ``None`` (fail-closed)."""
        metadata = getattr(need, "metadata", None)
        if not isinstance(metadata, dict):
            return None
        proposal = metadata.get(SPECIALIST_PROPOSAL_KEY)
        if proposal is None:
            return None
        return self._build(proposal, need)

    # -- validation (every refusal returns None) ---------------------------

    def _build(self, proposal: Any, need: DevelopmentNeed) -> SuppliedChanges | None:
        # 1. A proposal must be a real, identity-bearing code.generate proposal.
        if not isinstance(proposal, SpecialistProposal):
            return None
        if not str(proposal.provider_id).strip():
            return None
        if str(proposal.capability) != CODE_GENERATE:
            return None

        # 2. The payload must be a bounded mapping carrying ONLY the fields its
        #    declared change form allows (no action/execute/approve directives
        #    and no extra metadata). An absent ``change`` is the
        #    backward-compatible ``full_file`` default; an UNKNOWN change value
        #    is refused fail-closed rather than guessed.
        payload = proposal.payload
        if not isinstance(payload, dict) or not payload:
            return None
        raw_change = payload.get("change")
        if raw_change is None:
            change = CHANGE_FULL_FILE
        elif isinstance(raw_change, str):
            change = raw_change.strip().lower()
        else:
            return None
        if change == CHANGE_FULL_FILE:
            allowed = _FULL_FILE_FIELDS
        elif change == CHANGE_STRUCTURAL:
            allowed = _STRUCTURAL_FIELDS
        else:
            return None
        if set(payload) - allowed:
            return None

        # 3. Both forms must resolve to exactly ONE (path, content) pair, so
        #    every bound below applies identically to either form.
        if change == CHANGE_FULL_FILE:
            extracted = self._from_full_file(payload)
        else:
            extracted = self._from_structural(payload, need)
        if extracted is None:
            return None
        path, content = extracted

        # 5. Path safety: reuse the EXISTING sandbox confinement validator
        #    (absolute, drive prefix, ``..`` traversal, empty segments, length).
        if len(path) > self._policy.max_path_chars:
            return None
        try:
            CodeChangeSet.validate_path(path)
        except Exception:  # noqa: BLE001 — any confinement violation is a refusal
            return None

        # 6. Content bound (reuse the existing development-cycle policy).
        if len(content) > self._policy.max_content_chars:
            return None

        # 7. Containment in the need's DECLARED target, when one is declared.
        targets = _declared_targets(need)
        if targets and not any(
            _matches_declared_target(path, target) for target in targets
        ):
            return None

        # 8. The plan's ALREADY-SELECTED verification tests and bounded
        #    test-support closure travel the SAME convention every sibling
        #    supplier uses (``metadata["test_files"]`` /
        #    ``metadata["repository_context"]``), so the governed verification
        #    leg runs against the plan's bounded test target instead of
        #    degrading to an unbounded whole-workspace collection. This is the
        #    existing ``SuppliedChanges`` representation, not a new one; when
        #    the need carries neither key the result is unchanged. Malformed
        #    payloads fail closed (``None``), never partially.
        try:
            need_metadata = getattr(need, "metadata", None)
            if not isinstance(need_metadata, dict):
                need_metadata = {}
            test_files = _pairs(need_metadata.get("test_files", {}))
            repository_context = _pairs(
                need_metadata.get("repository_context", {})
            )
        except ValueError:
            return None

        note = payload.get("note")
        notes = str(note)[:_MAX_NOTES_CHARS] if isinstance(note, str) else ""
        return SuppliedChanges(
            code_changes=((path, content),),
            test_files=test_files,
            repository_context=repository_context,
            origin=self.origin,
            confidence=_clamp01(proposal.confidence),
            notes=notes,
        )

    # -- change forms ------------------------------------------------------

    @staticmethod
    def _from_full_file(payload: dict) -> tuple[str, str] | None:
        """The backward-compatible full-file form: exactly ONE file."""
        files = payload.get("files")
        if not isinstance(files, dict) or not files:
            return None
        if len(files) != 1:
            return None
        path, content = next(iter(files.items()))
        if not isinstance(path, str) or not isinstance(content, str):
            return None
        path = path.strip()
        if not path or not content.strip():
            return None
        # The proposal's own declared target(s) must agree with its files.
        declared = payload.get("paths")
        if declared is not None:
            if not isinstance(declared, (list, tuple)):
                return None
            if sorted(str(item).strip() for item in declared) != [path]:
                return None
        return path, content

    def _from_structural(self, payload: dict, need: DevelopmentNeed) -> tuple[str, str] | None:
        """The structural form: ONE anchored edit through the EXISTING editor.

        No second editor is created. The proposal is translated into the
        existing ``metadata["structural"]`` convention and delegated to
        :class:`~atlas.evolution.structural_editor.StructuralChangeSupplier`,
        which owns symbol resolution, AST validation, bounds and the
        preservation of every byte outside the anchored span. Any refusal is a
        ``None`` (fail-closed), never a partial change.
        """
        path = payload.get("path")
        symbol = payload.get("symbol")
        if not isinstance(path, str) or not isinstance(symbol, str):
            return None
        path = path.strip().replace("\\", "/")
        symbol = symbol.strip()
        if not path or not symbol:
            return None
        raw_kind = payload.get("kind", "replace")
        if not isinstance(raw_kind, str):
            return None
        kind = raw_kind.strip().lower()
        if kind not in _STRUCTURAL_KINDS:
            return None
        source = payload.get("source", "")
        if not isinstance(source, str):
            return None
        if kind != "delete" and not source.strip():
            return None
        # An architecture-sensitive module is never structurally authored, even
        # by an otherwise valid structural proposal.
        try:
            from atlas.evolution.promotion_gate import ARCHITECTURE_SENSITIVE_PREFIXES

            dotted = (
                path[:-3].replace("/", ".")
                if path.endswith(".py")
                else path.replace("/", ".")
            )
            if any(
                dotted.startswith(prefix) for prefix in ARCHITECTURE_SENSITIVE_PREFIXES
            ):
                return None
        except ImportError:  # pragma: no cover — the gate is always importable
            return None

        try:
            from dataclasses import replace

            from atlas.evolution.structural_editor import (
                STRUCTURAL_KEY,
                StructuralChangeSupplier,
                structural_spec,
            )

            edit = structural_spec(path, symbol, source, kind=kind)
            note = payload.get("note")
            if isinstance(note, str) and note.strip():
                edit["reason"] = note[:_MAX_NOTES_CHARS]
            metadata = dict(getattr(need, "metadata", None) or {})
            metadata[STRUCTURAL_KEY] = [edit]
            supplied = StructuralChangeSupplier(
                self._root, base_source=self._base_source
            ).supply_changes(replace(need, metadata=metadata))
        except Exception:  # noqa: BLE001 — any editor refusal is a refusal here
            return None
        if supplied is None:
            return None
        try:
            changes = tuple(supplied.code_changes or ())
        except Exception:  # noqa: BLE001
            return None
        if len(changes) != 1:
            return None
        result_path, content = changes[0]
        if str(result_path) != path or not str(content).strip():
            return None
        return path, str(content)


def _pairs(raw: Any) -> tuple[tuple[str, str], ...]:
    """Normalize ``{path: content}`` / ``[{path, content}]`` into pairs.

    Mirrors the EXISTING convention the deterministic and structural suppliers
    read. ``None``/empty yields ``()``; a malformed payload raises
    ``ValueError`` so the caller fails the whole change closed.
    """
    if raw is None or raw == {} or raw == []:
        return ()
    if isinstance(raw, dict):
        out: list[tuple[str, str]] = []
        for path, content in raw.items():
            if not isinstance(path, str) or not isinstance(content, str):
                raise ValueError("malformed metadata payload")
            out.append((path, content))
        return tuple(out)
    if isinstance(raw, list):
        out = []
        for item in raw:
            if (
                not isinstance(item, dict)
                or "path" not in item
                or "content" not in item
            ):
                raise ValueError("malformed metadata entry")
            out.append((str(item["path"]), str(item["content"])))
        return tuple(out)
    raise ValueError("malformed metadata payload")


__all__ = [
    "CHANGE_FULL_FILE",
    "CHANGE_STRUCTURAL",
    "SPECIALIST_ORIGIN",
    "SPECIALIST_PROPOSAL_KEY",
    "SUPPORTED_CHANGES",
    "SpecialistChangeSupplier",
]
