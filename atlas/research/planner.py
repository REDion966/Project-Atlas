"""Atlas Research — Research Planner (Phase 17.3).

Deterministically decomposes an existing :class:`~atlas.evolution.models.ResearchQuery`
into a :class:`~atlas.research.models.ResearchPlan`: sub-queries, target
sources, verification strategy, and maximum recursion depth.

Pure logic. No AI. No storage. No gateway. No dispatcher. The planner is
stateless — identical inputs always produce identical plans.

Source-kind selection precedence:
  1. Any ``workspace://`` URI ⇒ ``WORKSPACE`` (project-owned material).
  2. ``code://`` URI or code-like file extension ⇒ ``CODEBASE``.
  3. Anything else with a known document extension ⇒ ``DOCUMENT``.
  4. Otherwise default ⇒ ``DOCUMENT``.
"""

import re
from dataclasses import dataclass

from atlas.evolution.models import ResearchQuery
from atlas.research.models import ResearchPlan, SourceKind
from atlas.research.source_catalog import (
    CODE_EXTENSIONS,
    DOCUMENT_EXTENSIONS,
)


# ---------------------------------------------------------------------------
# Deterministic constants
# ---------------------------------------------------------------------------

_STOPWORDS: frozenset[str] = frozenset(
    {
        "a",
        "an",
        "the",
        "of",
        "in",
        "on",
        "at",
        "to",
        "for",
        "with",
        "and",
        "or",
        "by",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "how",
        "what",
        "when",
        "who",
        "which",
        "does",
        "do",
        "can",
        "we",
        "us",
        "our",
        "should",
        "must",
        "its",
        "it",
        "this",
        "that",
    }
)

# Formatting of every generated sub-query (``question`` field).
_SUB_QUERY_TEMPLATE: str = "{question} | aspect: {aspect}"

# Deterministic mapping from core subject tag → aspect label.
_TAG_ASPECTS: dict[str, str] = {
    "architecture": "architecture",
    "api": "api",
    "protocol": "protocol",
    "design": "design",
    "config": "configuration",
    "setup": "configuration",
    "storage": "storage",
    "persistence": "storage",
    "security": "security",
    "auth": "security",
    "performance": "performance",
    "reliability": "reliability",
    "testing": "testing",
    "test": "testing",
    "deployment": "deployment",
    "release": "deployment",
    "integration": "integration",
    "migration": "migration",
    "memory": "memory",
    "reasoning": "reasoning",
    "evolution": "evolution",
    "governance": "governance",
}

_MARKERS: tuple[tuple[str, SourceKind], ...] = (
    ("workspace://", SourceKind.WORKSPACE),
    ("code://", SourceKind.CODEBASE),
)

_DEFAULT_DEPTH: int = 1
_MAX_DEPTH: int = 3

_VERIFICATION_STRATEGIES: tuple[str, ...] = (
    "source_consensus",
    "internal_consistency",
    "none",
)


# ---------------------------------------------------------------------------
# Decomposition result (internal)
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class _Decomposition:
    """Internal decomposition result of the planner."""

    core_subject: str
    aspects: tuple[str, ...]
    source_kinds: tuple[SourceKind, ...]


# ---------------------------------------------------------------------------
# Planner
# ---------------------------------------------------------------------------


class ResearchPlanner:
    """Stateless, deterministic research query decomposition."""

    def plan(self, query: ResearchQuery) -> ResearchPlan:
        """Build a :class:`ResearchPlan` for the given query.

        Deterministic: the same query always yields the same plan. The
        plan embeds no observable clock time so repeated planning of the
        same query is byte-for-byte identical.
        """
        decomposition: _Decomposition = self.decompose(query)

        sub_queries: tuple[str, ...] = tuple(
            _SUB_QUERY_TEMPLATE.format(question=query.question, aspect=aspect)
            for aspect in decomposition.aspects
        )

        return ResearchPlan(
            plan_id=f"plan::{query.query_id}",
            query_id=query.query_id,
            question=query.question,
            sub_queries=sub_queries,
            target_sources=decomposition.source_kinds,
            verification_strategy=self.verification_strategy(query, decomposition),
            max_depth=self.max_depth(query, decomposition),
        )

    # -- decomposition ----------------------------------------------------

    def decompose(self, query: ResearchQuery) -> _Decomposition:
        """Pure decomposition: subject, aspects, sources.

        Exposed publicly so the sub-steps are independently testable;
        consumers should call :meth:`plan` for the public plan artifact.
        """
        question: str = query.question.strip()
        if not question:
            return _Decomposition("", (), ())
        core_subject: str = self.core_subject(question)
        aspects: tuple[str, ...] = self.aspects(question, core_subject)
        source_kinds: tuple[SourceKind, ...] = self.target_sources(question, aspects)
        return _Decomposition(core_subject, aspects, source_kinds)

    def core_subject(self, question: str) -> str:
        """Most significant noun of the question (last non-stopword)."""
        words: list[str] = [w for w in re.split(r"[^a-zA-Z0-9']+", question.lower()) if w]
        if not words:
            return ""
        for word in reversed(words):
            if word not in _STOPWORDS:
                return word.replace("'", "")
        return words[-1]

    def aspects(self, question: str, core_subject: str) -> tuple[str, ...]:
        """Ordered aspects to research, derived from the core subject."""
        subject_aspect: str = _TAG_ASPECTS.get(core_subject, "overview")
        return (subject_aspect,)

    def target_sources(self, question: str, aspects: tuple[str, ...]) -> tuple[SourceKind, ...]:
        """Source kinds to consult (pipeline precedence)."""
        normalized: str = question.lower()
        for marker, kind in _MARKERS:
            if marker in normalized:
                return (kind,)
        tokens: list[str] = [t for t in re.split(r"[^a-zA-Z0-9_.]+", normalized) if t]
        for token in tokens:
            if "." in token:
                extension: str = "." + _last_token(token, ".")
                if extension in CODE_EXTENSIONS:
                    return (SourceKind.CODEBASE,)
                if extension in DOCUMENT_EXTENSIONS:
                    return (SourceKind.DOCUMENT,)
        return (SourceKind.DOCUMENT,)

    def verification_strategy(self, query: ResearchQuery, decomposition: _Decomposition) -> str:
        """Deterministic verification strategy for the plan."""
        if not decomposition.core_subject:
            return _VERIFICATION_STRATEGIES[2]  # "none"
        if len(decomposition.aspects) > 1:
            return _VERIFICATION_STRATEGIES[0]  # "source_consensus"
        return _VERIFICATION_STRATEGIES[1]  # "internal_consistency"

    def max_depth(self, query: ResearchQuery, decomposition: _Decomposition) -> int:
        """Deterministic recursion depth bound for the plan."""
        if not decomposition.core_subject:
            return _DEFAULT_DEPTH
        token_count: int = len(query.question.split())
        if token_count <= 8:
            return _DEFAULT_DEPTH
        if token_count <= 24:
            return 2
        return _MAX_DEPTH


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _last_token(value: str, separator: str) -> str:
    """Return the substring after the last ``separator`` occurrence."""
    return value.rsplit(separator, 1)[1]
