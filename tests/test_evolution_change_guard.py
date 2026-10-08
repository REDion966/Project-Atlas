"""Command 2 (W3/A2) — deterministic change guards."""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from atlas.evolution.change_guard import (  # noqa: E402
    GUARD_FAILED_KEY,
    GUARD_FAILED_OUTCOME,
    characterise_change,
    guard_metadata,
    guard_reasons,
    was_guard_refused,
)
from atlas.evolution.development_diagnostic import (  # noqa: E402
    DevelopmentDiagnostic,
    DiagnosticFailureClass,
)
from atlas.evolution.development_repair import _is_repairable  # noqa: E402
from atlas.evolution.verification_attribution import (  # noqa: E402
    VerificationTransition,
    transition_of,
)

BEFORE = "def keep(a):\n    return a\n\n\ndef other(b):\n    return b\n"
AFTER = "def keep(a):\n    return a + 1\n\n\ndef other(b):\n    return b\n"


def _outcome(*, guard=True, **metadata):
    from atlas.evolution.development_models import DevelopmentOutcomeStatus

    class _Outcome:
        def __init__(self):
            self.metadata = dict(metadata)
            self.outcome = DevelopmentOutcomeStatus.FAILED
            self.verification_passed = False
            self.rollback_occurred = True
            if guard:
                self.metadata.setdefault(GUARD_FAILED_KEY, True)
                self.test_outcome = GUARD_FAILED_OUTCOME
            else:
                self.test_outcome = "failed"

    return _Outcome()


class TestCleanChanges:
    def test_bounded_single_target_change_is_accepted(self):
        result = characterise_change(
            base={"pkg/x.py": BEFORE}, applied={"pkg/x.py": AFTER}, target="pkg/x.py"
        )
        assert result.ok
        assert result.paths == ("pkg/x.py",)
        assert dict(result.per_file_line_delta)["pkg/x.py"] == 0
        assert result.removed_definitions == ()
        assert result.reasons == ()

    def test_catching_parameter_is_not_a_signature_change(self):
        result = characterise_change(
            base={"pkg/x.py": "def f(a):\n    return a\n"},
            applied={"pkg/x.py": "def f(a, b=1):\n    return a\n"},
            target="pkg/x.py",
        )
        assert result.ok

    def test_new_file_is_accepted(self):
        result = characterise_change(
            base={}, applied={"pkg/new.py": "X = 1\n"}, target="pkg/new.py"
        )
        assert result.ok

    def test_to_dict_is_json_safe(self):
        result = characterise_change(
            base={"pkg/x.py": BEFORE}, applied={"pkg/x.py": AFTER}, target="pkg/x.py"
        )
        payload = result.to_dict()
        assert payload["ok"] is True
        assert payload["per_file_line_delta"] == [["pkg/x.py", 0]]


class TestRefusals:
    def test_out_of_target_modification_is_refused(self):
        result = characterise_change(
            base={"pkg/x.py": BEFORE, "pkg/y.py": "Y = 1\n"},
            applied={"pkg/x.py": AFTER, "pkg/y.py": "Y = 2\n"},
            target="pkg/x.py",
        )
        assert not result.ok
        assert result.out_of_target == ("pkg/y.py",)
        assert any("outside the single authorized target" in r for r in result.reasons)

    def test_removed_definition_is_refused(self):
        result = characterise_change(
            base={"pkg/x.py": BEFORE},
            applied={"pkg/x.py": "def keep(a):\n    return a\n"},
            target="pkg/x.py",
        )
        assert not result.ok
        assert result.removed_definitions == ("pkg/x.py::other",)

    def test_removed_parameter_is_refused(self):
        result = characterise_change(
            base={"pkg/x.py": "def f(a, b):\n    return a\n"},
            applied={"pkg/x.py": "def f(a):\n    return a\n"},
            target="pkg/x.py",
        )
        assert not result.ok
        assert result.signature_changes
        assert any("removes parameter" in r for r in result.reasons)

    def test_no_op_is_refused(self):
        result = characterise_change(
            base={"pkg/x.py": BEFORE}, applied={"pkg/x.py": BEFORE}, target="pkg/x.py"
        )
        assert not result.ok
        assert any("no-op" in r for r in result.reasons)

    def test_parse_failure_is_refused(self):
        result = characterise_change(
            base={"pkg/x.py": BEFORE},
            applied={"pkg/x.py": "def broken(:\n"},
            target="pkg/x.py",
        )
        assert not result.ok
        assert not result.structurally_valid

    def test_oversized_change_is_refused(self):
        applied = {f"pkg/f{index}.py": "X = 1\n" for index in range(20)}
        result = characterise_change(base={}, applied=applied, target="pkg/f0.py")
        assert not result.ok
        assert not result.bounded

    def test_oversized_content_is_refused(self):
        result = characterise_change(
            base={}, applied={"pkg/x.py": "x" * 2_000_001}, target="pkg/x.py"
        )
        assert not result.ok
        assert not result.bounded

    def test_malformed_input_fails_closed(self):
        for bad in ({"pkg/x.py": 1}, [1, 2], 5):
            result = characterise_change(base=bad, applied={"a": "b"}, target="a")
            assert not result.ok
            assert any("malformed" in r for r in result.reasons)

    def test_empty_applied_content_is_refused(self):
        result = characterise_change(base={}, applied={}, target="")
        assert not result.ok

    def test_characterisation_never_raises(self):
        assert characterise_change(base=None, applied=None, target=None)


class TestGuardEvidence:
    def test_metadata_records_the_refusal(self):
        result = characterise_change(
            base={"pkg/x.py": BEFORE}, applied={"pkg/x.py": BEFORE}, target="pkg/x.py"
        )
        metadata = guard_metadata(result)
        assert metadata[GUARD_FAILED_KEY] is True
        assert metadata["change_characterisation"]["ok"] is False

    def test_guard_refusal_is_detected_on_an_outcome(self):
        outcome = _outcome(**guard_metadata(
            characterise_change(base={}, applied={}, target="")
        ))
        assert was_guard_refused(outcome)
        assert guard_reasons(outcome)

    def test_a_clean_outcome_is_not_a_refusal(self):
        assert not was_guard_refused(_outcome(guard=False))

    def test_refusal_is_never_a_verification_transition(self):
        # No pytest ran, so no verification verdict is claimed: the outcome can
        # never be attributed as pass_to_fail or fail_to_fail.
        outcome = _outcome(verification_baseline=None)
        assert transition_of(outcome) is VerificationTransition.UNKNOWN

    def test_refusal_is_an_attributable_authoring_defect(self):
        class _Result:
            status = type("S", (), {"name": "FAILED"})()
            message = "iteration failed."
            outcomes = [_outcome(verification_baseline=None)]

        diagnosis = DevelopmentDiagnostic().diagnose(_Result())
        assert diagnosis.failure_class is DiagnosticFailureClass.IMPLEMENTATION
        assert diagnosis.recoverable is True
        assert GUARD_FAILED_OUTCOME in diagnosis.evidence

    def test_refusal_is_repairable(self):
        assert _is_repairable(_outcome(verification_baseline=None))

    def test_guard_is_bounded(self):
        result = characterise_change(
            base={"pkg/x.py": BEFORE}, applied={"pkg/x.py": BEFORE}, target="pkg/x.py"
        )
        assert len(result.reasons) <= 12
        assert all(len(reason) <= 200 for reason in result.reasons)
