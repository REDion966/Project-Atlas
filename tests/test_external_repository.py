"""Real GitHub + internet repository intelligence (deterministic, offline).

Focused tests for the governed external-repository capability:
* target parsing + path confinement;
* bounded GitHub acquisition over an injected FAKE transport (no network);
* deterministic structural analysis reusing the existing RepositoryMap;
* Atlas-vs-external comparison (evidence-only);
* development-evidence hand-off (never authorization);
* security / fail-closed behaviour;
* self-knowledge wiring.

No live network is used; the real probe lives in a separate, explicitly run
path (documented in the report).
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from atlas.research.external_repository import (
    ComparisonVerdict,
    analyze_acquired_repository,
    compare_with_atlas,
    development_evidence,
    rank_relevant_symbols,
)
from atlas.research.sources.github import (
    AcquiredRepository,
    GitHubRepositorySource,
    github_host_policy,
    parse_repository_target,
    safe_repository_path,
)
from atlas.research.sources.web import DENY_ALL_HOSTS

_ACME = "acme/demo"
_TREE_URL = "https://api.github.com/repos/acme/demo/git/trees/main?recursive=1"
_META_URL = "https://api.github.com/repos/acme/demo"

_CORE = (
    "class Engine:\n"
    "    def run(self, x=1):\n"
    "        return x\n\n"
    "def helper(a, b):\n"
    "    return Engine().run(a)\n"
)
_UTIL = "def util(a):\n    return a\n"
_TREE = {
    "tree": [
        {"path": "demo/__init__.py", "type": "blob", "size": 0},
        {"path": "demo/core.py", "type": "blob", "size": len(_CORE)},
        {"path": "demo/sub/__init__.py", "type": "blob", "size": 0},
        {"path": "demo/sub/util.py", "type": "blob", "size": len(_UTIL)},
        {"path": "README.md", "type": "blob", "size": 12},
        {"path": "huge.py", "type": "blob", "size": 10_000_000},
        {"path": "../evil.py", "type": "blob", "size": 5},
    ]
}
_META = {
    "full_name": "acme/demo",
    "description": "A tiny demo repository.",
    "default_branch": "main",
    "language": "Python",
    "size": 12,
    "stargazers_count": 3,
    "archived": False,
}


class _FakeTransport:
    """Deterministic single-hop transport (never touches the network)."""

    def __init__(self, routes, *, errors=None):
        self.routes = routes
        self.errors = errors or {}
        self.calls: list[str] = []

    def get(self, url, timeout, max_bytes):
        self.calls.append(url)
        if url in self.errors:
            raise RuntimeError(self.errors[url])
        if url not in self.routes:
            return (404, [("content-type", "text/plain")], b"not found")
        status, headers, body = self.routes[url]
        return (status, headers, body)


def _json_body(payload) -> bytes:
    return json.dumps(payload).encode("utf-8")


def _routes(**overrides):
    routes = {
        _META_URL: (200, [("content-type", "application/json")], _json_body(_META)),
        _TREE_URL: (200, [("content-type", "application/json")], _json_body(_TREE)),
        "https://raw.githubusercontent.com/acme/demo/main/demo/core.py": (
            200, [("content-type", "text/plain")], _CORE.encode("utf-8")
        ),
        "https://raw.githubusercontent.com/acme/demo/main/demo/sub/util.py": (
            200, [("content-type", "text/plain")], _UTIL.encode("utf-8")
        ),
        "https://raw.githubusercontent.com/acme/demo/main/demo/__init__.py": (
            200, [("content-type", "text/plain")], b""
        ),
        "https://raw.githubusercontent.com/acme/demo/main/demo/sub/__init__.py": (
            200, [("content-type", "text/plain")], b""
        ),
        "https://raw.githubusercontent.com/acme/demo/main/README.md": (
            200, [("content-type", "text/plain")], b"# demo\n"
        ),
        "https://raw.githubusercontent.com/acme/demo/main/huge.py": (
            200, [("content-type", "text/plain")], b"HUGE"
        ),
    }
    routes.update(overrides)
    return routes


def _source(transport, *, policy=None, resolver=None):
    return GitHubRepositorySource(
        transport=transport,
        host_policy=policy if policy is not None else github_host_policy(),
        resolver=resolver or (lambda host: ("140.82.112.3",)),
    )


def _fixture_acquired() -> AcquiredRepository:
    return AcquiredRepository(
        ok=True,
        owner="acme",
        name="demo",
        ref="main",
        metadata=_META,
        files=(
            ("demo/__init__.py", ""),
            ("demo/core.py", _CORE),
            ("demo/sub/__init__.py", ""),
            ("demo/sub/util.py", _UTIL),
            ("README.md", "# demo\n"),
        ),
        provenance={"target": "acme/demo", "ref": "main"},
    )


# ---------------------------------------------------------------------------
# Target parsing + path confinement
# ---------------------------------------------------------------------------


class TestTargetParsing:
    @pytest.mark.parametrize(
        "target,expected",
        (
            ("acme/demo", ("acme", "demo")),
            ("https://github.com/acme/demo", ("acme", "demo")),
            ("https://github.com/acme/demo.git", ("acme", "demo")),
            ("git@github.com:acme/demo.git", ("acme", "demo")),
            ("github.com/acme/demo", ("acme", "demo")),
        ),
    )
    def test_valid_targets(self, target, expected):
        assert parse_repository_target(target) == expected

    @pytest.mark.parametrize(
        "target", ("", "no-slash", "a/../b", 123, None, "ftp://x/y")
    )
    def test_invalid_targets_fail_closed(self, target):
        assert parse_repository_target(target) is None

    def test_only_owner_and_name_are_used(self):
        # Extra path (e.g. a /tree/main/... URL suffix) is ignored entirely;
        # only the validated owner/name are used.
        assert parse_repository_target("https://github.com/acme/demo/tree/main/src") == (
            "acme",
            "demo",
        )

    @pytest.mark.parametrize(
        "path",
        ("/etc/passwd", "../secret", "a/../../b", "a\\b", "a/./b", "a//b", "") ,
    )
    def test_unsafe_paths_refused(self, path):
        assert safe_repository_path(path) is None

    def test_safe_paths_allowed(self):
        assert safe_repository_path("demo/core.py") == "demo/core.py"
        assert safe_repository_path(".github/workflows/ci.yml") is not None


# ---------------------------------------------------------------------------
# Acquisition (fake transport; no network)
# ---------------------------------------------------------------------------


class TestAcquisition:
    def test_acquires_bounded_source_files(self):
        transport = _FakeTransport(_routes())
        acquired = _source(transport).acquire(_ACME)
        assert acquired.ok is True
        assert acquired.owner == "acme" and acquired.name == "demo"
        assert acquired.ref == "main"
        paths = {p for p, _ in acquired.files}
        assert "demo/core.py" in paths and "README.md" in paths
        # Traversal + oversized files are never retrieved.
        assert "../evil.py" not in paths and "huge.py" not in paths
        assert any("huge.py" in e for e in acquired.errors)
        assert transport.calls  # real fetches occurred over the fake transport

    def test_keywords_rank_retrieval_order(self):
        transport = _FakeTransport(_routes())
        acquired = _source(transport).acquire(_ACME, keywords=("util",))
        assert acquired.files[0][0] == "demo/sub/util.py"

    def test_max_files_truncates(self):
        transport = _FakeTransport(_routes())
        acquired = _source(transport).acquire(_ACME, max_files=1)
        assert len(acquired.files) == 1
        assert acquired.truncated is True

    def test_unauthorized_host_is_denied(self):
        transport = _FakeTransport(_routes())
        acquired = _source(transport, policy=DENY_ALL_HOSTS).acquire(_ACME)
        assert acquired.ok is False
        assert acquired.errors
        assert transport.calls == []  # nothing was fetched

    def test_malformed_target_fails_closed(self):
        acquired = _source(_FakeTransport(_routes())).acquire("not-a-repo")
        assert acquired.ok is False

    def test_transport_failure_fails_closed(self):
        transport = _FakeTransport(_routes(), errors={_META_URL: "boom"})
        acquired = _source(transport).acquire(_ACME)
        assert acquired.ok is False
        assert acquired.errors

    def test_redirect_outside_policy_is_refused(self):
        transport = _FakeTransport(
            _routes(
                **{
                    _META_URL: (
                        302,
                        [("location", "https://evil.example/repos/acme/demo")],
                        b"",
                    )
                }
            )
        )
        acquired = _source(transport).acquire(_ACME)
        assert acquired.ok is False


# ---------------------------------------------------------------------------
# Structural analysis + relevance
# ---------------------------------------------------------------------------


class TestAnalysis:
    def test_structure_and_symbols(self):
        analysis = analyze_acquired_repository(_fixture_acquired(), keywords=("engine",))
        assert analysis.ok is True
        structure = analysis.structure
        assert structure.module_count >= 4
        assert structure.symbol_count >= 3
        assert "demo" in structure.packages and "demo.sub" in structure.packages
        assert ("python", structure.module_count) in structure.language_counts
        located = {item["qualified"] for item in analysis.relevant}
        assert any("Engine" in q for q in located)

    def test_relevance_is_case_insensitive_and_deterministic(self):
        analysis = analyze_acquired_repository(_fixture_acquired(), keywords=("ENGINE",))
        first = [item["qualified"] for item in analysis.relevant]
        second = [
            item["qualified"]
            for item in analyze_acquired_repository(
                _fixture_acquired(), keywords=("ENGINE",)
            ).relevant
        ]
        assert first == second
        assert first

    def test_no_keywords_returns_importance_slice(self):
        analysis = analyze_acquired_repository(_fixture_acquired())
        assert analysis.relevant  # bounded importance slice, deterministic

    def test_empty_acquisition_is_reported(self):
        analysis = analyze_acquired_repository(
            AcquiredRepository(ok=False, errors=("no files",))
        )
        assert analysis.ok is False
        assert analysis.limitations

    def test_temp_tree_is_disposable(self, tmp_path):
        analysis = analyze_acquired_repository(
            _fixture_acquired(), workdir=str(tmp_path)
        )
        assert analysis.ok is True
        # No external tree survives the analysis.
        assert list(tmp_path.iterdir()) == []

    def test_rank_relevant_reuses_symbol_queries(self):
        analysis = analyze_acquired_repository(_fixture_acquired())
        ranked = rank_relevant_symbols(analysis.repository_map, ("util",))
        assert ranked and "util" in ranked[0]["qualified"].lower()


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------


class TestComparison:
    def _analysis(self):
        return analyze_acquired_repository(_fixture_acquired(), keywords=("engine",))

    def test_matching_capability_is_already_supported(self):
        comparison = compare_with_atlas(
            self._analysis(),
            atlas_capability_names=("engine",),
            keywords=("engine",),
        )
        verdicts = {f.verdict for f in comparison.findings}
        assert ComparisonVerdict.ALREADY_SUPPORTED in verdicts

    def test_unmatched_keyword_is_a_gap(self):
        comparison = compare_with_atlas(
            self._analysis(), atlas_capability_names=(), keywords=("engine",)
        )
        assert any(
            f.verdict is ComparisonVerdict.CAPABILITY_GAP for f in comparison.findings
        )

    def test_every_finding_is_unvalidated_with_evidence(self):
        comparison = compare_with_atlas(self._analysis(), keywords=("engine",))
        assert comparison.findings
        for finding in comparison.findings:
            assert finding.validation_status == "unvalidated"
            assert finding.evidence and finding.evidence[0]["repository"] == "acme/demo"
            assert finding.risks

    def test_failed_analysis_yields_no_findings(self):
        comparison = compare_with_atlas(
            analyze_acquired_repository(AcquiredRepository(ok=False))
        )
        assert comparison.findings == ()
        assert comparison.limitations


# ---------------------------------------------------------------------------
# Development hand-off (evidence only)
# ---------------------------------------------------------------------------


class TestDevelopmentEvidence:
    def test_evidence_never_contains_authoring_payload(self):
        analysis = analyze_acquired_repository(_fixture_acquired(), keywords=("engine",))
        comparison = compare_with_atlas(analysis, keywords=("engine",))
        evidence = development_evidence(analysis, comparison, request="research X")
        assert "external_research" in evidence
        assert evidence["external_research"]["validation_status"] == "unvalidated"
        # Critically: no authoring payload can ride along.
        assert "scaffold" not in evidence
        assert "code_changes" not in evidence


# ---------------------------------------------------------------------------
# Security / fail-closed
# ---------------------------------------------------------------------------


class TestSecurity:
    def test_acquisition_never_executes_external_code(self, tmp_path):
        acquired = _fixture_acquired()
        # A file whose content would "write" if executed must be inert.
        analysis = analyze_acquired_repository(acquired, workdir=str(tmp_path))
        assert analysis.ok and list(tmp_path.iterdir()) == []

    def test_default_host_policy_is_deny_all(self):
        from atlas.research.sources.web import WebHostPolicy

        default = GitHubRepositorySource().host_policy
        assert isinstance(default, WebHostPolicy)
        assert default.allowed_hosts == frozenset()

    def test_resolution_failure_fails_closed(self):
        transport = _FakeTransport(_routes())
        source = _source(transport, resolver=lambda host: ())
        acquired = source.acquire(_ACME)
        assert acquired.ok is False


# ---------------------------------------------------------------------------
# Model independence
# ---------------------------------------------------------------------------


class TestModelIndependence:
    @pytest.mark.parametrize(
        "module",
        (
            "atlas/research/sources/github.py",
            "atlas/research/external_repository.py",
        ),
    )
    def test_no_ai_import(self, module):
        source = Path(module).read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
            elif isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
        assert not any(name.startswith("atlas.ai") for name in imported)


# ---------------------------------------------------------------------------
# Self-knowledge + kernel integration
# ---------------------------------------------------------------------------


def _started_atlas(monkeypatch, tmp_path):
    import atlas.kernel.atlas as kernel_mod
    from atlas.storage.research_storage import ResearchSQLiteStorage
    from tests.test_durable_guided_improvement import _storage_class

    monkeypatch.setattr(
        "atlas.kernel.atlas.SQLiteEvolutionStorage", _storage_class(tmp_path)
    )

    class _TmpResearch(ResearchSQLiteStorage):
        def __init__(self, db_path=None):  # noqa: D107
            super().__init__(db_path=tmp_path / "research.db")

    monkeypatch.setattr("atlas.kernel.atlas.ResearchSQLiteStorage", _TmpResearch)
    atlas = kernel_mod.Atlas()
    atlas.start()
    return atlas


class TestSelfKnowledgeAndKernel:
    def test_capability_is_self_described(self, monkeypatch, tmp_path):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            contract = atlas.capability_contract("external_repository.analyze")
            assert contract["found"] is True
            assert contract["components"] == ["external_repository_intelligence"]
            assert contract["dependency"] == "deterministic"
            located = atlas.architecture_model().locate(
                "external_repository.analyze"
            )
            assert located.found is True
        finally:
            atlas.shutdown()

    def test_kernel_analysis_is_deny_by_default(self, monkeypatch, tmp_path):
        atlas = _started_atlas(monkeypatch, tmp_path)
        try:
            # With the default (empty) host allow-list, GitHub is unreachable
            # and the analysis fails closed — no network, no execution.
            result = atlas.analyze_external_repository("acme/demo")
            assert result["acquisition"]["ok"] is False
            assert result["analysis"]["ok"] is False
            assert result["development_evidence"]["external_research"][
                "validation_status"
            ] == "unvalidated"
        finally:
            atlas.shutdown()
