"""Track C — Wiring metadata and CLI tests (Batch 4)."""

from atlas.longterm.cli_commands import (
    build_parser,
    run_episodes,
    run_procedures,
    run_search,
)
from atlas.longterm.capability_handlers import LongTermCapabilityFactory
from atlas.longterm.wiring import (
    longterm_component,
    longterm_components,
    longterm_evolution_component,
)


class TestComponentMetadata:
    def test_longterm_component(self):
        metadata = longterm_component()
        assert metadata.name == "longterm"
        assert metadata.package == "atlas.longterm"
        assert "memory.episodic_query" in metadata.provided_capabilities
        assert "memory.procedure_query" in metadata.provided_capabilities
        assert "memory.semantic_query" in metadata.provided_capabilities
        assert "memory.consolidate" in metadata.provided_capabilities

    def test_evolution_component(self):
        metadata = longterm_evolution_component()
        assert metadata.name == "longterm_evolution"
        assert "memory_consolidation_governed_ingest" in metadata.provided_capabilities

    def test_components_extends_core(self):
        components = longterm_components()
        names = {c.name for c in components}
        assert "longterm" in names
        assert "longterm_evolution" in names
        assert len(components) > 2


class TestCLI:
    def test_parser_actions(self):
        parser = build_parser()
        args = parser.parse_args(["episodes", "--limit", "5"])
        assert args.action == "episodes"
        assert args.limit == 5

    def test_procedures_parser(self):
        parser = build_parser()
        args = parser.parse_args(["procedures", "--category", "research", "--tool", "search"])
        assert args.action == "procedures"
        assert args.category == "research"
        assert args.tool == "search"

    def test_search_parser(self):
        parser = build_parser()
        args = parser.parse_args(["search", "alpha beta", "--limit", "7"])
        assert args.action == "search"
        assert args.query == "alpha beta"
        assert args.limit == 7

    def test_run_search_returns_results(self):
        from datetime import datetime

        from atlas.longterm.episode_repository import EpisodicRepository
        from atlas.longterm.models import Episode, EpisodeKind

        repository = EpisodicRepository()
        repository.store_episode(
            Episode(
                episode_id="ep1",
                kind=EpisodeKind.PIPELINE,
                title="Episode ep1",
                outcome="success",
                started_at=datetime(2026, 1, 1, 12, 0, 0),
                ended_at=datetime(2026, 1, 1, 12, 0, 5),
                tags=("alpha",),
            )
        )
        factory = LongTermCapabilityFactory(episodes=repository)
        result = run_search(factory, "alpha", limit=100)
        assert result.success
        assert result.output["count"] == 1
        assert result.output["results"][0]["item"]["episode_id"] == "ep1"

    def test_run_search_missing_query_fails_closed(self):
        factory = LongTermCapabilityFactory()
        result = run_search(factory, "")
        assert not result.success
        assert "query" in result.error

    def test_run_search_is_read_only(self):
        from datetime import datetime

        from atlas.longterm.episode_repository import EpisodicRepository
        from atlas.longterm.models import Episode, EpisodeKind

        repository = EpisodicRepository()
        repository.store_episode(
            Episode(
                episode_id="ep1",
                kind=EpisodeKind.PIPELINE,
                title="Episode ep1",
                outcome="success",
                started_at=datetime(2026, 1, 1, 12, 0, 0),
                ended_at=datetime(2026, 1, 1, 12, 0, 5),
                tags=("alpha",),
            )
        )
        factory = LongTermCapabilityFactory(episodes=repository)
        run_search(factory, "alpha")
        run_search(factory, "")
        assert repository.episode_count == 1
        assert repository.get_episode("ep1") is not None


class TestWorkspaceCliDispatch:
    def test_memory_search_dispatch_via_main(self, monkeypatch, capsys):
        """`atlas memory search <query>` is registered on the workspace CLI
        and dispatches end-to-end (read-only) against an empty store."""
        from unittest.mock import MagicMock

        from atlas.cli import main as cli_main

        monkeypatch.setattr(
            "atlas.cli.main.load_workspace_service", lambda: MagicMock()
        )
        monkeypatch.setattr(
            "sys.argv",
            ["atlas", "memory", "search", "alpha", "--limit", "5"],
        )
        cli_main.main()
        out = capsys.readouterr().out
        assert "count': 0" in out

    def test_memory_search_blank_query_reports_error(self, monkeypatch, capsys):
        """`atlas memory search ''` fails closed with a rendered error."""
        from unittest.mock import MagicMock

        from atlas.cli import main as cli_main

        monkeypatch.setattr(
            "atlas.cli.main.load_workspace_service", lambda: MagicMock()
        )
        monkeypatch.setattr("sys.argv", ["atlas", "memory", "search", ""])
        cli_main.main()
        out = capsys.readouterr().out
        assert out.startswith("error:")
        assert "query" in out

    def test_run_episodes_empty(self):
        factory = LongTermCapabilityFactory()
        result = run_episodes(factory)
        assert result.success
        assert result.output["episodes"] == []

    def test_run_procedures_empty(self):
        factory = LongTermCapabilityFactory()
        result = run_procedures(factory)
        assert result.success
        assert result.output["procedures"] == []

    def test_consolidate_fails_closed(self):
        from atlas.longterm.cli_commands import run_consolidate

        factory = LongTermCapabilityFactory()
        result = run_consolidate(factory)
        assert not result.success
        assert "sink" in result.error
