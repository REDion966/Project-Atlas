"""Atlas Research — External Repository Analysis (evidence-driven intelligence).

Deterministic, model-free structural analysis of an ALREADY-ACQUIRED external
repository (see :mod:`atlas.research.sources.github`), plus a structured
Atlas-vs-external comparison and a bounded development-evidence hand-off.

It reuses the EXISTING repository intelligence — :class:`RepositoryMap` /
``RepositoryMapBuilder`` (modules, imports, symbols, deterministic
``find_symbol`` / ``important_symbols`` / ``context_for``) — over a disposable
temporary tree; it does NOT create a second repository map.

Trust boundary (mandatory):

* external code is DATA: it is written to a temp tree and PARSED only — never
  imported, executed, installed, or evaluated;
* every finding is ``validation_status="unvalidated"`` — raw external structure
  is NOT trusted Atlas knowledge;
* the comparison is ANALYSIS, not authorization: it can inform a
  :class:`DevelopmentNeed` as EVIDENCE, but it never approves, promotes,
  activates, or bypasses the existing governance path.

Pure over the acquired data. No AI, no kernel, no storage.
"""

from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Sequence

from atlas.research.repository_map import RepositoryMap, RepositoryMapBuilder
from atlas.research.sources.github import safe_repository_path

# Bounds (deterministic).
MAX_ANALYSIS_MODULES: int = 2000
MAX_RELEVANT_SYMBOLS: int = 40
MAX_FINDINGS: int = 60
MAX_SIGNATURE_CHARS: int = 200
MAX_EVIDENCE_ITEMS: int = 20
MAX_FILES_TO_WRITE: int = 400

#: Deterministic mechanism vocabulary: a bounded token -> "appears to do" phrase.
MECHANISM_TOKENS: tuple[tuple[str, str], ...] = (
    ("registry", "maintains a registry of providers/handlers"),
    ("provider", "exposes a provider abstraction"),
    ("adapter", "normalizes via an adapter boundary"),
    ("planner", "plans work before execution"),
    ("dispatcher", "dispatches/routes work"),
    ("router", "routes requests to a handler"),
    ("executor", "executes a bounded unit of work"),
    ("sandbox", "isolates execution from the host"),
    ("verifier", "verifies results before acceptance"),
    ("verification", "verifies results before acceptance"),
    ("policy", "enforces a policy/authorization boundary"),
    ("plugin", "supports plugin/extension points"),
    ("session", "manages session/state"),
    ("cache", "caches results"),
    ("queue", "queues or schedules work"),
    ("graph", "represents structure as a graph"),
    ("context", "assembles bounded context"),
    ("store", "persists data"),
    ("memory", "manages memory/knowledge"),
    ("client", "wraps an external client"),
)

_ENTRY_MODULE_NAMES: frozenset[str] = frozenset(
    {"main", "__main__", "cli", "manage", "run", "app"}
)


class ComparisonVerdict(str, Enum):
    """Deterministic, evidence-only classification of an external mechanism."""

    ALREADY_SUPPORTED = "already_supported"
    PARTIALLY_SUPPORTED = "partially_supported"
    POTENTIAL_MECHANISM = "potential_mechanism"
    CAPABILITY_GAP = "capability_gap"
    ARCHITECTURAL_MISMATCH = "architectural_mismatch"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    NOT_APPLICABLE = "not_applicable"


@dataclass(frozen=True, slots=True)
class RepositoryStructure:
    """Bounded structural summary of an external repository."""

    packages: tuple[str, ...] = ()
    entry_points: tuple[str, ...] = ()
    module_count: int = 0
    symbol_count: int = 0
    edge_count: int = 0
    language_counts: tuple[tuple[str, int], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "packages": list(self.packages),
            "entry_points": list(self.entry_points),
            "module_count": self.module_count,
            "symbol_count": self.symbol_count,
            "edge_count": self.edge_count,
            "language_counts": [list(x) for x in self.language_counts],
        }


@dataclass(frozen=True, slots=True)
class ExternalRepositoryAnalysis:
    """Read-only analysis of one acquired external repository."""

    ok: bool
    repository: str = ""
    ref: str = ""
    structure: RepositoryStructure = field(default_factory=RepositoryStructure)
    relevant: tuple[dict[str, Any], ...] = ()
    repository_map: RepositoryMap | None = None
    errors: tuple[str, ...] = ()
    provenance: dict[str, Any] = field(default_factory=dict)
    limitations: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "repository": self.repository,
            "ref": self.ref,
            "structure": self.structure.to_dict(),
            "relevant": [dict(item) for item in self.relevant],
            "errors": list(self.errors),
            "provenance": dict(self.provenance),
            "limitations": list(self.limitations),
        }


@dataclass(frozen=True, slots=True)
class MechanismFinding:
    """One evidence-bound external mechanism observation (never authorization)."""

    repository: str
    location: str
    mechanism: str
    kind: str
    appears_to_do: str
    relevance_reason: str
    atlas_area: str
    verdict: ComparisonVerdict
    confidence: float
    validation_status: str = "unvalidated"
    evidence: tuple[dict[str, Any], ...] = ()
    integration: str = ""
    risks: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "repository": self.repository,
            "location": self.location,
            "mechanism": self.mechanism,
            "kind": self.kind,
            "appears_to_do": self.appears_to_do,
            "relevance_reason": self.relevance_reason,
            "atlas_area": self.atlas_area,
            "verdict": self.verdict.value,
            "confidence": self.confidence,
            "validation_status": self.validation_status,
            "evidence": [dict(e) for e in self.evidence],
            "integration": self.integration,
            "risks": self.risks,
        }


@dataclass(frozen=True, slots=True)
class RepositoryComparison:
    """Structured Atlas-vs-external comparison (analysis only)."""

    repository: str
    ref: str = ""
    findings: tuple[MechanismFinding, ...] = ()
    verdict_counts: tuple[tuple[str, int], ...] = ()
    limitations: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "repository": self.repository,
            "ref": self.ref,
            "verdict_counts": [list(x) for x in self.verdict_counts],
            "findings": [f.to_dict() for f in self.findings],
            "limitations": list(self.limitations),
        }


# ---------------------------------------------------------------------------
# Structural analysis
# ---------------------------------------------------------------------------


def analyze_acquired_repository(
    acquired: Any,
    *,
    workdir: str | None = None,
    keywords: Sequence[str] = (),
) -> ExternalRepositoryAnalysis:
    """Parse an acquired repository into a bounded structural analysis.

    Writes the acquired DATA files into a disposable temporary tree, builds the
    existing :class:`RepositoryMap` over it, derives a structural summary and a
    deterministic relevance slice, then removes the tree. The external code is
    never imported or executed.
    """
    files = tuple(getattr(acquired, "files", ()) or ())
    owner = str(getattr(acquired, "owner", "") or "")
    name = str(getattr(acquired, "name", "") or "")
    ref = str(getattr(acquired, "ref", "") or "")
    repository = f"{owner}/{name}".strip("/")
    provenance = dict(getattr(acquired, "provenance", {}) or {})
    if not files:
        return ExternalRepositoryAnalysis(
            ok=False,
            repository=repository,
            ref=ref,
            errors=tuple(getattr(acquired, "errors", ()) or ("no files acquired",)),
            provenance=provenance,
            limitations=("No repository content was available to analyse.",),
        )

    root = Path(tempfile.mkdtemp(prefix="atlas-external-", dir=workdir))
    errors: list[str] = []
    written = 0
    try:
        for path, text in files[:MAX_FILES_TO_WRITE]:
            safe = safe_repository_path(path)
            if safe is None:
                errors.append(f"{path}: refused (unsafe path)")
                continue
            target = root / safe
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8", errors="replace")
            written += 1
        repository_map = RepositoryMapBuilder(
            root, max_modules=MAX_ANALYSIS_MODULES
        ).build()
    except Exception as exc:  # fail-closed
        shutil.rmtree(root, ignore_errors=True)
        return ExternalRepositoryAnalysis(
            ok=False,
            repository=repository,
            ref=ref,
            errors=(f"analysis failed ({type(exc).__name__})",),
            provenance=provenance,
        )
    finally:
        # The external tree is disposable; nothing survives the analysis.
        shutil.rmtree(root, ignore_errors=True)

    structure = _structure_of(repository_map)
    relevant = rank_relevant_symbols(repository_map, keywords)
    limitations = (
        "Static structural analysis only: control flow, data flow, runtime "
        "behaviour, and semantics are NOT represented.",
        "External content is DATA and is unvalidated; nothing was executed.",
    )
    if getattr(acquired, "truncated", False):
        limitations += ("Acquisition was truncated by the configured bounds.",)
    return ExternalRepositoryAnalysis(
        ok=True,
        repository=repository,
        ref=ref,
        structure=structure,
        relevant=relevant,
        repository_map=repository_map,
        errors=tuple(errors[:100]),
        provenance=provenance,
        limitations=limitations,
    )


def _structure_of(repository_map: RepositoryMap) -> RepositoryStructure:
    packages = tuple(
        info.module for info in repository_map.modules if info.is_package
    )
    entry_points = tuple(
        sorted(
            info.module
            for info in repository_map.modules
            if not info.is_package and _looks_like_entry(info.module)
        )
    )
    language_counts: dict[str, int] = {}
    for info in repository_map.modules:
        language_counts[info.language or "unknown"] = (
            language_counts.get(info.language or "unknown", 0) + 1
        )
    return RepositoryStructure(
        packages=packages,
        entry_points=entry_points[:20],
        module_count=repository_map.module_count(),
        symbol_count=repository_map.symbol_count(),
        edge_count=repository_map.edge_count(),
        language_counts=tuple(sorted(language_counts.items())),
    )


def _looks_like_entry(module: str) -> bool:
    leaf = module.rsplit(".", 1)[-1]
    return leaf in _ENTRY_MODULE_NAMES


# ---------------------------------------------------------------------------
# Relevance (deterministic; reuses symbol intelligence)
# ---------------------------------------------------------------------------


def rank_relevant_symbols(
    repository_map: RepositoryMap,
    keywords: Sequence[str],
    limit: int = MAX_RELEVANT_SYMBOLS,
) -> tuple[dict[str, Any], ...]:
    """Deterministically rank repository symbols relevant to ``keywords``.

    Reuses the existing ``find_symbol`` / ``important_symbols`` /
    ``context_for`` queries. With no keywords it returns the bounded importance
    slice. Never semantic; never a model.
    """
    terms = _normalise(keywords)
    scored: dict[str, dict[str, Any]] = {}

    def _add(symbol: Any, matched: list[str]) -> None:
        qualified = str(getattr(symbol, "qualified", ""))
        if not qualified:
            return
        entry = scored.get(qualified)
        if entry is None:
            scored[qualified] = {
                "qualified": qualified,
                "name": str(getattr(symbol, "name", "")),
                "module": str(getattr(symbol, "module", "")),
                "kind": getattr(getattr(symbol, "kind", None), "value", ""),
                "signature": str(getattr(symbol, "signature", ""))[:MAX_SIGNATURE_CHARS],
                "references": int(getattr(symbol, "references", 0) or 0),
                "matched_keywords": list(matched),
            }
        else:
            for term in matched:
                if term not in entry["matched_keywords"]:
                    entry["matched_keywords"].append(term)

    if terms:
        for term in terms:
            # Deterministic, case-insensitive lexical match over the existing
            # symbol index (name / qualified / module), plus the indexed modules.
            for symbol in repository_map.symbols:
                name = str(getattr(symbol, "name", "")).lower()
                qualified = str(getattr(symbol, "qualified", "")).lower()
                module = str(getattr(symbol, "module", "")).lower()
                if term in name or term in qualified or term in module:
                    _add(symbol, [term])
            modules = {
                info.module
                for info in repository_map.modules
                if term in info.module.lower()
            }
            for symbol in repository_map.context_for(modules, max_symbols=limit):
                _add(symbol, [term])
    else:
        for symbol in repository_map.important_symbols(limit):
            _add(symbol, [])

    ranked = sorted(
        scored.values(),
        key=lambda item: (
            -len(item["matched_keywords"]),
            -item["references"],
            item["qualified"],
        ),
    )
    return tuple(ranked[: max(1, limit)])


def _normalise(values: Sequence[str]) -> tuple[str, ...]:
    out: list[str] = []
    for value in values or ():
        if isinstance(value, str):
            text = value.strip().lower()
            if text and text not in out:
                out.append(text)
    return tuple(out[:32])


# ---------------------------------------------------------------------------
# Atlas comparison
# ---------------------------------------------------------------------------


def compare_with_atlas(
    analysis: ExternalRepositoryAnalysis,
    *,
    atlas_capability_names: Sequence[str] = (),
    atlas_symbol_names: Sequence[str] = (),
    atlas_packages: Sequence[str] = (),
    keywords: Sequence[str] = (),
) -> RepositoryComparison:
    """Compare external findings against Atlas evidence (analysis only).

    Deterministic and evidence-only: it never claims Atlas lacks or has a
    capability without evidence, and every finding is explicitly unvalidated.
    """
    if not analysis.ok:
        return RepositoryComparison(
            repository=analysis.repository,
            ref=analysis.ref,
            limitations=("No analysis is available to compare.",),
        )

    capabilities = {c.lower() for c in atlas_capability_names if isinstance(c, str)}
    a_symbols = {s.lower() for s in atlas_symbol_names if isinstance(s, str)}
    packages = {p.lower() for p in atlas_packages if isinstance(p, str)}
    terms = _normalise(keywords)
    repository = analysis.repository

    findings: list[MechanismFinding] = []
    seen: set[str] = set()

    for item in analysis.relevant:
        qualified = str(item.get("qualified", ""))
        if not qualified or qualified in seen:
            continue
        seen.add(qualified)
        name = str(item.get("name", "")).lower()
        module = str(item.get("module", ""))
        matched = tuple(item.get("matched_keywords") or ())
        verdict, reason, area = _classify_relevance(
            name, module, matched, capabilities, a_symbols, packages
        )
        token_phrase = _mechanism_phrase(name, module)
        findings.append(
            MechanismFinding(
                repository=repository,
                location=qualified,
                mechanism=str(item.get("name", "")),
                kind=str(item.get("kind", "")),
                appears_to_do=token_phrase
                or f"defines {item.get('kind', 'symbol')} '{item.get('name', '')}'",
                relevance_reason=reason,
                atlas_area=area,
                verdict=verdict,
                confidence=_confidence(verdict, matched),
                evidence=(
                    {
                        "repository": repository,
                        "ref": analysis.ref,
                        "location": qualified,
                        "signature": item.get("signature", ""),
                        "matched_keywords": list(matched),
                        "provenance": dict(analysis.provenance),
                    },
                ),
                integration=(
                    "Requires evidence validation, then the existing governed "
                    "development path (sandbox → verify → OWNER)."
                ),
                risks=(
                    "External code is unvalidated and must never be executed or "
                    "promoted without the existing governance."
                ),
            )
        )
        if len(findings) >= MAX_FINDINGS:
            break

    counts: dict[str, int] = {}
    for finding in findings:
        counts[finding.verdict.value] = counts.get(finding.verdict.value, 0) + 1

    limitations = list(analysis.limitations)
    if not findings:
        limitations.append(
            "No external symbol matched the provided keywords/gap; the result "
            "is INSUFFICIENT_EVIDENCE rather than a claim."
        )
    return RepositoryComparison(
        repository=repository,
        ref=analysis.ref,
        findings=tuple(findings),
        verdict_counts=tuple(sorted(counts.items())),
        limitations=tuple(limitations),
    )


def _classify_relevance(
    name: str,
    module: str,
    matched: Sequence[str],
    capabilities: set[str],
    atlas_symbols: set[str],
    atlas_packages: set[str],
) -> tuple[ComparisonVerdict, str, str]:
    if not matched:
        return (
            ComparisonVerdict.POTENTIAL_MECHANISM,
            "Structurally prominent symbol (bounded importance ranking).",
            _atlas_area(name, module),
        )
    if name in capabilities or any(
        term and (term in c or c.endswith("." + term)) for term in matched for c in capabilities
    ):
        return (
            ComparisonVerdict.ALREADY_SUPPORTED,
            f"Atlas already registers a capability matching {sorted(matched)}.",
            "capability_registry",
        )
    if name in atlas_symbols or any(
        term and term in symbol for term in matched for symbol in atlas_symbols
    ):
        return (
            ComparisonVerdict.ALREADY_SUPPORTED,
            f"Atlas already defines a symbol matching {sorted(matched)}.",
            "repository_map",
        )
    if any(term and any(term in pkg for pkg in atlas_packages) for term in matched):
        return (
            ComparisonVerdict.PARTIALLY_SUPPORTED,
            f"An Atlas package area relates to {sorted(matched)}; equivalence is unproven.",
            "architecture_model",
        )
    return (
        ComparisonVerdict.CAPABILITY_GAP,
        f"No Atlas capability/symbol/package evidence matches {sorted(matched)}.",
        _atlas_area(name, module),
    )


def _atlas_area(name: str, module: str) -> str:
    for token, _phrase in MECHANISM_TOKENS:
        if token in name or token in module.lower():
            return f"atlas.{token}"
    return "unmapped"


def _mechanism_phrase(name: str, module: str) -> str:
    lowered = f"{name} {module}".lower()
    for token, phrase in MECHANISM_TOKENS:
        if token in lowered:
            return phrase
    return ""


def _confidence(verdict: ComparisonVerdict, matched: Sequence[str]) -> float:
    if verdict in (ComparisonVerdict.ALREADY_SUPPORTED, ComparisonVerdict.CAPABILITY_GAP):
        return min(0.9, 0.5 + 0.1 * len(matched))
    if verdict is ComparisonVerdict.PARTIALLY_SUPPORTED:
        return 0.5
    return 0.4


# ---------------------------------------------------------------------------
# Development-pipeline hand-off (EVIDENCE only — never authorization)
# ---------------------------------------------------------------------------


def development_evidence(
    analysis: ExternalRepositoryAnalysis,
    comparison: RepositoryComparison,
    *,
    request: str = "",
) -> dict[str, Any]:
    """Bounded EVIDENCE metadata for the EXISTING development pipeline.

    Returns a plain dict suitable for ``Atlas.run_development_driver(request,
    metadata=...)``. It contains ONLY evidence/context (provenance, findings,
    gaps) — never ``scaffold``/``code_changes`` — so it informs the existing gap
    assessment and cycle but cannot author, approve, or promote anything.
    """
    gaps = [
        f.to_dict()
        for f in comparison.findings
        if f.verdict is ComparisonVerdict.CAPABILITY_GAP
    ][:MAX_EVIDENCE_ITEMS]
    sources = tuple(
        str(url)
        for url in (
            analysis.provenance.get("target"),
        )
        if url
    )
    return {
        "external_research": {
            "request": (request or "")[:400],
            "repository": comparison.repository,
            "ref": comparison.ref,
            "structure": analysis.structure.to_dict(),
            "verdict_counts": [list(x) for x in comparison.verdict_counts],
            "gap_findings": gaps,
            "provenance": dict(analysis.provenance),
            "validation_status": "unvalidated",
        },
        # Only evidence sources — never scaffold/code_changes.
        "sources": sources,
    }
