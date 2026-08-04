"""Atlas Research — CLI Commands (Phase 17.9).

Presentation-only wrappers for the Track A capability handlers. These call
the handler functions exactly like a ``CapabilityRegistry`` dispatch would —
they never mutate state, never write knowledge, and never touch the
evolution pipeline directly. Research ingestion stays a governed evolution
path (see ``atlas.research.evolution_integration``).
"""

from __future__ import annotations

import argparse
import sys

from atlas.reasoning.execution.models import ExecutionResult
from atlas.research._extraction import claim_id_for
from atlas.research.capability_handlers import (
    CapabilityHandler,
    ResearchCapabilityFactory,
)
from atlas.research.models import KnowledgeClaim


def build_parser() -> argparse.ArgumentParser:
    """Build the ``atlas research`` subparser (presentation only)."""
    parser = argparse.ArgumentParser(prog="atlas research", description="Atlas Research CLI")
    subparsers = parser.add_subparsers(dest="action", required=True)

    query_parser = subparsers.add_parser("query", help="Run the research pipeline")
    query_parser.add_argument("question", help="Research question")
    query_parser.add_argument("--query-id", default="cli", help="Optional query id")
    query_parser.add_argument("--source", action="append", default=[], help="Source URI")

    verify_parser = subparsers.add_parser("verify", help="Verify extracted claims")
    verify_parser.add_argument("--claim", action="append", required=True, help="Claim statement")
    verify_parser.add_argument("--source", action="append", default=[], help="Source URI")

    summary_parser = subparsers.add_parser("summarize", help="Summarize a stored report")
    report_group = summary_parser.add_mutually_exclusive_group(required=True)
    report_group.add_argument("--report-id", help="Report id (loads from research storage)")
    report_group.add_argument("--report-file", help="Path to a research report JSON file")

    return parser


def _print_result(result: ExecutionResult) -> int:
    if not result.success:
        print(f"error: {result.error}")
        return 1
    print(result.output)
    return 0


def run_query(
    factory: ResearchCapabilityFactory,
    question: str,
    query_id: str = "cli",
    sources: list[str] | None = None,
) -> ExecutionResult:
    """Present ``atlas research query``."""
    handler: CapabilityHandler = factory.handlers()["research.query"]
    return handler(
        {
            "question": question,
            "query_id": query_id,
            "sources": sources or [],
        }
    )


def run_verify(
    factory: ResearchCapabilityFactory,
    statements: list[str],
    sources: list[str] | None = None,
) -> ExecutionResult:
    """Present ``atlas research verify``.

    Builds deterministic ``KnowledgeClaim`` objects from the supplied
    statements (stable sha256 claim ids via the extractor's helper) and
    resolves source URIs through the same adapter chain the capability
    handler uses, then dispatches through the ``research.verify`` handler.
    """
    handler: CapabilityHandler = factory.handlers()["research.verify"]
    claims: list[KnowledgeClaim] = [
        KnowledgeClaim(claim_id=claim_id_for(statement), statement=statement)
        for statement in statements
        if statement.strip()
    ]
    resolved_sources = factory._resolve_sources(sources or [])
    return handler(
        {
            "claims": claims,
            "sources": resolved_sources,
        }
    )


def run_summarize(factory: ResearchCapabilityFactory, report_id: str) -> ExecutionResult:
    """Present ``atlas research summarize`` (invokes the capability handler)."""
    handler: CapabilityHandler = factory.handlers()["research.summarize"]
    return handler(
        {
            "report_id": report_id,
        }
    )


def main(argv: list[str] | None = None) -> int:
    """Entry point for ``atlas research`` CLI commands."""
    args = build_parser().parse_args(argv)
    factory = ResearchCapabilityFactory()

    if args.action == "query":
        result = run_query(factory, args.question, args.query_id, args.source)
        return _print_result(result)
    if args.action == "verify":
        result = run_verify(factory, args.claim, args.source)
        return _print_result(result)
    if args.action == "summarize":
        if args.report_id:
            result = run_summarize(factory, args.report_id)
            return _print_result(result)
        # Presentation-only: a summary of inputs when no report is persisted.
        print({"summary": f"report file: {args.report_file}"})
        return 0
    print("no such research command")
    return 1


if __name__ == "__main__":
    sys.exit(main())
