"""Deterministic, evidence-grounded synthesis over an InvestigationReport (C3.3).

Pure logic. No AI, no network, no filesystem access, no mutation.

Transforms an already-produced read-only :class:`InvestigationReport` into a
deterministic prioritisation: which component the report's own evidence
supports reviewing first, and which concrete report evidence supports that
conclusion.

Design invariants
-----------------
* Deterministic and reproducible — the same report always yields the same
  synthesis (sorted, fixed weights, no randomness).
* Evidence-grounded — every conclusion cites actual report fields/findings;
  no evidence is invented.
* Bounded — deterministic caps on signals per component and rendered items.
* Fail-safe — when the evidence cannot support a ranking, it says so rather
  than inventing a reason.
* Read-only — ``modification_status`` is always ``"NONE"``; nothing is
  gathered, mutated, authorized, or executed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from atlas.conversation.investigation import InvestigationReport

#: Deterministic signal weights (fixed; documented for auditability).
_DEPENDENCY_WEIGHT: int = 3
_TEST_WEIGHT: int = 2
_REFERENCE_WEIGHT: int = 1

#: Bounds (deterministic caps).
_MAX_SIGNALS_PER_COMPONENT: int = 4
_MAX_RENDERED_RANKED: int = 3


@dataclass(frozen=True, slots=True)
class ComponentEvidence:
    """One component and the report evidence that supports ranking it."""

    component: str
    score: int
    signals: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-safe dict."""
        return {
            "component": self.component,
            "score": self.score,
            "signals": list(self.signals),
        }


@dataclass(frozen=True, slots=True)
class InvestigationSynthesis:
    """Deterministic synthesis derived from an InvestigationReport."""

    target: str
    finding_count: int
    component_count: int
    ranked_components: tuple[ComponentEvidence, ...] = ()
    recommended_focus: str | None = None
    recommended_reason: str = ""
    summary: str = ""
    evidence_basis: tuple[str, ...] = ()
    tied_components: tuple[str, ...] = ()
    insufficient_evidence: bool = False
    modification_status: str = "NONE"

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-safe dict."""
        return {
            "target": self.target,
            "finding_count": self.finding_count,
            "component_count": self.component_count,
            "ranked_components": [c.to_dict() for c in self.ranked_components],
            "recommended_focus": self.recommended_focus,
            "recommended_reason": self.recommended_reason,
            "summary": self.summary,
            "evidence_basis": list(self.evidence_basis),
            "tied_components": list(self.tied_components),
            "insufficient_evidence": self.insufficient_evidence,
            "modification_status": self.modification_status,
        }

    def to_markdown(self) -> str:
        """Render the synthesis as a conversational markdown report."""
        lines: list[str] = [
            f"## Investigation Synthesis: {self.target}",
            "",
            f"**Evidence base:** {self.finding_count} finding(s) across "
            f"{self.component_count} component(s)"
            + (
                f"; categories: {', '.join(self.evidence_basis)}"
                if self.evidence_basis
                else ""
            ),
            f"**Modification performed:** {self.modification_status}",
            "",
        ]

        lines.append("### Priority")
        if self.insufficient_evidence:
            lines.append(
                "**Review first:** insufficient evidence to prioritise a "
                "component."
            )
        else:
            lines.append(f"**Review first:** `{self.recommended_focus}`")
            if len(self.tied_components) > 1:
                others = [
                    c
                    for c in self.tied_components
                    if c != self.recommended_focus
                ]
                lines.append(
                    f"**Tied evidence:** {len(self.tied_components)} "
                    f"components share the top score "
                    f"({', '.join(others)})."
                )
        if self.recommended_reason:
            lines.append("")
            lines.append(f"**Why:** {self.recommended_reason}")

        focus = next(
            (
                c
                for c in self.ranked_components
                if c.component == self.recommended_focus
            ),
            None,
        )
        if focus is not None and focus.signals:
            lines.append("")
            lines.append("**Supporting evidence:**")
            for signal in focus.signals:
                lines.append(f"- {signal}")

        if self.ranked_components:
            lines.append("")
            lines.append("### Ranked components")
            for index, item in enumerate(
                self.ranked_components[:_MAX_RENDERED_RANKED], start=1
            ):
                lines.append(
                    f"{index}. `{item.component}` - evidence score "
                    f"{item.score}"
                )

        lines.append("")
        lines.append(
            "Deterministic synthesis over the existing investigation report. "
            "No new evidence was gathered and nothing was modified."
        )
        return "\n".join(lines)


class InvestigationSynthesizer:
    """Deterministic, read-only synthesizer over an InvestigationReport.

    Never gathers new evidence, never mutates, never calls a model. The
    conclusion is derived only from the report's existing structured fields.
    """

    def synthesize(self, report: InvestigationReport) -> InvestigationSynthesis:
        """Produce a deterministic synthesis from an investigation report."""
        target = str(getattr(report, "target", "") or "")
        components = tuple(getattr(report, "components", ()) or ())
        findings = tuple(getattr(report, "findings", ()) or ())

        # Index findings by category (order preserved for determinism).
        dependency_by_module: dict[str, list[str]] = {}
        test_findings: list[Any] = []
        reference_findings: list[Any] = []
        categories: set[str] = set()

        for finding in findings:
            category = str(getattr(finding, "category", "") or "")
            if category:
                categories.add(category)
            if category == "dependency":
                module = str(getattr(finding, "location", "") or "")
                description = str(getattr(finding, "description", "") or "")
                dependency_by_module.setdefault(module, []).append(description)
            elif category == "test":
                test_findings.append(finding)
            elif category == "reference":
                reference_findings.append(finding)

        ranked: list[ComponentEvidence] = []
        for component in components:
            ranked.append(
                self._score_component(
                    component,
                    dependency_by_module,
                    test_findings,
                    reference_findings,
                )
            )

        # Deterministic ordering: score desc, then component name asc.
        ranked.sort(key=lambda item: (-item.score, item.component))
        ranked_tuple = tuple(ranked)

        top = ranked_tuple[0] if ranked_tuple else None
        insufficient = top is None or top.score <= 0

        # Components sharing the top score (only meaningful when not
        # insufficient) — reported honestly instead of implying a unique win.
        tied: tuple[str, ...] = ()
        if top is not None and top.score > 0:
            tied = tuple(
                c.component for c in ranked_tuple if c.score == top.score
            )

        evidence_basis = tuple(sorted(categories))

        if insufficient:
            recommended_focus = None
            if not components and not findings:
                summary = (
                    f"No specific evidence found for '{target}'."
                )
                reason = (
                    "No components or findings were available to prioritise."
                )
            elif not components:
                reason = (
                    "The investigation produced findings but identified no "
                    "components to rank."
                )
                summary = (
                    f"Investigation of '{target}' produced {len(findings)} "
                    "finding(s) but no components."
                )
            else:
                reason = (
                    "The available evidence does not identify a component "
                    "with stronger support than the others."
                )
                summary = (
                    f"Investigation of '{target}' produced {len(findings)} "
                    f"finding(s) across {len(components)} component(s), but "
                    "the evidence does not support ranking one component "
                    "above another."
                )
        else:
            recommended_focus = top.component
            if len(tied) > 1:
                reason = (
                    f"{len(tied)} components share the strongest evidence "
                    f"(score {top.score}): {', '.join(tied)}. "
                    f"'{top.component}' is selected as a deterministic "
                    "(alphabetical) tie-break, not a unique evidence "
                    "advantage."
                )
                summary = (
                    f"Investigation of '{target}' produced {len(findings)} "
                    f"finding(s) across {len(components)} component(s). "
                    f"{len(tied)} components share the strongest evidence "
                    f"(score {top.score}); evidence supports reviewing "
                    f"'{top.component}' first (deterministic tie-break)."
                )
            else:
                if top.signals:
                    reason = (
                        f"'{top.component}' has the strongest combined "
                        f"evidence (score {top.score}) among the investigated "
                        "components, based on: " + "; ".join(top.signals)
                    )
                else:
                    reason = (
                        f"'{top.component}' has the strongest combined "
                        f"evidence (score {top.score})."
                    )
                summary = (
                    f"Investigation of '{target}' produced {len(findings)} "
                    f"finding(s) across {len(components)} component(s). "
                    f"Evidence supports reviewing '{top.component}' first "
                    f"(score {top.score})."
                )

        return InvestigationSynthesis(
            target=target,
            finding_count=len(findings),
            component_count=len(components),
            ranked_components=ranked_tuple,
            recommended_focus=recommended_focus,
            recommended_reason=reason,
            summary=summary,
            evidence_basis=evidence_basis,
            tied_components=tied,
            insufficient_evidence=insufficient,
            modification_status="NONE",
        )

    @staticmethod
    def _score_component(
        component: str,
        dependency_by_module: dict[str, list[str]],
        test_findings: list[Any],
        reference_findings: list[Any],
    ) -> ComponentEvidence:
        """Score one component from directly-attributable report evidence.

        The score counts EVERY attributable piece of evidence (so ranking is
        faithful), while the rendered ``signals`` are bounded to keep output
        small.
        """
        short_name = component.rsplit(".", 1)[-1]
        component_dir = "/".join(component.split(".")[:-1])

        score = 0
        signals: list[str] = []

        def _add_signal(text: str) -> None:
            if len(signals) < _MAX_SIGNALS_PER_COMPONENT:
                signals.append(text)

        # Architectural centrality: the component has outgoing dependencies.
        for description in dependency_by_module.get(component, ()):
            score += _DEPENDENCY_WEIGHT
            _add_signal(f'dependency evidence: "{description}"')

        # Test coverage: a test finding references the component's short name.
        for finding in test_findings:
            description = str(getattr(finding, "description", "") or "")
            if f"'{short_name}'" in description:
                score += _TEST_WEIGHT
                evidence = str(getattr(finding, "evidence", "") or "")
                cite = f" (e.g. {evidence})" if evidence else ""
                _add_signal(f'test evidence: "{description}"{cite}')

        # Implementation references: reference findings covering the
        # component's own directory.
        for finding in reference_findings:
            location = str(getattr(finding, "location", "") or "").rstrip("/")
            if location and location == component_dir:
                score += _REFERENCE_WEIGHT
                description = str(getattr(finding, "description", "") or "")
                _add_signal(f'implementation evidence: "{description}"')

        return ComponentEvidence(
            component=component,
            score=score,
            signals=tuple(signals),
        )
