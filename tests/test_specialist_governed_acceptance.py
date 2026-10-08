"""Kernel-level — the OPT-IN specialist route into the EXISTING governed cycle.

Pins the Command 3B wiring at the NORMAL entry point
(``Atlas.development_authoring_request``):

  * with ``[specialists].enabled = false`` (default) no specialist is built and a
    request that supplies no code block fails closed (no proposal, no execution);
  * with ``[specialists].enabled = true`` and a (fake) provider, a request that
    supplies no code block is authored by the specialist and reaches
    ``PENDING_APPROVAL`` — as an UNTRUSTED draft that still requires OWNER
    approval and governed execution;
  * an EXPLICITLY SUPPLIED edit still wins (deterministic-first): the structural
    route is used and the specialist is not consulted.

IMPORT NOTE — all ``atlas`` modules are imported LAZILY (via ``importlib``)
inside the helpers rather than at module scope. This kernel-starting test is far
too heavy for the bounded sandbox verification leg (it starts Atlas several times
and needs ``config.toml``, which the verification closure does not carry). The
repository map derives its test→module dependency graph from static ``import``
statements, so a lazy import keeps this test OUT of the bounded verification
target set for the modules it exercises and prevents it from being chosen as an
unsuitable verification target for unrelated changes. The transport is a fake; no
model, network or repository mutation is involved.
"""

from __future__ import annotations

import importlib
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
TARGET = "atlas/specialist_transport.py"
REQUEST = (
    "Add a module-level comment to atlas/specialist_transport.py describing "
    "the local transport, preserving behaviour."
)


def _enable_specialists(text: str) -> str:
    out = []
    inside = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("["):
            inside = stripped == "[specialists]"
        if inside and stripped == "enabled = false":
            line = line.replace("false", "true")
        out.append(line)
    return "\n".join(out)


def _config_class(config_path: pathlib.Path):
    Configuration = importlib.import_module("atlas.config.configuration").Configuration

    class _TmpConfiguration(Configuration):
        def __init__(self):
            super().__init__(filename=str(config_path))

    return _TmpConfiguration


def _storage_class(tmp_path: pathlib.Path):
    module = importlib.import_module("tests.test_durable_guided_improvement")
    return module._storage_class(tmp_path)


@pytest.fixture
def _fake_transport(monkeypatch):
    transport_mod = importlib.import_module("atlas.specialist_transport")
    body = (ROOT / TARGET).read_text(encoding="utf-8") + "\n# local-only note\n"

    def _factory(**kwargs):
        def _transport(request):
            return {"files": {TARGET: body}, "note": "fake"}

        return _transport

    monkeypatch.setattr(transport_mod, "ollama_transport", _factory)


def _started_atlas(monkeypatch, tmp_path, *, enabled: bool):
    monkeypatch.setattr(
        "atlas.kernel.atlas.SQLiteEvolutionStorage", _storage_class(tmp_path)
    )
    text = (ROOT / "config.toml").read_text(encoding="utf-8")
    if enabled:
        text = _enable_specialists(text)
    config_path = tmp_path / "config.toml"
    config_path.write_text(text, encoding="utf-8")
    monkeypatch.setattr(
        "atlas.kernel.atlas.Configuration", _config_class(config_path)
    )
    Atlas = importlib.import_module("atlas.kernel.atlas").Atlas

    atlas = Atlas()
    atlas.start()
    return atlas


class TestSpecialistRoute:
    def test_specialist_route_reaches_pending_approval(
        self, monkeypatch, tmp_path, _fake_transport
    ):
        atlas = _started_atlas(monkeypatch, tmp_path, enabled=True)
        try:
            assert atlas._specialist_author is not None  # noqa: SLF001
            payload = atlas.development_authoring_request(REQUEST)
            assert payload["ok"] is True, payload
            assert payload["proposal_status"] == "PENDING_APPROVAL"
            assert payload["entry"] is None  # specialist route, not supplied edit
            assert payload["authorized"] is False
            assert payload["executed"] is False
            assert payload["specialist"]["capability"] == "code.generate"
            assert payload["specialist"]["paths"] == [TARGET]
        finally:
            atlas.shutdown()

    def test_provider_disabled_fails_closed(self, monkeypatch, tmp_path):
        atlas = _started_atlas(monkeypatch, tmp_path, enabled=False)
        try:
            assert atlas._specialist_author is None  # noqa: SLF001
            payload = atlas.development_authoring_request(REQUEST)
            assert payload["ok"] is False
            assert payload["proposal_id"] == ""
            assert payload["authorized"] is False
            assert payload["executed"] is False
        finally:
            atlas.shutdown()

    def test_explicit_supplied_edit_still_wins(
        self, monkeypatch, tmp_path, _fake_transport
    ):
        atlas = _started_atlas(monkeypatch, tmp_path, enabled=True)
        try:
            request = (
                "Update the explicitly named helper `_indent_of` in "
                "atlas/evolution/structural_editor.py while preserving its "
                "public interface:\n\n"
                "```python\n"
                "def _indent_of(line: str) -> str:\n    return ''\n"
                "```\n"
            )
            payload = atlas.development_authoring_request(request)
            assert payload["ok"] is True, payload
            assert payload["entry"]["path"] == "atlas/evolution/structural_editor.py"
            assert payload["specialist"] is None
        finally:
            atlas.shutdown()
