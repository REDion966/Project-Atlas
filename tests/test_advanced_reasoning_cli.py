"""Track D — Advanced Reasoning CLI tests (Batch 2).

Verifies the presentation-only ``atlas reasoning`` command surface: read-only
commands delegate to the capability handlers; ``ingest`` is governed and
fails closed without a sink (never mutating any store).
"""

from __future__ import annotations

from atlas.advanced_reasoning.capability_handlers import (
    AdvancedReasoningCapabilityFactory,
)
from atlas.advanced_reasoning.cli_commands import (
    build_parser,
    main,
    run_causal,
    run_counterfactual,
    run_hypotheses,
    run_ingest,
    run_meta,
    run_trace,
    run_verify,
)
from atlas.advanced_reasoning.evolution_integration import IngestHandoffResult
from atlas.advanced_reasoning.models import (
    ReasoningStrategy,
    ReasoningTrace,
    TraceStatus,
)


def _make_trace(trace_id: str = "trace:known") -> ReasoningTrace:
    return ReasoningTrace(
        trace_id=trace_id,
        question="Is X supported?",
        strategy=ReasoningStrategy.DECOMPOSE,
        status=TraceStatus.COMPLETED,
        conclusion="inclined yes",
        confidence=0.8,
    )


class _FakeSink:
    def __init__(self, accept: bool = True) -> None:
        self.accept = accept
        self.requests = []

    def enqueue_request(self, request) -> IngestHandoffResult:
        self.requests.append(request)
        if not self.accept:
            return IngestHandoffResult(False, error="refused by policy")
        return IngestHandoffResult(True, request_id=request.request_id)


class TestParser:
    def test_build_parser_has_seven_actions(self):
        parser = build_parser()
        for action in (
            "trace",
            "causal",
            "counterfactual",
            "hypotheses",
            "verify",
            "meta",
            "ingest",
        ):
            assert action in parser._subparsers._group_actions[0].choices  # type: ignore[attr-defined]

    def test_unknown_action_raises_argparse_error(self, capsys):
        # An unknown subcommand is rejected by argparse (exit code 2) before
        # main()'s fallback branch is reached — the correct CLI behavior.
        import pytest

        with pytest.raises(SystemExit) as excinfo:
            main(["nonexistent"])
        assert excinfo.value.code == 2


class TestTrace:
    def test_run_trace_succeeds(self):
        result = run_trace(AdvancedReasoningCapabilityFactory(), "How does X work?")
        assert result.success
        assert result.output["trace"]["status"] == "COMPLETED"

    def test_main_trace(self, capsys):
        code = main(["trace", "What is torque?"])
        assert code == 0
        assert "trace_id" in capsys.readouterr().out


class TestCausal:
    def test_run_causal_succeeds(self):
        result = run_causal(AdvancedReasoningCapabilityFactory(), "a", "b")
        assert result.success
        assert result.output["count"] == 0


class TestCounterfactual:
    def test_run_counterfactual_succeeds(self):
        result = run_counterfactual(
            AdvancedReasoningCapabilityFactory(),
            "ignition",
            "without oxygen",
        )
        assert result.success


class TestHypotheses:
    def test_run_hypotheses_succeeds(self):
        result = run_hypotheses(
            AdvancedReasoningCapabilityFactory(),
            "The yield dropped sharply.",
        )
        assert result.success
        assert result.output["count"] >= 1


class TestVerify:
    def test_run_verify_claim(self):
        result = run_verify(AdvancedReasoningCapabilityFactory(), claim="The sky is blue.")
        assert result.success
        assert "verdict" in result.output

    def test_run_verify_without_target_fails(self):
        result = run_verify(AdvancedReasoningCapabilityFactory())
        assert not result.success


class TestMeta:
    def test_run_meta_succeeds(self):
        result = run_meta(AdvancedReasoningCapabilityFactory())
        assert result.success
        assert "recommended_strategy" in result.output


class TestIngest:
    def test_ingest_fails_closed_without_sink(self):
        result = run_ingest(
            AdvancedReasoningCapabilityFactory(),
            content="use decomposition for multi-fact queries",
        )
        assert not result.success
        assert "sink" in result.error

    def test_ingest_accepting_sink_succeeds(self):
        sink = _FakeSink(accept=True)
        from atlas.advanced_reasoning.evolution_integration import ReasoningIngestBridge

        result = run_ingest(
            AdvancedReasoningCapabilityFactory(),
            bridge=ReasoningIngestBridge(sink=sink),
            content="use decomposition for multi-fact queries",
        )
        assert result.success
        assert len(sink.requests) == 1

    def test_ingest_refusing_sink_fails(self):
        sink = _FakeSink(accept=False)
        from atlas.advanced_reasoning.evolution_integration import ReasoningIngestBridge

        result = run_ingest(
            AdvancedReasoningCapabilityFactory(),
            bridge=ReasoningIngestBridge(sink=sink),
            content="insight",
        )
        assert not result.success
        assert "refused" in result.error

    def test_ingest_by_trace_id_succeeds(self):
        factory = AdvancedReasoningCapabilityFactory()
        factory.service.repository.store_trace(_make_trace())
        sink = _FakeSink(accept=True)
        from atlas.advanced_reasoning.evolution_integration import ReasoningIngestBridge

        result = run_ingest(
            factory,
            bridge=ReasoningIngestBridge(sink=sink),
            trace_id="trace:known",
        )
        assert result.success
        assert result.metadata["governed"] is True

    def test_ingest_main_command_returns_fail_closed(self, capsys):
        # Without a sink the CLI ingest must fail closed and not crash.
        # _print_result prints the error to stdout and returns exit code 1.
        code = main(["ingest", "--content", "a valuable insight"])
        assert code == 1
        assert "sink" in capsys.readouterr().out
