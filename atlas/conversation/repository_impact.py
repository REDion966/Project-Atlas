"""Atlas Conversation — Repository Impact Analysis exposure (C4.2).

Deterministic, read-only exposure of Atlas's EXISTING repository
dependency/impact capability through the conversational path.

This module adds NO graph logic of its own: it reuses
:class:`atlas.research.repository_map.RepositoryMap` (``dependencies_of``,
``dependents_of``, ``impact_set``) and ``RepositoryMapBuilder``.

Design contract:
  * Bounded recognition: a request is recognized only when it carries an
    explicit impact/reverse-dependency cue AND a deterministically
    resolvable repository target token. There is NO general natural-language
    understanding and NO conversational reference resolution (GAP-C31-02
    remains deferred).
  * Deterministic: identical inputs against identical repository state yield
    identical results (sorted tuples, fixed depth).
  * Evidence-grounded: every listed module/file comes from the repository map.
  * Fail-closed: unknown or ambiguous targets are reported explicitly; no
    impact information is invented.
  * Read-only: never mutates the repository; ``modification_status`` is always
    ``"NONE"``. No AI/model, no network, no subprocess.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any

from atlas.conversation.normalization import collapse_whitespace

# ---------------------------------------------------------------------------
# Bounded recognition vocabulary (deterministic, explicit).
# ---------------------------------------------------------------------------

#: Explicit impact / reverse-dependency cues. A request is only recognized
#: as an impact request when one of these appears AND a repository target
#: token is present.
IMPACT_CUES: frozenset[str] = frozenset(
    {
        "depend on",
        "depends on",
        "dependents",
        "dependent modules",
        "impact of",
        "impact analysis",
        "what would be affected",
        "what is affected",
        "what would be impacted",
        "what is impacted",
        "would be affected",
        "would be impacted",
        "affected if i",
        "affects if i",
        "if i change",
        "if i modify",
        "if i refactor",
        "what breaks",
        "blast radius",
    }
)

#: Dotted Python module tokens (>= 2 segments), e.g.
#: ``atlas.conversation.conversation_state``.
_MODULE_TOKEN_RE = re.compile(
    r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+"
)

#: Repository path tokens ending in ``.py``, e.g.
#: ``atlas/conversation/conversation_state.py``.
_PATH_TOKEN_RE = re.compile(r"[A-Za-z0-9_./\\-]+\.py")

#: File suffixes that must never be treated as module-name segments (the
#: dotted-module regex would otherwise capture e.g. ``conversation_state.py``
#: or ``ROADMAP.md``).
_NON_MODULE_SUFFIXES: tuple[str, ...] = (
    ".py",
    ".md",
    ".txt",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".cfg",
    ".log",
    ".db",
    ".sqlite",
)


def extract_target_candidates(text: str) -> tuple[str, ...]:
    """Extract candidate repository module identifiers from ``text``.

    Returns normalized dotted module names, in first-appearance order,
    deduplicated. Paths are converted (``a/b.py`` -> ``a.b``). No resolution
    is attempted here.
    """
    if not isinstance(text, str) or not text:
        return ()
    seen: dict[str, None] = {}
    for match in _PATH_TOKEN_RE.finditer(text):
        raw = match.group(0).replace("\\", "/").lstrip("./")
        if raw.endswith(".py"):
            raw = raw[:-3]
        normalized = raw.replace("/", ".").strip(".")
        if normalized:
            seen[normalized] = None
    for match in _MODULE_TOKEN_RE.finditer(text):
        normalized = match.group(0).strip(".")
        if not normalized:
            continue
        if normalized.lower().endswith(_NON_MODULE_SUFFIXES):
            continue
        seen[normalized] = None
    return tuple(seen)


def looks_like_repository_impact_request(text: str) -> bool:
    """True when ``text`` is a bounded repository impact-analysis request.

    Requires BOTH an explicit impact cue and at least one repository target
    token. Conservative by design: anything else is left to the existing
    classification/fallback behavior.
    """
    if not isinstance(text, str) or not text:
        return False
    lowered = collapse_whitespace(text).lower()
    if not any(cue in lowered for cue in IMPACT_CUES):
        return False
    return bool(extract_target_candidates(text))


# ---------------------------------------------------------------------------
# Result model
# ---------------------------------------------------------------------------


class RepositoryImpactStatus(str, Enum):
    """Outcome of a repository impact-analysis request."""

    RESOLVED = "resolved"
    UNRESOLVED = "unresolved"
    AMBIGUOUS = "ambiguous"


@dataclass(frozen=True, slots=True)
class RepositoryImpactResult:
    """Deterministic, evidence-grounded repository impact result."""

    status: RepositoryImpactStatus
    query: str
    resolved_module: str = ""
    candidates: tuple[str, ...] = ()
    dependencies: tuple[str, ...] = ()
    dependents: tuple[str, ...] = ()
    impact: tuple[str, ...] = ()
    affected_files: tuple[str, ...] = ()
    message: str = ""
    modification_status: str = "NONE"

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-safe dict."""
        return {
            "status": self.status.value,
            "query": self.query,
            "resolved_module": self.resolved_module,
            "candidates": list(self.candidates),
            "dependencies": list(self.dependencies),
            "dependents": list(self.dependents),
            "impact": list(self.impact),
            "affected_files": list(self.affected_files),
            "message": self.message,
            "modification_status": self.modification_status,
        }

    def to_markdown(self) -> str:
        """Render the result as a conversational markdown response."""
        if self.status is not RepositoryImpactStatus.RESOLVED:
            lines = [
                "## Repository Impact Analysis",
                "",
                f"**Target:** could not be resolved ({self.status.value}).",
            ]
            if self.message:
                lines.append("")
                lines.append(self.message)
            if self.candidates:
                lines.append("")
                lines.append(
                    "**Candidate identifiers seen:** "
                    + ", ".join(f"`{c}`" for c in self.candidates)
                )
            lines.append("")
            lines.append("**Modification performed:** NONE")
            return "\n".join(lines)

        lines = [
            "## Repository Impact Analysis",
            "",
            f"**Target:** `{self.resolved_module}`",
            "",
            f"**Direct dependencies ({len(self.dependencies)}):** "
            + (", ".join(f"`{d}`" for d in self.dependencies) or "none"),
            f"**Direct dependents ({len(self.dependents)}):** "
            + (", ".join(f"`{d}`" for d in self.dependents) or "none"),
            f"**Transitive impact ({len(self.impact)}):** "
            + (", ".join(f"`{m}`" for m in self.impact) or "none"),
        ]
        if self.affected_files:
            lines.append("")
            lines.append("**Affected files:**")
            for path in self.affected_files:
                lines.append(f"- {path}")
        lines.append("")
        lines.append(f"**Interpretation:** {self.message}")
        lines.append("")
        lines.append("**Modification performed:** NONE")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Analyzer
# ---------------------------------------------------------------------------


class RepositoryImpactAnalyzer:
    """Deterministic, read-only repository impact analyzer.

    Reuses the existing :class:`RepositoryMap` capability; it defines no
    graph logic of its own.
    """

    def __init__(self, repo_root: Any | None = None) -> None:
        self._root = repo_root

    def analyze(self, query: str) -> RepositoryImpactResult:
        """Analyze a bounded repository impact question."""
        candidates = extract_target_candidates(query)
        if not candidates:
            return RepositoryImpactResult(
                status=RepositoryImpactStatus.UNRESOLVED,
                query=query,
                message=(
                    "No repository module identifier was found in the "
                    "request. Provide a dotted module name (e.g. "
                    "atlas.conversation.conversation_state)."
                ),
            )

        repo_map = self._build_map()
        known = {info.module for info in repo_map.modules}
        resolved = [c for c in candidates if c in known]

        if not resolved:
            return RepositoryImpactResult(
                status=RepositoryImpactStatus.UNRESOLVED,
                query=query,
                candidates=candidates,
                message=(
                    "The identifier(s) do not match any module in the "
                    "repository map. No impact information was produced."
                ),
            )

        unique = tuple(dict.fromkeys(resolved))
        if len(unique) > 1:
            return RepositoryImpactResult(
                status=RepositoryImpactStatus.AMBIGUOUS,
                query=query,
                candidates=unique,
                message=(
                    "Multiple repository targets were provided; refusing to "
                    "guess which one to analyze. Provide a single module."
                ),
            )

        module = unique[0]
        dependencies = tuple(repo_map.dependencies_of(module))
        dependents = tuple(repo_map.dependents_of(module))
        impact = tuple(sorted(repo_map.impact_set(module)))

        # Affected files: paths of everything that could be affected
        # (direct dependents + transitive impact), deterministically sorted.
        path_by_module = {info.module: info.path for info in repo_map.modules}
        affected_modules = sorted(set(dependents) | set(impact))
        affected_files = tuple(
            path_by_module[m] for m in affected_modules if path_by_module.get(m)
        )

        if affected_modules:
            message = (
                f"{len(dependents)} module(s) directly import "
                f"'{module}'; {len(impact)} module(s) are affected within "
                f"the repository map's transitive impact depth. (Empty "
                "results are reported honestly, not treated as errors.)"
            )
        else:
            message = (
                "No internal modules directly import this module and the "
                "transitive impact set is empty within the repository map's "
                "depth. This is a valid empty result, not an error."
            )

        return RepositoryImpactResult(
            status=RepositoryImpactStatus.RESOLVED,
            query=query,
            resolved_module=module,
            candidates=candidates,
            dependencies=dependencies,
            dependents=dependents,
            impact=impact,
            affected_files=affected_files,
            message=message,
        )

    def _build_map(self):
        """Build the repository map via the existing builder (lazy import)."""
        from atlas.research.repository_map import RepositoryMapBuilder

        root = self._root
        if root is None:
            from pathlib import Path

            root = Path.cwd()
        return RepositoryMapBuilder(root).build()
