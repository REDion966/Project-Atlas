"""Track C — Long-Term Learning storage protocol tests (Batch 1).

Verifies the :class:`LongTermStorage` protocol is importable, runtime
checkable, and structurally compatible with the model types it references.
"""

from typing import Protocol

from atlas.longterm.models import (
    ConsolidationRecord,
    Episode,
    EpisodeEvent,
    Procedure,
)
from atlas.longterm.storage_protocol import LongTermStorage


class TestLongTermStorageProtocol:
    def test_is_protocol(self):
        assert issubclass(LongTermStorage, Protocol)

    def test_is_runtime_checkable(self):
        # @runtime_checkable decorator adds __instancecheck__ to the protocol class.
        assert hasattr(LongTermStorage, "__instancecheck__")

    def test_has_lifecycle_methods(self):
        for method in ("initialize", "close", "is_available"):
            assert hasattr(LongTermStorage, method)

    def test_has_episode_methods(self):
        for method in ("store_episode", "load_episodes", "load_episode"):
            assert hasattr(LongTermStorage, method)

    def test_has_episode_event_methods(self):
        for method in ("store_episode_event", "load_episode_events"):
            assert hasattr(LongTermStorage, method)

    def test_has_procedure_methods(self):
        for method in ("store_procedure", "load_procedures", "load_procedure"):
            assert hasattr(LongTermStorage, method)

    def test_has_consolidation_methods(self):
        for method in ("store_consolidation_record", "load_consolidation_records"):
            assert hasattr(LongTermStorage, method)

    def test_model_types_are_importable(self):
        assert Episode is not None
        assert EpisodeEvent is not None
        assert Procedure is not None
        assert ConsolidationRecord is not None