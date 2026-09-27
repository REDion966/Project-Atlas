"""Regression guard: ``[development.envelope]`` MUST be parsed into settings.

The parsing path silently regressed once — the ``[development.envelope]`` table
was ignored by ``Configuration.load()``, so ``Configuration.get("development",
"envelope")`` returned ``None`` and the Development Envelope stayed disabled no
matter what ``config.toml`` said.

Unlike the activation suites (which monkeypatch ``Configuration`` to a temp
file), these tests load the REAL repository ``config.toml`` (no monkeypatch, no
temp file, no fake) so this can never silently regress again.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

from atlas.config.configuration import Configuration
from atlas.evolution.development_envelope import DevelopmentEnvelope

REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = REPO_ROOT / "config.toml"

#: The values configured in the repository's real config.toml.
EXPECTED = {
    "enabled": True,
    "allowed_operations": ["sandbox_development"],
    "max_risk_level": "low",
    "max_runs_per_window": 5,
    "window_seconds": 3600,
}


def _file_envelope_table() -> dict:
    with CONFIG_PATH.open("rb") as handle:
        data = tomllib.load(handle)
    return data["development"]["envelope"]


def test_real_config_envelope_is_parsed_and_enabled():
    """The real config.toml's [development.envelope] reaches the settings."""
    configuration = Configuration(str(CONFIG_PATH))
    configuration.load()

    parsed = configuration.get("development", "envelope", default=None)
    assert parsed is not None, "the [development.envelope] table was not parsed"
    # The parsed mapping faithfully mirrors the file's own table.
    assert parsed == _file_envelope_table()
    for key, value in EXPECTED.items():
        assert parsed[key] == value, key

    # Mirror the kernel's exact consumption path:
    # Configuration.get(...) -> DevelopmentEnvelope.from_mapping(...).
    envelope = DevelopmentEnvelope.from_mapping(parsed)
    assert envelope.enabled is True
    assert set(envelope.allowed_operations) == {"sandbox_development"}
    assert envelope.max_risk_level == "low"
    assert envelope.max_runs_per_window == 5
    assert envelope.window_seconds == 3600


def test_absent_envelope_table_remains_fail_closed(tmp_path):
    """Without the table, the envelope must stay disabled (unchanged)."""
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        "[application]\n"
        'name = "Atlas"\n'
        'version = "0.20.0"\n\n'
        "[ai]\n"
        'provider = "Mock Provider"\n'
        'model = "atlas-mock-v1"\n'
        "temperature = 0.7\n"
        "timeout = 300\n\n"
        "[conversation]\n"
        "history_limit = 20\n\n"
        "[logging]\n"
        'level = "INFO"\n\n'
        "[development]\n"
        "model_assisted_authoring = false\n",
        encoding="utf-8",
    )
    configuration = Configuration(str(config_path))
    configuration.load()

    parsed = configuration.get("development", "envelope", default=None)
    assert parsed is None
    assert DevelopmentEnvelope.from_mapping(parsed).enabled is False
