"""Atlas Long-Term Learning — CLI Commands (Track C, Batch 4).

Presentation-only wrappers for the Track C surface:

  atlas memory episodes   — query recent episodes (outcome / limit filters)
  atlas memory procedures — query distilled procedures (category / tool filters)
  atlas memory consolidate — GOVERNED consolidation through the evolution
                             ingest bridge (never mutates repositories)

``consolidate`` NEVER calls repository mutation methods from Track C code.
It runs the pure consolidator, builds a PENDING consolidation audit record,
and passes it through the :class:`LongTermIngestBridge` to the Phase 16
governed sink. Without a sink, consolidation fails closed — the repositories
are never mutated directly, and the request is never applied by Track C.

No kernel, runtime, dispatcher, scheduler, gateway, storage, events, or AI
imports — presentation layer only, mirroring
:mod:`atlas.research.cli_commands` (Track A) and
:mod:`atlas.toolchain.cli_commands` (Track B).
"""

from __future__ import annotations

import argparse
import sys

from atlas.longterm.capability_handlers import LongTermCapabilityFactory
from atlas.longterm.evolution_integration import LongTermIngestBridge
from atlas.reasoning.execution.models import ExecutionResult


def build_parser() -> argparse.ArgumentParser:
    """Build the ``atlas memory`` subparser (episodes / procedures / consolidate)."""

    parser = argparse.ArgumentParser(
        prog="atlas memory", description="Atlas Long-Term Memory CLI"
    )
    subparsers = parser.add_subparsers(dest="action", required=True)

    episodes_parser = subparsers.add_parser(
        "episodes", help="Query recent episodes"
    )
    episodes_parser.add_argument(
        "--limit", type=int, default=100, help="Max episodes to return"
    )
    episodes_parser.add_argument("--outcome", default="", help="Filter by outcome")
    episodes_parser.add_argument(
        "--since", default="", help="ISO timestamp; only episodes at/after it"
    )

    procedures_parser = subparsers.add_parser(
        "procedures", help="Query distilled procedures"
    )
    procedures_parser.add_argument(
        "--limit", type=int, default=100, help="Max procedures to return"
    )
    procedures_parser.add_argument("--category", default="", help="Filter by category")
    procedures_parser.add_argument(
        "--tool", default="", help="Filter by referenced tool name"
    )

    consolidate_parser = subparsers.add_parser(
        "consolidate", help="Run governed consolidation"
    )
    consolidate_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run the pure pass and report candidates without submitting to the sink",
    )

    return parser


def _print_result(result: ExecutionResult) -> int:
    """Print an ExecutionResult and return a process exit code."""
    if not result.success:
        print(f"error: {result.error}")
        return 1
    print(result.output)
    return 0


def run_episodes(
    factory: LongTermCapabilityFactory,
    limit: int = 100,
    outcome: str = "",
    since: str = "",
) -> ExecutionResult:
    """Present ``atlas memory episodes`` (via the episodic_query handler)."""
    handler = factory.handlers()["memory.episodic_query"]
    params: dict = {"limit": limit}
    if outcome:
        params["outcome"] = outcome
    if since:
        params["since"] = since
    return handler(params)


def run_procedures(
    factory: LongTermCapabilityFactory,
    limit: int = 100,
    category: str = "",
    tool: str = "",
) -> ExecutionResult:
    """Present ``atlas memory procedures`` (via the procedure_query handler)."""
    handler = factory.handlers()["memory.procedure_query"]
    params: dict = {"limit": limit}
    if category:
        params["category"] = category
    if tool:
        params["tool"] = tool
    return handler(params)


def run_consolidate(
    factory: LongTermCapabilityFactory,
    bridge: LongTermIngestBridge | None = None,
    dry_run: bool = False,
) -> ExecutionResult:
    """Present ``atlas memory consolidate`` — GOVERNED consolidation.

    Runs the pure consolidator over the injected repositories, builds one
    PENDING :class:`ConsolidationRecord`, and — unless ``dry_run`` — hands
    the governed request through the injected :class:`LongTermIngestBridge`
    to the Phase 16 sink. Without a sink the consolidation fails closed
    and the repositories are never mutated.
    """
    wired = LongTermCapabilityFactory(
        episodes=factory.episodes,
        procedures=factory.procedures,
        consolidator=factory._consolidator,
        tracker=factory._tracker,
        evolve_bridge=bridge
        if bridge is not None
        else LongTermIngestBridge(),
    )
    result = wired.handlers()["memory.consolidate"]({})
    if dry_run:
        result.metadata["dry_run"] = True
        result.output["dry_run"] = True
    return result


def main(argv: list[str] | None = None) -> int:
    """Entry point for ``atlas memory`` commands."""
    args = build_parser().parse_args(argv)
    factory = LongTermCapabilityFactory()

    if args.action == "episodes":
        result = run_episodes(factory, args.limit, args.outcome, args.since)
        return _print_result(result)
    if args.action == "procedures":
        result = run_procedures(factory, args.limit, args.category, args.tool)
        return _print_result(result)
    if args.action == "consolidate":
        result = run_consolidate(factory, dry_run=args.dry_run)
        return _print_result(result)
    print("no such memory command")
    return 1


if __name__ == "__main__":
    sys.exit(main())
