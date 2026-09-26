"""Atlas Evolution — Bounded, governed development REPAIR primitive.

The repair/retry step of the Atlas Agent Workbench, internalized from the
bounded recovery loops of mini-SWE-agent, OpenHands, and MiniMax Mini-Agent —
adapted to Atlas's deterministic-first, model-optional, sandbox-only,
governance-preserving architecture.

It is **not a new execution loop**. It is a drop-in implementation of the
EXISTING ``SelfDevelopmentLoop`` change-supplier protocol::

    (proposal, history) -> SandboxWorkload | None

Behaviour:

* first attempt (empty history) -> the existing baseline workload, unchanged;
* after a FAILED sandbox attempt -> a bounded CORRECTIVE workload authored by
  the OPTIONAL, untrusted repair model, validated by the EXISTING
  :class:`~atlas.evolution.model_assisted_supplier.ModelAssistedChangeSupplier`
  (path confinement, architecture-sensitive-prefix refusal, size/format bounds,
  fail-closed);
* with no repair model wired -> the baseline workload is returned unchanged
  (deterministic-first; no behaviour change).

Every guarantee remains with the EXISTING loop and governance: the corrective
change is applied only inside a disposable ``CodeSandbox``, verified by the
existing verifier, and NEVER promoted. This module mints no authority, approves
nothing, promotes nothing, writes nothing, and adds no model dependency.
"""

from __future__ import annotations

from typing import Any, Callable

from atlas.evolution.development_cycle import DevelopmentNeed
from atlas.evolution.development_models import (
    DevelopmentOutcome,
    DevelopmentOutcomeStatus,
    SandboxWorkload,
)
from atlas.evolution.model_assisted_supplier import ModelAssistedChangeSupplier

#: Bounds applied to the bounded failure-context prompt built for the model.
_MAX_SUMMARY_CHARS: int = 800
_MAX_TITLE_CHARS: int = 200

#: The existing supplier-protocol signature used by ``SelfDevelopmentLoop``.
BaselineSupplier = Callable[[Any, list], SandboxWorkload | None]
RepairModel = Callable[[str], Any]


def _baseline_workload(proposal: Any, history: list) -> SandboxWorkload | None:
    """The EXISTING baseline workload (lazy import to avoid import cycles)."""
    from atlas.evolution.self_development_loop import metadata_change_supplier

    return metadata_change_supplier(proposal, history)


def _outcome_status(outcome: Any) -> Any:
    return getattr(outcome, "outcome", None)


def _is_correctable(outcome: Any) -> bool:
    """True when the last iteration failed in a way a bounded repair may address.

    Governance/objective refusals are never "repaired" — those are terminal and
    fail closed. Only a sandbox implementation/verification FAILURE is eligible.
    """
    return _outcome_status(outcome) is DevelopmentOutcomeStatus.FAILED


class RepairChangeSupplier:
    """Bounded corrective change supplier over the existing loop seam.

    Args:
        baseline: Optional baseline supplier (the existing metadata supplier by
            default). Always tried first so behaviour without a model is
            unchanged.
        repair_model: Optional duck-typed callable ``prompt -> str|dict|AIResponse``
            used ONLY to author a corrective change after a failure. ``None``
            (the default) disables repair entirely.
    """

    def __init__(
        self,
        *,
        baseline: BaselineSupplier | None = None,
        repair_model: RepairModel | None = None,
    ) -> None:
        self._baseline = baseline
        self._repair_model = repair_model
        self._supplier = ModelAssistedChangeSupplier(authoring_model=repair_model)

    @property
    def repair_enabled(self) -> bool:
        return self._repair_model is not None

    def __call__(
        self, proposal: Any, history: list | None = None
    ) -> SandboxWorkload | None:
        """Return the baseline workload, or a bounded corrective one after failure."""
        history = list(history or ())
        baseline = self._get_baseline(proposal, history)
        if self._repair_model is None or not history:
            return baseline
        last = history[-1]
        if not _is_correctable(last):
            return baseline
        corrected = self._author_correction(proposal, last, baseline)
        return corrected if corrected is not None else baseline

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _get_baseline(self, proposal: Any, history: list) -> SandboxWorkload | None:
        supplier = self._baseline or _baseline_workload
        try:
            return supplier(proposal, history)
        except Exception:
            return None

    def _author_correction(
        self, proposal: Any, failed: Any, baseline: SandboxWorkload | None
    ) -> SandboxWorkload | None:
        """Author ONE bounded corrective workload via the existing supplier.

        Reuses ``ModelAssistedChangeSupplier`` for all validation and bounds, so
        a corrective change can never reach a path the deterministic supplier
        could not; any failure returns ``None`` (the caller falls back to the
        baseline workload — fail-closed).
        """
        try:
            supplied = self._supplier.supply_changes(
                self._build_need(proposal, failed)
            )
        except Exception:
            return None
        if supplied is None or not supplied.code_changes:
            return None
        try:
            code_changes = tuple(
                {"path": path, "content": content}
                for path, content in supplied.code_changes
            )
        except Exception:
            return None
        test_files = dict(supplied.test_files)
        if not test_files and baseline is not None:
            # Preserve the baseline verification requirement so a corrected
            # implementation is still measured against the same tests.
            test_files = dict(baseline.test_files)
        verify_target = baseline.verify_target if baseline is not None else ""
        return SandboxWorkload(
            code_changes=code_changes,
            test_files=test_files,
            verify_target=verify_target,
        )

    @staticmethod
    def _build_need(proposal: Any, failed: Any) -> DevelopmentNeed:
        """Bounded failure context the model must reason about (untrusted input)."""
        status = _outcome_status(failed)
        status_name = getattr(status, "name", str(status))
        message = str(getattr(failed, "message", "") or "")[:_MAX_SUMMARY_CHARS]
        changed = tuple(getattr(failed, "changed_files", ()) or ())
        test_outcome = str(getattr(failed, "test_outcome", "") or "")
        rollback = bool(getattr(failed, "rollback_occurred", False))
        verification_passed = bool(getattr(failed, "verification_passed", False))
        title = str(getattr(proposal, "title", "") or "development")[: _MAX_TITLE_CHARS]
        summary = (
            "The previous sandbox development attempt FAILED and must be "
            "repaired. Author a bounded corrective change (draft only).\n"
            f"Objective: {title}\n"
            f"status={status_name} test_outcome={test_outcome} "
            f"verification_passed={verification_passed} rollback={rollback}\n"
            f"changed_files={', '.join(changed) or '-'}\n"
            f"message={message}"
        )
        return DevelopmentNeed(
            title=f"Repair failed development attempt: {title}"[:_MAX_TITLE_CHARS],
            summary=summary[:_MAX_SUMMARY_CHARS],
            rationale="Bounded corrective change after a governed sandbox failure.",
        )
