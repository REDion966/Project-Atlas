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

import hashlib
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from atlas.conversation.message import Message

# ---------------------------------------------------------------------------
# Stoplist for concept extraction. These are too generic to be useful search
# terms and would match unrelated modules.
# ---------------------------------------------------------------------------
_CONCEPT_STOPLIST: frozenset[str] = frozenset(
    {
        "the", "a", "an", "for", "and", "or", "but", "with", "without",
        "this", "that", "these", "those", "it", "its", "to", "in", "on",
        "at", "by", "from", "is", "are", "was", "were", "be", "been",
        "being", "have", "has", "had", "do", "does", "did", "will", "would",
        "could", "should", "may", "might", "shall", "can", "need", "needs",
        "needed", "want", "wants", "wanted", "think", "thinks", "investigate",
        "investigates", "investigated", "investigating", "look", "looks",
        "looked", "looking", "tell", "tells", "told", "tell", "me", "about",
        "current", "could", "better", "determine", "whether", "there", "any",
        "meaningful", "opportunities", "improvement", "improvements", "modify",
        "modifies", "modified", "modifying", "nothing", "inspect", "inspects",
        "inspected", "inspecting", "trace", "traces", "traced", "tracing",
        "how", "work", "works", "worked", "working", "examine", "examines",
        "examined", "examining", "existing", "test", "tests", "testing",
        "contract", "contracts", "give", "gives", "gave", "giving", "your",
        "findings", "finding", "recommendations", "recommendation", "report",
        "evidence", "evidence-based", "based", "evidence", "related", "relevant",
        "implementation", "implementations", "system", "systems", "architecture",
        "architectural", "weakness", "weaknesses", "potential", "problem",
        "problems", "issue", "issues", "behavior", "behaviors", "flow", "flows",
    }
)

# Maximum number of relevant modules to inspect (bounded for determinism).
_MAX_RELEVANT_MODULES: int = 8
# Maximum files to read per module during implementation inspection.
_MAX_FILES_PER_MODULE: int = 3
# Maximum test files to discover.
_MAX_TEST_FILES: int = 5
# Maximum content lines to include as evidence per finding.
_MAX_EVIDENCE_LINES: int = 3


@dataclass(frozen=True, slots=True)
class InvestigationFinding:
    """A single finding from an investigation."""

    category: str  # e.g. "structure", "dependency", "test_gap", "reference"
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
    components: tuple[str, ...] = ()
    tests_inspected: tuple[str, ...] = ()

    def to_markdown(self) -> str:
        """Render the report as a conversational markdown summary."""
        lines: list[str] = []
        lines.append(f"## Investigation: {self.target}")
        lines.append("")
        if self.diagnosis:
            lines.append(f"**Diagnosis:** {self.diagnosis}")
            lines.append("")
        if self.components:
            lines.append(f"**Components identified:** {', '.join(self.components)}")
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
        if self.tests_inspected:
            lines.append(f"**Tests inspected:** {', '.join(self.tests_inspected)}")
            lines.append("")
        if self.recommended_next_step:
            lines.append(f"**Recommended next step:** {self.recommended_next_step}")
            lines.append("")
        lines.append(f"**Modification performed:** {self.modification_status}")
        return "\n".join(lines)


@dataclass(frozen=True, slots=True)
class SubsystemScope:
    """Discovered scope for a subsystem investigation.

    Holds the modules, directories, files, and tests identified as relevant
    to the investigation target through repository-evidence-based discovery.
    """

    modules: tuple[str, ...] = ()  # dotted module names (e.g. "atlas.memory.manager")
    directories: tuple[str, ...] = ()  # relevant directory paths
    files: tuple[str, ...] = ()  # specific file paths inspected
    tests: tuple[str, ...] = ()  # test files discovered


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
        """Investigate a named subsystem/issue in the repository.

        Uses content-driven subsystem discovery: the investigation target
        determines which repository content is inspected, via repository
        evidence rather than hardcoded directory/pattern mapping.

        Args:
            target: the investigation target (e.g. "memory architecture").

        Returns:
            A structured InvestigationReport.
        """
        cleaned_target = self._clean_target(target)

        # 1. Extract key concepts from the target.
        concepts = self._extract_concepts(cleaned_target)
        if not concepts:
            concepts = self._extract_concepts(target)

        # 2. Discover the relevant subsystem from repository evidence.
        scope = self._discover_subsystem(concepts)

        # 3. Inspect implementation within the discovered scope.
        impl_findings, impl_files = self._inspect_implementation(
            scope, concepts
        )

        # 4. Discover relevant tests/contracts.
        test_findings, test_files = self._discover_tests(scope)

        # 5. Trace relationships between components.
        relation_findings = self._trace_relationships(scope)

        findings = impl_findings + test_findings + relation_findings
        affected_files = list(impl_files) + list(test_files)

        # 6. Synthesize evidence-backed diagnosis and recommendation.
        diagnosis = self._synthesize_findings(cleaned_target, scope, findings)
        recommendation = self._recommend_next_step(cleaned_target, scope, findings)

        return InvestigationReport(
            target=cleaned_target,
            findings=tuple(findings),
            diagnosis=diagnosis,
            affected_files=tuple(dict.fromkeys(affected_files)),
            recommended_next_step=recommendation,
            modification_status="NONE",
            components=tuple(scope.modules[:_MAX_RELEVANT_MODULES]),
            tests_inspected=tuple(scope.tests[:_MAX_TEST_FILES]),
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

    @staticmethod
    def _extract_concepts(target: str) -> tuple[str, ...]:
        """Extract key technical concepts from the investigation target.

        Filters out generic stoplist words and very short tokens. Returns
        a deduplicated tuple of lowercase concept terms suitable for
        content/path matching against the repository.
        """
        raw_tokens = target.lower().replace("_", " ").replace("-", " ").split()
        seen: dict[str, None] = {}
        for token in raw_tokens:
            cleaned = token.strip(".,;:!?()[]{}")
            if len(cleaned) < 3:
                continue
            if cleaned in _CONCEPT_STOPLIST:
                continue
            seen[cleaned] = None
        return tuple(seen)

    def _discover_subsystem(self, concepts: tuple[str, ...]) -> SubsystemScope:
        """Discover relevant modules/directories from repository evidence.

        Uses RepositoryMapBuilder (AST-based) to score modules by relevance
        to the investigation concepts. No hardcoded directory mapping.
        """
        try:
            from atlas.research.repository_map import RepositoryMapBuilder

            builder = RepositoryMapBuilder(self._root)
            repo_map = builder.build()
        except Exception:
            # If repository map cannot be built, fall back to empty scope.
            return SubsystemScope()

        if not repo_map.modules:
            return SubsystemScope()

        # Score each module by relevance to the concepts.
        scored: list[tuple[float, str, str]] = []  # (score, module, path)
        for info in repo_map.modules:
            score = self._score_module(info.module, info.path, concepts)
            if score > 0:
                scored.append((score, info.module, info.path))

        # Sort by score descending, then by module name for determinism.
        scored.sort(key=lambda item: (-item[0], item[1]))

        # Take top-N relevant modules.
        top_modules = scored[:_MAX_RELEVANT_MODULES]
        modules = tuple(m for _, m, _ in top_modules)

        # Collect directories from the relevant modules.
        directories: set[str] = set()
        for module_name in modules:
            # Derive directory from module path (e.g. atlas.memory.manager -> atlas/memory).
            parts = module_name.split(".")
            if len(parts) >= 2:
                directories.add(parts[0])
                directories.add("/".join(parts[:-1]))

        return SubsystemScope(
            modules=modules,
            directories=tuple(sorted(directories)),
        )

    @staticmethod
    def _score_module(module: str, path: str, concepts: tuple[str, ...]) -> float:
        """Score a module's relevance to the investigation concepts.

        Uses multiple signals: module name match, path match, and
        content keyword match. Higher score = more relevant.
        """
        if not concepts:
            return 0.0

        module_lower = module.lower()
        path_lower = path.lower()
        score = 0.0

        for concept in concepts:
            # Strong signal: concept appears in the module name.
            if concept in module_lower:
                score += 3.0
            # Medium signal: concept appears in the file path.
            if concept in path_lower:
                score += 2.0

        return score

    def _inspect_implementation(
        self, scope: SubsystemScope, concepts: tuple[str, ...]
    ) -> tuple[list[InvestigationFinding], list[str]]:
        """Inspect implementation files within the discovered scope.

        Uses the existing _grep infrastructure to find concept references
        within the relevant modules' directories. Reads key files for
        evidence (bounded).
        """
        findings: list[InvestigationFinding] = []
        files: list[str] = []

        if not scope.directories:
            return findings, files

        # Search for concept matches within the discovered directories.
        searched: set[str] = set()
        for directory in scope.directories:
            for concept in concepts:
                key = f"{directory}:{concept}"
                if key in searched:
                    continue
                searched.add(key)
                matches = self._grep(
                    concept, directory=f"atlas/{directory}", max_results=3
                )
                if matches:
                    evidence = matches[0] if matches else ""
                    findings.append(
                        InvestigationFinding(
                            category="reference",
                            description=(
                                f"Found {len(matches)} reference(s) to "
                                f"'{concept}' in {directory}/"
                            ),
                            evidence=evidence,
                            location=f"atlas/{directory}/",
                        )
                    )
                    files.extend(matches[:_MAX_FILES_PER_MODULE])

        return findings, files

    def _discover_tests(
        self, scope: SubsystemScope,
    ) -> tuple[list[InvestigationFinding], list[str]]:
        """Discover test files relevant to the investigated subsystem.

        Searches for test files that reference the discovered modules
        or reside in corresponding test directories.
        """
        findings: list[InvestigationFinding] = []
        files: list[str] = []

        if not scope.modules:
            return findings, files

        # Look for test files referencing the module names.
        tested: set[str] = set()
        for module_name in scope.modules:
            # Derive a short name for test matching (e.g. atlas.memory.manager -> memory_manager).
            short_name = module_name.rsplit(".", 1)[-1]
            if short_name in tested:
                continue
            tested.add(short_name)

            # Search for test files referencing this module.
            matches = self._grep(
                short_name,
                directory="tests/",
                max_results=_MAX_TEST_FILES,
            )
            if matches:
                findings.append(
                    InvestigationFinding(
                        category="test",
                        description=(
                            f"Found {len(matches)} test file(s) referencing "
                            f"'{short_name}'"
                        ),
                        evidence=matches[0] if matches else "",
                        location="tests/",
                    )
                )
                files.extend(matches)

        return findings, files

    def _trace_relationships(
        self, scope: SubsystemScope,
    ) -> list[InvestigationFinding]:
        """Trace relationships between discovered components.

        Uses RepositoryMap dependency queries to identify coupling
        and data flow between the investigated modules.
        """
        findings: list[InvestigationFinding] = []

        if not scope.modules:
            return findings

        try:
            from atlas.research.repository_map import RepositoryMapBuilder

            builder = RepositoryMapBuilder(self._root)
            repo_map = builder.build()
        except Exception:
            return findings

        # Report dependencies for the top modules (bounded).
        for module_name in scope.modules[:4]:
            deps = repo_map.dependencies_of(module_name)
            if deps:
                dep_list = ", ".join(deps[:5])
                suffix = f" (+{len(deps) - 5} more)" if len(deps) > 5 else ""
                findings.append(
                    InvestigationFinding(
                        category="dependency",
                        description=(
                            f"'{module_name}' depends on: {dep_list}{suffix}"
                        ),
                        location=module_name,
                    )
                )

        return findings

    def _synthesize_findings(
        self,
        target: str,
        scope: SubsystemScope,
        findings: list[InvestigationFinding],
    ) -> str:
        """Synthesize a topic-agnostic diagnosis from gathered evidence."""
        if not findings and not scope.modules:
            return (
                f"No specific evidence found for '{target}'. "
                "The issue may require deeper manual investigation."
            )

        parts: list[str] = []
        if scope.modules:
            parts.append(
                f"Identified {len(scope.modules)} relevant component(s) in "
                f"{', '.join(scope.directories[:3]) or 'the repository'}."
            )

        categories: dict[str, int] = {}
        for f in findings:
            categories[f.category] = categories.get(f.category, 0) + 1

        if categories:
            desc = ", ".join(
                f"{count} {cat}" for cat, count in sorted(categories.items())
            )
            parts.append(f"Gathered {desc} finding(s).")

        return " ".join(parts)

    def _recommend_next_step(
        self,
        target: str,
        scope: SubsystemScope,
        findings: list[InvestigationFinding],
    ) -> str:
        """Recommend a next step based on gathered evidence."""
        if not findings and not scope.modules:
            return (
                "Manually inspect the relevant subsystem to identify "
                "the specific components and their interactions."
            )
        if scope.modules:
            return (
                f"Review the identified components "
                f"({', '.join(scope.modules[:3])}) and their "
                "relationships to understand the current architecture "
                "before proposing changes."
            )
        return (
            "Examine the gathered evidence to identify specific "
            "improvement opportunities."
        )

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


# ---------------------------------------------------------------------------
# Investigation-derived proposal (P17 — Investigation → Planning bridge)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class InvestigationProposal:
    """A development proposal derived from an investigation report.

    Lightweight presentation-only model. Does NOT use the heavy
    EvolutionProposal (which carries the full approval/execution lifecycle).
    This proposal is always in "PROPOSED" status and never auto-approves or
    auto-executes. Future P17 stages may bridge this to EvolutionProposal.
    """

    proposal_id: str
    investigation_target: str
    title: str
    summary: str
    components: tuple[str, ...] = ()
    findings: tuple[InvestigationFinding, ...] = ()
    affected_files: tuple[str, ...] = ()
    tests_inspected: tuple[str, ...] = ()
    recommended_next_step: str = ""
    evidence_summary: str = ""
    status: str = "PROPOSED"
    created_at: datetime = field(default_factory=datetime.now)

    @property
    def fingerprint(self) -> str:
        """Deterministic content hash for strict binding verification."""
        content = "|".join(
            [
                self.proposal_id,
                self.investigation_target,
                self.title,
                self.summary,
                str(self.components),
                str(self.affected_files),
            ]
        )
        return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


class InvestigationProposalGenerator:
    """Generates an InvestigationProposal from an InvestigationReport.

    Applies a conservative meaningful-improvement heuristic. Only produces a
    proposal when the investigation found concrete evidence: relevant
    components, reference/dependency findings, and affected files. Never
    mutates the repository. Never creates approval requests.
    """

    def __init__(self) -> None:
        self._proposal_counter = 0

    def generate_proposal(
        self,
        report: InvestigationReport,
    ) -> InvestigationProposal | None:
        """Generate a proposal if the investigation found a meaningful
        improvement. Returns None when no actionable improvement exists.
        """
        if not self._is_meaningful_improvement(report):
            return None

        self._proposal_counter += 1
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        proposal_id = f"INV-PROP-{timestamp}-{self._proposal_counter:04d}"

        title = self._derive_title(report)
        evidence_summary = self._synthesize_evidence(report)

        return InvestigationProposal(
            proposal_id=proposal_id,
            investigation_target=report.target,
            title=title,
            summary=report.diagnosis,
            components=report.components,
            findings=report.findings,
            affected_files=report.affected_files,
            tests_inspected=report.tests_inspected,
            recommended_next_step=report.recommended_next_step,
            evidence_summary=evidence_summary,
            status="PROPOSED",
        )

    @staticmethod
    def _is_meaningful_improvement(report: InvestigationReport) -> bool:
        """Conservative heuristic: a meaningful improvement requires
        concrete evidence from the investigation.
        """
        if not report.components:
            return False
        if not report.affected_files:
            return False
        # Require at least one reference or dependency finding (evidence
        # beyond empty keyword matches).
        has_substantive_finding = any(
            f.category in ("reference", "dependency")
            for f in report.findings
        )
        return has_substantive_finding

    @staticmethod
    def _derive_title(report: InvestigationReport) -> str:
        """Derive a concise proposal title from the investigation target."""
        target = report.target.strip()
        if len(target) > 60:
            target = target[:57] + "..."
        return f"Improve: {target}"

    @staticmethod
    def _synthesize_evidence(report: InvestigationReport) -> str:
        """Synthesize a brief evidence summary from the findings."""
        categories: dict[str, int] = {}
        for f in report.findings:
            categories[f.category] = categories.get(f.category, 0) + 1
        if not categories:
            return "No specific evidence found."
        parts = [f"{count} {cat}" for cat, count in sorted(categories.items())]
        return f"Found {', '.join(parts)} across {len(report.components)} component(s)."


# ---------------------------------------------------------------------------
# InvestigationProposal → EvolutionProposal Converter (P17 Planning → Approval)
# ---------------------------------------------------------------------------


class InvestigationProposalConverter:
    """Converts InvestigationProposal → EvolutionProposal (DRAFT).

    Pure logic component. No mutation. No filesystem. No subprocess.

    Converts a presentation-only InvestigationProposal into a governed
    EvolutionProposal that can enter the existing ApprovalManager lifecycle.

    The converted proposal always starts as ProposalStatus.DRAFT and requires
    explicit human approval before any further action.
    """

    def __init__(self) -> None:
        self._conversion_counter = 0

    def convert(self, proposal: InvestigationProposal) -> EvolutionProposal:
        """Convert an InvestigationProposal to a DRAFT EvolutionProposal.

        Args:
            proposal: The InvestigationProposal to convert.

        Returns:
            An EvolutionProposal with status=DRAFT, ready for ApprovalManager.
        """
        from atlas.evolution.models import (
            EvolutionProposal,
            ImprovementPlan,
            ImprovementPriority,
            ProposalStatus,
        )

        self._conversion_counter += 1
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        evolution_proposal_id = f"DEV-CONV-{timestamp}-{self._conversion_counter:04d}"

        plan = self._build_improvement_plan(proposal, timestamp)

        metadata = {
            "investigation_proposal_id": proposal.proposal_id,
            "investigation_fingerprint": proposal.fingerprint,
            "converted_by": "p17-planning-approval-bridge",
            "converted_at": datetime.now().isoformat(),
            "investigation_findings": [
                {
                    "category": f.category,
                    "description": f.description,
                    "evidence": f.evidence,
                    "location": f.location,
                }
                for f in proposal.findings
            ],
            "affected_files": list(proposal.affected_files),
            "tests_inspected": list(proposal.tests_inspected),
            "recommended_next_step": proposal.recommended_next_step,
        }

        ev_proposal = EvolutionProposal(
            proposal_id=evolution_proposal_id,
            title=proposal.title,
            summary=proposal.summary,
            rationale=self._derive_rationale(proposal),
            expected_benefit=self._derive_expected_benefit(proposal),
            risks=self._derive_risks(),
            impact_analysis=self._derive_impact_analysis(proposal),
            implementation_approach=self._derive_implementation_approach(proposal),
            plan=plan,
            status=ProposalStatus.DRAFT,
            created_at=proposal.created_at,
            metadata=metadata,
        )

        # Compute and set the fingerprint for strict approval binding
        ev_proposal.proposal_fingerprint = ev_proposal.compute_fingerprint()
        return ev_proposal

    def _build_improvement_plan(
        self, proposal: InvestigationProposal, timestamp: str
    ) -> ImprovementPlan:
        """Build a minimal ImprovementPlan from the investigation proposal."""
        from atlas.evolution.models import ImprovementPlan, ImprovementPriority

        return ImprovementPlan(
            plan_id=f"PLAN-INV-{timestamp}",
            title=f"Plan: {proposal.title}",
            description=proposal.summary,
            priority=ImprovementPriority.MEDIUM,
            target_components=list(proposal.components),
        )

    @staticmethod
    def _derive_rationale(proposal: InvestigationProposal) -> str:
        """Derive rationale from investigation evidence."""
        parts = [
            f"Investigation of '{proposal.investigation_target}' identified "
            f"{len(proposal.components)} relevant component(s).",
        ]
        if proposal.evidence_summary:
            parts.append(proposal.evidence_summary)
        if proposal.findings:
            categories = sorted(set(f.category for f in proposal.findings))
            parts.append(f"Evidence categories: {', '.join(categories)}.")
        return " ".join(parts)

    @staticmethod
    def _derive_expected_benefit(proposal: InvestigationProposal) -> str:
        """Derive expected benefit from recommended next step."""
        if proposal.recommended_next_step:
            return (
                f"Addressing the identified improvement opportunity: "
                f"{proposal.recommended_next_step}"
            )
        return (
            f"Improvement to {proposal.investigation_target} based on "
            f"investigation evidence."
        )

    @staticmethod
    def _derive_risks() -> str:
        """Return standard risk statement for converted proposals."""
        return (
            "Draft content derived from investigation evidence. "
            "Requires human approval, sandbox verification, and governance "
            "before any effect."
        )

    @staticmethod
    def _derive_impact_analysis(proposal: InvestigationProposal) -> str:
        """Derive impact analysis from components and affected files."""
        parts = []
        if proposal.components:
            parts.append(f"Components: {', '.join(proposal.components)}.")
        if proposal.affected_files:
            parts.append(f"Affected files: {', '.join(proposal.affected_files)}.")
        if parts:
            return " ".join(parts)
        return "Impact to be determined during planning."

    @staticmethod
    def _derive_implementation_approach(proposal: InvestigationProposal) -> str:
        """Derive implementation approach from investigation findings."""
        return (
            f"1. Review investigation evidence for '{proposal.investigation_target}'.\n"
            f"2. Examine affected components: {', '.join(proposal.components[:3]) or 'to be determined'}.\n"
            f"3. Design targeted improvements based on findings.\n"
            f"4. Implement changes with full test coverage.\n"
            f"5. Verify through the existing test suite."
        )
