"""Controlled, safe configuration for tests that assert the DEFAULT posture.

A test must never assert "the safe default" by reading the operator's live
``config.toml`` — that couples the assertion to one operator's settings and
breaks the moment that operator legitimately turns a feature on. These helpers
build a controlled temp ``config.toml`` with every opt-in left at its code
default, so such tests verify the CODE's behaviour instead.

The temp config keeps only the tables the loader *requires* (application / ai /
conversation / logging) and deliberately OMITS the safety-relevant keys
(``external_providers``, ``allow_fallback``, ``research.web_allowed_hosts``,
``development.model_assisted_authoring`` and the whole ``[development.envelope]``
table), so the resolved values come from the code defaults.
"""

from __future__ import annotations

from pathlib import Path

#: Minimal config with every opt-in absent (i.e. at its code default).
SAFE_CONFIG_TOML = """\
[application]
name = "Atlas"
version = "0.20.0"

[ai]
provider = "Ollama"
model = "qwen3:8b"
temperature = 0.7
timeout = 300

[conversation]
history_limit = 20

[logging]
level = "INFO"
"""


def write_safe_config(directory: Path) -> Path:
    """Write the controlled safe ``config.toml`` into ``directory``."""
    path = Path(directory) / "config.toml"
    path.write_text(SAFE_CONFIG_TOML, encoding="utf-8")
    return path


def bound_configuration(config_path: Path):
    """Return a ``Configuration`` subclass pinned to ``config_path``.

    Patching ``atlas.kernel.atlas.Configuration`` with the result makes
    ``Atlas()`` load the controlled temp config without touching any
    application logic.
    """
    from atlas.config.configuration import Configuration

    class _BoundConfiguration(Configuration):
        def __init__(self) -> None:  # noqa: D107 - test shim
            super().__init__(filename=str(config_path))

    return _BoundConfiguration
