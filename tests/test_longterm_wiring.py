"""Track C — Wiring metadata and CLI tests (Batch 4)."""

from atlas.longterm.cli_commands import build_parser, run_episodes, run_procedures
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
