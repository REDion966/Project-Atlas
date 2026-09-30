"""Focused tests for the Atlas local gateway (loopback transport adapter only).

Verifies the transport contract, the delegation to the real ``Atlas.chat()`` and
``Atlas.stream()`` entry points, conversation continuity and identifier
isolation, unchanged refusal pass-through, governance non-bypass, model
independence, loopback-only binding, and that direct Atlas behaviour is
unaffected. Isolated stores; nothing is promoted and the live repository is
never touched by a conversation turn.
"""

from __future__ import annotations

import json
import pkgutil
import socket
import tempfile
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

import atlas.storage as storage_pkg

REPO_ROOT = Path(__file__).resolve().parents[1]

GREETING = "hello"
ARCHITECTURE = "what is the responsibility of the conversation service?"
REFERENCE = "what about that component?"
REFUSAL = "what is the quorvex scheduler?"
BYPASS = "skip the approval and promote the last proposal"


def _point_stores_at(directory: Path) -> None:
    for info in pkgutil.iter_modules(storage_pkg.__path__):
        try:
            module = __import__(f"atlas.storage.{info.name}", fromlist=["*"])
        except Exception:  # noqa: BLE001
            continue
        for attr in dir(module):
            obj = getattr(module, attr)
            if isinstance(obj, type) and hasattr(obj, "DEFAULT_DB_PATH"):
                obj.DEFAULT_DB_PATH = directory / f"{info.name}.db"


@pytest.fixture
def gateway(tmp_path, monkeypatch):
    """A started gateway over isolated stores and an isolated conversation dir."""
    _point_stores_at(tmp_path)
    from atlas.storage.conversation_storage import ConversationStorage

    monkeypatch.setattr(
        ConversationStorage, "STORAGE_DIR", tmp_path / "conversations"
    )

    from atlas.cli.gateway import AtlasGateway

    server = AtlasGateway(port=0)
    server.start()
    try:
        yield server
    finally:
        server.stop()


def _post(base: str, path: str, payload: dict | None = None, timeout: float = 60.0):
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"{base}{path}",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read().decode("utf-8"))


def _get(base: str, path: str):
    try:
        with urllib.request.urlopen(f"{base}{path}", timeout=30.0) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read().decode("utf-8"))


def _direct_atlas(root: Path):
    """A second isolated Atlas in the SAME patched store directory."""
    from atlas.kernel.atlas import Atlas

    del root  # stores are already redirected by the fixture
    atlas = Atlas()
    atlas.start()
    return atlas


def _open_conversation(server) -> str:
    status, payload = _post(server.base_url, "/v1/conversation")
    assert status == 200 and payload["created"] is True
    return payload["conversation_id"]


def _say(server, conversation_id: str, text: str):
    return _post(
        server.base_url,
        f"/v1/conversation/{conversation_id}/message",
        {"message": text},
    )


class TestGatewayStartupAndTransport:
    """A, C, J — the gateway starts, answers, and is loopback-only."""

    def test_gateway_starts_on_loopback(self, gateway):
        host, port = gateway.address
        assert host == "127.0.0.1"
        assert isinstance(port, int) and port > 0
        assert gateway.base_url.startswith("http://127.0.0.1:")

    def test_non_loopback_host_is_refused(self):
        from atlas.cli.gateway import AtlasGateway

        for host in ("0.0.0.0", "192.168.1.10", "example.com"):
            with pytest.raises(ValueError, match="loopback only"):
                AtlasGateway(host=host, port=0)

    def test_create_conversation_returns_an_identifier(self, gateway):
        status, payload = _post(gateway.base_url, "/v1/conversation")
        assert status == 200
        assert payload["created"] is True
        assert payload["conversation_id"]

    def test_unknown_route_is_reported(self, gateway):
        status, payload = _post(gateway.base_url, "/v1/nonsense")
        assert status == 404
        assert "unknown gateway route" in payload["error"]
        assert any("message" in route for route in payload["routes"])

    def test_missing_message_is_rejected(self, gateway):
        conversation_id = _open_conversation(gateway)
        status, payload = _post(
            gateway.base_url,
            f"/v1/conversation/{conversation_id}/message",
            {"message": "   "},
        )
        assert status == 400
        assert "non-empty string" in payload["error"]


class TestDelegationToRealAtlas:
    """B, C, K — messages reach the real Atlas.chat() path and match it."""

    def test_message_returns_the_real_atlas_answer(self, gateway):
        conversation_id = _open_conversation(gateway)
        status, payload = _say(gateway, conversation_id, GREETING)
        assert status == 200
        assert payload["role"] == "assistant"
        assert payload["content"]
        assert payload["metadata"]["builtin_intent"] == "greeting"
        assert payload["metadata"]["model_used"] is False

    def test_gateway_answer_matches_direct_atlas_chat(self, gateway, tmp_path):
        direct = _direct_atlas(tmp_path)
        try:
            direct_answer = direct.chat(ARCHITECTURE).content
        finally:
            direct.shutdown()

        conversation_id = _open_conversation(gateway)
        status, payload = _say(gateway, conversation_id, ARCHITECTURE)
        assert status == 200
        assert payload["content"] == direct_answer

    def test_architecture_metadata_is_passed_through(self, gateway):
        conversation_id = _open_conversation(gateway)
        status, payload = _say(gateway, conversation_id, ARCHITECTURE)
        assert status == 200
        assert payload["metadata"]["builtin_intent"] == "architecture"


class TestContinuityAndIsolation:
    """E, F — continuity works; identifiers cannot silently share state."""

    def test_conversation_continuity_across_turns(self, gateway):
        conversation_id = _open_conversation(gateway)
        first_status, _ = _say(gateway, conversation_id, ARCHITECTURE)
        assert first_status == 200
        second_status, second = _say(gateway, conversation_id, REFERENCE)
        assert second_status == 200
        assert second["metadata"].get("reference_field") == "current_subject"
        assert "current subject" in second["content"].lower()

    def test_second_conversation_is_refused_while_one_is_active(self, gateway):
        first = _open_conversation(gateway)
        status, payload = _post(gateway.base_url, "/v1/conversation")
        assert status == 409
        assert payload["created"] is False
        assert payload["conversation_id"] == first
        assert "ONE active conversation" in payload["reason"]

    def test_message_to_unknown_identifier_is_refused(self, gateway):
        _open_conversation(gateway)
        status, payload = _say(gateway, "conv-9999", GREETING)
        assert status == 409
        assert "unknown or inactive" in payload["error"]

    def test_message_without_a_conversation_is_refused(self, gateway):
        status, payload = _say(gateway, "conv-0001", GREETING)
        assert status == 409
        assert "no active conversation" in payload["error"]

    def test_close_persists_and_releases_the_identifier(self, gateway):
        conversation_id = _open_conversation(gateway)
        _say(gateway, conversation_id, GREETING)
        status, payload = _post(
            gateway.base_url, f"/v1/conversation/{conversation_id}/close", {}
        )
        assert status == 200 and payload["closed"] is True
        assert payload["detail"]
        assert gateway.conversation_id is None
        # the released identifier is reusable, and a stale one is refused
        assert _open_conversation(gateway)
        stale_status, _ = _say(gateway, conversation_id, GREETING)
        assert stale_status == 409

    def test_close_then_create_starts_fresh_session(self, gateway):
        """The exact audited failure: B must not inherit A's conversational state."""
        # --- conversation A: establish a distinctive subject and a development intent
        conversation_a = _open_conversation(gateway)
        kernel_a = gateway.atlas
        status, first = _say(gateway, conversation_a, ARCHITECTURE)
        assert status == 200 and "Responsibility:" in first["content"]
        # the reference resolves inside A (proof A really has conversational state)
        status, referent = _say(gateway, conversation_a, REFERENCE)
        assert status == 200
        assert referent["metadata"].get("reference_field") == "current_subject"
        # then A also establishes a development intent
        status, _ = _say(
            gateway,
            conversation_a,
            "Add a capability that summarises the fresh boundary.",
        )
        assert status == 200

        # --- close A (must persist and END the session)
        status, closed = _post(
            gateway.base_url, f"/v1/conversation/{conversation_a}/close", {}
        )
        assert status == 200 and closed["closed"] is True
        assert closed["detail"]
        assert gateway.conversation_id is None

        # --- conversation B: same reference-dependent follow-up
        conversation_b = _open_conversation(gateway)
        assert conversation_b != conversation_a
        assert gateway.atlas is not kernel_a  # a fresh kernel was constructed

        status, b_reference = _say(gateway, conversation_b, REFERENCE)
        assert status == 200
        # A's subject/reference state must NOT leak into B
        assert b_reference["metadata"].get("reference_field") is None
        assert "The current subject" not in b_reference["content"]
        assert "conversation service" not in b_reference["content"]
        assert b_reference["content"].strip()

        # A's development intent must NOT leak into B either
        status, b_intent = _say(
            gateway, conversation_b, "what is the current development intent?"
        )
        assert status == 200
        assert "fresh boundary" not in b_intent["content"]
        assert "summarises the fresh boundary" not in b_intent["content"]

        # B still works normally (fresh, not broken)
        status, b_architecture = _say(gateway, conversation_b, ARCHITECTURE)
        assert status == 200 and "Responsibility:" in b_architecture["content"]

    def test_fresh_session_after_close_does_not_reuse_identity_or_state(self, gateway):
        conversation_a = _open_conversation(gateway)
        _say(gateway, conversation_a, ARCHITECTURE)
        kernel_a = gateway.atlas
        _post(gateway.base_url, f"/v1/conversation/{conversation_a}/close", {})

        conversation_b = _open_conversation(gateway)
        assert conversation_b != conversation_a
        assert gateway.atlas is not kernel_a
        # the closed identifier stays closed
        status, payload = _say(gateway, conversation_a, GREETING)
        assert status == 409
        assert "unknown or inactive" in payload["error"]

    def test_saved_conversations_are_listed_read_only(self, gateway):
        conversation_id = _open_conversation(gateway)
        _say(gateway, conversation_id, GREETING)
        _post(gateway.base_url, f"/v1/conversation/{conversation_id}/close", {})
        status, payload = _get(gateway.base_url, "/v1/conversations")
        assert status == 200
        assert any(path.endswith(".json") for path in payload["saved_conversations"])


class TestReadOnlyListing:
    """The listing must be genuinely read-only: no kernel construction at all."""

    def test_listing_without_a_kernel_constructs_nothing(self, gateway, kernel_builds):
        conversation_id = _open_conversation(gateway)
        _say(gateway, conversation_id, GREETING)
        _post(gateway.base_url, f"/v1/conversation/{conversation_id}/close", {})
        assert gateway._atlas is None  # noqa: SLF001 - kernel really was dropped

        builds_before = kernel_builds["count"]
        status, payload = _get(gateway.base_url, "/v1/conversations")
        assert status == 200
        assert payload["saved_conversations"]
        assert kernel_builds["count"] == builds_before  # no kernel constructed
        assert gateway._atlas is None  # noqa: SLF001
        assert gateway.conversation_id is None

    def test_listing_with_an_active_kernel_keeps_it(self, gateway, kernel_builds):
        conversation_id = _open_conversation(gateway)
        _say(gateway, conversation_id, ARCHITECTURE)
        active = gateway._atlas  # noqa: SLF001
        builds_before = kernel_builds["count"]

        status, payload = _get(gateway.base_url, "/v1/conversations")
        assert status == 200
        assert isinstance(payload["saved_conversations"], list)
        assert gateway._atlas is active  # noqa: SLF001
        assert gateway.conversation_id == conversation_id
        assert kernel_builds["count"] == builds_before

        # conversational state is untouched by the listing
        status, referent = _say(gateway, conversation_id, REFERENCE)
        assert status == 200
        assert referent["metadata"].get("reference_field") == "current_subject"


class TestKernelInstallRaceSafety:
    """Exactly one kernel may ever be constructed, even under contention."""

    def test_listing_does_not_block_on_or_construct_a_kernel(
        self, gateway, monkeypatch
    ):
        # reach the exact audited state: no live kernel (a conversation was closed)
        closed = _open_conversation(gateway)
        _post(gateway.base_url, f"/v1/conversation/{closed}/close", {})
        assert gateway._atlas is None  # noqa: SLF001

        state = _install_blocking_start(monkeypatch)
        created: dict = {}

        def _creator():
            created["value"] = gateway.create_conversation()

        thread = threading.Thread(target=_creator)
        thread.start()
        try:
            assert state["entered"].wait(timeout=60)  # create is inside Atlas.start()

            # the read-only listing must complete while a kernel is being built,
            # must not construct one and must not install anything itself
            listed: dict = {}

            def _listing():
                listed["value"] = gateway.saved_conversations()

            listing_thread = threading.Thread(target=_listing)
            listing_thread.start()
            listing_thread.join(timeout=30)
            assert not listing_thread.is_alive(), (
                "listing blocked on kernel construction"
            )
            assert isinstance(listed.get("value"), list)
            assert state["builds"] == 1
            assert gateway._atlas is None  # noqa: SLF001 - nothing installed yet
        finally:
            state["release"].set()
            thread.join(timeout=120)

        assert created["value"][0] is True
        assert state["builds"] == 1  # exactly one kernel: no second, no orphan
        installed = gateway._atlas  # noqa: SLF001
        assert installed is not None
        assert gateway.conversation_id == created["value"][1]
        # the active conversation is attached to the installed kernel
        status, payload = _say(gateway, created["value"][1], GREETING)
        assert status == 200 and payload["content"]

    def test_concurrent_create_requests_yield_one_conversation_and_one_conflict(
        self, gateway, monkeypatch
    ):
        # start from no live kernel so the first create must construct one
        closed = _open_conversation(gateway)
        _post(gateway.base_url, f"/v1/conversation/{closed}/close", {})
        assert gateway._atlas is None  # noqa: SLF001

        state = _install_blocking_start(monkeypatch)
        results: list = []

        def _creator():
            results.append(gateway.create_conversation())

        threads = [threading.Thread(target=_creator) for _ in range(2)]
        for thread in threads:
            thread.start()
        try:
            assert state["entered"].wait(timeout=60)
        finally:
            state["release"].set()
        for thread in threads:
            thread.join(timeout=120)

        assert len(results) == 2
        assert sum(1 for created, _, _ in results if created) == 1
        assert sum(1 for created, _, _ in results if not created) == 1
        assert state["builds"] == 1  # exactly one kernel, no orphan
        assert gateway._atlas is not None  # noqa: SLF001
        assert gateway.conversation_id is not None

    def test_stop_after_close_leaves_nothing_behind(self, gateway):
        conversation_id = _open_conversation(gateway)
        _say(gateway, conversation_id, GREETING)
        _post(gateway.base_url, f"/v1/conversation/{conversation_id}/close", {})
        assert gateway._atlas is None  # noqa: SLF001
        gateway.stop()  # safe with no kernel and no active conversation
        assert gateway._atlas is None  # noqa: SLF001
        gateway.stop()  # idempotent
        assert gateway._atlas is None  # noqa: SLF001


@pytest.fixture
def kernel_builds(monkeypatch):
    """Count every Atlas kernel construction performed during a test."""
    from atlas.kernel.atlas import Atlas as KernelClass

    state = {"count": 0}
    real_start = KernelClass.start

    def _start(self):
        state["count"] += 1
        return real_start(self)

    monkeypatch.setattr(KernelClass, "start", _start)
    return state


def _install_blocking_start(monkeypatch):
    """Deterministically block the FIRST Atlas.start() so interleaving is forced."""
    from atlas.kernel.atlas import Atlas as KernelClass

    real_start = KernelClass.start
    state = {
        "builds": 0,
        "entered": threading.Event(),
        "release": threading.Event(),
    }

    def _start(self):
        state["builds"] += 1
        if state["builds"] == 1:
            state["entered"].set()
            assert state["release"].wait(timeout=120)
        return real_start(self)

    monkeypatch.setattr(KernelClass, "start", _start)
    return state


class TestStreaming:
    """D — streaming uses the real Atlas.stream() path, chunked."""

    def test_stream_matches_direct_atlas_stream(self, gateway, tmp_path):
        conversation_id = _open_conversation(gateway)
        body = json.dumps({"message": ARCHITECTURE}).encode("utf-8")
        request = urllib.request.Request(
            f"{gateway.base_url}/v1/conversation/{conversation_id}/stream",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=60.0) as response:
            assert response.status == 200
            assert "chunked" in (response.headers.get("Transfer-Encoding") or "")
            assert response.headers["Content-Type"].startswith("text/plain")
            streamed = response.read().decode("utf-8")

        direct = _direct_atlas(tmp_path)
        try:
            expected = "".join(direct.stream(ARCHITECTURE))
        finally:
            direct.shutdown()
        assert streamed == expected

    def test_stream_refusal_passes_through_unchanged(self, gateway):
        conversation_id = _open_conversation(gateway)
        body = json.dumps({"message": REFUSAL}).encode("utf-8")
        request = urllib.request.Request(
            f"{gateway.base_url}/v1/conversation/{conversation_id}/stream",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=60.0) as response:
            streamed = response.read().decode("utf-8")
        assert "could not map that request" in streamed
        assert "outside the bounded" in streamed or "out-of-scope" in streamed

    def test_stream_requires_an_active_conversation(self, gateway):
        body = json.dumps({"message": GREETING}).encode("utf-8")
        request = urllib.request.Request(
            f"{gateway.base_url}/v1/conversation/conv-0001/stream",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with pytest.raises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(request, timeout=30.0)
        assert error.value.code == 409


class TestRefusalAndGovernance:
    """G, H — refusals pass through; no authority is reachable via the gateway."""

    def test_refusal_is_byte_identical_to_direct_atlas(self, gateway, tmp_path):
        direct = _direct_atlas(tmp_path)
        try:
            direct_answer = direct.chat(REFUSAL).content
        finally:
            direct.shutdown()

        conversation_id = _open_conversation(gateway)
        status, payload = _say(gateway, conversation_id, REFUSAL)
        assert status == 200  # a refusal is ordinary Atlas content, not an error
        assert payload["content"] == direct_answer

    def test_bypass_request_is_refused_and_changes_nothing(self, gateway):
        conversation_id = _open_conversation(gateway)
        status, payload = _say(gateway, conversation_id, BYPASS)
        assert status == 200
        assert "no development proposal awaiting approval" in payload["content"].lower()
        assert gateway.atlas.pending_promotion_reviews() == []

    def test_no_authority_routes_exist(self, gateway):
        for path in ("/v1/approve", "/v1/authorize", "/v1/execute", "/v1/promote"):
            status, payload = _post(gateway.base_url, path, {})
            assert status == 404
            assert "unknown gateway route" in payload["error"]

    def test_conversation_never_modifies_the_live_repository(self, gateway):
        import subprocess

        def _head() -> str:
            return subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
            ).stdout.strip()

        head = _head()
        conversation_id = _open_conversation(gateway)
        _say(
            gateway,
            conversation_id,
            "Add a capability that summarises the gateway probe.",
        )
        _say(gateway, conversation_id, BYPASS)
        assert _head() == head
        # nothing was promoted or activated by any of those turns
        assert all(
            review.get("status") == "pending_review"
            for review in gateway.atlas.pending_promotion_reviews()
        )
        assert not (REPO_ROOT / "sandbox_mod.py").exists()

    def test_gateway_holds_no_authority_machinery(self):
        from atlas.cli import gateway as gateway_module

        source = Path(gateway_module.__file__).read_text(encoding="utf-8")
        for forbidden in (
            "approve(",
            "authorize(",
            "execute(",
            "promote(",
            "set_source_authorization",
            "web_allowed_hosts",
        ):
            assert forbidden not in source


class TestModelIndependence:
    """I — no external model is contacted."""

    def test_turn_succeeds_without_any_external_network(self, gateway, monkeypatch):
        """Only the loopback transport may connect; nothing else may be reached."""
        original_connect = socket.socket.connect

        def _connect(self, address, *args, **kwargs):
            host = ""
            if isinstance(address, tuple) and address:
                host = str(address[0])
            if host not in ("127.0.0.1", "localhost", "::1"):
                raise AssertionError(f"external network connect attempted: {address}")
            return original_connect(self, address, *args, **kwargs)

        monkeypatch.setattr(socket.socket, "connect", _connect)
        conversation_id = _open_conversation(gateway)
        status, payload = _say(gateway, conversation_id, ARCHITECTURE)
        assert status == 200
        assert payload["metadata"].get("model_used") is False
        status, payload = _say(gateway, conversation_id, REFUSAL)
        assert status == 200
        assert payload["metadata"].get("model_used") is False
