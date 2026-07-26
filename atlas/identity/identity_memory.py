"""
Atlas Identity Memory — Phase 8.0 Cognitive Identity Foundation.

Bounded storage for identity components. No unlimited growth.
All collections use configurable maximum sizes with oldest-first eviction.
Pure logic — no infrastructure dependencies.
"""

from collections import deque
from typing import Any


class IdentityMemory:
    """
    Bounded in-memory storage for identity data.

    Every collection has a maximum capacity. When exceeded, the
    oldest entries are evicted first. This prevents unlimited growth
    and keeps identity memory bounded and predictable.
    """

    def __init__(
        self,
        max_beliefs: int = 200,
        max_goals: int = 20,
        max_principles: int = 30,
        max_preferences: int = 50,
        max_strengths: int = 30,
        max_weaknesses: int = 30,
        max_capability_profiles: int = 100,
        max_improvement_history: int = 200,
    ):
        if any(v <= 0 for v in [
            max_beliefs, max_goals, max_principles, max_preferences,
            max_strengths, max_weaknesses, max_capability_profiles,
            max_improvement_history,
        ]):
            raise ValueError("All max sizes must be positive integers")

        self._max_beliefs = max_beliefs
        self._max_goals = max_goals
        self._max_principles = max_principles
        self._max_preferences = max_preferences
        self._max_strengths = max_strengths
        self._max_weaknesses = max_weaknesses
        self._max_capability_profiles = max_capability_profiles
        self._max_improvement_history = max_improvement_history

        self._beliefs: deque[Any] = deque(maxlen=max_beliefs)
        self._goals: deque[Any] = deque(maxlen=max_goals)
        self._principles: deque[Any] = deque(maxlen=max_principles)
        self._preferences: deque[Any] = deque(maxlen=max_preferences)
        self._strengths: deque[Any] = deque(maxlen=max_strengths)
        self._weaknesses: deque[Any] = deque(maxlen=max_weaknesses)
        self._capability_profiles: deque[Any] = deque(maxlen=max_capability_profiles)
        self._improvement_history: deque[Any] = deque(maxlen=max_improvement_history)

        # Decision style is a singleton — only one current style
        self._decision_style: Any = None

    # ------------------------------------------------------------------
    # Beliefs
    # ------------------------------------------------------------------

    def store_belief(self, belief: Any) -> None:
        """Store a belief. Evicts oldest if at capacity."""
        self._beliefs.append(belief)

    def get_beliefs(self, n: int | None = None) -> list[Any]:
        """Return recent beliefs, newest first."""
        items = list(reversed(self._beliefs))
        return items[:n] if n else items

    def get_beliefs_by_category(self, category: str, n: int = 50) -> list[Any]:
        """Return beliefs matching a category."""
        return [
            b for b in reversed(self._beliefs)
            if getattr(b, "category", "") == category
        ][:n]

    def find_belief_by_id(self, belief_id: str) -> Any | None:
        """Find a belief by its ID."""
        for b in reversed(self._beliefs):
            if getattr(b, "belief_id", "") == belief_id:
                return b
        return None

    def remove_belief(self, belief_id: str) -> bool:
        """Remove a belief by ID. Returns True if found and removed."""
        to_keep = [b for b in self._beliefs if getattr(b, "belief_id", "") != belief_id]
        found = len(to_keep) < len(self._beliefs)
        self._beliefs = deque(to_keep, maxlen=self._max_beliefs)
        return found

    # ------------------------------------------------------------------
    # Goals
    # ------------------------------------------------------------------

    def store_goal(self, goal: Any) -> None:
        self._goals.append(goal)

    def get_goals(self) -> list[Any]:
        return list(reversed(self._goals))

    def get_goal_by_id(self, goal_id: str) -> Any | None:
        for g in reversed(self._goals):
            if getattr(g, "goal_id", "") == goal_id:
                return g
        return None

    # ------------------------------------------------------------------
    # Principles
    # ------------------------------------------------------------------

    def store_principle(self, principle: Any) -> None:
        self._principles.append(principle)

    def get_principles(self) -> list[Any]:
        return list(reversed(self._principles))

    # ------------------------------------------------------------------
    # Engineering Preferences
    # ------------------------------------------------------------------

    def store_preference(self, preference: Any) -> None:
        self._preferences.append(preference)

    def get_preferences(self) -> list[Any]:
        return sorted(
            self._preferences,
            key=lambda p: getattr(p, "priority", 0),
            reverse=True,
        )

    # ------------------------------------------------------------------
    # Strengths / Weaknesses
    # ------------------------------------------------------------------

    def store_strength(self, strength: Any) -> None:
        self._strengths.append(strength)

    def get_strengths(self) -> list[Any]:
        return sorted(
            self._strengths,
            key=lambda s: getattr(s, "confidence", 0),
            reverse=True,
        )

    def store_weakness(self, weakness: Any) -> None:
        self._weaknesses.append(weakness)

    def get_weaknesses(self) -> list[Any]:
        return sorted(
            self._weaknesses,
            key=lambda w: getattr(w, "severity", 0),
            reverse=True,
        )

    # ------------------------------------------------------------------
    # Capability Profiles
    # ------------------------------------------------------------------

    def store_capability(self, profile: Any) -> None:
        self._capability_profiles.append(profile)

    def get_capabilities(self) -> list[Any]:
        return list(reversed(self._capability_profiles))

    def get_capability_by_name(self, name: str) -> Any | None:
        for c in reversed(self._capability_profiles):
            if getattr(c, "capability_name", "") == name:
                return c
        return None

    # ------------------------------------------------------------------
    # Decision Style
    # ------------------------------------------------------------------

    def store_decision_style(self, style: Any) -> None:
        self._decision_style = style

    def get_decision_style(self) -> Any | None:
        return self._decision_style

    # ------------------------------------------------------------------
    # Improvement History
    # ------------------------------------------------------------------

    def store_improvement(self, entry: Any) -> None:
        self._improvement_history.append(entry)

    def get_improvements(self, n: int | None = None) -> list[Any]:
        items = list(reversed(self._improvement_history))
        return items[:n] if n else items

    def get_improvements_by_status(self, status: Any, n: int = 50) -> list[Any]:
        return [
            e for e in reversed(self._improvement_history)
            if getattr(e, "status", None) == status
        ][:n]

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    def summary(self) -> dict[str, int]:
        """Return a summary of memory contents."""
        return {
            "beliefs": len(self._beliefs),
            "goals": len(self._goals),
            "principles": len(self._principles),
            "preferences": len(self._preferences),
            "strengths": len(self._strengths),
            "weaknesses": len(self._weaknesses),
            "capability_profiles": len(self._capability_profiles),
            "improvement_history": len(self._improvement_history),
            "has_decision_style": self._decision_style is not None,
        }

    def clear(self) -> None:
        """Remove all stored data."""
        self._beliefs.clear()
        self._goals.clear()
        self._principles.clear()
        self._preferences.clear()
        self._strengths.clear()
        self._weaknesses.clear()
        self._capability_profiles.clear()
        self._improvement_history.clear()
        self._decision_style = None