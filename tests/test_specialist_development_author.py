"""The bounded specialist -> development producer (Command 3B).

Proves the producer side of the Atlas-owned specialist seam: given a
``DevelopmentNeed`` (+ Atlas plan context) it constructs a BOUNDED
``BoundedSpecialistTask`` through the EXISTING seam, invokes the registered
provider, and returns the VALIDATED ``SpecialistProposal`` — or ``None`` on
every refusal. No model, network or filesystem is touched (the transport is a
fake), and the author mints no authority.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

from atlas.evolution.development_cycle import DevelopmentNeed
from atlas.evolution.specialist_change_supplier import SPECIALIST_PROPOSAL_KEY
from atlas.evolution.specialist_development import (
    MAX_CONTEXT_SOURCE_CHARS,
    SpecialistDevelopmentAuthor,
)
from atlas.specialist_providers import HttpCodeGenerationProvider
from atlas.specialists import CODE_GENERATE, SpecialistProposal, SpecialistRegistry

ROOT = pathlib.Path(__file__).resolve().parents[1]
TARGET = "atlas/example/widget.py"
NEW = "# widget\n"


def _need():
    return DevelopmentNeed(
        title="Add a widget helper",
        summary="Add a small widget helper module.",
        rationale="The widget subsystem needs a helper.",
    )


def _registry(transport, provider_id="fake.code"):
    registry = SpecialistRegistry()
    registry.register(
        HttpCodeGenerationProvider(
            transport=transport, provider_id=provider_id, model_id="fake-1"
        )
    )
    return registry


class TestProducer:
    def test_inert_without_a_registry(self):
        author = SpecialistDevelopmentAuthor(None)
        assert author.available is False
        assert author.propose(_need(), target=TARGET) is None

    def test_inert_without_a_code_generate_provider(self):
        author = SpecialistDevelopmentAuthor(SpecialistRegistry())
        assert author.available is False
        assert author.propose(_need(), target=TARGET) is None

    def test_non_development_need_is_refused(self):
        author = SpecialistDevelopmentAuthor(_registry(lambda r: {"files": {TARGET: NEW}}))
        assert author.propose(object(), target=TARGET) is None  # type: ignore[arg-type]

    def test_proposes_a_bounded_task_and_returns_the_validated_proposal(self):
        sent: dict = {}

        def transport(request):
            sent.update(request)
            return {"files": {TARGET: NEW}, "note": "proposed"}

        author = SpecialistDevelopmentAuthor(_registry(transport))
        proposal = author.propose(
            _need(),
            target=TARGET,
            plan={"target": TARGET, "route": "specialist_model"},
            verification_tests=("tests/test_widget.py",),
        )
        assert isinstance(proposal, SpecialistProposal)
        assert proposal.capability == CODE_GENERATE
        assert proposal.payload["files"] == {TARGET: NEW}
        # The provider received ONLY the bounded, Atlas-owned contract.
        assert sent["capability"] == CODE_GENERATE
        assert sent["target"] == TARGET
        assert sent["verification_tests"] == ["tests/test_widget.py"]

    def test_propose_with_metadata_attaches_the_dedicated_key(self):
        author = SpecialistDevelopmentAuthor(_registry(lambda r: {"files": {TARGET: NEW}}))
        result = author.propose_with_metadata(_need(), target=TARGET)
        assert result is not None
        proposal, metadata = result
        assert metadata[SPECIALIST_PROPOSAL_KEY] is proposal

    def test_propose_with_metadata_is_none_without_a_proposal(self):
        author = SpecialistDevelopmentAuthor(_registry(lambda r: {"files": {}}))
        assert author.propose_with_metadata(_need(), target=TARGET) is None

    def test_fail_closed_when_the_provider_raises(self):
        def boom(request):
            raise RuntimeError("runtime down")

        author = SpecialistDevelopmentAuthor(_registry(boom))
        assert author.propose(_need(), target=TARGET) is None

    @pytest.mark.parametrize(
        "response",
        [None, "x", {}, {"files": {}}, {"files": {TARGET: ""}}],
    )
    def test_fail_closed_on_malformed_output(self, response):
        author = SpecialistDevelopmentAuthor(_registry(lambda r: response))
        assert author.propose(_need(), target=TARGET) is None

    def test_bounded_source_context_from_the_repository_map(self):
        class _Info:
            module = "atlas.example.widget"
            path = TARGET
            source_excerpt = "x = 1\n" * 20_000

        class _Map:
            modules = (_Info(),)

        sent: dict = {}

        def transport(request):
            sent.update(request)
            return {"files": {TARGET: NEW}}

        author = SpecialistDevelopmentAuthor(
            _registry(transport), repository_map=_Map()
        )
        author.propose(_need(), target=TARGET)
        assert TARGET in sent["context"]
        assert len(sent["context"][TARGET]) <= MAX_CONTEXT_SOURCE_CHARS

    def test_author_cannot_approve_promote_or_execute(self):
        author = SpecialistDevelopmentAuthor(_registry(lambda r: {"files": {TARGET: NEW}}))
        for forbidden in ("apply", "approve", "promote", "authorize", "execute"):
            assert not hasattr(author, forbidden)

    def test_module_imports_no_vendor_or_network_client(self):
        source = (
            ROOT / "atlas" / "evolution" / "specialist_development.py"
        ).read_text(encoding="utf-8")
        imported: set[str] = set()
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Import):
                imported.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        for forbidden in (
            "openai", "anthropic", "requests", "httpx", "socket",
            "subprocess", "urllib", "torch", "transformers",
        ):
            assert forbidden not in imported
