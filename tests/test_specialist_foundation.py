"""The Atlas-owned specialist seam: zero-provider safety and untrusted output.

Proves the foundation is inert by default, deterministic when providers exist,
and fail-closed against malformed, empty, oversized or unsafe proposals.

No model, network, filesystem or governance surface is touched.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

from atlas.specialists import (
    CODE_GENERATE,
    LANGUAGE_INTERPRET,
    MAX_CONTEXT_CHARS,
    MAX_CONTEXT_FILES,
    SPECIALIST_CAPABILITIES,
    BoundedSpecialistTask,
    SpecialistProposal,
    SpecialistRegistry,
    SpecialistProvider,
    validate_proposal,
)

ROOT = pathlib.Path(__file__).resolve().parents[1]


class _Fake:
    """Minimal specialist: declares capabilities, returns a canned proposal."""

    def __init__(self, provider_id, capabilities, payload=None, raises=False,
                 model_id="fake-1"):
        self._id = provider_id
        self._caps = frozenset(capabilities)
        self._payload = payload if payload is not None else {"note": "ok"}
        self._raises = raises
        self._model = model_id
        self.calls = 0

    @property
    def provider_id(self):
        return self._id

    def capabilities(self):
        return self._caps

    def propose(self, task):
        self.calls += 1
        if self._raises:
            raise RuntimeError("provider exploded")
        return SpecialistProposal(
            provider_id=self._id,
            capability=task.capability,
            payload=dict(self._payload),
            model_id=self._model,
            confidence=0.5,
        )


def _task(capability=CODE_GENERATE, **kw):
    return BoundedSpecialistTask(capability=capability, **kw)


# ---------------------------------------------------------------------------
# Zero-provider behaviour (deterministic-first)
# ---------------------------------------------------------------------------


class TestZeroProvider:
    def test_registry_is_empty_by_default(self):
        registry = SpecialistRegistry()
        assert registry.providers() == ()

    @pytest.mark.parametrize("capability", sorted(SPECIALIST_CAPABILITIES))
    def test_no_provider_selects_nothing(self, capability):
        registry = SpecialistRegistry()
        assert registry.select(capability) is None
        assert registry.supports(capability) is False

    def test_no_provider_request_returns_none(self):
        registry = SpecialistRegistry()
        assert registry.request(_task()) is None

    def test_module_imports_no_model_or_framework(self):
        source = (ROOT / "atlas" / "specialists.py").read_text(encoding="utf-8")
        imported: set[str] = set()
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Import):
                imported.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        for forbidden in (
            "openai", "anthropic", "requests", "httpx", "torch",
            "transformers", "langchain", "llama_index",
        ):
            assert forbidden not in imported


# ---------------------------------------------------------------------------
# Selection and substitution
# ---------------------------------------------------------------------------


class TestSelection:
    def test_simple_capability_matching(self):
        registry = SpecialistRegistry()
        registry.register(_Fake("a", [CODE_GENERATE]))
        assert registry.select(CODE_GENERATE).provider_id == "a"
        assert registry.select(LANGUAGE_INTERPRET) is None

    def test_registration_order_is_the_only_ranking(self):
        registry = SpecialistRegistry()
        registry.register(_Fake("first", [CODE_GENERATE]))
        registry.register(_Fake("second", [CODE_GENERATE]))
        assert registry.select(CODE_GENERATE).provider_id == "first"

    def test_provider_is_substitutable(self):
        """Swapping the provider changes no Atlas code — only selection."""
        first = SpecialistRegistry()
        first.register(_Fake("a", [CODE_GENERATE], {"note": "a"}))
        second = SpecialistRegistry()
        second.register(_Fake("b", [CODE_GENERATE], {"note": "b"}))
        assert first.request(_task()).payload == {"note": "a"}
        assert second.request(_task()).payload == {"note": "b"}

    def test_duplicate_registration_is_idempotent(self):
        provider = _Fake("a", [CODE_GENERATE])
        registry = SpecialistRegistry()
        registry.register(provider)
        registry.register(provider)
        assert len(registry.providers()) == 1

    def test_registration_requires_identity(self):
        with pytest.raises(ValueError):
            SpecialistRegistry().register(_Fake("", [CODE_GENERATE]))

    def test_unknown_capability_never_selects(self):
        registry = SpecialistRegistry()
        registry.register(_Fake("a", [CODE_GENERATE]))
        assert registry.select("code.destroy_the_world") is None


# ---------------------------------------------------------------------------
# Fail-closed proposal handling
# ---------------------------------------------------------------------------


class TestFailClosed:
    def test_provider_failure_falls_back(self):
        registry = SpecialistRegistry()
        registry.register(_Fake("a", [CODE_GENERATE], raises=True))
        assert registry.request(_task()) is None

    def test_empty_payload_is_rejected(self):
        registry = SpecialistRegistry()
        registry.register(_Fake("a", [CODE_GENERATE], payload={}))
        assert registry.request(_task()) is None

    def test_capability_mismatch_is_rejected(self):
        proposal = SpecialistProposal(
            provider_id="a", capability=CODE_REVIEW if False else "code.review",
            payload={"note": "x"},
        )
        assert validate_proposal(proposal, _task(CODE_GENERATE)).accepted is False

    def test_none_and_wrong_types_are_rejected(self):
        assert validate_proposal(None, _task()).accepted is False
        assert validate_proposal({"note": "x"}, _task()).accepted is False

    def test_unsupported_capability_cannot_even_be_requested(self):
        with pytest.raises(ValueError):
            BoundedSpecialistTask(capability="code.destroy")

    def test_path_traversal_is_rejected(self):
        proposal = SpecialistProposal(
            provider_id="a",
            capability=CODE_GENERATE,
            payload={"paths": ["../outside.py"], "note": "x"},
        )
        assert validate_proposal(proposal, _task()).accepted is False

    def test_absolute_external_path_is_rejected(self):
        proposal = SpecialistProposal(
            provider_id="a",
            capability=CODE_GENERATE,
            payload={"paths": ["C:/Windows/system32/x.py"], "note": "x"},
        )
        assert validate_proposal(proposal, _task()).accepted is False

    def test_path_outside_the_declared_target_is_rejected(self):
        proposal = SpecialistProposal(
            provider_id="a",
            capability=CODE_GENERATE,
            payload={"paths": ["atlas/other.py"], "note": "x"},
        )
        outcome = validate_proposal(
            proposal, _task(), allowed_paths=("atlas/evolution/structural_editor.py",)
        )
        assert outcome.accepted is False
        assert "outside the target" in outcome.reason

    def test_declared_target_path_is_accepted(self):
        proposal = SpecialistProposal(
            provider_id="a",
            capability=CODE_GENERATE,
            payload={"paths": ["atlas/evolution/structural_editor.py"], "note": "x"},
        )
        outcome = validate_proposal(
            proposal, _task(), allowed_paths=("atlas/evolution/structural_editor.py",)
        )
        assert outcome.accepted is True

    def test_oversized_payload_is_rejected(self):
        proposal = SpecialistProposal(
            provider_id="a", capability=CODE_GENERATE, payload={"blob": "x" * 50_000}
        )
        assert validate_proposal(proposal, _task()).accepted is False


# ---------------------------------------------------------------------------
# Bounded input (a provider never receives an unbounded repository)
# ---------------------------------------------------------------------------


class TestBoundedTask:
    def test_context_is_capped_in_sorted_order(self):
        context = {f"atlas/f{index:03d}.py": "x" for index in range(60)}
        bounded = _task(context=context).bounded()
        assert len(bounded.context) <= MAX_CONTEXT_FILES
        assert list(bounded.context) == sorted(bounded.context)

    def test_context_total_size_is_capped(self):
        context = {f"atlas/f{index}.py": "y" * 30_000 for index in range(10)}
        bounded = _task(context=context).bounded()
        assert sum(len(v) for v in bounded.context.values()) <= MAX_CONTEXT_CHARS

    def test_bounding_is_deterministic(self):
        context = {"atlas/b.py": "b", "atlas/a.py": "a"}
        first = _task(context=context).bounded()
        second = _task(context=context).bounded()
        assert first.context == second.context == {"atlas/a.py": "a", "atlas/b.py": "b"}

    def test_a_real_repository_context_is_materially_shrunk(self):
        """Even a repository-scale mapping is bounded before a provider sees it."""
        big = {
            p.relative_to(ROOT).as_posix(): "z" * 2000
            for p in list((ROOT / "atlas").rglob("*.py"))[:300]
        }
        bounded = _task(context=big).bounded()
        assert len(bounded.context) <= MAX_CONTEXT_FILES
        assert sum(len(v) for v in bounded.context.values()) <= MAX_CONTEXT_CHARS


# ---------------------------------------------------------------------------
# Authority boundary
# ---------------------------------------------------------------------------


class TestAuthorityBoundary:
    def test_a_proposal_can_never_be_a_decision(self):
        proposal = SpecialistProposal(provider_id="a", capability=CODE_GENERATE)
        for forbidden in (
            "approve", "authorize", "promote", "apply", "authorized", "approved",
        ):
            assert not hasattr(proposal, forbidden)

    def test_registry_cannot_apply_or_promote(self):
        registry = SpecialistRegistry()
        for forbidden in ("apply", "approve", "promote", "authorize", "execute"):
            assert not hasattr(registry, forbidden)

    def test_provider_protocol_exposes_only_the_bounded_contract(self):
        assert set(SpecialistProvider.__protocol_attrs__) == {
            "provider_id",
            "capabilities",
            "propose",
        }
