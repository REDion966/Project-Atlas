"""Phase 17.2 — Research source adapters: tests.

Covers support detection, normalized outputs, fail-closed behavior, and
protocol conformance for atlas/research/sources/*.
"""

from pathlib import Path

import pytest

from atlas.research.models import SourceKind
from atlas.research.source_adapter import SourceAdapter
from atlas.research.sources import (
    CodebaseSourceAdapter,
    DocumentSourceAdapter,
    WorkspaceSourceAdapter,
)


class TestDocumentSourceAdapter:
    def test_supports_markdown(self, sample_document_path):
        adapter = DocumentSourceAdapter()
        assert adapter.supports(str(sample_document_path))

    def test_supports_file_scheme(self, sample_document_path):
        adapter = DocumentSourceAdapter()
        assert adapter.supports(f"file://{sample_document_path}")

    def test_rejects_unknown_scheme(self):
        adapter = DocumentSourceAdapter()
        assert not adapter.supports("https://example.com/doc.md")

    def test_rejects_code_extension(self, sample_code_path):
        adapter = DocumentSourceAdapter()
        assert not adapter.supports(str(sample_code_path))

    def test_rejects_missing_file(self):
        adapter = DocumentSourceAdapter()
        assert not adapter.supports("does/not/exist.md")

    def test_rejects_empty_uri(self):
        adapter = DocumentSourceAdapter()
        assert not adapter.supports("")

    def test_load_normalizes(self, sample_document_path):
        adapter = DocumentSourceAdapter()
        profile = adapter.load(str(sample_document_path))
        assert profile.kind == SourceKind.DOCUMENT
        assert profile.uri == str(sample_document_path)
        assert "Atlas" in profile.text
        assert profile.language == "markdown"
        assert profile.content_type == "md"
        assert profile.byte_size > 0
        assert profile.tokens_estimate > 0
        assert profile.line_count > 0
        assert "load_error" not in profile.metadata

    def test_load_unsupported_scheme_raises(self):
        adapter = DocumentSourceAdapter()
        with pytest.raises(ValueError):
            adapter.load("https://example.com/doc.md")

    def test_load_empty_uri_raises(self):
        adapter = DocumentSourceAdapter()
        with pytest.raises(ValueError):
            adapter.load("")

    def test_load_missing_file_fails_closed(self, tmp_path):
        adapter = DocumentSourceAdapter()
        profile = adapter.load(str(tmp_path / "missing.md"))
        assert profile.text == ""
        assert profile.byte_size == 0
        assert "load_error" in profile.metadata

    def test_metadata_builds_research_source(self, sample_document_path):
        adapter = DocumentSourceAdapter()
        source = adapter.metadata(str(sample_document_path))
        assert source.uri == str(sample_document_path)
        assert source.kind == SourceKind.DOCUMENT
        assert source.title == "guide.md"

    def test_conforms_to_protocol(self):
        assert isinstance(DocumentSourceAdapter(), SourceAdapter)


class TestWorkspaceSourceAdapter:
    def test_supports_workspace_uri(self, sample_document_path, tmp_path):
        adapter = WorkspaceSourceAdapter(root=tmp_path)
        uri = f"workspace://{sample_document_path.name}"
        assert adapter.supports(uri)

    def test_rejects_path_without_scheme(self, tmp_path):
        adapter = WorkspaceSourceAdapter(root=tmp_path)
        assert not adapter.supports(f"{tmp_path}/guide.md")

    def test_rejects_unknown_scheme(self):
        adapter = WorkspaceSourceAdapter(root=None)
        assert not adapter.supports("file://missing.md")

    def test_rejects_absolute_resource(self, sample_code_path):
        """supports() fails closed on absolute resources — never raises."""
        adapter = WorkspaceSourceAdapter(root=None, resolver=lambda p: sample_code_path)
        assert not adapter.supports(f"workspace://{sample_code_path}")

    def test_load_via_resolver(self, sample_document_path):
        adapter = WorkspaceSourceAdapter(
            root=None,
            resolver=lambda resource_path: sample_document_path,
        )
        uri = "workspace://guide.md"
        profile = adapter.load(uri)
        assert profile.kind == SourceKind.WORKSPACE
        assert profile.uri == uri
        assert "Atlas" in profile.text
        assert "load_error" not in profile.metadata

    def test_load_requires_root_or_resolver(self):
        adapter = WorkspaceSourceAdapter(root=None)
        with pytest.raises(ValueError):
            adapter.load("workspace://guide.md")

    def test_load_empty_uri_raises(self):
        adapter = WorkspaceSourceAdapter(root=None)
        with pytest.raises(ValueError):
            adapter.load("")

    def test_metadata_kind_is_workspace(self, sample_document_path):
        adapter = WorkspaceSourceAdapter(root=None, resolver=lambda p: sample_document_path)
        source = adapter.metadata("workspace://guide.md")
        assert source.kind == SourceKind.WORKSPACE
        assert source.title == "guide.md"

    def test_conforms_to_protocol(self):
        assert isinstance(WorkspaceSourceAdapter(root=None), SourceAdapter)
        assert isinstance(
            WorkspaceSourceAdapter(root=None, resolver=lambda path: Path(path)),
            SourceAdapter,
        )


class TestCodebaseSourceAdapter:
    def test_supports_python(self, sample_code_path):
        adapter = CodebaseSourceAdapter()
        assert adapter.supports(str(sample_code_path))

    def test_supports_code_scheme(self, sample_code_path):
        adapter = CodebaseSourceAdapter()
        assert adapter.supports(f"code://{sample_code_path}")

    def test_accepts_file_scheme(self, sample_code_path):
        adapter = CodebaseSourceAdapter()
        assert adapter.supports(f"file://{sample_code_path}")

    def test_rejects_document_extension(self, sample_document_path):
        adapter = CodebaseSourceAdapter()
        assert not adapter.supports(f"code://{sample_document_path}")

    def test_rejects_unknown_scheme(self):
        adapter = CodebaseSourceAdapter()
        assert not adapter.supports("https://example.com/planner.py")

    def test_rejects_empty_uri(self):
        adapter = CodebaseSourceAdapter()
        assert not adapter.supports("")

    def test_load_normalizes(self, sample_code_path):
        adapter = CodebaseSourceAdapter()
        profile = adapter.load(str(sample_code_path))
        assert profile.kind == SourceKind.CODEBASE
        assert profile.uri == str(sample_code_path)
        assert profile.text.replace("\r\n", "\n").replace("\r", "\n") == (
            "def plan() -> str:\n    return 'ok'\n"
        )
        assert profile.language == "python"
        assert profile.content_type == "py"
        assert profile.line_count == 2
        assert "load_error" not in profile.metadata

    def test_load_missing_file_fails_closed(self, tmp_path):
        adapter = CodebaseSourceAdapter()
        profile = adapter.load(str(tmp_path / "missing.py"))
        assert profile.text == ""
        assert profile.byte_size == 0
        assert "load_error" in profile.metadata

    def test_load_unsupported_scheme_raises(self):
        adapter = CodebaseSourceAdapter()
        with pytest.raises(ValueError):
            adapter.load("https://example.com/planner.py")

    def test_load_empty_uri_raises(self):
        adapter = CodebaseSourceAdapter()
        with pytest.raises(ValueError):
            adapter.load("")

    def test_metadata_kind_is_codebase(self, sample_code_path):
        adapter = CodebaseSourceAdapter()
        source = adapter.metadata(str(sample_code_path))
        assert source.kind == SourceKind.CODEBASE
        assert source.title == "planner.py"

    def test_conforms_to_protocol(self):
        assert isinstance(CodebaseSourceAdapter(), SourceAdapter)


class TestSupportDisjointness:
    """No URI is claimed by more than one adapter."""

    def test_markdown_claimed_only_by_document(self, sample_document_path):
        path = str(sample_document_path)
        assert DocumentSourceAdapter().supports(path)
        assert not CodebaseSourceAdapter().supports(path)

    def test_python_claimed_only_by_codebase(self, sample_code_path):
        path = str(sample_code_path)
        assert CodebaseSourceAdapter().supports(path)
        assert not DocumentSourceAdapter().supports(path)

    def test_workspace_scheme_claimed_only_by_workspace(self, sample_document_path):
        adapter = WorkspaceSourceAdapter(root=None, resolver=lambda p: sample_document_path)
        uri = "workspace://guide.md"
        assert adapter.supports(uri)
        assert not DocumentSourceAdapter().supports(uri)
        assert not CodebaseSourceAdapter().supports(uri)
