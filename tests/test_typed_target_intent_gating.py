"""Typed-target intent gating — capability-level tests.

Development intent should be recognizable because a request names an ADDRESSABLE
architectural identity (the existing ``ArchitectureTargetResolver`` says so), not
because it happens to contain a word from a maintained noun list.

These tests pin the STRUCTURAL behaviour, not vocabulary:

* the resolver supplies identity/type; it never supplies intent;
* the development CUE is still required;
* merely mentioning a target does not make a request a development request;
* an AMBIGUOUS or UNRESOLVED target never fabricates a development target;
* with no resolver injected, behaviour is byte-identical to before.

Deterministic and model-free throughout.
"""

from __future__ import annotations

import sys

import pytest

sys.path.insert(0, r"F:\Project Atlas")

from atlas.conversation.task_intake import TaskIntake


class _Resolution:
    """Minimal stand-in matching the resolver's read-only surface."""

    def __init__(self, *, resolved: bool, identity_type: str = "") -> None:
        self.is_resolved = resolved
        self.identity_type = identity_type


class _StubResolver:
    """Resolves only surfaces it was told about (no guessing).

    Matching normalises the way the real resolver does (case, separators,
    surrounding punctuation) so the stub tests the GATING behaviour rather than
    an exact-string accident.
    """

    def __init__(self, known: dict[str, str], *, ambiguous: frozenset[str] = frozenset()):
        self._known = {_key(k): v for k, v in known.items()}
        self._ambiguous = {_key(a) for a in ambiguous}
        self.calls: list[str] = []

    def resolve(self, surface: str, *, expected_type: str | None = None):
        self.calls.append(surface)
        key = _key(surface)
        if key in self._ambiguous:
            return _Resolution(resolved=False)
        identity_type = self._known.get(key)
        if identity_type is None:
            return _Resolution(resolved=False)
        return _Resolution(resolved=True, identity_type=identity_type)


def _key(text: str) -> str:
    """Normalised comparison key, matching the real resolver's surface key.

    Tokens are split on non-alphanumeric runs AND joined on a single space, so
    surrounding punctuation ("...service.") cannot leave a trailing separator that
    makes two spellings of the same surface compare unequal.
    """
    import re

    return " ".join(t for t in re.split(r"[^0-9A-Za-z]+", str(text).lower()) if t)


# ---------------------------------------------------------------------------
# 1. Target typing is what qualifies the request (not a noun list)
# ---------------------------------------------------------------------------


class TestTargetTypingQualifies:
    @pytest.mark.parametrize(
        "surface",
        (
            "the conversation service",
            "the conversation component",
            "the conversation subsystem",
            "the conversation module",
            "the conversation capability",
        ),
    )
    def test_addressable_surface_yields_development_intent(self, surface):
        resolver = _StubResolver({surface: "component"})
        intake = TaskIntake(target_resolver=resolver)
        spec = intake.intake(f"Improve {surface}.")
        assert spec.task_type.value == "development_request", surface

    def test_every_supported_identity_type_qualifies(self):
        """component / capability / module / package / symbol all qualify."""
        for identity_type in ("component", "capability", "module", "package", "symbol"):
            resolver = _StubResolver({"the target thing": identity_type})
            intake = TaskIntake(target_resolver=resolver)
            spec = intake.intake("Improve the target thing.")
            assert spec.task_type.value == "development_request", identity_type

    def test_resolver_is_only_consulted_for_the_target(self):
        """The resolver qualifies the TARGET; the cue still decides intent."""
        resolver = _StubResolver({"the widget": "component"})
        intake = TaskIntake(target_resolver=resolver)
        spec = intake.intake("Improve the widget.")
        assert spec.task_type.value == "development_request"
        assert resolver.calls, "the resolver must actually have been consulted"


# ---------------------------------------------------------------------------
# 2. The development CUE is still required
# ---------------------------------------------------------------------------


class TestCueStillRequired:
    @pytest.mark.parametrize(
        "text",
        (
            "Tell me about the widget.",
            "What is the widget?",
            "How does the widget work?",
            "Explain the widget.",
            "Describe the widget.",
            "Investigate the widget.",
        ),
    )
    def test_target_without_a_development_cue_is_not_development(self, text):
        resolver = _StubResolver({"the widget": "component"})
        intake = TaskIntake(target_resolver=resolver)
        spec = intake.intake(text)
        assert spec.task_type.value != "development_request", text

    def test_resolver_alone_cannot_create_development_intent(self):
        """An addressable target with no cue stays non-development."""
        resolver = _StubResolver({"the conversation service": "component"})
        intake = TaskIntake(target_resolver=resolver)
        assert intake.intake("Tell me about the conversation service.").task_type.value != (
            "development_request"
        )


# ---------------------------------------------------------------------------
# 3. Negation still wins
# ---------------------------------------------------------------------------


class TestNegationUnchanged:
    @pytest.mark.parametrize(
        "text",
        (
            "Don't improve the widget.",
            "Do not improve the widget.",
            "Do not modify the widget.",
        ),
    )
    def test_negated_development_cue_is_not_development(self, text):
        resolver = _StubResolver({"the widget": "component"})
        intake = TaskIntake(target_resolver=resolver)
        assert intake.intake(text).task_type.value != "development_request", text


# ---------------------------------------------------------------------------
# 4. Ambiguity / unresolved stay fail-closed
# ---------------------------------------------------------------------------


class TestFailClosedTargets:
    def test_ambiguous_target_does_not_create_development_intent(self):
        resolver = _StubResolver({}, ambiguous=frozenset({"the widget"}))
        intake = TaskIntake(target_resolver=resolver)
        assert intake.intake("Improve the widget.").task_type.value != (
            "development_request"
        )

    def test_unresolved_target_does_not_create_development_intent(self):
        resolver = _StubResolver({})  # nothing resolves
        intake = TaskIntake(target_resolver=resolver)
        assert intake.intake("Improve the widget.").task_type.value != (
            "development_request"
        )

    def test_blank_target_is_not_development(self):
        resolver = _StubResolver({})
        intake = TaskIntake(target_resolver=resolver)
        assert intake.intake("Improve.").task_type.value != "development_request"

    def test_raising_resolver_fails_closed(self):
        class _Boom:
            def resolve(self, surface, *, expected_type=None):
                raise RuntimeError("resolver unavailable")

        intake = TaskIntake(target_resolver=_Boom())
        assert intake.intake("Improve the widget.").task_type.value != (
            "development_request"
        )


# ---------------------------------------------------------------------------
# 5. Backwards compatibility with no resolver
# ---------------------------------------------------------------------------


class TestNoResolverIsUnchanged:
    def test_existing_noun_gated_forms_still_work(self):
        intake = TaskIntake()
        for text in (
            "Improve the conversation capability.",
            "Improve the conversation module.",
            "Add a deterministic regression test.",
            "Fix a documented bug.",
        ):
            assert intake.intake(text).task_type.value == "development_request", text

    def test_without_resolver_a_service_target_is_not_development(self):
        """Exactly the pre-existing behaviour: no resolver, no typed gating."""
        intake = TaskIntake()
        spec = intake.intake("Improve the conversation service.")
        assert spec.task_type.value == "conversation"

    def test_absent_resolver_is_never_consulted(self):
        resolver = _StubResolver({"the widget": "component"})
        with_resolver = TaskIntake(target_resolver=resolver)
        with_resolver.intake("Improve the widget.")
        assert resolver.calls


# ---------------------------------------------------------------------------
# 6. Real pipeline through the real resolver
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def kernel():
    from atlas.kernel.atlas import Atlas

    atlas = Atlas()
    atlas.start()
    try:
        _ = atlas.repository_map
        yield atlas
    finally:
        atlas.shutdown()


class TestRealPipeline:
    @pytest.mark.parametrize(
        "text",
        (
            "Improve the conversation service.",
            "Improve the conversation component.",
            "Improve the conversation subsystem.",
            "Improve the conversation module.",
            "Improve the conversation capability.",
        ),
    )
    def test_real_kernel_routes_each_surface_to_development(self, kernel, text):
        spec = kernel._conversation._intake(text)
        assert spec.task_type.value == "development_request", text

    def test_real_kernel_keeps_questions_non_development(self, kernel):
        for text in (
            "What is the conversation service?",
            "How does the conversation service work?",
            "Tell me about the conversation service.",
        ):
            spec = kernel._conversation._intake(text)
            assert spec.task_type.value != "development_request", text

    def test_real_kernel_still_investigates(self, kernel):
        spec = kernel._conversation._intake("Investigate the conversation service.")
        assert spec.task_type.value == "investigation_request"

    def test_real_resolver_sees_module_identities_from_the_start(self, kernel):
        """Regression: the resolver must not be frozen at a pre-map snapshot.

        The kernel builds the conversation BEFORE the repository map exists. A
        resolver built from that snapshot addresses only component/capability
        identities, so module identities were silently unresolvable for the whole
        session.
        """
        resolver = kernel._architectural_target_resolver()
        assert resolver is not None
        # Forced AFTER the map exists; the provider form must pick it up.
        assert resolver.resolve("the knowledge manager.").is_resolved

    def test_real_kernel_unresolved_target_is_not_development(self, kernel):
        spec = kernel._conversation._intake(
            "Improve the zzz nonexistent widget while preserving the contract."
        )
        assert spec.task_type.value != "development_request"

    def test_real_kernel_does_not_contact_a_provider(self, kernel):
        assert not bool(kernel._config.get("ai", "external_providers", default=False))
