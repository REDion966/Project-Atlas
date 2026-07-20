"""
Atlas Goal Manager
"""

from __future__ import annotations

from atlas.agents.goal import Goal


class GoalManager:

    def __init__(self):

        self._goals: list[Goal] = []

    def add(
        self,
        goal: Goal,
    ) -> None:

        self._goals.append(goal)

    def all(self) -> list[Goal]:

        return list(self._goals)