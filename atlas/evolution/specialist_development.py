"""Atlas Evolution — the bounded specialist -> development producer (Command 3B).

The PRODUCER side of the Atlas-owned specialist seam. The governance seam
(:class:`~atlas.evolution.specialist_change_supplier.SpecialistChangeSupplier`)
already consumes a validated :class:`~atlas.specialists.SpecialistProposal`;
this module turns an ordinary, already-understood development request into such
a proposal through a REAL provider — bounded task -> inference -> parse ->
Atlas validation — and nothing more:

    DevelopmentNeed (+ Atlas localization / plan context)
        -> BoundedSpecialistTask           (existing Atlas-owned seam)
        -> SpecialistRegistry.request(...)  (bounded, fail-closed)
        -> validated SpecialistProposal    (UNTRUSTED input, never a decision)

Authority
---------
This module cannot and does not execute, run tests, approve, promote, apply,
write, or judge the provider's trustworthiness. It sends only the bounded task
(re-applied by :meth:`BoundedSpecialistTask.bounded`), performs no filesystem or
network I/O itself (transport is injected through the provider), and returns
``None`` on EVERY refusal. The proposal it returns is input to the EXISTING
governed pipeline, which still validates it, sandboxes it, verifies it, and
requires OWNER approval before anything is applied.

Standard library only. No vendor import.
"""

from __future__ import annotations

from typing import Any

from atlas.evolution.development_cycle import DevelopmentNeed
from atlas.specialists import (
    CODE_GENERATE,
    BoundedSpecialistTask,
    SpecialistProposal,
    SpecialistRegistry,
)

#: Bound on the source context placed in a task (the task itself re-bounds).
MAX_CONTEXT_SOURCE_CHARS: int = 20_000
#: Bound on the bounded plan summary placed in a task.
MAX_PLAN_ITEMS: int = 8
#: Bound on the request text placed in a task.
MAX_REQUEST_CHARS: int = 4_000


def _bounded_text(value: Any, limit: int) -> str:
    """Return a bounded, stripped string, or ``""`` for non-strings."""
    if not isinstance(value, str):
        return ""
    return value.strip()[:limit]


def _module_name(target: str) -> str:
    """Normalize a target (dotted module or repo path) to a dotted module."""
    text = str(target or "").strip().replace("\\", "/")
    if text.endswith(".py"):
        text = text[:-3]
    return text.strip(".").replace("/", ".")


class SpecialistDevelopmentAuthor:
    """Bounded producer over the EXISTING Atlas-owned specialist seam.

    Args:
        registry: A :class:`~atlas.specialists.SpecialistRegistry`. When it does
            not serve ``code.generate`` the author is inert and :meth:`propose`
            returns ``None`` (deterministic-first behaviour is unchanged).
        repository_map: Optional duck-typed ``RepositoryMap``-like object (or a
            zero-arg callable returning one) used to build the BOUNDED source
            context for the target module. Optional: without it the task simply
            carries no repository context.
    """

    def __init__(
        self,
        registry: SpecialistRegistry | None = None,
        *,
        repository_map: Any | None = None,
    ) -> None:
        self._registry = registry
        self._repository_map = repository_map

    @property
    def available(self) -> bool:
        """True when a provider serving ``code.generate`` is registered."""
        registry = self._registry
        if registry is None:
            return False
        try:
            return bool(registry.supports(CODE_GENERATE))
        except Exception:  # noqa: BLE001 — a broken registry is not available
            return False

    # -- producer ----------------------------------------------------------

    def propose(
        self,
        need: DevelopmentNeed,
        *,
        target: str = "",
        plan: dict[str, Any] | None = None,
        verification_tests: tuple[str, ...] = (),
        context: dict[str, str] | None = None,
    ) -> SpecialistProposal | None:
        """Run ONE bounded specialist request for ``need`` (or ``None``).

        ``target`` is the DECLARED, already-localized target (from the plan);
        ``plan`` is a bounded JSON-safe summary; ``verification_tests`` are the
        plan's already-selected tests; ``context`` is an optional explicit
        ``path -> content`` mapping. When ``context`` is not supplied, a bounded
        source excerpt of the target module is taken from the repository map.

        Fail-closed: an unavailable provider, a malformed task, a raising
        provider, a refused capability, or rejected output all yield ``None``.
        """
        if not self.available or not isinstance(need, DevelopmentNeed):
            return None
        try:
            task = self._build_task(
                need,
                target=target,
                plan=plan,
                verification_tests=verification_tests,
                context=context,
            )
            # The registry re-applies ``.bounded()`` and Atlas validation.
            return self._registry.request(task)
        except Exception:  # noqa: BLE001 — any failure is not a proposal
            return None

    def propose_with_metadata(
        self,
        need: DevelopmentNeed,
        **kwargs: Any,
    ) -> tuple[SpecialistProposal, dict[str, Any]] | None:
        """Return ``(proposal, metadata)`` where metadata carries the proposal.

        Convenience for callers that build a need to hand to the EXISTING
        governed cycle: the returned ``metadata`` is the need's metadata with the
        validated proposal attached under the seam's dedicated key. Returns
        ``None`` when no proposal was produced, so the caller falls through to
        its existing deterministic path unchanged.
        """
        from atlas.evolution.specialist_change_supplier import (
            SPECIALIST_PROPOSAL_KEY,
        )

        proposal = self.propose(need, **kwargs)
        if proposal is None:
            return None
        metadata = dict(getattr(need, "metadata", None) or {})
        metadata[SPECIALIST_PROPOSAL_KEY] = proposal
        return proposal, metadata

    # -- internals ---------------------------------------------------------

    def _resolve_map(self) -> Any | None:
        repository_map = self._repository_map
        if callable(repository_map):
            try:
                return repository_map()
            except Exception:  # noqa: BLE001
                return None
        return repository_map

    def _build_context(self, target: str) -> dict[str, str]:
        """Bounded ``path -> source`` for the target module, or ``{}``."""
        repository_map = self._resolve_map()
        if repository_map is None or not target:
            return {}
        module = _module_name(target)
        if not module:
            return {}
        for info in getattr(repository_map, "modules", ()) or ():
            name = str(getattr(info, "module", "") or "")
            if name != module:
                continue
            source = str(getattr(info, "source_excerpt", "") or "")
            if not source:
                return {}
            path = str(getattr(info, "path", "") or "") or (
                module.replace(".", "/") + ".py"
            )
            return {path: source[:MAX_CONTEXT_SOURCE_CHARS]}
        return {}

    def _build_task(
        self,
        need: DevelopmentNeed,
        *,
        target: str,
        plan: dict[str, Any] | None,
        verification_tests: tuple[str, ...],
        context: dict[str, str] | None,
    ) -> BoundedSpecialistTask:
        request = _bounded_text(
            " ".join(
                part
                for part in (
                    getattr(need, "title", ""),
                    getattr(need, "summary", ""),
                    getattr(need, "rationale", ""),
                    getattr(need, "expected_benefit", ""),
                )
                if isinstance(part, str) and part.strip()
            ),
            MAX_REQUEST_CHARS,
        )
        bounded_plan: dict[str, Any] = {}
        if isinstance(plan, dict):
            for index, (key, value) in enumerate(plan.items()):
                if index >= MAX_PLAN_ITEMS:
                    break
                bounded_plan[str(key)[:64]] = value
        bounded_context = context if isinstance(context, dict) and context else None
        if not bounded_context:
            bounded_context = self._build_context(target)
        return BoundedSpecialistTask(
            capability=CODE_GENERATE,
            request=request,
            target=_bounded_text(target, 128),
            context={str(k): str(v) for k, v in (bounded_context or {}).items()},
            plan=bounded_plan,
            verification_tests=tuple(
                str(item) for item in (verification_tests or ())
            ),
        )


__all__ = [
    "MAX_CONTEXT_SOURCE_CHARS",
    "SpecialistDevelopmentAuthor",
]
