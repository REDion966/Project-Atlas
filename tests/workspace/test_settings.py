"""Atlas WorkspaceSettings — legacy-tolerance regression tests.

Reproduces the real-world Stage-2 blocker: legacy ``~/.atlas/workspace.json``
files may lack the top-level ``settings`` object (or individual fields), and
``WorkspaceSettings.from_dict`` previously raised ``KeyError: 'created_at'``
on them, crashing every CLI invocation before dispatch.

Pure verification. No I/O.
"""

from __future__ import annotations

from datetime import datetime, timezone

from atlas.workspace.models.settings import WorkspaceSettings


class TestFromDictLegacyTolerance:
    def test_empty_settings_dict_uses_defaults(self):
        settings = WorkspaceSettings.from_dict({})

        assert settings.version == "1.0"
        assert settings.autosave is True
        assert settings.default_project_id == ""
        assert settings.ai_provider == ""
        assert isinstance(settings.created_at, datetime)
        assert isinstance(settings.updated_at, datetime)

    def test_present_fields_are_parsed(self):
        settings = WorkspaceSettings.from_dict(
            {
                "version": "1.1",
                "autosave": False,
                "default_project_id": "proj-1",
                "ai_provider": "ollama",
                "created_at": "2026-01-02T03:04:05+00:00",
                "updated_at": "2026-01-03T03:04:05+00:00",
            }
        )

        assert settings.version == "1.1"
        assert settings.autosave is False
        assert settings.default_project_id == "proj-1"
        assert settings.ai_provider == "ollama"
        assert settings.created_at.isoformat() == "2026-01-02T03:04:05+00:00"
        assert settings.updated_at.isoformat() == "2026-01-03T03:04:05+00:00"

    def test_partial_settings_fill_only_missing_fields(self):
        settings = WorkspaceSettings.from_dict({"version": "2.0"})

        assert settings.version == "2.0"
        assert settings.autosave is True
        assert isinstance(settings.created_at, datetime)

    def test_round_trip_preserves_values(self):
        original = WorkspaceSettings.from_dict(
            {
                "version": "1.0",
                "autosave": True,
                "created_at": "2026-06-01T00:00:00+00:00",
                "updated_at": "2026-06-01T00:00:00+00:00",
            }
        )
        restored = WorkspaceSettings.from_dict(original.to_dict())

        assert restored.to_dict() == original.to_dict()