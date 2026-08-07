"""Atlas Advanced Reasoning — CausalReasoner (Track D, Batch 2).

Deterministic causal analysis over the injected :class:`CausalGraphProvider`.
Provides causal chain analysis, root-cause analysis, counterfactual
("what-if") evaluation, and human-readable path explanations.

The reasoner NEVER owns causal data: all graph state is read through the
injected provider protocol and never mutated, cached as authoritative, or
persisted by this module. Counterfactual evaluation is modeled as a pure
filter over the provider's observed paths — the provider itself is never
modified.

Pure logic. No storage. No kernel. No AI SDKs. No atlas.reasoning imports.
"""

from __future__ import annotations

from atlas.advanced_reasoning.catalog import COUNTERFACTUAL_ID_PREFIX
from atlas.advanced_reasoning.models import (
    CausalPath,
    CounterfactualResult,
)
from atlas.advanced_reasoning.protocols import CausalGraphProvider

#: Default maximum traversal depth when a caller omits it.
_DEFAULT_MAX_DEPTH: int = 5

#: Token stop-words excluded from path-based explanation matching.
_STOP_WORDS: frozenset[str] = frozenset(
    {
        "a", "an", "the", "of", "to", "in", "on", "for", "and", "or",
        "with", "from", "by", "is", "are", "was", "were", "that", "this",
        "as", "at", "be",
    }
)


class CausalReasoner:
    """Read-only causal reasoning over an injected graph provider.

    Args:
        graph_provider: The injected read-only causal graph source. When
            ``None``, every analysis returns empty results (fail-soft).
    """

    def __init__(self, graph_provider: CausalGraphProvider | None = None) -> None:
        self._graph_provider = graph_provider

    # ------------------------------------------------------------------
    # Causal chain analysis
    # ------------------------------------------------------------------

    def analyze(
        self,
        source: str,
        target: str,
        max_depth: int | None = None,
    ) -> tuple[CausalPath, ...]:
        """Analyze the causal chains from ``source`` to ``target``.

        Deterministic: paths are returned ordered by confidence (highest
        first), then by path id.

        Returns:
            Ordered causal paths, or an empty tuple when no provider is
            injected, no paths exist, or the provider raises.
        """
        depth = max(1, max_depth or _DEFAULT_MAX_DEPTH)
        provider = self._graph_provider
        if provider is None:
            return ()
        try:
            paths = tuple(provider.causal_paths(source, target, max_depth=depth))
        except Exception:
            return ()
        return tuple(
            sorted(
                (p for p in paths if p.path_id),
                key=lambda p: (round(p.confidence, 6), p.path_id),
                reverse=True,
            )
        )

    # ------------------------------------------------------------------
    # Root cause analysis
    # ------------------------------------------------------------------

    def root_causes(
        self,
        entity: str,
        max_depth: int | None = None,
    ) -> tuple[CausalPath, ...]:
        """Find directed causal paths that terminate at ``entity``.

        Only paths that the provider can confirm as causal into ``entity``
        are kept — the reasoner never infers direction itself.

        Returns:
            Confirmed incoming causal paths, ordered by confidence, or an
            empty tuple when none are confirmable.
        """
        depth = max(1, max_depth or _DEFAULT_MAX_DEPTH)
        provider = self._graph_provider
        if provider is None:
            return ()
        try:
            related = tuple(provider.related_entities(entity, max_depth=depth))
        except Exception:
            return ()
        incoming: list[CausalPath] = []
        for candidate in related:
            paths = self.analyze(candidate, entity, max_depth=depth)
            incoming.extend(paths)
        return tuple(
            sorted(
                (p for p in incoming if p.path_id),
                key=lambda p: (round(p.confidence, 6), p.path_id),
                reverse=True,
            )
        )

    # ------------------------------------------------------------------
    # Counterfactual / what-if evaluation
    # ------------------------------------------------------------------

    def counterfactual(
        self,
        source_event: str,
        assumption: str,
        max_depth: int | None = None,
        result_id: str | None = None,
    ) -> CounterfactualResult:
        """Evaluate what changes when ``assumption`` blocks part of causality.

        The assumption is interpreted as a *blocking condition*: causal
        paths carrying the assumption's subject tokens (entity ids or
        relation types) are excluded from the "after" state. This is a pure
        read-only filter — the graph provider is never mutated.

        Returns:
            A CounterfactualResult comparing before/after paths.
        """
        depth = max(1, max_depth or _DEFAULT_MAX_DEPTH)
        blocked = self._blocked_tokens(assumption)
        baseline = self._all_paths_from(source_event, depth)
        after = tuple(
            p for p in baseline
            if not self._path_blocked(p, blocked)
        )
        changed = len(after) != len(baseline) or (
            tuple(p.path_id for p in after) != tuple(p.path_id for p in baseline)
        )
        return CounterfactualResult(
            result_id=result_id or f"{COUNTERFACTUAL_ID_PREFIX}:{len(after)}:{len(baseline)}",
            source_event=source_event,
            assumption=assumption.strip(),
            paths_before=baseline,
            paths_after=after,
            changed=changed,
            effect_summary=self._effect_summary(baseline, after, blocked),
            metadata={
                "blocked_tokens": tuple(sorted(blocked)),
                "max_depth": depth,
            },
        )

    def what_if(
        self,
        source_event: str,
        assumption: str,
        max_depth: int | None = None,
    ) -> CounterfactualResult:
        """Alias of :meth:`counterfactual` for what-if scenarios."""
        return self.counterfactual(
            source_event=source_event,
            assumption=assumption,
            max_depth=max_depth,
        )

    # ------------------------------------------------------------------
    # Explanation
    # ------------------------------------------------------------------

    @staticmethod
    def explain(path: CausalPath) -> str:
        """Build a deterministic human-readable explanation of ``path``.

        Examples:
            "a causes d via [b, c]" when entity ids are known, or
            "a leads to d (relation: causes, enables)" otherwise.
        """
        chain = path.entity_ids
        relations = path.relation_types
        if not chain:
            return f"{path.source} influences {path.target}"
        if len(chain) > 1 and len(relations) == len(chain) - 1:
            edges = " -> ".join(
                f"{chain[i]} [{relations[i]}]" for i in range(len(relations))
            )
            return f"{path.source} leads to {path.target} via {edges} (confidence {path.confidence:.2f})"
        return (
            f"{path.source} leads to {path.target} via {', '.join(chain[1:])} "
            f"(confidence {path.confidence:.2f})"
        )

    @classmethod
    def explain_all(cls, paths: tuple[CausalPath, ...]) -> tuple[str, ...]:
        """Explain every path in ``paths`` in deterministic order."""
        return tuple(cls.explain(path) for path in paths)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _all_paths_from(
        self,
        source_event: str,
        depth: int,
    ) -> tuple[CausalPath, ...]:
        """All confirmable causal paths originating at ``source_event``."""
        provider = self._graph_provider
        if provider is None:
            return ()
        try:
            related = tuple(provider.related_entities(source_event, max_depth=depth))
        except Exception:
            return ()
        paths: list[CausalPath] = []
        for target in related:
            paths.extend(self.analyze(source_event, target, max_depth=depth))
        return tuple(
            sorted(
                (p for p in paths if p.path_id),
                key=lambda p: (round(p.confidence, 6), p.path_id),
                reverse=True,
            )
        )

    @staticmethod
    def _blocked_tokens(assumption: str) -> frozenset[str]:
        """Tokens from the assumption that act as blocking conditions."""
        tokens = {
            token.lower().rstrip("s")
            for token in assumption.lower().split()
            if len(token) >= 3 and token not in _STOP_WORDS
        }
        return frozenset(tokens)

    @staticmethod
    def _path_blocked(
        path: CausalPath,
        blocked: frozenset[str],
    ) -> bool:
        """True when any path entity or relation matches a blocked token."""
        if not blocked:
            return False
        entities = {name.lower().rstrip("s") for name in path.entity_ids}
        relations = {rel.lower().rstrip("s") for rel in path.relation_types}
        sources = {path.source.lower().rstrip("s"), path.target.lower().rstrip("s")}
        return bool(blocked & (entities | relations | sources))

    @staticmethod
    def _effect_summary(
        before: tuple[CausalPath, ...],
        after: tuple[CausalPath, ...],
        blocked: frozenset[str],
    ) -> str:
        """Deterministic summary of the counterfactual effect."""
        if not blocked:
            return "No blocking condition derived from the assumption."
        if len(after) == len(before):
            return (
                "No change: no causal path matched the blocking condition "
                f"({' '.join(sorted(blocked))})."
            )
        removed = len(before) - len(after)
        return (
            f"Blocking {' '.join(sorted(blocked))} removes {removed} "
            f"causal path(s): {len(before)} -> {len(after)}."
        )
