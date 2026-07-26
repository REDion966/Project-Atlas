"""
Atlas Capability Profiler — Phase 8.0 Cognitive Identity Foundation.

Continuously evaluates Atlas's strongest and weakest abilities.
Tracks confidence, maturity, and stability of each capability.
Pure logic. No AI. No infrastructure.
"""

from datetime import datetime

from atlas.identity.models import CapabilityProfile, MaturityLevel, StrengthProfile, WeaknessProfile


class CapabilityProfiler:
    """
    Evaluates and profiles Atlas's capabilities.

    Capabilities are assessed along three axes:
    - Confidence: how sure Atlas is about this capability (0.0-1.0)
    - Maturity: how developed the capability is (EMERGING → MATURE)
    - Stability: how reliable the capability is (0.0-1.0)
    """

    # Known Atlas capabilities to seed initial profiles
    DEFAULT_CAPABILITIES = [
        ("reasoning", "Structured reasoning pipeline with capability analysis"),
        ("planning", "Goal decomposition into sub-goals and steps"),
        ("memory_retrieval", "Semantic search across stored memories"),
        ("knowledge_retrieval", "Structured knowledge queries"),
        ("tool_usage", "Tool selection and execution via engine"),
        ("understanding", "Concept extraction and pattern analysis"),
        ("learning", "Experience collection and knowledge extraction"),
        ("reflection", "Bounded reflective analysis on reasoning outcomes"),
        ("world_modeling", "Causal graph and entity relationship modeling"),
        ("evolution_observation", "Runtime metrics and self-observation"),
    ]

    def __init__(self, memory: "IdentityMemory | None" = None):  # type: ignore[name-defined]
        if memory is None:
            from atlas.identity.identity_memory import IdentityMemory
            memory = IdentityMemory()

        self._memory = memory
        self._profile_counter = 0
        self._strength_counter = 0
        self._weakness_counter = 0

    # ------------------------------------------------------------------
    # Capability profiles
    # ------------------------------------------------------------------

    def register_capability(
        self,
        name: str,
        description: str = "",
        confidence: float = 0.5,
        maturity: MaturityLevel = MaturityLevel.DEVELOPING,
    ) -> CapabilityProfile:
        """Register or update a capability profile."""
        self._profile_counter += 1
        profile = CapabilityProfile(
            capability_id=f"CAP-{self._profile_counter:06d}",
            capability_name=name,
            description=description,
            confidence=confidence,
            maturity=maturity,
            stability=confidence * 0.8,
        )
        self._memory.store_capability(profile)
        return profile

    def seed_default_capabilities(self) -> list[CapabilityProfile]:
        """Create initial capability profiles for all known Atlas capabilities."""
        profiles = []
        for name, desc in self.DEFAULT_CAPABILITIES:
            # Check if already exists
            existing = self._memory.get_capability_by_name(name)
            if existing is None:
                profile = self.register_capability(name, desc)
                profiles.append(profile)
            else:
                profiles.append(existing)
        return profiles

    def update_capability(
        self,
        name: str,
        success: bool,
        confidence_delta: float = 0.0,
    ) -> CapabilityProfile | None:
        """
        Update a capability profile based on usage outcome.

        Success increases stability and confidence slightly.
        Failure decreases stability.
        """
        existing = self._memory.get_capability_by_name(name)
        if existing is None:
            return None

        new_usage = getattr(existing, "usage_count", 0) + 1
        new_success = getattr(existing, "success_count", 0) + (1 if success else 0)

        # Confidence moves slowly
        old_conf = getattr(existing, "confidence", 0.5)
        success_rate = new_success / new_usage if new_usage > 0 else old_conf
        target_conf = (success_rate * 0.7) + (old_conf * 0.3)  # Smooth moving average
        new_conf = round(min(1.0, max(0.0, target_conf + confidence_delta)), 4)

        # Stability follows success rate
        new_stability = round(success_rate, 4)

        # Maturity evolves based on usage and success
        new_maturity = self._assess_maturity(new_usage, new_success, getattr(existing, "maturity", MaturityLevel.DEVELOPING))

        updated = CapabilityProfile(
            capability_id=existing.capability_id,
            capability_name=name,
            description=getattr(existing, "description", ""),
            confidence=new_conf,
            maturity=new_maturity,
            stability=new_stability,
            usage_count=new_usage,
            success_count=new_success,
            last_assessed=datetime.now(),
            notes=getattr(existing, "notes", ""),
        )

        self._memory.store_capability(updated)
        return updated

    def get_capability(self, name: str) -> CapabilityProfile | None:
        return self._memory.get_capability_by_name(name)

    def get_all_capabilities(self) -> list[CapabilityProfile]:
        return self._memory.get_capabilities()

    # ------------------------------------------------------------------
    # Strengths
    # ------------------------------------------------------------------

    def identify_strength(self, area: str, description: str, confidence: float = 0.7) -> StrengthProfile:
        """Identify a strength area."""
        self._strength_counter += 1
        profile = StrengthProfile(
            profile_id=f"STR-{self._strength_counter:06d}",
            area=area,
            description=description,
            confidence=confidence,
        )
        self._memory.store_strength(profile)
        return profile

    def get_strengths(self) -> list[StrengthProfile]:
        return self._memory.get_strengths()

    # ------------------------------------------------------------------
    # Weaknesses
    # ------------------------------------------------------------------

    def identify_weakness(
        self,
        area: str,
        description: str,
        severity: int = 3,
        mitigation: str = "",
    ) -> WeaknessProfile:
        """Identify a weakness area with optional mitigation strategy."""
        self._weakness_counter += 1
        profile = WeaknessProfile(
            profile_id=f"WEAK-{self._weakness_counter:06d}",
            area=area,
            description=description,
            severity=severity,
            mitigation=mitigation,
        )
        self._memory.store_weakness(profile)
        return profile

    def get_weaknesses(self) -> list[WeaknessProfile]:
        return self._memory.get_weaknesses()

    # ------------------------------------------------------------------
    # Auto-profiling from capability data
    # ------------------------------------------------------------------

    def auto_profile(self) -> tuple[list[StrengthProfile], list[WeaknessProfile]]:
        """
        Automatically identify strengths and weaknesses from capability profiles.

        High-confidence, stable capabilities become strengths.
        Low-confidence, unstable capabilities become weaknesses.
        """
        capabilities = self._memory.get_capabilities()
        new_strengths: list[StrengthProfile] = []
        new_weaknesses: list[WeaknessProfile] = []

        for cap in capabilities:
            conf = getattr(cap, "confidence", 0.5)
            stability = getattr(cap, "stability", 0.5)

            if conf >= 0.7 and stability >= 0.6:
                new_strengths.append(self.identify_strength(
                    area=cap.capability_name,
                    description=getattr(cap, "description", ""),
                    confidence=conf,
                ))
            elif conf < 0.4 or stability < 0.3:
                new_weaknesses.append(self.identify_weakness(
                    area=cap.capability_name,
                    description=getattr(cap, "description", ""),
                    severity=int((1.0 - stability) * 10),
                    mitigation="Needs more practice and error analysis",
                ))

        return new_strengths, new_weaknesses

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _assess_maturity(
        usage_count: int,
        success_count: int,
        current: MaturityLevel,
    ) -> MaturityLevel:
        """Assess maturity based on usage and success history."""
        if usage_count < 5:
            return MaturityLevel.EMERGING
        if usage_count < 20:
            return MaturityLevel.DEVELOPING

        success_rate = success_count / usage_count if usage_count > 0 else 0

        if success_rate >= 0.9 and usage_count >= 50:
            return MaturityLevel.MATURE
        if success_rate >= 0.7:
            return MaturityLevel.STABLE
        if success_rate < 0.4:
            return MaturityLevel.DECLINING

        return current

    def summary(self) -> dict:
        """Return a summary of capability state."""
        caps = self._memory.get_capabilities()
        return {
            "capabilities_tracked": len(caps),
            "mature_count": sum(1 for c in caps if getattr(c, "maturity", None) == MaturityLevel.MATURE),
            "stable_count": sum(1 for c in caps if getattr(c, "maturity", None) == MaturityLevel.STABLE),
            "developing_count": sum(1 for c in caps if getattr(c, "maturity", None) == MaturityLevel.DEVELOPING),
            "strengths": len(self._memory.get_strengths()),
            "weaknesses": len(self._memory.get_weaknesses()),
            "avg_confidence": round(
                sum(getattr(c, "confidence", 0) for c in caps) / max(1, len(caps)), 3
            ),
        }

    @property
    def memory(self):
        return self._memory