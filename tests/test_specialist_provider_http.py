"""The first concrete specialist provider: bounded ``code.generate``.

Proves the adapter is inert by default, bounded in, fail-closed out, and that a
validated proposal NEVER becomes a repository change, an approval or a
promotion. Transport is a fake, so no model, network or process is involved.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

from atlas.specialists import (
    CODE_GENERATE,
    CODE_REVIEW,
    BoundedSpecialistTask,
    SpecialistRegistry,
)
from atlas.specialist_providers import (
    HttpCodeGenerationProvider,
    build_code_generation_request,
    parse_code_generation_response,
)

ROOT = pathlib.Path(__file__).resolve().parents[1]
TARGET = "atlas/evolution/structural_editor.py"

GOOD = {
    "files": {TARGET: "def _indent_of(line: str) -> str:\n    return ''\n"},
    "note": "proposed",
}


def _task(**kw):
    defaults = dict(
        capability=CODE_GENERATE,
        request="Make the helper return an empty string.",
        target=TARGET,
        context={TARGET: "original source"},
        plan={"target": "atlas.evolution.structural_editor"},
        verification_tests=("tests/test_structural_editor.py",),
    )
    defaults.update(kw)
    return BoundedSpecialistTask(**defaults)


# ---------------------------------------------------------------------------
# 1. Adapter contract
# ---------------------------------------------------------------------------


class TestAdapterContract:
    def test_identity_and_capability_are_exposed(self):
        provider = HttpCodeGenerationProvider(transport=lambda req: GOOD)
        assert provider.provider_id == "http.code"
        assert provider.capabilities() == frozenset({CODE_GENERATE})

    def test_requires_identity(self):
        with pytest.raises(ValueError):
            HttpCodeGenerationProvider(transport=lambda req: GOOD, provider_id="  ")

    def test_looks_like_a_specialist_provider(self):
        from atlas.specialists import SpecialistProvider

        assert isinstance(
            HttpCodeGenerationProvider(transport=lambda req: GOOD),
            SpecialistProvider,
        )


# ---------------------------------------------------------------------------
# 2. Real round trip (over a fake transport — no model is contacted)
# ---------------------------------------------------------------------------


class TestRoundTrip:
    def test_full_round_trip_yields_a_validated_proposal(self):
        sent = {}

        def transport(request):
            sent.update(request)
            return GOOD

        registry = SpecialistRegistry()
        registry.register(HttpCodeGenerationProvider(transport=transport))
        proposal = registry.request(_task())

        assert proposal is not None
        assert proposal.capability == CODE_GENERATE
        assert proposal.payload["paths"] == [TARGET]
        assert proposal.payload["files"] == GOOD["files"]
        # the provider received ONLY the bounded contract
        assert sent["target"] == TARGET
        assert sent["capability"] == CODE_GENERATE
        assert sent["verification_tests"] == ["tests/test_structural_editor.py"]

    def test_proposal_is_not_a_repository_change(self):
        before = (ROOT / TARGET).read_text(encoding="utf-8")
        registry = SpecialistRegistry()
        registry.register(HttpCodeGenerationProvider(transport=lambda req: GOOD))
        registry.request(_task())
        assert (ROOT / TARGET).read_text(encoding="utf-8") == before

    def test_proposal_grants_nothing(self):
        registry = SpecialistRegistry()
        registry.register(HttpCodeGenerationProvider(transport=lambda req: GOOD))
        proposal = registry.request(_task())
        for forbidden in ("apply", "approve", "promote", "authorize", "execute"):
            assert not hasattr(proposal, forbidden)


# ---------------------------------------------------------------------------
# 3. Bounded input
# ---------------------------------------------------------------------------


class TestBoundedRequest:
    def test_request_is_bounded_before_it_leaves_atlas(self):
        task = _task(context={f"atlas/f{i:03d}.py": "x" * 5000 for i in range(200)})
        request = build_code_generation_request(task)
        assert len(request["context"]) <= 24
        assert sum(len(v) for v in request["context"].values()) <= 60_000

    def test_request_is_deterministic(self):
        task = _task(context={"atlas/b.py": "b", "atlas/a.py": "a"})
        assert build_code_generation_request(task) == build_code_generation_request(task)


# ---------------------------------------------------------------------------
# 4. Fail-closed behaviour
# ---------------------------------------------------------------------------


class TestFailClosed:
    def test_unavailable_provider_is_inert(self):
        provider = HttpCodeGenerationProvider(transport=None)
        assert provider.available is False
        assert provider.propose(_task()) is None

    def test_explicitly_unavailable_provider_is_inert(self):
        provider = HttpCodeGenerationProvider(
            transport=lambda req: GOOD, available=False
        )
        assert provider.propose(_task()) is None

    def test_raising_transport_falls_back(self):
        def boom(request):
            raise RuntimeError("network down")

        registry = SpecialistRegistry()
        registry.register(HttpCodeGenerationProvider(transport=boom))
        assert registry.request(_task()) is None

    def test_wrong_capability_is_refused_by_the_adapter(self):
        provider = HttpCodeGenerationProvider(transport=lambda req: GOOD)
        assert provider.propose(_task(capability=CODE_REVIEW)) is None

    @pytest.mark.parametrize(
        "response",
        [
            None,
            "not a dict",
            [],
            {},
            {"files": {}},
            {"files": {"": "x"}},
            {"files": {TARGET: ""}},
            {"files": {TARGET: 123}},
            {"files": "nope"},
            {"files": None},
        ],
    )
    def test_malformed_responses_are_rejected(self, response):
        assert (
            parse_code_generation_response(response, _task(), provider_id="p") is None
        )

    def test_malformed_response_through_the_registry_is_none(self):
        registry = SpecialistRegistry()
        registry.register(HttpCodeGenerationProvider(transport=lambda req: {"files": {}}))
        assert registry.request(_task()) is None

    def test_path_traversal_in_provider_output_is_rejected(self):
        evil = {"files": {"../outside.py": "x = 1\n"}}
        registry = SpecialistRegistry()
        registry.register(HttpCodeGenerationProvider(transport=lambda req: evil))
        # the adapter produces a proposal; ATLAS validation rejects it
        assert registry.request(_task()) is None


# ---------------------------------------------------------------------------
# 5. Zero-provider and substitution
# ---------------------------------------------------------------------------


class TestZeroProviderAndSubstitution:
    def test_zero_providers_still_yields_nothing(self):
        assert SpecialistRegistry().request(_task()) is None

    def test_deterministic_operation_needs_no_provider(self):
        """The task/validation path is pure and provider-independent."""
        task = _task()
        assert build_code_generation_request(task)["target"] == TARGET

    def test_providers_are_substitutable(self):
        first = SpecialistRegistry()
        first.register(
            HttpCodeGenerationProvider(
                transport=lambda req: {"files": {TARGET: "a = 1\n"}}
            )
        )
        second = SpecialistRegistry()
        second.register(
            HttpCodeGenerationProvider(
                provider_id="other", transport=lambda req: {"files": {TARGET: "b = 2\n"}}
            )
        )
        assert first.request(_task()).payload["files"][TARGET] == "a = 1\n"
        assert second.request(_task()).payload["files"][TARGET] == "b = 2\n"


# ---------------------------------------------------------------------------
# 6. No governance bypass and no vendor coupling
# ---------------------------------------------------------------------------


class TestBoundaries:
    def test_module_imports_no_vendor_or_network_client(self):
        source = (ROOT / "atlas" / "specialist_providers.py").read_text(
            encoding="utf-8"
        )
        imported: set[str] = set()
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Import):
                imported.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        for forbidden in (
            "openai", "anthropic", "requests", "httpx", "urllib",
            "socket", "subprocess", "torch", "transformers",
        ):
            assert forbidden not in imported

    def test_adapter_cannot_approve_or_promote(self):
        provider = HttpCodeGenerationProvider(transport=lambda req: GOOD)
        for forbidden in ("apply", "approve", "promote", "authorize", "execute"):
            assert not hasattr(provider, forbidden)

    def test_no_sandbox_or_governance_module_is_imported(self):
        source = (ROOT / "atlas" / "specialist_providers.py").read_text(
            encoding="utf-8"
        )
        for forbidden in ("code_sandbox", "approval_manager", "promotion"):
            assert f"import {forbidden}" not in source
