"""Shared pytest fixtures for the Phase 17.1–17.3 research tests."""

import pytest


@pytest.fixture(scope="module")
def safe_kernel_config(tmp_path_factory):
    """Make every ``Atlas()`` this module builds load a controlled safe config.

    Points ``atlas.kernel.atlas.Configuration`` at a temp ``config.toml`` with
    every opt-in left at its code default (no ``external_providers``,
    ``allow_fallback``, ``web_allowed_hosts`` or ``[development.envelope]``).
    Tests that assert the *default* posture then verify the code's behaviour
    instead of the operator's live ``config.toml``. The original is restored
    after the module.
    """
    from tests.safe_kernel_config import bound_configuration, write_safe_config

    config_path = write_safe_config(tmp_path_factory.mktemp("safe_kernel_config"))

    import atlas.kernel.atlas as kernel_mod

    original = kernel_mod.Configuration
    kernel_mod.Configuration = bound_configuration(config_path)
    try:
        yield config_path
    finally:
        kernel_mod.Configuration = original


@pytest.fixture(scope="session", autouse=True)
def _isolate_kernel_config_session(tmp_path_factory):
    """Session-wide: every ``Atlas()`` loads a controlled safe ``config.toml``.

    No test should depend on the operator's live ``config.toml``. Without this,
    a single operator opt-in (e.g. ``external_providers = true``) leaks into
    every kernel-building test — flipping assertions *and* making tests attempt
    real provider calls. Tests that read the real file or build their own
    ``Configuration`` are unaffected.
    """
    from tests.safe_kernel_config import bound_configuration, write_safe_config

    config_path = write_safe_config(tmp_path_factory.mktemp("session_safe_config"))

    import atlas.kernel.atlas as kernel_mod

    original = kernel_mod.Configuration
    kernel_mod.Configuration = bound_configuration(config_path)
    try:
        yield config_path
    finally:
        kernel_mod.Configuration = original


@pytest.fixture
def sample_document_path(tmp_path):
    """A real markdown document file on disk."""
    doc = tmp_path / "guide.md"
    doc.write_text("# Atlas\n\nHow does Atlas implement architecture governance?\n", encoding="utf-8")
    return doc


@pytest.fixture
def sample_code_path(tmp_path):
    """A real Python source file on disk."""
    code = tmp_path / "planner.py"
    code.write_text("def plan() -> str:\n    return 'ok'\n", encoding="utf-8")
    return code
