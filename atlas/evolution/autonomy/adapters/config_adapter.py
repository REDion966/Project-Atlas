"""Production ``StateReader`` adapter for the CONFIG scope.

Wraps the real :class:`~atlas.config.configuration.Configuration` and
implements the read side of the Phase 16 protocols from
:mod:`atlas.evolution.autonomy.applier`.

Namespace (deterministic): ``config.<key.path>`` where ``key.path`` uses
dots to address nested settings (e.g. ``config.ai.provider``).

IMPORTANT — staged-config safety boundary:

The existing Phase 16 architecture NEVER mutates live configuration.
``ConfigApplier`` stages entries as ``StagedConfigEntry`` records that are
activated at next boot (Phase 16.7 ``BootActivationService``), and the
``ScheduleStore``/``staged_config`` table is the governing persistence for
that path. There is no live config-write API inside ``Configuration``.

Therefore this adapter is deliberately **read-oriented only**. It
implements ``read``/``has`` (StateReader) and fails closed on
``write``/``remove`` (StateWriter) with a documented error, preserving the
constitutional safety boundary rather than inventing live mutation
behavior. Writes to config state must continue to flow through the
governed staged-config path — never through a raw adapter.

This decision is explained here and in the adapter tests rather than
faked or papered over.

Pure adapter layer: no governance, no AI, no async, no new persistence.
"""

from __future__ import annotations

from typing import Any

from atlas.config.configuration import Configuration
from atlas.evolution.autonomy.applier import StateReader, StateWriter

#: Deterministic namespace prefix for CONFIG-scope state keys.
CONFIG_NAMESPACE = "config."


class ConfigWriteUnsupportedError(NotImplementedError):
    """Raised for config writes; config mutation is governed/staged only."""


class ConfigStateAdapter(StateReader, StateWriter):
    """Production config-scope adapter over ``Configuration`` (read-only).

    Writes are intentionally unsupported: config changes must flow through
    the Phase 16 staged-config path (ConfigApplier + ScheduleStore + boot
    activation), not through a live-mutation adapter.
    """

    def __init__(self, configuration: Configuration) -> None:
        if configuration is None:
            raise ValueError("Configuration is required")
        self._configuration = configuration

    # ------------------------------------------------------------------
    # Key normalization
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize(key: str) -> tuple[str, ...]:
        """Convert ``config.<a>.<b>`` to the tuple ``("a", "b")``.

        Accepts both the namespaced form and the bare dotted form.
        """
        if key.startswith(CONFIG_NAMESPACE):
            key = key[len(CONFIG_NAMESPACE):]
        parts = [p for p in key.split(".") if p]
        if not parts:
            raise ValueError("Config key cannot be empty")
        return tuple(parts)

    # ------------------------------------------------------------------
    # StateReader
    # ------------------------------------------------------------------

    def read(self, key: str, default: Any = None) -> Any:
        """Return the configuration value at ``key``, or ``default``.

        Resolution uses the existing ``Configuration.get(*keys, default=)``
        path so behavior matches every other Atlas config accessor.
        """
        parts = self._normalize(key)
        return self._configuration.get(*parts, default=default)

    def has(self, key: str) -> bool:
        """Return True when a non-None value exists at ``key``.

        ``has`` uses the sentinel-``default`` trick so a configured value
        that is ``None`` still reads as present.
        """
        sentinel = object()
        return self.read(key, default=sentinel) is not sentinel

    # ------------------------------------------------------------------
    # StateWriter — intentionally unsupported
    # ------------------------------------------------------------------

    def write(self, key: str, value: Any) -> None:
        """Fail closed: config writes are not allowed via this adapter.

        Config changes MUST flow through the governed staged-config path
        (ConfigApplier → ScheduleStore → boot activation).
        """
        raise ConfigWriteUnsupportedError(
            "ConfigStateAdapter is read-only by design: config mutation is "
            "governed through the Phase 16 staged-config path, never a "
            "live-mutation adapter."
        )

    def remove(self, key: str) -> bool:
        """Fail closed: config removal is not allowed via this adapter."""
        raise ConfigWriteUnsupportedError(
            "ConfigStateAdapter is read-only by design: config removal is "
            "governed through the Phase 16 staged-config path, never a "
            "live-mutation adapter."
        )
