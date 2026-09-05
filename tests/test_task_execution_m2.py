"""M2 — Task execution contract regression tests (F1 fix).

Proves the approved :meth:`Task.run()` contract:

  * a non-terminal task transitions RUNNING -> FAILED with a clear reason and
    never performs external work;
  * a terminal task (COMPLETED / FAILED / CANCELLED) is left untouched;
  * a scheduled task can reach :meth:`Worker.execute()` without raising the
    previous ``AttributeError``.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from atlas.scheduler.scheduler import Scheduler
from atlas.scheduler.worker import Worker
from atlas.task.task import Task
from atlas.task.task_status import TaskStatus


class TestTaskRunContract:
    """Pinned behavioral contract for ``Task.run()`` (M2/F1)."""

    def test_pending_task_runs_to_failed_with_reason(self):
        task = Task(name="pending-task")
        assert task.status is TaskStatus.PENDING

        result = task.run()

        assert result is None
        assert task.status is TaskStatus.FAILED
        assert task.started_at is not None
        assert task.finished_at is not None
        assert task.error == "Task has no executable payload"

    def test_running_task_runs_to_failed(self):
        task = Task(name="running-task")
        task.start()
        assert task.status is TaskStatus.RUNNING

        task.run()

        assert task.status is TaskStatus.FAILED
        assert task.error == "Task has no executable payload"

    def test_paused_task_runs_to_failed(self):
        task = Task(name="paused-task")
        task.pause()
        assert task.status is TaskStatus.PAUSED

        task.run()

        assert task.status is TaskStatus.FAILED
        assert task.error == "Task has no executable payload"

    def test_completed_task_is_left_untouched(self):
        task = Task(name="done-task")
        task.start()
        task.complete()
        finished_at = task.finished_at

        result = task.run()

        assert result is None
        assert task.status is TaskStatus.COMPLETED
        assert task.finished_at == finished_at
        assert task.error is None

    def test_failed_task_preserves_existing_error(self):
        task = Task(name="failed-task")
        task.start()
        task.fail("original failure")
        original_finished = task.finished_at

        result = task.run()

        assert result is None
        assert task.status is TaskStatus.FAILED
        assert task.error == "original failure"
        assert task.finished_at == original_finished

    def test_cancelled_task_is_left_untouched(self):
        task = Task(name="cancelled-task")
        task.cancel()
        finished_at = task.finished_at

        result = task.run()

        assert result is None
        assert task.status is TaskStatus.CANCELLED
        assert task.finished_at == finished_at

    def test_run_does_not_invoke_external_execution(self, monkeypatch):
        """``run()`` must not reach tools, capabilities, orchestration,
        evolution, AI providers, filesystem, or network."""
        import atlas.task.task as task_mod

        task = Task(name="isolated-task")

        # Remove any attribute that could imply external execution; the method
        # must succeed using only the lifecycle helpers it already owns.
        assert task.run() is None
        assert task.status is TaskStatus.FAILED

        # The module must not import execution machinery.
        src = inspect_getsource(task_mod)
        for forbidden in (
            "ToolExecutor",
            "OrchestrationExecutor",
            "GoalExecutionEngine",
            "EvolutionScheduler",
            "SelfDevelopmentLoop",
            "CapabilityRegistry",
            "open(",
            "requests.",
            "subprocess.",
        ):
            assert forbidden not in src


def inspect_getsource(mod):
    import inspect
    return inspect.getsource(mod)


class TestWorkerExecuteDoesNotCrash:
    """A scheduled task must reach ``Worker.execute()`` without the previous
    ``AttributeError``."""

    def test_worker_execute_completes_without_attribute_error(self):
        task = Task(name="scheduled-task")
        scheduler = Scheduler()
        scheduled = scheduler.schedule(task, datetime(2020, 1, 1))

        worker = Worker()
        worker.execute(scheduled)  # must not raise AttributeError

        assert scheduled.executed is True
        assert task.status is TaskStatus.FAILED
        assert task.error == "Task has no executable payload"

    def test_scheduler_tick_runs_due_task_safely(self):
        task = Task(name="tick-task")
        scheduler = Scheduler()
        scheduler.schedule(task, datetime(2020, 1, 1))  # long past due

        scheduler.tick()  # must not raise

        assert task.status is TaskStatus.FAILED
