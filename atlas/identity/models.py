"""
Atlas Identity Models — Phase 8.0 Cognitive Identity Foundation.

Immutable data models representing Atlas's persistent internal identity.
All models are pure dataclasses — no business logic, no infrastructure.
Identity NEVER edits code. These models are read-only context providers.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class BeliefConfidence(str, Enum):
    """Confidence level for a core belief."""
    ESTABLISHED = "established"       # Confirmed by repeated evidence
    STRONG = "strong"                 # Well-supported, rarely contradicted
    MODERATE = "moderate"             # Supported but needs more evidence
    TENTATIVE = "tentative"           # Preliminary, needs verification
    WEAK = "weak"                     # Insufficient evidence
    RETIRED = "retired"               # Formerly held, no longer active


class ImprovementStatus(str, Enum):
    """Status of a proposed or applied improvement."""
    PROPOSED = "proposed"
    APPROVED = "approved"
    REJECTED = "rejected"
    APPLIED = "applied"
    OBSOLETE = "obsolete"


class MaturityLevel(str, Enum):
    """Maturity of a capability."""
    EMERGING = "emerging"
    DEVELOPING = "developing"
    STABLE = "stable"
    MATURE = "mature"
    DECLINING = "declining"


# ---------------------------------------------------------------------------
# Core identity data models
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class LongTermGoal:
    """
    A long-term goal Atlas holds for itself.

    Goals are permanent aspirations that guide behavior across sessions.
    """
    goal_id: str
    description: str
    priority: int = 1                     # 1-10, higher = more important
    established_at: datetime = field(default_factory=datetime.now)
    progress_note: str = ""               # Qualitative progress description


@dataclass(frozen=True, slots=True)
class CorePrinciple:
    """
    An immutable operating principle that Atlas follows.

    Principles are architecture-invariant. They persist across
    provider changes, model swaps, and framework upgrades.
    """
    principle_id: str
    title: str
    description: str
    established_at: datetime = field(default_factory=datetime.now)


@dataclass(frozen=True, slots=True)
class CoreBelief:
    """
    A belief Atlas currently holds about itself or its domain.

    Beliefs can change gradually through accumulated evidence.
    They are NEVER changed instantly.
    """
    belief_id: str
    statement: str
    category: str = "general"             # e.g. "self", "architecture", "domain", "user"
    confidence: BeliefConfidence = BeliefConfidence.TENTATIVE
    evidence_count: int = 0
    established_at: datetime = field(default_factory=datetime.now)
    last_updated: datetime = field(default_factory=datetime.now)
    retired_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class EngineeringPreference:
    """
    A stable engineering preference Atlas has developed over time.

    Precedence: Architecture > Correctness > Performance > Simplicity.
    """
    preference_id: str
    name: str
    description: str
    priority: int = 5                     # 1-10
    examples: list[str] = field(default_factory=list)
    established_at: datetime = field(default_factory=datetime.now)


@dataclass(frozen=True, slots=True)
class CapabilityProfile:
    """Overall capability assessment maintained by CapabilityProfiler."""
    capability_id: str
    capability_name: str
    description: str = ""
    confidence: float = 0.5               # 0.0 - 1.0
    maturity: MaturityLevel = MaturityLevel.DEVELOPING
    stability: float = 0.5                # How stable/reliable (0.0 - 1.0)
    usage_count: int = 0
    success_count: int = 0
    last_assessed: datetime = field(default_factory=datetime.now)
    notes: str = ""


@dataclass(frozen=True, slots=True)
class StrengthProfile:
    """A recognized strength of Atlas."""
    profile_id: str
    area: str                             # e.g. "reasoning", "planning", "tools"
    description: str
    confidence: float = 0.7
    evidence_count: int = 1
    established_at: datetime = field(default_factory=datetime.now)


@dataclass(frozen=True, slots=True)
class WeaknessProfile:
    """A recognized weakness of Atlas — tracked for improvement."""
    profile_id: str
    area: str
    description: str
    severity: int = 3                     # 1-10, higher = more severe
    mitigation: str = ""
    established_at: datetime = field(default_factory=datetime.now)


@dataclass(frozen=True, slots=True)
class DecisionStyle:
    """
    Atlas's learned decision-making preferences.

    These evolve gradually over time through accumulated experience.
    No single session changes decision style significantly.
    """
    style_id: str
    preferred_reasoning_style: str = "structured_analysis"
    preferred_planning_style: str = "stepwise_decomposition"
    preferred_tool_usage: str = "selective"
    preferred_explanation_style: str = "transparent"
    confidence: float = 0.5
    last_updated: datetime = field(default_factory=datetime.now)


@dataclass(frozen=True, slots=True)
class ImprovementEntry:
    """
    A record of an approved identity improvement.

    Evolution may propose identity changes. Only approved changes
    are recorded here. Identity never modifies itself.
    """
    entry_id: str
    target_component: str                 # e.g. "beliefs", "preferences", "style"
    description: str
    status: ImprovementStatus = ImprovementStatus.PROPOSED
    proposed_at: datetime = field(default_factory=datetime.now)
    approved_at: datetime | None = None
    applied_at: datetime | None = None
    evidence_source: str = ""


# ---------------------------------------------------------------------------
# Root identity container
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class CoreIdentity:
    """
    The complete immutable snapshot of Atlas's cognitive identity.

    This is a value object — to change identity, create a new snapshot.
    Identity evolution is deliberate, gradual, and approved.
    """
    identity_id: str
    name: str = "Atlas"
    description: str = (
        "A modular, AI-independent intelligent agent operating framework. "
        "Built for decades, not demos. Augments human capability through "
        "trustworthy, modular, intelligent automation."
    )
    created_at: datetime = field(default_factory=datetime.now)
    last_updated: datetime = field(default_factory=datetime.now)
    version: int = 1

    # Sub-components (empty by default, populated by IdentityEngine)
    goals: list[LongTermGoal] = field(default_factory=list)
    principles: list[CorePrinciple] = field(default_factory=list)
    beliefs: list[CoreBelief] = field(default_factory=list)
    engineering_preferences: list[EngineeringPreference] = field(default_factory=list)
    strengths: list[StrengthProfile] = field(default_factory=list)
    weaknesses: list[WeaknessProfile] = field(default_factory=list)
    decision_style: DecisionStyle | None = None
    improvement_history: list[ImprovementEntry] = field(default_factory=list)