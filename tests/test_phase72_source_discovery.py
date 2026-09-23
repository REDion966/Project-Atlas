"""Phase 7.2 — Technology/source discovery: evidence contract.

Investigation result: source discovery/selection and the web security controls
already exist, so no new browser/search framework was introduced.

* ``ResearchPlanner.target_sources`` selects a source kind deterministically
  from the question (workspace:// / code:// / http(s):// / file extension).
* ``source_selection.select_repository_sources`` selects AUTHORIZED local
  CODEBASE sources; it never selects web and never grants authorization.
* ``WebSourceAdapter`` stays deny-by-default with full SSRF/bounds controls.
"""

from __future__ import annotations

from atlas.evolution.models import ResearchQuery
from atlas.research.models import SourceKind
from atlas.research.planner import ResearchPlanner
from atlas.research.repository_map import RepositoryMapBuilder
from atlas.research.source_selection import select_repository_sources
from atlas.research.sources.web import WebSourceAdapter


def _target_sources(question: str):
    return ResearchPlanner().plan(
        ResearchQuery(query_id="q", question=question)
    ).target_sources


class TestPhase72SourceDiscovery:
    def test_source_kind_is_selected_by_uri_marker(self):
        assert _target_sources("see https://example.com/doc") == (SourceKind.WEB,)
        assert _target_sources("code://atlas/memory") == (SourceKind.CODEBASE,)
        assert _target_sources("workspace://notes.md") == (SourceKind.WORKSPACE,)
        assert _target_sources("what is in atlas/memory/manager.py") == (
            SourceKind.CODEBASE,
        )

    def test_local_source_selection_is_deterministic_and_authorized_only(self, tmp_path):
        root = tmp_path / "repo"
        (root / "atlas").mkdir(parents=True)
        (root / "atlas" / "__init__.py").write_text("", encoding="utf-8")
        (root / "atlas" / "memory_manager.py").write_text("x = 1\n", encoding="utf-8")
        repo_map = RepositoryMapBuilder(root).build()

        selected = select_repository_sources("memory manager", repo_map)
        assert all(spec.startswith("code://") for spec in selected)
        assert select_repository_sources("memory manager", repo_map) == selected
        # No match -> honest empty selection (no fabricated/unauthorized source).
        assert select_repository_sources("zzzzz", repo_map) == ()

    def test_web_discovery_is_deny_by_default(self):
        adapter = WebSourceAdapter()
        # No allowlist configured -> no host is fetchable.
        assert adapter.supports("http://example.com/page") is False
        assert adapter.supports("http://127.0.0.1/") is False
        assert adapter.supports("ftp://example.com/x") is False
