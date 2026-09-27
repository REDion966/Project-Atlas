"""Atlas Conversation — Evidence-based gap analysis over an InvestigationReport.

A bounded, deterministic, read-only capability that consumes ONLY the
structured evidence of an already-produced :class:`InvestigationReport` (its
components and its ``reference`` / ``test`` / ``dependency`` findings) and
reports the concrete gaps that evidence demonstrates for a component the
investigation actually identified.

Design invariants
-----------------
* **Evidence-driven.** A gap is reported only when the report's own evidence
  shows the component is in scope but the expected evidence class is absent.
  The analysis gathers no new evidence and invents no repository fact.
* **Traceable.** Every gap retains :class:`EvidenceCitation` records — the exact
  report findings it rests on — so the evidence-to-gap relationship can be
  inspected.
* **Observation vs. interpretation.** Each gap separates the observed
  report-derived fact (``observation``) from the bounded inference
  (``interpretation``); uncertainty is never silently converted to certainty.
* **Honest when it cannot conclude.** When the report carries no findings, or
  no test evidence to assess coverage against, the result is marked
  ``insufficient_evidence`` instead of manufacturing a gap.
* **Read-only and model-independent.** No AI, no network, no execution, no
  repository mutation, no proposal, no authority. ``modification_status`` is
  always ``"NONE"``.

This is deliberately NOT the existing ``InvestigationSynthesizer`` (which ranks
components by evidence weight). It produces structured *gap* findings, not a
prioritisation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any

from atlas.conversation.investigation import InvestigationReport
from atlas.conversation.normalization import (
    canonicalize_surface,
    collapse_whitespace,
)


class GapCategory(str, Enum):
    """Bounded, evidence-anchored gap categories.

    Both are grounded in the report's own data: the component list plus the
    findings the investigation gathered for it.
    """

    #: A component in scope whose only evidence is directory-level reference
    #: findings — the investigation recorded no evidence that names it.
    UNCOVERED_COMPONENT = "uncovered_component"
    #: A non-test component in scope with component-level evidence but no test
    #: evidence (no ``test`` finding references it).
    UNTESTED_COMPONENT = "untested_component"


class GapSufficiency(str, Enum):
    """Whether a gap rests on component-level or only directory-level evidence."""

    SUFFICIENT = "sufficient"
    INSUFFICIENT = "insufficient"


@dataclass(frozen=True, slots=True)
class EvidenceCitation:
    """One report finding cited as the basis of a gap (traceability)."""

    category: str
    description: str
    location: str
    evidence: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "description": self.description,
            "location": self.location,
            "evidence": self.evidence,
        }


@dataclass(frozen=True, slots=True)
class ConcreteGap:
    """A single evidence-backed gap, traceable to the report findings."""

    gap_id: str
    category: GapCategory
    component: str
    observation: str
    interpretation: str
    sufficiency: GapSufficiency
    evidence: tuple[EvidenceCitation, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "gap_id": self.gap_id,
            "category": self.category.value,
            "component": self.component,
            "observation": self.observation,
            "interpretation": self.interpretation,
            "sufficiency": self.sufficiency.value,
            "evidence": [c.to_dict() for c in self.evidence],
        }


@dataclass(frozen=True, slots=True)
class GapAnalysisReport:
    """Structured, evidence-grounded gap analysis over one InvestigationReport."""

    target: str
    objective: str
    gaps: tuple[ConcreteGap, ...] = ()
    insufficient_evidence: bool = False
    summary: str = ""
    evidence_basis: tuple[str, ...] = ()
    finding_count: int = 0
    component_count: int = 0
    modification_status: str = "NONE"

    def to_dict(self) -> dict[str, Any]:
        return {
            "target": self.target,
            "objective": self.objective,
            "gaps": [g.to_dict() for g in self.gaps],
            "gap_count": len(self.gaps),
            "insufficient_evidence": self.insufficient_evidence,
            "summary": self.summary,
            "evidence_basis": list(self.evidence_basis),
            "finding_count": self.finding_count,
            "component_count": self.component_count,
            "modification_status": self.modification_status,
        }

    def to_markdown(self) -> str:
        """Render the analysis as a conversational markdown report."""
        lines: list[str] = [f"## Evidence Gap Analysis: {self.target}", ""]

        basis = (
            f"; categories: {', '.join(self.evidence_basis)}"
            if self.evidence_basis
            else ""
        )
        lines.append(
            f"**Evidence base:** {self.finding_count} finding(s) across "
            f"{self.component_count} component(s){basis}."
        )
        lines.append("")

        if self.insufficient_evidence:
            lines.append(f"**Result:** {self.summary}")
        elif not self.gaps:
            lines.append("**Concrete gaps:** none demonstrated by this evidence.")
            lines.append("")
            lines.append(self.summary)
        else:
            lines.append(f"**Concrete gaps ({len(self.gaps)}):**")
            for index, gap in enumerate(self.gaps, start=1):
                lines.append(
                    f"{index}. **[{gap.category.value}]** `{gap.component}`"
                )
                lines.append(f"   - Observed: {gap.observation}")
                lines.append(f"   - Gap: {gap.interpretation}")
                for citation in gap.evidence:
                    loc = f" ({citation.location})" if citation.location else ""
                    lines.append(
                        f"   - Evidence [{citation.category}]: "
                        f"{citation.description}{loc}"
                    )

        lines.append("")
        lines.append(f"**Modification performed:** {self.modification_status}")
        lines.append(
            "Deterministic analysis over the existing investigation report. "
            "No new evidence was gathered and nothing was modified."
        )
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Bounded conversational recognition
#
# A gap-analysis request is recognized ONLY when it references the retained
# investigation findings/result by a bounded multi-word phrase AND carries an
# analysis cue. This is a recognizer for the conversation layer — it does not
# extend the reference resolver's vocabulary and does not alter any existing
# classification.
# ---------------------------------------------------------------------------

#: The reference phrase must name the RETAINED findings/result as a standalone
#: referent: a trailing "of" qualifier ("the findings of the audit") names a
#: fresh object, so it is deliberately NOT matched and keeps its existing route.
_FINDINGS_REFERENCE_RE = re.compile(
    r"\b(?:the investigation findings|the findings|what you found"
    r"|what did you find|what you just found)\b(?!\s+of\b)"
)

_ANALYSIS_CUE_RE = re.compile(
    r"\b(?:analy[sz]e|analy[sz]ing|analysis|identify|assess|assessment"
    r"|determine|gap|gaps|missing|insufficient|limitation|limitations"
    r"|weakness|weaknesses|coverage)\b"
)


def is_evidence_gap_analysis_request(text: str) -> bool:
    """True when ``text`` is a bounded request to analyze retained findings.

    Deterministic and bounded: the turn must reference the retained
    findings/result by one of a small enumerated multi-word phrase AND carry an
    analysis cue. A generic "Analyze <subject>" turn — including "the findings
    of X" — is never matched.
    """
    if not isinstance(text, str) or not text.strip():
        return False
    normalized = collapse_whitespace(canonicalize_surface(text)).lower()
    if _FINDINGS_REFERENCE_RE.search(normalized) is None:
        return False
    return _ANALYSIS_CUE_RE.search(normalized) is not None


# ---------------------------------------------------------------------------
# Analyzer
# ---------------------------------------------------------------------------

_TEST_FINDING_RE = re.compile(r"referencing '([^']+)'")


class EvidenceGapAnalyzer:
    """Deterministic, read-only evidence-gap analysis over an InvestigationReport.

    Never gathers new evidence, never mutates anything, never calls a model.
    """

    def analyze(self, report: InvestigationReport) -> GapAnalysisReport:
        """Analyze a report's own evidence for concrete, traceable gaps."""
        target = str(getattr(report, "target", "") or "")
        objective = str(getattr(report, "objective", "") or "")
        components = tuple(getattr(report, "components", ()) or ())
        findings = tuple(getattr(report, "findings", ()) or ())

        evidence_basis = tuple(sorted({f.category for f in findings if f.category}))
        base = {
            "target": target,
            "objective": objective,
            "evidence_basis": evidence_basis,
            "finding_count": len(findings),
            "component_count": len(components),
        }

        if not findings and not components:
            return GapAnalysisReport(
                **base,
                gaps=(),
                insufficient_evidence=True,
                summary=(
                    "the report carries no findings or components, so no gap "
                    "analysis is possible."
                ),
            )

        test_findings = tuple(f for f in findings if f.category == "test")
        if not test_findings:
            # No test evidence was gathered, so test coverage cannot be assessed
            # and an "untested" conclusion would be an evidence blind spot
            # rather than a demonstrated gap.
            return GapAnalysisReport(
                **base,
                gaps=(),
                insufficient_evidence=True,
                summary=(
                    "the report carries no test evidence, so test-coverage gaps "
                    "cannot be distinguished from an evidence blind spot."
                ),
            )

        test_names = self._referenced_names(test_findings)
        dep_locations = {f.location for f in findings if f.category == "dependency"}
        ref_dirs = {
            str(f.location).rstrip("/") for f in findings if f.category == "reference"
        }

        gaps: list[ConcreteGap] = []
        for component in components:
            component = str(component)
            short = component.rsplit(".", 1)[-1]
            directory = "/".join(component.split(".")[:-1])

            has_test = short in test_names
            has_dependency = component in dep_locations
            has_reference = directory in ref_dirs

            if has_test:
                continue
            if component.startswith("tests.") or short.startswith("test_"):
                # A test module is not itself expected to carry test evidence.
                continue

            if not has_dependency and not has_reference:
                citations = self._component_citations(component, directory, findings)
                gap = ConcreteGap(
                    gap_id=f"GAP-{len(gaps) + 1:04d}",
                    category=GapCategory.UNCOVERED_COMPONENT,
                    component=component,
                    observation=(
                        f"the investigation identified '{component}' as in scope, "
                        f"but recorded no finding that names it and no "
                        f"directory-level reference evidence for '{directory or '.'}'."
                    ),
                    interpretation=(
                        "no component-level evidence was established for this "
                        "component by the investigation."
                    ),
                    sufficiency=GapSufficiency.INSUFFICIENT,
                    evidence=citations,
                )
            else:
                citations = self._component_citations(
                    component, directory, findings
                )
                gap = ConcreteGap(
                    gap_id=f"GAP-{len(gaps) + 1:04d}",
                    category=GapCategory.UNTESTED_COMPONENT,
                    component=component,
                    observation=(
                        f"the investigation identified '{component}' and found "
                        f"implementation evidence for it, but no test finding "
                        f"references '{short}'."
                    ),
                    interpretation=(
                        f"no test evidence was found for this component by the "
                        f"investigation (test files referencing '{short}')."
                    ),
                    sufficiency=GapSufficiency.SUFFICIENT,
                    evidence=citations,
                )
            gaps.append(gap)

        if gaps:
            summary = (
                f"{len(gaps)} concrete evidence-backed gap(s) identified from "
                f"{len(findings)} finding(s) across {len(components)} component(s)."
            )
        else:
            summary = (
                "No concrete evidence-backed gaps were demonstrated: every "
                "non-test component the investigation identified carries test "
                "evidence and directory-level implementation evidence."
            )

        return GapAnalysisReport(
            **base,
            gaps=tuple(gaps),
            insufficient_evidence=False,
            summary=summary,
        )

    @staticmethod
    def _referenced_names(test_findings: tuple[Any, ...]) -> set[str]:
        """Extract the quoted short names from ``test`` finding descriptions."""
        names: set[str] = set()
        for finding in test_findings:
            match = _TEST_FINDING_RE.search(str(getattr(finding, "description", "")))
            if match:
                names.add(match.group(1))
        return names

    @staticmethod
    def _component_citations(
        component: str, directory: str, findings: tuple[Any, ...]
    ) -> tuple[EvidenceCitation, ...]:
        """Cite the findings that establish the component's own evidence."""
        citations: list[EvidenceCitation] = []
        for finding in findings:
            category = str(getattr(finding, "category", ""))
            location = str(getattr(finding, "location", ""))
            if category == "dependency" and location == component:
                citations.append(EvidenceGapAnalyzer._cite(finding))
            elif category == "reference" and location.rstrip("/") == directory:
                citations.append(EvidenceGapAnalyzer._cite(finding))
        return tuple(citations)

    @staticmethod
    def _cite(finding: Any) -> EvidenceCitation:
        return EvidenceCitation(
            category=str(getattr(finding, "category", "")),
            description=str(getattr(finding, "description", "")),
            location=str(getattr(finding, "location", "")),
            evidence=str(getattr(finding, "evidence", "")),
        )
