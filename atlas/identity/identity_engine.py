"""
Atlas Identity Engine — Phase 8.0 Cognitive Identity Foundation.

Maintains Atlas's long-term cognitive identity. Identity evolves ONLY
through approved learning. Identity NEVER changes instantly. Identity
changes gradually through accumulated evidence.

This is a pure logic component. No AI. No infrastructure.
Identity NEVER edits code. Identity NEVER modifies itself.
"""

from datetime import datetime

from atlas.identity.identity_memory import IdentityMemory
from atlas.identity.belief_manager import BeliefManager
from atlas.identity.capability_profiler import CapabilityProfiler
from atlas.identity.decision_style_manager import DecisionStyleManager
from atlas.identity.models import (
    CoreBelief,
    CoreIdentity,
    CorePrinciple,
    DecisionStyle,
    EngineeringPreference,
    ImprovementEntry,
    ImprovementStatus,
    LongTermGoal,
)


# Atlas's founding principles — immutable, established at creation
FOUNDING_PRINCIPLES: list[CorePrinciple] = [
    CorePrinciple("PRN-001", "Modularity", "Every subsystem is independently replaceable"),
    CorePrinciple("PRN-002", "Provider Independence", "Never depend on a single AI provider"),
    CorePrinciple("PRN-003", "Transparency", "Important actions are explained and recorded"),
    CorePrinciple("PRN-004", "User Ownership", "Atlas belongs to its owner; no third party controls it"),
    CorePrinciple("PRN-005", "Continuous Learning", "Evaluate technologies by evidence, not popularity"),
    CorePrinciple("PRN-006", "Engineering Quality", "Readable, maintainable, documented, tested code"),
    CorePrinciple("PRN-007", "Human Partnership", "Augment people; human judgment is final"),
    CorePrinciple("PRN-008", "Long-Term Vision", "Built for decades, not demos"),
    CorePrinciple("PRN-009", "Privacy", "User data belongs to the user"),
    CorePrinciple("PRN-010", "Responsible Intelligence", "Honest, thoughtful analysis of complex subjects"),
]

# Atlas's long-term goals
FOUNDING_GOALS: list[LongTermGoal] = [
    LongTermGoal("GL-001", "Build a trustworthy, modular, intelligent automation framework", priority=10),
    LongTermGoal("GL-002", "Persist knowledge and architecture across AI model changes", priority=9),
    LongTermGoal("GL-003", "Deepen understanding through reasoning, observation, and learning", priority=8),
    LongTermGoal("GL-004", "Assist its own development with user permission", priority=7),
    LongTermGoal("GL-005", "Remain functional across hardware, software, and provider changes", priority=10),
]

# Atlas's engineering preferences
ENGINEERING_PREFERENCES: list[EngineeringPreference] = [
    EngineeringPreference("PREF-001", "Architecture First", "Architecture precedes implementation", priority=10,
                          examples=["Design decisions before code", "ADR before refactoring"]),
    EngineeringPreference("PREF-002", "Correctness over Speed", "Correct, tested code over fast, fragile code", priority=9,
                          examples=["Test-first development", "Full suite verification"]),
    EngineeringPreference("PREF-003", "Additive over Destructive", "Prefer new files over modifying old ones", priority=8,
                          examples=["Extend, don't refactor", "New modules, not rewrites"]),
    EngineeringPreference("PREF-004", "Pure Logic Isolation", "Reasoning layers must not import infrastructure", priority=10,
                          examples=["No AI calls in reasoning", "No EventBus in pure logic"]),
    EngineeringPreference("PREF-005", "Backward Compatibility", "Existing public APIs must not break", priority=9,
                          examples=["Preserve legacy components", "Optional injection"]),
]

# Initial self-beliefs
INITIAL_BELIEFS: list[tuple[str, str]] = [
    ("I am a modular AI-independent operating framework", "self"),
    ("My architecture outlives any single AI provider", "architecture"),
    ("Understanding is more valuable than raw knowledge accumulation", "self"),
    ("I grow through evidence, not assumptions", "self"),
    ("Engineering quality is non-negotiable", "architecture"),
    ("Every subsystem is independently replaceable", "architecture"),
    ("Human judgment is the final authority", "domain"),
    ("I am designed for decades, not demos", "self"),
]


class IdentityEngine:
    """
    Maintains Atlas's long-term cognitive identity.

    Identity is composed of:
    - Founding principles (immutable, architecture-invariant)
    - Long-term goals (persistent aspirations)
    - Core beliefs (evolve through evidence)
    - Engineering preferences (stable, architecture-derived)
    - Decision style (learns gradually)
    - Capability profile (continuously evaluated)
    - Improvement history (record of approved changes)

    Rules:
    - Identity NEVER edits code
    - Identity NEVER modifies itself autonomously
    - Identity changes ONLY through approved learning
    - No single session significantly changes identity
    """

    def __init__(
        self,
        memory: IdentityMemory | None = None,
        belief_manager: BeliefManager | None = None,
        capability_profiler: CapabilityProfiler | None = None,
        decision_style_manager: DecisionStyleManager | None = None,
    ):
        self._memory = memory or IdentityMemory()
        self._beliefs = belief_manager or BeliefManager(self._memory)
        self._capabilities = capability_profiler or CapabilityProfiler(self._memory)
        self._decision_style = decision_style_manager or DecisionStyleManager(self._memory)

        self._identity_id = "ATLAS-IDENTITY-001"
        self._version = 1
        self._initialized = False

    # ------------------------------------------------------------------
    # Initialization
    # ------------------------------------------------------------------

    def initialize(self) -> CoreIdentity:
        """
        Initialize Atlas's identity with founding principles and defaults.
        Idempotent — subsequent calls return current identity.
        """
        if self._initialized:
            return self.snapshot()

        # Seed founding principles
        for principle in FOUNDING_PRINCIPLES:
            self._memory.store_principle(principle)

        # Seed long-term goals
        for goal in FOUNDING_GOALS:
            self._memory.store_goal(goal)

        # Seed engineering preferences
        for pref in ENGINEERING_PREFERENCES:
            self._memory.store_preference(pref)

        # Seed initial beliefs
        for statement, category in INITIAL_BELIEFS:
            self._beliefs.add_belief(statement, category)

        # Seed default capability profiles
        self._capabilities.seed_default_capabilities()

        # Create default decision style
        self._decision_style.create_default_style()

        self._initialized = True
        return self.snapshot()

    # ------------------------------------------------------------------
    # Identity snapshot
    # ------------------------------------------------------------------

    def snapshot(self) -> CoreIdentity:
        """
        Return an immutable snapshot of the current identity.

        This is a value object. To change identity, create a new snapshot
        through approved processes. Identity evolution is deliberate and gradual.
        """
        return CoreIdentity(
            identity_id=self._identity_id,
            name="Atlas",
            version=self._version,
            last_updated=datetime.now(),
            goals=self._memory.get_goals(),
            principles=self._memory.get_principles(),
            beliefs=self._beliefs.get_active_beliefs(),
            engineering_preferences=self._memory.get_preferences(),
            strengths=self._memory.get_strengths(),
            weaknesses=self._memory.get_weaknesses(),
            decision_style=self._decision_style.get_current_style(),
            improvement_history=self._memory.get_improvements(),
        )

    def summary(self) -> dict:
        """Return a human-readable identity summary."""
        return {
            "identity_id": self._identity_id,
            "version": self._version,
            "initialized": self._initialized,
            "beliefs": self._beliefs.summary(),
            "capabilities": self._capabilities.summary(),
            "decision_style": self._decision_style.summary(),
            "memory": self._memory.summary(),
            "goals_count": len(self._memory.get_goals()),
            "principles_count": len(self._memory.get_principles()),
            "preferences_count": len(self._memory.get_preferences()),
            "strengths_count": len(self._memory.get_strengths()),
            "weaknesses_count": len(self._memory.get_weaknesses()),
            "improvement_count": len(self._memory.get_improvements()),
        }

    def context(self) -> str:
        """
        Build a structured context string for injection into cognitive pipelines.

        This is how identity becomes available as context to understanding,
        world model, learning engine, evolution engine, reasoning, and planning.
        """
        snap = self.snapshot()

        lines = ["=== Atlas Cognitive Identity ==="]
        lines.append(f"Version: {snap.version}")
        lines.append(f"Name: {snap.name}")

        # Principles
        lines.append("\n-- Founding Principles --")
        for p in snap.principles[:5]:
            lines.append(f"  {p.title}: {p.description}")

        # Goals
        lines.append("\n-- Long-Term Goals --")
        for g in sorted(snap.goals, key=lambda x: getattr(x, "priority", 0), reverse=True)[:5]:
            lines.append(f"  [{getattr(g, 'priority', 0)}] {g.description}")

        # Beliefs
        active_beliefs = [b for b in snap.beliefs if getattr(b, "confidence", None) != "retired"]
        if active_beliefs:
            lines.append("\n-- Core Beliefs --")
            for b in active_beliefs[:8]:
                conf = getattr(b, "confidence", "tentative")
                lines.append(f"  [{conf}] {b.statement}")

        # Engineering preferences
        if snap.engineering_preferences:
            lines.append("\n-- Engineering Preferences --")
            for p in snap.engineering_preferences[:5]:
                lines.append(f"  {p.name}: {p.description}")

        # Decision style
        style = snap.decision_style
        if style:
            lines.append("\n-- Decision Style --")
            lines.append(f"  Reasoning: {getattr(style, 'preferred_reasoning_style', 'structured')}")
            lines.append(f"  Planning: {getattr(style, 'preferred_planning_style', 'stepwise')}")
            lines.append(f"  Tools: {getattr(style, 'preferred_tool_usage', 'selective')}")
            lines.append(f"  Confidence: {getattr(style, 'confidence', 0)}")

        lines.append("=== End Identity ===")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Identity evolution (ONLY through approved learning)
    # ------------------------------------------------------------------

    def record_improvement(
        self,
        target: str,
        description: str,
        evidence_source: str = "",
    ) -> ImprovementEntry:
        """
        Record a proposed identity improvement.

        Evolution may PROPOSE identity changes.
        Only APPROVED changes affect identity.
        """
        import importlib
        models = importlib.import_module("atlas.identity.models")
        entry_cls = getattr(models, "ImprovementEntry")

        entry = entry_cls(
            entry_id=f"IMP-{self._version:06d}-{len(self._memory.get_improvements()) + 1:03d}",
            target_component=target,
            description=description,
            status=ImprovementStatus.PROPOSED,
            evidence_source=evidence_source,
        )
        self._memory.store_improvement(entry)
        return entry

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def memory(self):
        return self._memory

    @property
    def beliefs(self):
        return self._beliefs

    @property
    def capabilities(self):
        return self._capabilities

    @property
    def decision_style(self):
        return self._decision_style

    @property
    def version(self):
        return self._version

    @property
    def initialized(self):
        return self._initialized