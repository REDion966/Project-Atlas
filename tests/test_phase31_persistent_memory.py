"""Phase 3.1 — Persistent memory: evidence contract.

Investigation result (evidence, not aspiration): Atlas already owns a
deterministic, model-independent, Atlas-owned persistent memory capability, so
no new memory infrastructure was introduced.

The authoritative persistent-memory path is the existing ``atlas.memory``
subsystem:

* ``atlas/memory/models/memory.py::Memory`` — a structured memory item
  (``id``, ``title``, ``content``, ``memory_type``, ``importance``, ``tags``,
  ``source``, ``created_at``, ``updated_at``) with ``to_dict``/``from_dict``.
* ``atlas/memory/storage/json_storage.py::Storage`` — the file-backed
  persistence adapter (JSON).
* ``atlas/memory/repository/memory_repository.py::MemoryRepository`` — CRUD
  over the storage adapter; reads/writes the file per operation, so no explicit
  restore step is required after a fresh process start.
* ``atlas/memory/service/memory_manager_service.py::MemoryManagerService`` —
  the kernel-wired, Atlas-owned retrieval interface (``add_memory`` /
  ``get_memory`` / ``list_memories`` / ``delete_memory`` / ``search``); the
  container key is ``memory``.

Richer SQLite-backed persistence also already exists (Track C long-term
memory; experience/evolution/understanding/research/toolchain/reasoning
storage), and MEMORY-scope writes are reachable through the governed autonomy
adapter (``atlas/evolution/autonomy/adapters/memory_adapter.py``). These tests
pin the core requirement: a structured item that survives a genuine process
boundary, is retrievable through the Atlas-owned interface, and requires no
external model/network.
"""

from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

from atlas.memory.enums import MemoryImportance, MemoryType
from atlas.memory.models.memory import Memory
from atlas.memory.repository.memory_repository import MemoryRepository
from atlas.memory.storage.json_storage import Storage

_REPO_ROOT = Path(__file__).resolve().parents[1]

#: Two-process driver: ``write`` stores one memory and exits; ``read`` (a fresh
#: interpreter) retrieves it through the Atlas-owned repository interface. The
#: target file is injected by environment so the real repository is exercised
#: without touching the repository's own data/memory.json.
_DRIVER = """
import os
import sys
from pathlib import Path

from atlas.memory.storage.json_storage import Storage

Storage.MEMORY_FILE = Path(os.environ["ATLAS_MEM_FILE"])
Storage.DATA_DIR = Storage.MEMORY_FILE.parent

from atlas.memory.enums import MemoryType
from atlas.memory.models.memory import Memory
from atlas.memory.repository.memory_repository import MemoryRepository

repo = MemoryRepository()
if sys.argv[1] == "write":
    repo.add(
        Memory(
            id="proc-1",
            title="Process-boundary memory",
            content="from-process-A",
            memory_type=MemoryType.PROJECT,
            tags=["phase31"],
            source="process-a",
        )
    )
    print("WROTE")
else:
    memory = repo.get("proc-1")
    assert memory is not None, "memory lost across process boundary"
    assert memory.content == "from-process-A"
    assert memory.tags == ["phase31"]
    assert memory.source == "process-a"
    print("READ:" + memory.content)
"""


class TestPhase31PersistentMemoryEvidence:
    def test_memory_item_is_structured_and_serializable(self):
        memory = Memory(
            id="m1",
            title="Title",
            content="Content",
            memory_type=MemoryType.PROJECT,
            importance=MemoryImportance.HIGH,
            tags=["a", "b"],
            source="unit-test",
        )

        data = memory.to_dict()
        assert data["id"] == "m1"
        assert data["memory_type"] == "project"
        assert data["importance"] == MemoryImportance.HIGH.value
        assert data["tags"] == ["a", "b"]
        assert data["source"] == "unit-test"
        assert data["created_at"]
        assert data["updated_at"]

        # A fresh object reconstructs the identical structured record.
        assert Memory.from_dict(data) == memory

    def test_repository_persists_to_disk_and_reloads(self, tmp_path):
        memory_file = tmp_path / "memory.json"

        with patch.object(Storage, "MEMORY_FILE", memory_file):
            MemoryRepository().add(
                Memory(
                    id="p31-a",
                    title="Persisted",
                    content="survives",
                    tags=["phase31"],
                    source="test",
                )
            )
            assert memory_file.exists()

        # A brand-new repository instance over the same file (as after a fresh
        # initialization) reads the record back deterministically.
        with patch.object(Storage, "MEMORY_FILE", memory_file):
            loaded = MemoryRepository().get("p31-a")
            assert loaded is not None
            assert loaded.content == "survives"
            assert loaded.tags == ["phase31"]
            assert loaded.source == "test"

    def test_memory_survives_a_process_boundary(self, tmp_path):
        memory_file = tmp_path / "memory.json"
        driver = tmp_path / "driver.py"
        driver.write_text(_DRIVER, encoding="utf-8")
        env = dict(
            os.environ,
            PYTHONPATH=str(_REPO_ROOT),
            ATLAS_MEM_FILE=str(memory_file),
        )

        proc_a = subprocess.run(
            [sys.executable, str(driver), "write"],
            cwd=str(tmp_path),
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert proc_a.returncode == 0, proc_a.stderr
        assert "WROTE" in proc_a.stdout
        assert memory_file.exists()

        # Process A has terminated; a fresh interpreter retrieves the memory.
        proc_b = subprocess.run(
            [sys.executable, str(driver), "read"],
            cwd=str(tmp_path),
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert proc_b.returncode == 0, proc_b.stderr
        assert "READ:from-process-A" in proc_b.stdout

    def test_memory_persistence_path_has_no_model_or_network_imports(self):
        banned = ("openai", "anthropic", "ollama", "requests", "httpx", "urllib")
        for relative in (
            "atlas/memory/storage/json_storage.py",
            "atlas/memory/repository/memory_repository.py",
            "atlas/memory/service/memory_manager_service.py",
            "atlas/memory/models/memory.py",
        ):
            tree = ast.parse(
                (_REPO_ROOT / relative).read_text(encoding="utf-8")
            )
            imported: set[str] = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.update(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported.add(node.module)
            for module in imported:
                assert not module.startswith(banned), (
                    f"{relative} imports {module}"
                )
