"""NLU-3 — dimension-level research completeness tests.

Deterministic and model-free: no provider, no kernel, no network.
"""

from __future__ import annotations

from atlas.authority.service import AuthorityService
from atlas.orchestration.execution_models import (
    ExecutionRequest,
    ExecutionState,
    ExecutionStatus,
    ExecutionStep,
)
from atlas.orchestration.executor import OrchestrationExecutor
from atlas.orchestration.models import NodeKind
from atlas.orchestration.reporting import orchestration_result_to_message
from atlas.research.dimensions import dimension_coverage, extract_dimensions
from atlas.session.context import SessionContext
from atlas.session.manager import SessionManager

_REPO_QUESTION = (
    "Research the memory service, including memory storage, memory search, and "
    "memory ranking of the atlas memory subsystem."
)
_PHONE_QUESTION = (
    "Research the camera stabilization and autofocus of the Samsung Galaxy S26 Ultra."
)


# ---------------------------------------------------------------------------
# Requested-dimension extraction
# ---------------------------------------------------------------------------


class TestExtractDimensions:
    def test_camera_aspects(self):
        dims = extract_dimensions(
            "Research the camera specifications, stabilization, autofocus, video "
            "recording, and low-light performance of the Samsung Galaxy S26 Ultra."
        )
        assert dims == (
            "camera specifications",
            "stabilization",
            "autofocus",
            "video recording",
            "low-light performance",
        )

    def test_display_aspects(self):
        dims = extract_dimensions(
            "Research the display resolution, refresh rate, brightness, battery "
            "capacity, charging speed, and camera system of this smartphone."
        )
        assert dims == (
            "display resolution",
            "refresh rate",
            "brightness",
            "battery capacity",
            "charging speed",
            "camera system",
        )

    def test_including_marker_excludes_the_subject(self):
        assert extract_dimensions(_REPO_QUESTION) == (
            "memory storage",
            "memory search",
            "memory ranking",
        )

    def test_single_aspect_request_has_no_dimensions(self):
        assert extract_dimensions(
            "Research the camera specifications of the Samsung Galaxy S26 Ultra."
        ) == ()

    def test_plain_question_has_no_dimensions(self):
        assert extract_dimensions("Research the memory architecture.") == ()
        assert extract_dimensions("") == ()

    def test_ordinary_prose_is_not_mistaken_for_dimensions(self):
        assert extract_dimensions(
            "How should Atlas combine document sources, workspace resources and "
            "codebase files into a single normalized representation that supports "
            "citation tracking, claim verification and confidence scoring?"
        ) == ()


# ---------------------------------------------------------------------------
# Evidence-to-dimension coverage (bounded token rule)
# ---------------------------------------------------------------------------


class TestDimensionCoverage:
    def test_all_dimensions_covered(self):
        supported, unsupported = dimension_coverage(
            ("memory storage", "memory search"),
            ["the memory storage layer and the memory search surface"],
        )
        assert supported == ("memory storage", "memory search")
        assert unsupported == ()

    def test_partial_coverage(self):
        supported, unsupported = dimension_coverage(
            ("memory storage", "memory search", "gpu acceleration"),
            ["the memory storage layer stores memories"],
        )
        assert supported == ("memory storage",)
        assert unsupported == ("memory search", "gpu acceleration")

    def test_coincidental_keyword_does_not_cover_a_phone_dimension(self):
        # "Atlas's stabilization module" is not smartphone-camera stabilization.
        supported, unsupported = dimension_coverage(
            ("camera stabilization",),
            ["Atlas's stabilization module keeps the runtime stable"],
        )
        assert supported == ()
        assert unsupported == ("camera stabilization",)

    def test_wrong_dimension_is_not_coverage(self):
        supported, unsupported = dimension_coverage(
            ("autofocus",), ["the memory service stores and retrieves memories"]
        )
        assert supported == ()
        assert unsupported == ("autofocus",)

    def test_shared_vocabulary_does_not_mark_both_complete(self):
        supported, unsupported = dimension_coverage(
            ("memory storage", "memory search"), ["the memory storage module"]
        )
        assert supported == ("memory storage",)
        assert unsupported == ("memory search",)


# ---------------------------------------------------------------------------
# Executor completeness decisions
# ---------------------------------------------------------------------------


class _AcquisitionResult:
    def __init__(self, status, sources, requested=(), supported=(), unsupported=(), claims=0):
        self.status = status
        self.sources = list(sources)
        self.claim_count = claims
        self.findings = ""
        self.requested_dimensions = tuple(requested)
        self.supported_dimensions = tuple(supported)
        self.unsupported_dimensions = tuple(unsupported)

    def to_dict(self):
        return {
            "status": self.status,
            "sources": list(self.sources),
            "claim_count": self.claim_count,
            "requested_dimensions": list(self.requested_dimensions),
            "supported_dimensions": list(self.supported_dimensions),
            "unsupported_dimensions": list(self.unsupported_dimensions),
        }


class _ResearchService:
    def __init__(self, result):
        self._result = result

    def acquire(self, **kwargs):
        return self._result


def _run(question, result):
    authority = AuthorityService("Owner")
    ctx = SessionContext.from_session(SessionManager(authority).create_session("owner"))
    executor = OrchestrationExecutor(
        research_service=_ResearchService(result), authority_service=authority
    )
    step = ExecutionStep(
        step_id="s1", kind=NodeKind.RESEARCH, target="acquire", inputs={"question": question}
    )
    return executor.execute(ExecutionRequest(steps=(step,), session_context=ctx))


_SOURCES = ["code://atlas/memory/service/memory_service.py"]
_DIMS = ("memory storage", "memory search", "memory ranking")


class TestExecutorDimensionCompleteness:
    def test_all_dimensions_covered_is_complete(self):
        result = _run(
            _REPO_QUESTION,
            _AcquisitionResult("ok", _SOURCES, _DIMS, _DIMS, (), claims=20),
        )
        assert result.status is ExecutionStatus.COMPLETED
        assert result.steps[0].state is ExecutionState.COMPLETED

    def test_some_dimensions_covered_is_partial(self):
        result = _run(
            _REPO_QUESTION,
            _AcquisitionResult(
                "ok",
                _SOURCES,
                _DIMS,
                ("memory storage",),
                ("memory search", "memory ranking"),
                claims=20,
            ),
        )
        assert result.status is ExecutionStatus.PARTIAL
        assert result.steps[0].state is ExecutionState.COMPLETED
        completeness = result.steps[0].metadata["research_completeness"]
        assert completeness["status"] == "partial"
        assert completeness["supported"] == ["memory storage"]
        assert completeness["unsupported"] == ["memory search", "memory ranking"]

    def test_no_dimension_covered_is_no_relevant_evidence(self):
        result = _run(
            _REPO_QUESTION,
            _AcquisitionResult("ok", _SOURCES, _DIMS, (), _DIMS, claims=20),
        )
        assert result.status is ExecutionStatus.FAILED
        assert result.steps[0].failure_kind == "no_relevant_evidence"

    def test_no_evidence_is_no_evidence(self):
        result = _run(_REPO_QUESTION, _AcquisitionResult("noop", [], claims=0))
        assert result.status is ExecutionStatus.FAILED
        assert result.steps[0].failure_kind == "no_evidence"

    def test_irrelevant_source_is_not_success(self):
        # A code source whose path coincidentally contains a requested-dimension
        # word must not satisfy a phone-camera request.
        result = _run(
            _PHONE_QUESTION,
            _AcquisitionResult(
                "ok",
                ["code://atlas/research/stabilization.py"],
                ("camera stabilization", "autofocus"),
                (),
                ("camera stabilization", "autofocus"),
                claims=10,
            ),
        )
        assert result.status is ExecutionStatus.FAILED
        assert result.steps[0].failure_kind == "no_relevant_evidence"

    def test_single_aspect_request_is_complete_not_partial(self):
        result = _run(
            "Research the memory architecture.",
            _AcquisitionResult("ok", _SOURCES, claims=20),
        )
        assert result.status is ExecutionStatus.COMPLETED


class TestPartialReporting:
    def test_partial_report_names_supported_and_unsupported(self):
        result = _run(
            _REPO_QUESTION,
            _AcquisitionResult(
                "ok",
                _SOURCES,
                _DIMS,
                ("memory storage",),
                ("memory search", "memory ranking"),
                claims=20,
            ),
        )
        message = orchestration_result_to_message(result, intent="research")
        content = message.content
        assert "partially completed" in content.lower()
        assert "- memory storage" in content
        assert "- memory search" in content
        assert "- memory ranking" in content
        assert "Done" not in content

    def test_complete_report_does_not_mention_partial(self):
        result = _run(
            _REPO_QUESTION,
            _AcquisitionResult("ok", _SOURCES, _DIMS, _DIMS, (), claims=20),
        )
        message = orchestration_result_to_message(result, intent="research")
        assert "partially" not in message.content.lower()
        assert "Done" in message.content
