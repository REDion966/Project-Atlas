"""
Atlas Evolution Governance — Data Models

Pure data models for evolution governance.
Phase 13.1 — Evolution Governance Foundation.

No business logic. No infrastructure. Deterministic and auditable.
"""

from dataclasses import dataclass, field
from enum import Enum, auto


class ScopeType(Enum):
    """What kind of change a proposal intends to make.

    Determines which governance rules apply and what execution
    level is required for the change to proceed.
    """

    CONFIG = auto()      # Internal Atlas configuration
    MEMORY = auto()      # Memory, knowledge, world model
    KNOWLEDGE = auto()   # Knowledge base entries
    CODE = auto()        # Code artifacts / patches
    IDENTITY = auto()    # Identity principles, beliefs, preferences
    CAPABILITY = auto()  # Capability registry surface (additive, Phase 16)
    UNKNOWN = auto()     # Unclassified


@dataclass(frozen=True, slots=True)
class GovernanceRule:
    """
    A single auditable governance constraint.

    Each rule defines:
      - What scope of change it applies to.
      - The minimum execution level required (optional).
      - Whether the change is forbidden outright.

    Attributes:
        rule_id: Unique identifier for this rule (e.g. "GOV-001").
        description: Human-readable explanation of the rule.
        scope: The ScopeType this rule applies to.
        min_execution_level: Minimum ExecutionLevel required. If None,
            no level check is performed.
        forbidden: If True, any proposal matching this scope is
            unconditionally rejected regardless of execution level.
    """

    rule_id: str
    description: str
    scope: ScopeType
    min_execution_level: int | None = None
    forbidden: bool = False


@dataclass(frozen=True, slots=True)
class GovernanceDecision:
    """
    Result of evaluating a proposal against governance constraints.

    Attributes:
        approved: Whether the proposal passed all governance checks.
        reason: Human-readable explanation of the decision.
        violated_rules: List of rule_ids that were violated, if any.
    """

    approved: bool
    reason: str = ""
    violated_rules: list[str] = field(default_factory=list)
