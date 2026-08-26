"""
Atlas Proposal Generator

Converts improvement plans into human-readable engineering proposals.
Includes rationale, expected benefit, risks, and required approval.

Phase 7.0 — Self-Evolution Foundation.

NOTE — Rendering/formatting layer only (intentional separation):
  This module is deliberately a formatting layer. It takes an
  already-computed ``ImprovementPlan`` and renders it into a
  human-readable ``EvolutionProposal`` document. It does NOT:
    - detect weaknesses (ImprovementPlanner's job)
    - plan or prioritise improvements (ImprovementPlanner's job)
    - make planning decisions (DecisionIntelligenceEngine's job)
    - approve, reject, or execute anything (ApprovalManager /
      EvolutionExecutionEngine's job)
  Keeping ProposalGenerator a pure, deterministic formatter allows the
  planning logic above it to evolve independently without coupling the
  rendered proposal text to planning internals.
"""

from datetime import datetime

from atlas.evolution.models import (
    EvolutionProposal,
    ImprovementPlan,
    ImprovementPriority,
    ProposalStatus,
)


class ProposalGenerator:
    """
    Generates human-readable engineering proposals from improvement plans.

    This is a pure logic component with no infrastructure dependencies.
    It converts structured plans into proposals suitable for user review
    and approval. It is intentionally a rendering/formatting layer only —
    all analysis, detection, and planning decisions are made upstream by
    ImprovementPlanner and DecisionIntelligenceEngine before a plan
    reaches this generator.
    """

    def __init__(self) -> None:
        self._proposal_counter = 0

    def _next_proposal_id(self) -> str:
        """Generate a unique proposal identifier."""
        self._proposal_counter += 1
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        return f"PROP-{timestamp}-{self._proposal_counter:04d}"

    def generate_proposal(
        self,
        plan: ImprovementPlan,
    ) -> EvolutionProposal:
        """
        Generate a human-readable engineering proposal from an improvement plan.

        Stage F: bounded evidence carried on ``plan.metadata`` (e.g. a
        research-evidence summary) is copied into the proposal metadata
        under ``"planning_evidence"`` — advisory only, never overwriting
        keys already present.

        Args:
            plan: The ImprovementPlan to convert into a proposal.

        Returns:
            An EvolutionProposal with detailed rationale, risks, and
            implementation approach.
        """
        planning_evidence = dict(getattr(plan, "metadata", {}) or {})
        return EvolutionProposal(
            proposal_id=self._next_proposal_id(),
            title=plan.title,
            summary=self._generate_summary(plan),
            rationale=self._generate_rationale(plan),
            expected_benefit=plan.expected_benefit,
            risks=self._generate_risks(plan),
            impact_analysis=self._generate_impact_analysis(plan),
            implementation_approach=self._generate_approach(plan),
            plan=plan,
            status=ProposalStatus.DRAFT,
            metadata=(
                {"planning_evidence": planning_evidence}
                if planning_evidence
                else {}
            ),
        )

    def generate_proposals(
        self,
        plans: list[ImprovementPlan],
    ) -> list[EvolutionProposal]:
        """
        Generate proposals for multiple improvement plans.

        Args:
            plans: A list of ImprovementPlan instances.

        Returns:
            A list of EvolutionProposal instances, one per plan,
            sorted by priority (highest first).
        """
        proposals = [self.generate_proposal(plan) for plan in plans]
        proposals.sort(
            key=lambda p: p.plan.priority.value,
        )
        return proposals

    def _generate_summary(
        self,
        plan: ImprovementPlan,
    ) -> str:
        """Generate a high-level summary of the proposal."""
        weakness_count = len(plan.weaknesses)
        components = ", ".join(plan.target_components)

        return (
            f"This proposal addresses {weakness_count} identified "
            f"weakness(es) in {components}. "
            f"Priority: {plan.priority.name}. "
            f"Complexity: {plan.complexity_estimate}."
        )

    def _generate_rationale(
        self,
        plan: ImprovementPlan,
    ) -> str:
        """Generate the rationale explaining why this change is needed."""
        parts: list[str] = [
            f"Analysis of recent observations has identified "
            f"{len(plan.weaknesses)} area(s) requiring improvement "
            f"in the following components: {', '.join(plan.target_components)}.",
        ]

        for i, weakness in enumerate(plan.weaknesses, 1):
            parts.append(
                f"{i}. {weakness.area}: {weakness.description} "
                f"(Severity: {weakness.severity.name})"
            )

        parts.append(
            "Addressing these weaknesses will improve system reliability, "
            "performance, and maintainability."
        )

        return "\n".join(parts)

    def _generate_risks(
        self,
        plan: ImprovementPlan,
    ) -> str:
        """Generate a risk assessment for the proposal."""
        risks: list[str] = []

        if plan.complexity_estimate == "high":
            risks.append(
                "High complexity: implementation may require significant "
                "changes across multiple components."
            )
        elif plan.complexity_estimate == "medium":
            risks.append(
                "Medium complexity: changes are localized but may require "
                "coordination between components."
            )
        else:
            risks.append(
                "Low complexity: changes are isolated and well-understood."
            )

        if any(w.severity == ImprovementPriority.CRITICAL for w in plan.weaknesses):
            risks.append(
                "Critical severity: delaying implementation may lead to "
                "further system degradation."
            )

        risks.append(
            "All changes will be verified through the existing test suite "
            "before deployment."
        )

        return "\n".join(risks)

    def _generate_impact_analysis(
        self,
        plan: ImprovementPlan,
    ) -> str:
        """Generate an analysis of which components are affected."""
        components = plan.target_components

        impact_map = {
            "runtime": (
                "Affects request handling, response generation, and "
                "overall system performance metrics."
            ),
            "reasoning": (
                "Affects the reasoning pipeline, capability selection, "
                "routing, and execution components."
            ),
            "tools": (
                "Affects the tool registry, selector, executor, and "
                "engine components."
            ),
            "memory": (
                "Affects memory storage, retrieval, ranking, and "
                "context assembly components."
            ),
            "system_health": (
                "Affects system monitoring, health checks, and "
                "error recovery components."
            ),
        }

        parts: list[str] = []
        for component in components:
            impact = impact_map.get(component, f"Affects {component} components.")
            parts.append(f"- {component}: {impact}")

        parts.append(
            "\nBackward compatibility will be preserved. "
            "No existing public APIs will be modified."
        )

        return "\n".join(parts)

    def _generate_approach(
        self,
        plan: ImprovementPlan,
    ) -> str:
        """Generate a high-level implementation approach."""
        approaches = {
            "runtime": (
                "1. Profile current runtime performance to establish baseline.\n"
                "2. Identify bottlenecks in request processing pipeline.\n"
                "3. Implement targeted optimizations.\n"
                "4. Verify improvements through performance tests."
            ),
            "reasoning": (
                "1. Analyze recent reasoning outcomes to identify failure patterns.\n"
                "2. Review capability handler implementations.\n"
                "3. Improve routing criteria and fallback logic.\n"
                "4. Add additional verification steps to the reasoning pipeline."
            ),
            "tools": (
                "1. Review failing tool implementations.\n"
                "2. Improve error handling and recovery in tool execution.\n"
                "3. Add input validation where missing.\n"
                "4. Update tool documentation and tests."
            ),
            "memory": (
                "1. Review memory retrieval and ranking algorithms.\n"
                "2. Improve relevance scoring.\n"
                "3. Optimize memory storage and indexing.\n"
                "4. Add monitoring for retrieval quality metrics."
            ),
            "system_health": (
                "1. Diagnose reported component health issues.\n"
                "2. Implement targeted fixes for failing components.\n"
                "3. Add proactive health monitoring.\n"
                "4. Verify system stability through integration tests."
            ),
        }

        primary_area = plan.target_components[0] if plan.target_components else "general"
        approach = approaches.get(
            primary_area,
            "1. Analyze the identified weaknesses.\n"
            "2. Design targeted improvements.\n"
            "3. Implement changes with full test coverage.\n"
            "4. Verify through the existing test suite."
        )

        return approach
