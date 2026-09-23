"""Phase 13.6 — Cross-process / restart continuity.

Validation result: a cycle's outcome written in one process is recovered by a
completely separate process, which can then see what happened and what remains
open — using only the EXISTING durable evolution storage. No in-memory-only
state is treated as durable history.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]

_CYCLE_CHILD = '''
import os
import sys
from pathlib import Path

from tests.phase13_support import run_cycle, sqlite_memory

db, repo, module, cap, subject = sys.argv[1:6]
db_path = Path(db)
memory, storage = sqlite_memory(db_path.parent, name=db_path.name)
try:
    result = run_cycle(
        memory, Path(repo), subject=subject, capability=cap, module=module,
        promotion_authorized=False,
    )
    print("CHILD_TERMINAL " + result.terminal.value)
    print("CHILD_OUTCOME " + result.outcome.value)
    print("CHILD_PID " + str(os.getpid()))
finally:
    storage.close()
'''

_RESTART_CHILD = '''
import json, sys
from pathlib import Path
from tests.phase13_support import sqlite_memory
from atlas.evolution.evolution_continuity import continuation_view, subject_history

db, subject = sys.argv[1:3]
memory, storage = sqlite_memory(Path(db).parent, name=Path(db).name)
try:
    memory.restore()
    view = continuation_view(memory)
    opportunity = view.for_subject(subject)
    payload = {
        "opportunity": opportunity.to_dict() if opportunity else None,
        "may_attempt": list(view.may_attempt(subject)),
        "history": [f.to_dict() for f in subject_history(memory, subject)],
    }
    print("RESTART_JSON " + json.dumps(payload, sort_keys=True))
finally:
    storage.close()
'''


def _env() -> dict[str, str]:
    env = {"PYTHONPATH": str(_ROOT), "PYTHONDONTWRITEBYTECODE": "1"}
    for key in ("PATH", "SYSTEMROOT", "TEMP", "TMP"):
        value = os.environ.get(key)
        if value:
            env[key] = value
    return env


def _run(script: str, tmp_path: Path, *args: str) -> subprocess.CompletedProcess:
    path = tmp_path / f"phase13_child_{abs(hash(script)) % 10000}.py"
    path.write_text(script, encoding="utf-8")
    return subprocess.run(
        [sys.executable, str(path), *args],
        cwd=str(_ROOT),
        env=_env(),
        capture_output=True,
        text=True,
        timeout=300,
    )


class TestPhase136CrossProcessRestart:
    def test_a_separate_process_recovers_prior_evolution_state(self, tmp_path):
        db = tmp_path / "phase13_restart.db"
        repo = tmp_path / "repo"
        repo.mkdir()

        first = _run(
            _CYCLE_CHILD,
            tmp_path,
            str(db),
            str(repo),
            "atlas/example/restart_handlers.py",
            "example.restart",
            "cap.restart",
        )
        assert first.returncode == 0, first.stderr[-1500:]
        assert "CHILD_TERMINAL pending_promotion_review" in first.stdout

        second = _run(_RESTART_CHILD, tmp_path, str(db), "cap.restart")
        assert second.returncode == 0, second.stderr[-1500:]
        marker = next(
            line
            for line in second.stdout.splitlines()
            if line.startswith("RESTART_JSON ")
        )
        payload = json.loads(marker[len("RESTART_JSON ") :])

        opportunity = payload["opportunity"]
        assert opportunity is not None
        assert opportunity["state"] == "deferred"
        assert opportunity["last_terminal"] == "pending_promotion_review"
        assert payload["may_attempt"][0] is False
        assert payload["history"][0]["terminal"] == "pending_promotion_review"

    def test_the_restart_process_is_genuinely_separate(self, tmp_path):
        db = tmp_path / "phase13_pid.db"
        repo = tmp_path / "repo2"
        repo.mkdir()
        completed = _run(
            _CYCLE_CHILD,
            tmp_path,
            str(db),
            str(repo),
            "atlas/example/pid_handlers.py",
            "example.pid",
            "cap.pid",
        )
        assert completed.returncode == 0, completed.stderr[-1500:]
        assert db.is_file()  # durable, not in-memory
        child_pid = int(
            next(
                line
                for line in completed.stdout.splitlines()
                if line.startswith("CHILD_PID ")
            )[len("CHILD_PID ") :]
        )
        assert child_pid != os.getpid()

    def test_no_durable_state_means_no_invented_history(self, tmp_path):
        empty = tmp_path / "phase13_empty.db"
        completed = _run(_RESTART_CHILD, tmp_path, str(empty), "cap.absent")
        assert completed.returncode == 0, completed.stderr[-1500:]
        payload = json.loads(
            next(
                line
                for line in completed.stdout.splitlines()
                if line.startswith("RESTART_JSON ")
            )[len("RESTART_JSON ") :]
        )
        assert payload["opportunity"] is None
        assert payload["may_attempt"][0] is True  # a fresh subject is attemptable
        assert payload["history"] == []
