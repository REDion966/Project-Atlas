"""
Atlas Evolution Governance — Rule Engine

Evaluates evolution proposals against governance constraints.
Pure logic. Deterministic. No infrastructure. No AI.

Phase 13.1 — Evolution Governance Foundation.
"""

from atlas.evolution.models import (
    EvolutionProposal,
    ExecutionLevel,
)
from atlas.evolution.governance.models import (
    GovernanceDecision,
    ScopeType,
)
from atlas.evolution.governance.constraint_registry import ConstraintRegistry


class RuleEngine:
    """
    Evaluates evolution proposals against governance constraints.

    The engine is stateless and deterministic: the same proposal and
    execution level always produce the same GovernanceDecision.

    Receives its ConstraintRegistry via dependency injection so it is
    fully testable with custom rule sets.

    Pure logic. No storage. No AI. No side effects.
    """

    def __init__(
        self,
        constraint_registry: ConstraintRegistry | None = None,
    ) -> None:
        """Initialise the rule engine.

        Args:
            constraint_registry: A ConstraintRegistry instance.
                If None, a default registry with standard governance
                rules is created.
        """
        self._registry = constraint_registry or ConstraintRegistry()

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def registry(self) -> ConstraintRegistry:
        """Return the injected ConstraintRegistry."""
        return self._registry

    # ------------------------------------------------------------------
    # Evaluation
    # ------------------------------------------------------------------

    def evaluate(
        self,
        proposal: EvolutionProposal,
        current_level: ExecutionLevel = ExecutionLevel.ADMINISTRATIVE,
    ) -> GovernanceDecision:
        """
        Evaluate a proposal against all applicable governance rules.

        The evaluation process:
          1. Determine the proposal's scope from target_components.
          2. Load all rules that apply to this scope.
          3. For each matching rule:
               a. If the rule is forbidden → reject.
               b. If the rule requires a higher execution level than
                  the current level → reject.
          4. If no rules are violated, the proposal is approved.

        Args:
            proposal: The EvolutionProposal to evaluate.
            current_level: The current ExecutionLevel of the system.
                Defaults to ADMINISTRATIVE (the Phase 11 baseline).

        Returns:
            A GovernanceDecision with the result of the evaluation.
        """
        scope = self._determine_scope(proposal)
        matching_rules = self._registry.get_rules_for_scope(scope)

        if not matching_rules:
            return GovernanceDecision(
                approved=True,
                reason=(
                    f"No governance rules apply to scope "
                    f"'{scope.name}'. Proposal is allowed."
                ),
            )

        violated: list[str] = []
        for rule in matching_rules:
            # Check if the change is forbidden outright
            if rule.forbidden:
                violated.append(
                    f"{rule.rule_id}: {rule.description} "
                    f"(change is forbidden)"
                )
                continue

            # Check execution level requirement
            if rule.min_execution_level is not None:
                if current_level.value < rule.min_execution_level:
                    violated.append(
                        f"{rule.rule_id}: {rule.description} "
                        f"(requires level {rule.min_execution_level}, "
                        f"current level is {current_level.value})"
                    )

        if violated:
            return GovernanceDecision(
                approved=False,
                reason=(
                    f"Proposal '{proposal.proposal_id}' "
                    f"({proposal.title}) violated "
                    f"{len(violated)} governance rule(s)."
                ),
                violated_rules=violated,
            )

        return GovernanceDecision(
            approved=True,
            reason=(
                f"Proposal '{proposal.proposal_id}' "
                f"({proposal.title}) passed all governance checks "
                f"for scope '{scope.name}' at execution level "
                f"{current_level.value} ({current_level.name})."
            ),
        )

    # ------------------------------------------------------------------
    # Scope detection
    # ------------------------------------------------------------------

    @staticmethod
    def _determine_scope(proposal: EvolutionProposal) -> ScopeType:
        """Map a proposal's target components to a ScopeType.

        Uses keyword matching against the proposal's
        ImprovementPlan.target_components list.

        Keyword mappings:
          - "identity" → IDENTITY
          - "config" or "configuration" → CONFIG
          - "code" → CODE
          - "memory" → MEMORY
          - "knowledge" → KNOWLEDGE
          - everything else → UNKNOWN

        Args:
            proposal: The EvolutionProposal to classify.

        Returns:
            The detected ScopeType.
        """
        target_components = proposal.plan.target_components

        # Build a set of lowercased component names for matching
        components_lower = {c.lower() for c in target_components}

        # Check in priority order (most specific first)
        if "identity" in components_lower:
            return ScopeType.IDENTITY

        if "config" in components_lower or "configuration" in components_lower:
            return ScopeType.CONFIG

        if "code" in components_lower:
            return ScopeType.CODE

        if "memory" in components_lower:
            return ScopeType.MEMORY

        if "knowledge" in components_lower:
            return ScopeType.KNOWLEDGE

        return ScopeType.UNKNOWN

    @staticmethod
    def classify_scope(target_components: list[str]) -> ScopeType:
        """Classify a list of target component names into a ScopeType.

        Convenience method for testing without creating a full proposal.

        Args:
            target_components: List of component name strings.

        Returns:
            The detected ScopeType.
        """
        components_lower = {c.lower() for c in target_components}

        if "identity" in components_lower:
            return ScopeType.IDENTITY
        if "config" in components_lower or "configuration" in components_lower:
            return ScopeType.CONFIG
        if "code" in components_lower:
            return ScopeType.CODE
        if "memory" in components_lower:
            return ScopeType.MEMORY
        if "knowledge" in components_lower:
            return ScopeType.KNOWLEDGE
        return ScopeType.UNKNOWN
