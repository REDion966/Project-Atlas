"""
Atlas Task Queue

Simple in-memory task queue.
"""

from __future__ import annotations

from collections import deque

from atlas.task.task import Task
from atlas.task.task_status import TaskStatus


class TaskQueue:
    """
    FIFO queue for Atlas tasks.
    """

    def __init__(self):

        self._queue = deque()

    def enqueue(
        self,
        task: Task,
    ) -> None:
        """
        Add a task to the queue.
        """

        task.status = TaskStatus.QUEUED

        self._queue.append(task)

    def dequeue(self) -> Task | None:
        """
        Remove the next task.
        """

        if not self._queue:
            return None

        return self._queue.popleft()

    def peek(self) -> Task | None:
        """
        Return the next task without removing it.
        """

        if not self._queue:
            return None

        return self._queue[0]

    def remove(
        self,
        task_id: str,
    ) -> bool:
        """
        Remove a task by ID.
        """

        for task in list(self._queue):

            if task.id == task_id:

                self._queue.remove(task)

                return True

        return False

    def clear(self) -> None:
        """
        Remove all queued tasks.
        """

        self._queue.clear()

    def size(self) -> int:
        """
        Return queue size.
        """

        return len(self._queue)

    def empty(self) -> bool:
        """
        Return whether queue is empty.
        """

        return len(self._queue) == 0

    def tasks(self) -> list[Task]:
        """
        Return queued tasks.
        """

        return list(self._queue)