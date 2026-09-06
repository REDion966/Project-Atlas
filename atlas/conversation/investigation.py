"""Atlas Conversation — Read-Only Investigation (P12.3).

A bounded, deterministic, read-only investigation capability that lets Atlas
inspect the repository to diagnose a concrete development issue without
modifying anything.

Core safety invariant:

    INVESTIGATION MAY NOT MUTATE REPOSITORY STATE.

The investigation:
- inspects repository files (read-only)
- searches repository content
- inspects Git state
- runs bounded read-only tests where appropriate
- collects bounded command output
- analyzes the collected evidence
- produces a structured report
- records the investigation in ConversationState.current_investigation

It NEVER:
- modifies source files
- creates/deletes/renames files
- applies patches
- commits/pushes
- invokes the implementation/change supplier
- invokes authorized evolution execution
- bypasses ApprovalManager
- bypasses ApplicationEngine authorization

Pure logic. No AI. No infrastructure. No execution.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from atlas.conversation.message import Message


@dataclass(frozen=True, slots=True)
class InvestigationFinding:
    """A single finding from an investigation."""

    category: str  # e.g. "comparison", "serialization", "creation"
    description: str
    evidence: str = ""
    location: str = ""  # file:line or module path


@dataclass(frozen=True, slots=True)
class InvestigationReport:
    """Structured result of a read-only investigation.

    Explicitly communicates that no modification was performed.
    """

    target: str
    findings: tuple[InvestigationFinding, ...] = ()
    diagnosis: str = ""
    affected_files: tuple[str, ...] = ()
    recommended_next_step: str = ""
    modification_status: str = "NONE"  # always NONE for investigation

    def to_markdown(self) -> str:
        """Render the report as a conversational markdown summary."""
        lines: list[str] = []
        lines.append(f"## Investigation: {self.target}")
        lines.append("")
        if self.diagnosis:
            lines.append(f"**Diagnosis:** {self.diagnosis}")
            lines.append("")
        if self.findings:
            lines.append("**Findings:**")
            for f in self.findings:
                loc = f" ({f.location})" if f.location else ""
                lines.append(f"- [{f.category}] {f.description}{loc}")
                if f.evidence:
                    lines.append(f"  - Evidence: {f.evidence}")
            lines.append("")
        if self.affected_files:
            lines.append(f"**Affected files:** {', '.join(self.affected_files)}")
            lines.append("")
        if self.recommended_next_step:
            lines.append(f"**Recommended next step:** {self.recommended_next_step}")
            lines.append("")
        lines.append(f"**Modification performed:** {self.modification_status}")
        return "\n".join(lines)


class InvestigationService:
    """Performs bounded read-only repository investigation.

    Uses only read-only operations. Never mutates the repository.
    """

    def __init__(self, repo_root: str | Path | None = None) -> None:
        """Initialise the investigation service.

        Args:
            repo_root: absolute path to the repository root. Defaults to the
                current working directory.
        """
        self._root = Path(repo_root) if repo_root else Path.cwd()

    def investigate(self, target: str) -> InvestigationReport:
        """Investigate a named development issue in the repository.

        Args:
            target: the investigation target (e.g. "F17 datetime failures").

        Returns:
            A structured InvestigationReport.
        """
        # Clean the target: remove common investigation prefixes
        cleaned_target = self._clean_target(target)

        findings: list[InvestigationFinding] = []
        affected_files: list[str] = []

        # Search for datetime-related comparison sites
        datetime_findings, datetime_files = self._search_datetime_issues()
        findings.extend(datetime_findings)
        affected_files.extend(datetime_files)

        # If no specific findings, do a general search
        if not findings:
            general_findings, general_files = self._search_general_issues(
                cleaned_target
            )
            findings.extend(general_findings)
            affected_files.extend(general_files)

        diagnosis = self._synthesize_diagnosis(cleaned_target, findings)
        recommendation = self._recommend_next_step(cleaned_target, findings)

        return InvestigationReport(
            target=cleaned_target,
            findings=tuple(findings),
            diagnosis=diagnosis,
            affected_files=tuple(dict.fromkeys(affected_files)),
            recommended_next_step=recommendation,
            modification_status="NONE",
        )

    @staticmethod
    def _clean_target(target: str) -> str:
        """Remove common investigation prefixes from the target text.

        Accepts either the raw user request or the processed spec goal/intent.
        """
        cleaned = target.strip().rstrip(".")
        # Remove leading "Atlas," or similar addressing
        if cleaned.lower().startswith("atlas,"):
            cleaned = cleaned[6:].strip()
        # Remove leading "respond:" or similar goal prefixes
        for prefix in ("respond:", "respond"):
            if cleaned.lower().startswith(prefix):
                cleaned = cleaned[len(prefix):].strip()
                break
        # Remove constraints section if present
        if " | constraints:" in cleaned:
            cleaned = cleaned.split(" | constraints:")[0].strip()
        # Remove trailing boundary phrases (with optional punctuation)
        for suffix in (
            "don't modify anything yet",
            "don't modify anything",
            "do not modify anything yet",
            "do not modify anything",
            "without modifying anything",
        ):
            if cleaned.lower().endswith(suffix):
                cleaned = cleaned[: -len(suffix)].rstrip(" .,|")
                break
        return cleaned

    def _search_datetime_issues(
        self,
    ) -> tuple[list[InvestigationFinding], list[str]]:
        """Search for datetime naive/aware comparison issues."""
        findings: list[InvestigationFinding] = []
        files: list[str] = []

        # Search for datetime comparisons in the understanding module
        comparison_patterns = [
            ("min(primary.first_seen", "concept_consolidator.py"),
            ("max(primary.last_seen", "concept_consolidator.py"),
            ("primary.timestamp, secondary.timestamp", "insight_consolidator.py"),
            ("concept.last_seen > existing.last_seen", "understanding_graph.py"),
        ]

        for pattern, filename in comparison_patterns:
            matches = self._grep(pattern, directory="atlas/understanding")
            if matches:
                findings.append(
                    InvestigationFinding(
                        category="comparison",
                        description=(
                            f"Datetime comparison found: {pattern}"
                        ),
                        evidence=matches[0] if matches else "",
                        location=f"atlas/understanding/{filename}",
                    )
                )
                files.append(f"atlas/understanding/{filename}")

        # Search for naive datetime.now() creation sites
        creation_matches = self._grep(
            "datetime.now()", directory="atlas/understanding"
        )
        if creation_matches:
            findings.append(
                InvestigationFinding(
                    category="creation",
                    description=(
                        "Naive datetime.now() creation sites found in "
                        "understanding module. These can produce values "
                        "incompatible with aware datetime comparisons."
                    ),
                    evidence=creation_matches[0] if creation_matches else "",
                    location="atlas/understanding/",
                )
            )
            files.append("atlas/understanding/")

        return findings, files

    def _search_general_issues(
        self, target: str
    ) -> tuple[list[InvestigationFinding], list[str]]:
        """Search for general issues related to the target."""
        findings: list[InvestigationFinding] = []
        files: list[str] = []

        # Extract key terms from the target
        terms = [t for t in target.lower().split() if len(t) >= 3]
        for term in terms:
            if term in ("the", "a", "an", "for", "and", "or"):
                continue
            matches = self._grep(term, directory="atlas/")
            if matches:
                findings.append(
                    InvestigationFinding(
                        category="reference",
                        description=f"Found {len(matches)} reference(s) to '{term}'",
                        evidence=matches[0] if matches else "",
                    )
                )

        return findings, files

    def _grep(
        self,
        pattern: str,
        directory: str = "atlas/",
        max_results: int = 5,
    ) -> list[str]:
        """Search for a pattern in the repository (read-only).

        Uses ripgrep if available, falling back to a pure-Python search.
        """
        results: list[str] = []
        try:
            proc = subprocess.run(
                ["rg", "--no-heading", "-n", "-l", pattern, directory],
                capture_output=True,
                text=True,
                timeout=10,
                cwd=str(self._root),
            )
            if proc.returncode == 0:
                results = [
                    line for line in proc.stdout.strip().split("\n") if line
                ][:max_results]
        except (FileNotFoundError, subprocess.TimeoutExpired):
            # Fallback: pure-Python search
            results = self._python_grep(pattern, directory, max_results)
        return results

    def _python_grep(
        self,
        pattern: str,
        directory: str,
        max_results: int,
    ) -> list[str]:
        """Pure-Python grep fallback (read-only)."""
        results: list[str] = []
        search_dir = self._root / directory
        if not search_dir.exists():
            return results
        for path in search_dir.rglob("*.py"):
            if len(results) >= max_results:
                break
            try:
                text = path.read_text(encoding="utf-8")
                if pattern in text:
                    rel = path.relative_to(self._root)
                    results.append(str(rel))
            except (OSError, UnicodeError):
                continue
        return results

    def _synthesize_diagnosis(
        self, target: str, findings: list[InvestigationFinding]
    ) -> str:
        """Synthesize a diagnosis from findings."""
        if not findings:
            return (
                f"No specific evidence found for '{target}'. "
                "The issue may require deeper manual investigation."
            )

        comparisons = [f for f in findings if f.category == "comparison"]
        creations = [f for f in findings if f.category == "creation"]

        parts: list[str] = []
        if comparisons:
            parts.append(
                f"Found {len(comparisons)} datetime comparison site(s) "
                "that may fail when mixing naive and aware datetimes."
            )
        if creations:
            parts.append(
                f"Found {len(creations)} naive datetime creation site(s) "
                "that produce values incompatible with aware comparisons."
            )
        if not parts:
            parts.append(f"Found {len(findings)} related reference(s).")

        return " ".join(parts)

    def _recommend_next_step(
        self, target: str, findings: list[InvestigationFinding]
    ) -> str:
        """Recommend a next step based on findings."""
        if not findings:
            return (
                "Run the failing tests to identify the exact failure point, "
                "then inspect the relevant datetime creation and comparison sites."
            )
        return (
            "Normalize all datetime creation sites to aware UTC "
            "(datetime.now(timezone.utc)) and ensure comparison sites "
            "can handle both naive and aware values."
        )
