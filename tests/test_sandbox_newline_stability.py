"""Sandbox text I/O is newline-faithful (Command 3 finding).

The E2 apply read-back verify compares the written content to the requested
content, so a lossy newline translation would reject a VALID change containing
CRLF. These focus the smallest invariant: ``CodeSandbox.write_text`` /
``read_text`` round-trip content byte-faithfully, and the E2 applier's read-back
accepts CRLF content.
"""

from __future__ import annotations

from atlas.evolution.autonomy.code_execution import CodeApplier
from atlas.evolution.autonomy.code_sandbox import CodeSandbox
from atlas.evolution.autonomy.models import EvolutionRequest
from atlas.evolution.governance.models import ScopeType

CRLF = "def f():\n    return 1\r\n\r\n# crlf note\r\n"


def _request(content: str) -> EvolutionRequest:
    return EvolutionRequest(
        request_id="diag-newline",
        source="diag",
        target_scope=ScopeType.CODE,
        change_payload={"code_changes": [{"path": "mod.py", "content": content}]},
    )


def test_crlf_content_round_trips_through_the_sandbox():
    sandbox = CodeSandbox()
    try:
        sandbox.write_text("a/b.py", CRLF)
        assert sandbox.read_text("a/b.py") == CRLF
    finally:
        sandbox.cleanup()


def test_applier_read_back_accepts_crlf_content():
    sandbox = CodeSandbox()
    try:
        request = _request(CRLF)
        assert CodeApplier().apply(request, sandbox.writer()).success
        assert CodeApplier().verify(request, sandbox.reader()).passed
    finally:
        sandbox.cleanup()


def test_lf_content_still_round_trips():
    sandbox = CodeSandbox()
    try:
        text = "VALUE = 1\n"
        sandbox.write_text("mod.py", text)
        assert sandbox.read_text("mod.py") == text
    finally:
        sandbox.cleanup()
