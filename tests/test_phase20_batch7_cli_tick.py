"""
Phase 20 Batch 7 — Make Atlas.tick() reachable from the CLI.

Tests proving a completed CLI interaction invokes Atlas.tick() exactly
once, and that Atlas.tick() itself coordinates TaskManager, Evolution
Scheduler, and GoalExecutionEngine.settle().

Uses fakes/mocks only — no real evolution/model providers.
"""

import unittest
from unittest.mock import MagicMock, patch

from atlas.kernel.atlas import Atlas


class FakeStreamingAtlas:
    """Fake Atlas that records lifecycle calls and yields chunks."""

    def __init__(self):
        self.start_calls = 0
        self.shutdown_calls = 0
        self.tick_calls = 0
        self.stream_calls = 0

    def start(self):
        self.start_calls += 1

    def shutdown(self):
        self.shutdown_calls += 1

    def tick(self):
        self.tick_calls += 1

    def stream(self, text):
        self.stream_calls += 1
        yield f"reply:{text}"


class TestCLIRunTick(unittest.TestCase):
    """A/B/C: tick is invoked once per completed interaction."""

    def _run_cli(self, inputs):
        fake = FakeStreamingAtlas()
        with patch("atlas.cli.cli.Atlas", return_value=fake):
            from atlas.cli.cli import AtlasCLI

            cli = AtlasCLI()
            with patch("builtins.input", side_effect=inputs):
                with patch("builtins.print"):
                    cli.run()
        return fake

    def test_normal_interaction_triggers_tick(self):
        """A: a normal interaction causes Atlas.tick() to be invoked."""
        fake = self._run_cli(["hello", "exit"])

        self.assertEqual(fake.tick_calls, 1)
        self.assertEqual(fake.stream_calls, 1)
        self.assertEqual(fake.shutdown_calls, 1)

    def test_tick_once_per_interaction(self):
        """B: tick is invoked exactly once per completed interaction."""
        fake = self._run_cli(["first", "second", "exit"])

        self.assertEqual(fake.tick_calls, 2)
        self.assertEqual(fake.stream_calls, 2)

    def test_slash_command_does_not_tick(self):
        """C: slash commands and blank lines never invoke tick."""
        fake = self._run_cli(["/help", "", "exit"])

        self.assertEqual(fake.tick_calls, 0)
        self.assertEqual(fake.stream_calls, 0)


class TestAtlasTickCoordination(unittest.TestCase):
    """Kernel-level: Atlas.tick() coordinates its three subsystems."""

    def test_tick_calls_task_scheduler_and_goal_settle(self):
        atlas = Atlas()

        task_manager = MagicMock()
        scheduler = MagicMock()
        goal_executor = MagicMock()

        atlas._task_manager = task_manager
        atlas._evolution_scheduler = scheduler
        atlas._goal_executor = goal_executor

        atlas.tick()

        task_manager.tick.assert_called_once_with()
        scheduler.tick.assert_called_once_with()
        goal_executor.settle.assert_called_once_with()

    def test_tick_is_fail_soft_without_scheduler(self):
        """Missing evolution scheduler must not break the tick."""
        atlas = Atlas()
        task_manager = MagicMock()
        goal_executor = MagicMock()

        atlas._task_manager = task_manager
        atlas._evolution_scheduler = None
        atlas._goal_executor = goal_executor

        atlas.tick()

        task_manager.tick.assert_called_once_with()
        goal_executor.settle.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
