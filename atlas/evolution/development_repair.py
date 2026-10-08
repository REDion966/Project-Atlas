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
from atlas.evolution.verification_attribution import (
    VerificationTransition,
    transition_of,
)

#: Bounds applied to the bounded failure-context prompt built for the model.
_MAX_SUMMARY_CHARS: int = 2600
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


def _is_repairable(outcome: Any) -> bool:
    """True only for an ATTRIBUTABLE verification failure (repair candidate).

    A failure is repairable when the change was actually APPLIED (no rollback)
    and a targeted test genuinely failed/errored. Command 4 makes attribution
    PRECISE when a pre-change BASELINE was recorded: a failure that also occurs
    WITHOUT the change (``fail_to_fail``) is not the change's fault, so no
    corrective change is authored for it. Environment signals (a verification
    timeout), rollbacks, governance/objective/capability refusals and unknown
    failures are likewise NOT repairable.
    """
    if _outcome_status(outcome) is not DevelopmentOutcomeStatus.FAILED:
        return False
    if _was_guard_refused(outcome):
        # Command 2 (W3) — the guard refused an APPLIED change, so no pytest
        # verdict exists. That is an attributable AUTHORING/CHANGE defect (the
        # change was illegal, not the tests), and bounded corrective authoring is
        # the one legitimate response, so it IS repairable — without being
        # reinterpreted as a verification transition.
        return True
    if bool(getattr(outcome, "rollback_occurred", False)):
        return False
    if bool(getattr(outcome, "verification_passed", False)):
        return False
    transition = transition_of(outcome)
    if transition in (
        VerificationTransition.ALREADY_FAILING,
        VerificationTransition.FIXED,
        VerificationTransition.STILL_PASSING,
    ):
        return False
    test_outcome = (getattr(outcome, "test_outcome", "") or "").strip().lower()
    return test_outcome in ("failed", "error")


def _was_guard_refused(outcome: Any) -> bool:
    """True when the deterministic change guard refused the applied change."""
    from atlas.evolution.change_guard import was_guard_refused

    try:
        return bool(was_guard_refused(outcome))
    except Exception:  # noqa: BLE001 — absent evidence is not a refusal
        return False


def _held_out_boundary(workload: Any) -> Any:
    """The HELD-OUT verification boundary for a repair (or an empty one).

    The workload's ``test_files`` ARE the plan's selected verification set, so
    they are exactly the artifacts the corrective author is judged by and must
    not see. An explicit ``held_out_tests`` declaration is honoured as well.
    """
    from atlas.evolution.held_out_context import HeldOutBoundary, boundary_of

    files = {
        str(path): str(content)
        for path, content in ((getattr(workload, "test_files", None) or {}) or {}).items()
    }
    if not files:
        return HeldOutBoundary()
    return boundary_of(
        metadata={"held_out_tests": sorted(files)},
        sources=files,
    )


def _safe_author_context(sources: Any, boundary: Any) -> dict[str, str]:
    """The held-out-filtered author context (never the raw mapping)."""
    from atlas.evolution.held_out_context import safe_context

    try:
        return safe_context(dict(sources or {}), boundary)
    except Exception:  # noqa: BLE001 — a failed filter yields NO context
        return {}


def _failure_category(failed: Any) -> str:
    """The bounded ABSTRACT failure category an author may be told (Command 2 A3)."""
    from atlas.evolution.held_out_context import abstract_failure_category

    try:
        return abstract_failure_category(failed)
    except Exception:  # noqa: BLE001 — an unknown category is still bounded
        return "unknown"


def _workload_paths(workload: Any) -> list[str]:
    """The repo-relative paths a workload changes (bounded)."""
    paths: list[str] = []
    for change in getattr(workload, "code_changes", ()) or ():
        if isinstance(change, dict) and change.get("path"):
            paths.append(str(change["path"]))
    return paths


def _content_for(workload: Any, path: str) -> str:
    """The workload's content for ``path`` (or ``""``)."""
    for change in getattr(workload, "code_changes", ()) or ():
        if isinstance(change, dict) and str(change.get("path")) == path:
            return str(change.get("content") or "")
    return ""


def _author_context(author: Any, target: str) -> dict[str, str]:
    """The author's OWN bounded repository context for ``target`` (or ``{}``).

    Reuses the specialist author's existing bounded context builder so the repair
    sees the SAME repository evidence the initial generation did — no second
    context mechanism.
    """
    builder = getattr(author, "_build_context", None)
    if callable(builder):
        result = builder(target)
        if isinstance(result, dict):
            return {str(k): str(v) for k, v in result.items()}
    return {}


class RepairChangeSupplier:
    """Bounded corrective change supplier over the existing loop seam.

    Args:
        baseline: Optional baseline supplier (the existing metadata supplier by
            default). Always tried first so behaviour without a model is
            unchanged.
        repair_model: Optional duck-typed callable ``prompt -> str|dict|AIResponse``
            used ONLY to author a corrective change after a failure. ``None``
            (the default) disables repair entirely.
        repository_map: Optional read-only ``RepositoryMap``-like object used to
            build BOUNDED, deterministically-ranked repository context for the
            repair prompt. Optional and evidence-only: with no map the prompt is
            byte-identical to before.
    """

    def __init__(
        self,
        *,
        baseline: BaselineSupplier | None = None,
        repair_model: RepairModel | None = None,
        repository_map: Any | None = None,
        architecture_model: Any | None = None,
        repair_author: Any | None = None,
    ) -> None:
        self._baseline = baseline
        self._repair_model = repair_model
        self._repository_map = repository_map
        self._repair_author = repair_author
        self._supplier = ModelAssistedChangeSupplier(
            authoring_model=repair_model,
            repository_map=repository_map,
            architecture_model=architecture_model,
        )

    @property
    def repair_enabled(self) -> bool:
        return self._repair_model is not None or self.specialist_repair_enabled

    @property
    def specialist_repair_enabled(self) -> bool:
        """True when the ACTIVE specialist seam is wired for repair.

        ``repair_author`` is the EXISTING
        :class:`~atlas.evolution.specialist_development.SpecialistDevelopmentAuthor`
        (or any object exposing the same bounded ``propose`` surface, or a
        zero-arg callable returning one). It authors the corrective change
        through the SAME Atlas-owned ``code.generate`` seam the initial
        generation used — no second provider, no second author.
        """
        return callable(getattr(self._resolved_repair_author(), "propose", None))

    def _resolved_repair_author(self) -> Any | None:
        """Resolve the repair author (a provider callable is invoked lazily).

        Lazy resolution keeps a single specialist instance wired even when the
        supplier is constructed before that instance exists.
        """
        author = self._repair_author
        if author is not None and not hasattr(author, "propose") and callable(author):
            try:
                return author()
            except Exception:  # noqa: BLE001 — a broken provider is not available
                return None
        return author

    def __call__(
        self, proposal: Any, history: list | None = None
    ) -> SandboxWorkload | None:
        """Return the baseline workload, or a bounded corrective one after failure."""
        history = list(history or ())
        baseline = self._get_baseline(proposal, history)
        if not self.repair_enabled or not history:
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
        """Author ONE bounded corrective workload.

        Prefers the ACTIVE Atlas-owned specialist seam (``code.generate``); falls
        back to the EXISTING generic model supplier. Either way the corrective
        change is bounded, untrusted, and applied/verified by the existing loop.

        Command 2 (A3) — ONE held-out verification boundary is derived from the
        baseline workload's verification tests and is enforced on BOTH corrective
        authors, so neither can see the artifacts it is judged by.
        """
        boundary = _held_out_boundary(baseline)
        corrected = self._author_specialist_correction(
            proposal, failed, baseline, boundary
        )
        if corrected is not None:
            return corrected
        return self._author_model_correction(proposal, failed, baseline, boundary)

    def _author_model_correction(
        self,
        proposal: Any,
        failed: Any,
        baseline: SandboxWorkload | None,
        boundary: Any = None,
    ) -> SandboxWorkload | None:
        """Author ONE bounded corrective workload via the existing supplier.

        Reuses ``ModelAssistedChangeSupplier`` for all validation and bounds, so
        a corrective change can never reach a path the deterministic supplier
        could not; any failure returns ``None`` (the caller falls back to the
        baseline workload — fail-closed).
        """
        try:
            supplied = self._supplier.supply_changes(
                self._build_need(proposal, failed, boundary=boundary)
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

    def _author_specialist_correction(
        self,
        proposal: Any,
        failed: Any,
        baseline: SandboxWorkload | None,
        boundary: Any = None,
    ) -> SandboxWorkload | None:
        """Author the corrective change through the ACTIVE specialist seam.

        Fail-closed and tightly bounded:

          * only a genuine, *attributable* verification failure is repaired
            (a failed/errored targeted test on an APPLIED change — never a
            rollback, timeout, governance or environment failure);
          * exactly ONE baseline target is corrected (no scope expansion);
          * the returned change must target the SAME authorized path and must
            DIFFER from the failing content — a restatement of the failing
            change is refused (this is the Command 3C failure mode);
          * the baseline verification tests and target are preserved so the
            correction is measured against the SAME bounded tests.

        Any deviation returns ``None`` (the caller falls back to the baseline —
        fail-closed). No new provider, author or governance path is introduced.
        """
        author = self._resolved_repair_author()
        if not callable(getattr(author, "propose", None)) or baseline is None:
            return None
        if not _is_repairable(failed):
            return None
        targets = _workload_paths(baseline)
        if len(targets) != 1:
            return None
        target = targets[0]
        base_content = _content_for(baseline, target)
        if not base_content:
            return None
        try:
            need = self._build_need(proposal, failed, target=target, boundary=boundary)
            # Command 2 (W2) — the ONE reusable context builder selects the
            # target's bounded symbol REGION (with its structural/dependency
            # neighbours) from the read-only repository map.
            context: dict[str, str] = {}
            try:
                from atlas.evolution.context_builder import (
                    RepositoryContextRequest,
                    context_sources,
                )

                context = dict(
                    context_sources(
                        self._repository_map,
                        RepositoryContextRequest(module=target),
                    )
                    or {}
                )
            except Exception:  # noqa: BLE001 — a failed selection is no context
                context = {}
            if not context:
                # Fall back to the author's OWN bounded target source, which is
                # the pre-change repository content the correction regresses to.
                try:
                    context = dict(_author_context(author, target) or {})
                except Exception:  # noqa: BLE001
                    context = {}
            # Command 2 (A3) — the HELD-OUT verification boundary. The baseline
            # verification test sources are NO LONGER added to the context (they
            # are exactly the artifacts this correction is judged by), and any
            # held-out content carried inside a surviving value is redacted.
            context = _safe_author_context(context, boundary)
            candidate = author.propose(
                need,
                target=target,
                plan={
                    "target": target,
                    "route": "specialist_repair",
                    "failure": str(getattr(failed, "test_outcome", "") or "")[:64],
                    "failure_category": _failure_category(failed),
                    "attribution": transition_of(failed).value,
                },
                # No held-out verification identity crosses the boundary: the
                # author receives a bounded failure CATEGORY, never which tests
                # judge it.
                verification_tests=(),
                context=context or None,
            )
        except Exception:
            return None
        supplied = self._consume_specialist(
            candidate, need, target, base_source={target: base_content}
        )
        if supplied is None:
            return None
        changes = list(supplied.code_changes or ())
        if len(changes) != 1:
            return None
        path, content = changes[0]
        if path != target or not str(content).strip():
            return None
        if content == base_content:
            # A genuine corrective change must DIFFER from the failing content.
            return None
        return SandboxWorkload(
            code_changes=tuple(
                {"path": path, "content": content} for path, content in changes
            ),
            test_files=dict(baseline.test_files or {}),
            verify_target=baseline.verify_target,
        )

    def _consume_specialist(
        self,
        candidate: Any,
        need: DevelopmentNeed,
        target: str,
        base_source: Any = None,
    ) -> Any | None:
        """Run the candidate through the EXISTING proposal consumer seam.

        Reuses the EXISTING
        :class:`~atlas.evolution.specialist_change_supplier.SpecialistChangeSupplier`
        for ALL validation (identity, capability, one file, path containment,
        target containment), so a corrective change is subject to exactly the
        same Atlas-owned checks as the initial generation.
        """
        if candidate is None:
            return None
        try:
            from dataclasses import replace

            from atlas.evolution.specialist_change_supplier import (
                SPECIALIST_PROPOSAL_KEY,
                SpecialistChangeSupplier,
            )

            dotted = (
                target[:-3].replace("/", ".")
                if target.endswith(".py")
                else target.replace("/", ".")
            )
            metadata = dict(getattr(need, "metadata", None) or {})
            metadata[SPECIALIST_PROPOSAL_KEY] = candidate
            repair_need = replace(
                need, target_components=(target, dotted), metadata=metadata
            )
            return SpecialistChangeSupplier(base_source=base_source).supply_changes(
                repair_need
            )
        except Exception:
            return None

    @staticmethod
    def _build_need(
        proposal: Any, failed: Any, target: str = "", boundary: Any = None
    ) -> DevelopmentNeed:
        """Bounded failure context the model must reason about (untrusted input)."""
        status = _outcome_status(failed)
        status_name = getattr(status, "name", str(status))
        message = str(getattr(failed, "message", "") or "")[:_MAX_SUMMARY_CHARS]
        changed = tuple(getattr(failed, "changed_files", ()) or ())
        test_outcome = str(getattr(failed, "test_outcome", "") or "")
        rollback = bool(getattr(failed, "rollback_occurred", False))
        verification_passed = bool(getattr(failed, "verification_passed", False))
        title = str(getattr(proposal, "title", "") or "development")[: _MAX_TITLE_CHARS]
        scope = target or (changed[0] if changed else "-")
        summary = (
            f"The previous change to the single file {scope} caused the targeted "
            "tests to FAIL. Produce the CORRECTED FULL new content of "
            f"{scope} so those tests pass again — revert or adjust the previous "
            "change as needed. Read the failing test expectations in the "
            "repository context below and satisfy them. Change ONLY that file "
            "and preserve all other behaviour.\n"
            f"status={status_name} test_outcome={test_outcome} "
            f"verification_passed={verification_passed} rollback={rollback}\n"
            f"changed_files={', '.join(changed) or '-'}\n"
            f"attribution={transition_of(failed).value}\n"
            f"failure={message}"
        )
        if boundary is not None:
            try:
                # Command 2 (A3) — a held-out test's own source can be carried
                # inside a pytest failure message, so the bounded failure text is
                # redacted against the held-out sources before it is sent.
                summary = boundary.redact(summary)
            except Exception:  # noqa: BLE001 — keep the bounded text unchanged
                pass
        return DevelopmentNeed(
            title=f"Repair failed development attempt: {title}"[:_MAX_TITLE_CHARS],
            summary=summary[:_MAX_SUMMARY_CHARS],
            rationale="Bounded corrective change after a governed sandbox failure.",
        )
