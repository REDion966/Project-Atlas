"""Atlas Long-Term Learning — EpisodicRepository (Track C, Batch 2).

Bounded in-memory store for episodes and episode events. Storage-agnostic:
persistence is delegated to an injected :class:`LongTermStorage` protocol
adapter (dual-write, best-effort). Failures in storage writes never break
the in-memory path.

Pure logic. No SQLite. No kernel. No gateway. No runtime. No events.
"""

from __future__ import annotations

import logging
from collections import deque
from datetime import datetime
from typing import Any

from atlas.longterm.models import Episode, EpisodeEvent

logger = logging.getLogger(__name__)


class EpisodicRepository:
    """Bounded repository for episodic memory.

    Stores :class:`Episode` and :class:`EpisodeEvent` objects in memory.
    When a ``LongTermStorage`` adapter is injected, writes are dual-routed
    (best-effort; storage failures are logged and swallowed). Reads fall
    back to memory when storage is unavailable.
    """

    def __init__(
        self,
        max_episodes: int = 10_000,
        max_events_per_episode: int = 1_000,
        storage: Any | None = None,
    ) -> None:
        """Initialize the repository.

        Args:
            max_episodes: Maximum number of episodes retained before eviction.
            max_events_per_episode: Maximum events kept per episode.
            storage: Optional ``LongTermStorage`` protocol adapter.
        """
        if max_episodes <= 0:
            raise ValueError("max_episodes must be positive")
        if max_events_per_episode <= 0:
            raise ValueError("max_events_per_episode must be positive")

        self._max_episodes = max_episodes
        self._max_events_per_episode = max_events_per_episode
        self._storage = storage

        self._episodes: deque[Episode] = deque(maxlen=max_episodes)
        self._episode_index: dict[str, Episode] = {}
        self._events: dict[str, list[EpisodeEvent]] = {}

    # ------------------------------------------------------------------
    # Episodes
    # ------------------------------------------------------------------

    def store_episode(self, episode: Episode) -> None:
        """Store or update an episode.

        If the episode already exists, the old entry is replaced. If the
        store is full, the oldest episode is evicted (and removed from the
        index).
        """
        old = self._episode_index.get(episode.episode_id)
        if old is not None:
            # Replace in place in the deque.
            self._episodes.remove(old)
            self._episodes.append(episode)
            self._episode_index[episode.episode_id] = episode
        else:
            if len(self._episodes) == self._max_episodes:
                # Manually evict the oldest so the index stays consistent.
                evicted = self._episodes.popleft()
                self._episode_index.pop(evicted.episode_id, None)
            self._episodes.append(episode)
            self._episode_index[episode.episode_id] = episode
        self._try_storage_write("store_episode", episode)

    def get_episode(self, episode_id: str) -> Episode | None:
        """Retrieve a single episode by ID."""
        return self._episode_index.get(episode_id)

    def get_episodes(self, n: int = 100) -> list[Episode]:
        """Return the most recent n episodes (newest first)."""
        if n <= 0:
            return []
        return list(reversed(self._episodes))[:n]

    def get_episodes_since(self, since: datetime) -> list[Episode]:
        """Return episodes with started_at >= the given timestamp (oldest first)."""
        return [e for e in self._episodes if e.started_at >= since]

    def get_episodes_by_kind(self, kind: Any, n: int = 100) -> list[Episode]:
        """Return episodes filtered by kind (newest first)."""
        if n <= 0:
            return []
        return [e for e in reversed(self._episodes) if e.kind == kind][:n]

    def get_episodes_by_outcome(self, outcome: str, n: int = 100) -> list[Episode]:
        """Return episodes filtered by outcome (newest first)."""
        if n <= 0:
            return []
        return [e for e in reversed(self._episodes) if e.outcome == outcome][:n]

    def get_episodes_by_source(self, source_experience_id: str) -> list[Episode]:
        """Return episodes linked to a given experience ID."""
        return [
            e for e in self._episodes
            if e.source_experience_id == source_experience_id
        ]

    def remove_episode(self, episode_id: str) -> bool:
        """Remove an episode and its events. Returns True if removed."""
        episode = self._episode_index.pop(episode_id, None)
        if episode is None:
            return False
        try:
            self._episodes.remove(episode)
        except ValueError:
            pass
        self._events.pop(episode_id, None)
        return True

    @property
    def episode_count(self) -> int:
        """Number of episodes stored."""
        return len(self._episodes)

    def _try_evict_oldest(self) -> None:
        """Evict the oldest episode if over the max (deque handles it)."""
        # The deque maxlen handles eviction automatically on append.
        pass

    # ------------------------------------------------------------------
    # Episode events
    # ------------------------------------------------------------------

    def store_event(self, event: EpisodeEvent) -> None:
        """Append or overwrite an event for an episode.

        Events are stored per-episode in an ordered list (by sequence).
        Duplicates (same event_id) are replaced in place.
        """
        ep_events = self._events.setdefault(event.episode_id, [])
        for i, existing in enumerate(ep_events):
            if existing.event_id == event.event_id:
                ep_events[i] = event
                break
        else:
            ep_events.append(event)
            # Bound per-episode event count.
            if len(ep_events) > self._max_events_per_episode:
                del ep_events[: len(ep_events) - self._max_events_per_episode]
        self._try_storage_write("store_episode_event", event)

    def get_events(self, episode_id: str) -> list[EpisodeEvent]:
        """Return events for an episode, ordered by sequence."""
        return list(self._events.get(episode_id, []))

    def get_event(self, episode_id: str, event_id: str) -> EpisodeEvent | None:
        """Retrieve a single event by episode/event ID."""
        for event in self._events.get(episode_id, []):
            if event.event_id == event_id:
                return event
        return None

    def remove_events(self, episode_id: str) -> bool:
        """Remove all events for an episode. Returns True if any existed."""
        return self._events.pop(episode_id, None) is not None

    # ------------------------------------------------------------------
    # Summary & admin
    # ------------------------------------------------------------------

    def summary(self) -> dict[str, Any]:
        """Return a summary dict of the repository state."""
        return {
            "episode_count": self.episode_count,
            "max_episodes": self._max_episodes,
            "max_events_per_episode": self._max_events_per_episode,
            "storage_available": self._storage is not None and bool(
                getattr(self._storage, "is_available", lambda: False)()
            ),
        }

    def clear(self) -> None:
        """Clear all stored data."""
        self._episodes.clear()
        self._episode_index.clear()
        self._events.clear()

    # ------------------------------------------------------------------
    # Storage integration (best-effort dual-write)
    # ------------------------------------------------------------------

    def _try_storage_write(self, method_name: str, data: object) -> None:
        """Write to the storage adapter, degrading gracefully on failure."""
        storage = self._storage
        if storage is None:
            return
        try:
            if not storage.is_available():
                return
            if method_name == "store_episode":
                storage.store_episode(data)  # type: ignore[arg-type]
            elif method_name == "store_episode_event":
                storage.store_episode_event(data)  # type: ignore[arg-type]
        except Exception:
            logger.exception("Long-term episode storage write failed for %s", method_name)

    def restore(self) -> dict[str, Any]:
        """Load persisted episodes/events from storage into memory.

        Returns a summary dict: ``{"restored_episodes": int, "restored_events": int}``.
        If no storage is injected or the storage is unavailable, returns zeros.
        """
        storage = self._storage
        if storage is None:
            return {"restored_episodes": 0, "restored_events": 0}
        try:
            if not storage.is_available():
                return {"restored_episodes": 0, "restored_events": 0}
            episodes = storage.load_episodes()
            for ep in episodes:
                if ep.episode_id in self._episode_index:
                    continue
                self._episodes.append(ep)
                self._episode_index[ep.episode_id] = ep
                for ev in storage.load_episode_events(ep.episode_id):
                    self._events.setdefault(ep.episode_id, []).append(ev)
        except Exception:
            logger.exception("Failed to restore episodes from storage")

        restored_episodes = len(self._episodes)
        restored_events = sum(len(v) for v in self._events.values())
        return {
            "restored_episodes": restored_episodes,
            "restored_events": restored_events,
        }
