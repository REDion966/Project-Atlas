"""Shared pytest fixtures for the Phase 17.1–17.3 research tests."""

import pytest


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
