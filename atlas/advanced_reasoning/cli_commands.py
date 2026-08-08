"""Atlas Advanced Reasoning — CLI Commands (Track D, Batch 2).

Presentation-only wrappers for the Track D surface:

  atlas reasoning trace          — deterministic multi-step reasoning
  atlas reasoning causal         — causal path analysis
  atlas reasoning counterfactual — what-if evaluation under an assumption
  atlas reasoning hypotheses     — generate and rank competing hypotheses
  atlas reasoning verify         — self-verify a trace or claim
  atlas reasoning meta           — meta-reasoning strategy-effectiveness report
  atlas reasoning ingest         — GOVERNED ingest through the evolution bridge

``ingest`` NEVER mutates any store from Track D code. It builds an
INFORMATION-scope KNOWLEDGE request and passes it through the
:class:`ReasoningIngestBridge` to the Phase 16 governed sink. Without a
sink the ingest fails closed — no state is ever mutated by Track D
(TRACK_D §6, §8).

No kernel, runtime, dispatcher, scheduler, gateway, storage, events, or AI
imports — presentation layer only, mirroring
:mod:`atlas.longterm.cli_commands` (Track C) and
:mod:`atlas.toolchain.cli_commands` (Track B).
"""

from __future__ import annotations

import argparse
import sys

from atlas.advanced_reasoning.capability_handlers import (
    AdvancedReasoningCapabilityFactory,
)
from atlas.advanced_reasoning.evolution_integration import ReasoningIngestBridge
from atlas.advanced_reasoning.service import AdvancedReasoningService
from atlas.reasoning.execution.models import ExecutionResult


def build_parser() -> argparse.ArgumentParser:
    """Build the ``atlas reasoning`` subparser."""

    parser = argparse.ArgumentParser(
        prog="atlas reasoning", description="Atlas Advanced Reasoning CLI"
    )
    subparsers = parser.add_subparsers(dest="action", required=True)

    trace_parser = subparsers.add_parser(
        "trace", help="Run deterministic multi-step reasoning"
    )
    trace_parser.add_argument("question", help="Question or claim to reason about")
    trace_parser.add_argument(
        "--max-steps", type=int, default=None, help="Optional step budget"
    )
    trace_parser.add_argument(
        "--trace-id", default="", help="Optional stable trace id"
    )

    causal_parser = subparsers.add_parser(
        "causal", help="Analyze causal paths between source and target"
    )
    causal_parser.add_argument("--source", required=True, help="Source entity/event")
    causal_parser.add_argument("--target", required=True, help="Target entity/event")
    causal_parser.add_argument(
        "--max-depth", type=int, default=None, help="Optional traversal depth"
    )

    counterfactual_parser = subparsers.add_parser(
        "counterfactual", help="Evaluate a what-if scenario"
    )
    counterfactual_parser.add_argument("--event", required=True, help="Source event")
    counterfactual_parser.add_argument(
        "--assumption", required=True, help="Altered assumption to evaluate"
    )
    counterfactual_parser.add_argument(
        "--max-depth", type=int, default=None, help="Optional traversal depth"
    )
    counterfactual_parser.add_argument(
        "--result-id", default="", help="Optional stable result id"
    )

    hypotheses_parser = subparsers.add_parser(
        "hypotheses", help="Generate and rank competing hypotheses"
    )
    hypotheses_parser.add_argument("claim", help="Claim to generate hypotheses for")
    hypotheses_parser.add_argument(
        "--limit", type=int, default=None, help="Optional hypothesis limit"
    )
    hypotheses_parser.add_argument(
        "--set-id", default="", help="Optional stable hypothesis set id"
    )

    verify_parser = subparsers.add_parser(
        "verify", help="Self-verify a trace or a claim"
    )
    verify_parser.add_argument(
        "--trace-id", default="", help="Optional trace id to verify"
    )
    verify_parser.add_argument("--claim", default="", help="Optional claim to verify")
    verify_parser.add_argument(
        "--report-id", default="", help="Optional stable report id"
    )

    meta_parser = subparsers.add_parser(
        "meta", help="Produce a meta-reasoning strategy-effectiveness report"
    )
    meta_parser.add_argument(
        "--limit", type=int, default=None, help="Optional history window size"
    )
    meta_parser.add_argument(
        "--assessment-id", default="", help="Optional stable assessment id"
    )

    ingest_parser = subparsers.add_parser(
        "ingest", help="GOVERNED: submit a distilled reasoning insight"
    )
    ingest_parser.add_argument(
        "--trace-id", default="", help="Optional source trace id"
    )
    ingest_parser.add_argument(
        "--content", default="", help="Insight content when no trace id is given"
    )
    ingest_parser.add_argument(
        "--strategy-name", default="", help="Optional strategy label"
    )
    ingest_parser.add_argument(
        "--confidence", type=float, default=0.0, help="Optional confidence 0.0-1.0"
    )

    return parser


def _print_result(result: ExecutionResult) -> int:
    """Print an ExecutionResult and return a process exit code."""
    if not result.success:
        print(f"error: {result.error}")
        return 1
    print(result.output)
    return 0


def run_trace(
    factory: AdvancedReasoningCapabilityFactory,
    question: str,
    max_steps: int | None = None,
    trace_id: str = "",
) -> ExecutionResult:
    """Present ``atlas reasoning trace`` (via the reasoning.trace handler)."""
    handler = factory.handlers()["reasoning.trace"]
    params: dict = {"question": question}
    if max_steps is not None:
        params["max_steps"] = max_steps
    if trace_id:
        params["trace_id"] = trace_id
    return handler(params)


def run_causal(
    factory: AdvancedReasoningCapabilityFactory,
    source: str,
    target: str,
    max_depth: int | None = None,
) -> ExecutionResult:
    """Present ``atlas reasoning causal`` (via the reasoning.causal handler)."""
    handler = factory.handlers()["reasoning.causal"]
    params: dict = {"source": source, "target": target}
    if max_depth is not None:
        params["max_depth"] = max_depth
    return handler(params)


def run_counterfactual(
    factory: AdvancedReasoningCapabilityFactory,
    event: str,
    assumption: str,
    max_depth: int | None = None,
    result_id: str = "",
) -> ExecutionResult:
    """Present ``atlas reasoning counterfactual`` (via the handler)."""
    handler = factory.handlers()["reasoning.counterfactual"]
    params: dict = {"event": event, "assumption": assumption}
    if max_depth is not None:
        params["max_depth"] = max_depth
    if result_id:
        params["result_id"] = result_id
    return handler(params)


def run_hypotheses(
    factory: AdvancedReasoningCapabilityFactory,
    claim: str,
    limit: int | None = None,
    set_id: str = "",
) -> ExecutionResult:
    """Present ``atlas reasoning hypotheses`` (via the handler)."""
    handler = factory.handlers()["reasoning.hypotheses"]
    params: dict = {"claim": claim}
    if limit is not None:
        params["limit"] = limit
    if set_id:
        params["set_id"] = set_id
    return handler(params)


def run_verify(
    factory: AdvancedReasoningCapabilityFactory,
    trace_id: str = "",
    claim: str = "",
    report_id: str = "",
) -> ExecutionResult:
    """Present ``atlas reasoning verify`` (via the reasoning.verify handler)."""
    handler = factory.handlers()["reasoning.verify"]
    params: dict = {}
    if trace_id:
        params["trace_id"] = trace_id
    if claim:
        params["claim"] = claim
    if report_id:
        params["report_id"] = report_id
    return handler(params)


def run_meta(
    factory: AdvancedReasoningCapabilityFactory,
    limit: int | None = None,
    assessment_id: str = "",
) -> ExecutionResult:
    """Present ``atlas reasoning meta`` (via the reasoning.meta handler)."""
    handler = factory.handlers()["reasoning.meta"]
    params: dict = {}
    if limit is not None:
        params["limit"] = limit
    if assessment_id:
        params["assessment_id"] = assessment_id
    return handler(params)


def run_ingest(
    factory: AdvancedReasoningCapabilityFactory,
    bridge: ReasoningIngestBridge | None = None,
    trace_id: str = "",
    content: str = "",
    strategy_name: str = "",
    confidence: float = 0.0,
) -> ExecutionResult:
    """Present ``atlas reasoning ingest`` — GOVERNED ingest.

    Rebuilds the service with the supplied (or default sink-less)
    :class:`ReasoningIngestBridge` so the ingest handler routes through the
    governed sink — or fails closed without one (TRACK_D §8).
    """
    ingest_bridge = bridge if bridge is not None else ReasoningIngestBridge()
    wired = AdvancedReasoningCapabilityFactory(
        service=AdvancedReasoningService(
            multi_step=factory.service.multi_step,
            causal=factory.service.causal,
            hypotheses=factory.service.hypotheses,
            verifier=factory.service.verifier,
            meta=factory.service.meta,
            repository=factory.service.repository,
            ingest_bridge=ingest_bridge,
            config=factory.service.config,
        )
    )
    handler = wired.handlers()["reasoning.ingest"]
    params: dict = {"confidence": confidence}
    if trace_id:
        params["trace_id"] = trace_id
    if content:
        params["content"] = content
    if strategy_name:
        params["strategy_name"] = strategy_name
    return handler(params)


def main(argv: list[str] | None = None) -> int:
    """Entry point for ``atlas reasoning`` commands."""
    args = build_parser().parse_args(argv)
    factory = AdvancedReasoningCapabilityFactory()

    if args.action == "trace":
        result = run_trace(factory, args.question, args.max_steps, args.trace_id)
        return _print_result(result)
    if args.action == "causal":
        result = run_causal(factory, args.source, args.target, args.max_depth)
        return _print_result(result)
    if args.action == "counterfactual":
        result = run_counterfactual(
            factory, args.event, args.assumption, args.max_depth, args.result_id
        )
        return _print_result(result)
    if args.action == "hypotheses":
        result = run_hypotheses(factory, args.claim, args.limit, args.set_id)
        return _print_result(result)
    if args.action == "verify":
        result = run_verify(factory, args.trace_id, args.claim, args.report_id)
        return _print_result(result)
    if args.action == "meta":
        result = run_meta(factory, args.limit, args.assessment_id)
        return _print_result(result)
    if args.action == "ingest":
        result = run_ingest(
            factory,
            trace_id=args.trace_id,
            content=args.content,
            strategy_name=args.strategy_name,
            confidence=args.confidence,
        )
        return _print_result(result)
    print("no such reasoning command")
    return 1


if __name__ == "__main__":
    sys.exit(main())
