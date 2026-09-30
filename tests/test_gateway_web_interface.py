"""Focused tests for the private static page served by the local gateway.

Covers the interface layer only: static serving confined to the designated root,
path-traversal/arbitrary-file rejection, the same-origin page's flow (create →
message → stream → close → list → reopen), the active-conversation query, and
the invariants the page must not weaken (loopback only, no authority route, no
external resource, existing session-boundary and concurrency protections).

Isolated stores; nothing is promoted; the live repository is never written to.
"""

from __future__ import annotations

import json
import pkgutil
import socket
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

import pytest

import atlas.storage as storage_pkg

REPO_ROOT = Path(__file__).resolve().parents[1]

ARCHITECTURE = "what is the responsibility of the conversation service?"
REFERENCE = "what about that component?"
REFUSAL = "what is the quorvex scheduler?"


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


def _raw(base: str, path: str, method: str = "GET", payload=None):
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"{base}{path}",
        data=body,
        headers={"Content-Type": "application/json"} if body else {},
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=120.0) as response:
            return response.status, response.read(), dict(response.headers)
    except urllib.error.HTTPError as error:
        return error.code, error.read(), dict(error.headers)


def _json(base: str, path: str, method: str = "GET", payload=None):
    status, body, headers = _raw(base, path, method, payload)
    try:
        return status, json.loads(body.decode("utf-8")), headers
    except (UnicodeDecodeError, json.JSONDecodeError):
        return status, {"raw": body.decode("utf-8", "replace")}, headers


def _open(base: str) -> str:
    status, payload, _ = _json(base, "/v1/conversation", "POST")
    assert status == 200 and payload["created"] is True
    return payload["conversation_id"]


class TestStaticPageIsServedSameOrigin:
    def test_root_serves_the_page(self, gateway):
        status, body, headers = _raw(gateway.base_url, "/")
        assert status == 200
        assert headers.get("Content-Type", "").startswith("text/html")
        assert headers.get("Cache-Control") == "no-store"
        text = body.decode("utf-8")
        assert "<title>Atlas — local</title>" in text
        assert "v1/conversation" in text

    def test_index_html_serves_the_same_page(self, gateway):
        status, body, _ = _raw(gateway.base_url, "/index.html")
        assert status == 200
        assert b"new conversation" in body.lower()

    def test_page_has_no_external_resource(self, gateway):
        _, body, _ = _raw(gateway.base_url, "/")
        text = body.decode("utf-8")
        for forbidden in ("http://", "https://", "//cdn", "<script src=", "<link rel="):
            assert forbidden not in text
        assert "ws://" not in text and "WebSocket" not in text

    def test_page_is_same_origin_and_loopback_bound(self, gateway):
        host, port = gateway.address
        assert host == "127.0.0.1"
        _, _, headers = _raw(gateway.base_url, "/")
        assert "Access-Control-Allow-Origin" not in headers


class TestStaticConfinement:
    @pytest.mark.parametrize(
        "path",
        [
            "/../config.toml",
            "/../../config.toml",
            "/..%2f..%2fconfig.toml",
            "/%2e%2e/%2e%2e/config.toml",
            "/web/../../README.md",
            "/atlas/kernel/atlas.py",
            "/atlas/cli/gateway.py",
            "/config.toml",
            "/README.md",
            "/pyproject.toml",
            "/atlas_data/atlas_experience.db",
            "/../atlas_data/atlas_experience.db",
        ],
    )
    def test_repository_and_store_files_are_unreachable(self, gateway, path):
        status, body, _ = _raw(gateway.base_url, path)
        assert status == 404, f"{path} was served"
        assert b"unknown gateway route" in body

    def test_missing_asset_is_rejected(self, gateway):
        status, _, _ = _raw(gateway.base_url, "/nope.js")
        assert status == 404

    def test_directory_request_is_rejected(self, gateway):
        status, _, _ = _raw(gateway.base_url, "/web/")
        assert status == 404

    def test_unknown_v1_route_remains_404(self, gateway):
        status, payload, _ = _json(gateway.base_url, "/v1/nope")
        assert status == 404
        assert "unknown gateway route" in payload["error"]


class TestPageFlowThroughTheGateway:
    """Everything the page does, exercised over the real HTTP surface."""

    def test_active_conversation_query(self, gateway):
        status, payload, _ = _json(gateway.base_url, "/v1/conversation")
        assert status == 200
        assert payload["active"] is False and payload["conversation_id"] is None
        conversation_id = _open(gateway.base_url)
        status, payload, _ = _json(gateway.base_url, "/v1/conversation")
        assert status == 200
        assert payload["active"] is True
        assert payload["conversation_id"] == conversation_id

    def test_create_message_stream_close_list(self, gateway):
        conversation_id = _open(gateway.base_url)

        status, payload, _ = _json(
            gateway.base_url,
            f"/v1/conversation/{conversation_id}/message",
            "POST",
            {"message": ARCHITECTURE},
        )
        assert status == 200
        assert "Responsibility:" in payload["content"]
        assert payload["metadata"]["builtin_intent"] == "architecture"

        status, body, headers = _raw(
            gateway.base_url,
            f"/v1/conversation/{conversation_id}/stream",
            "POST",
            {"message": ARCHITECTURE},
        )
        assert status == 200
        assert "chunked" in headers.get("Transfer-Encoding", "")
        assert headers.get("Content-Type", "").startswith("text/plain")
        assert "Responsibility:" in body.decode("utf-8")

        status, payload, _ = _json(
            gateway.base_url, f"/v1/conversation/{conversation_id}/close", "POST", {}
        )
        assert status == 200 and payload["closed"] is True
        assert payload["detail"]

        status, payload, _ = _json(gateway.base_url, "/v1/conversations")
        assert status == 200
        assert any(path.endswith(".json") for path in payload["saved_conversations"])

    def test_refusal_is_displayed_unmodified(self, gateway):
        from atlas.kernel.atlas import Atlas

        direct = Atlas()
        direct.start()
        try:
            expected = direct.chat(REFUSAL).content
        finally:
            direct.shutdown()
        conversation_id = _open(gateway.base_url)
        status, payload, _ = _json(
            gateway.base_url,
            f"/v1/conversation/{conversation_id}/message",
            "POST",
            {"message": REFUSAL},
        )
        assert status == 200
        assert payload["content"] == expected

    def test_error_payload_is_reported_for_bad_input(self, gateway):
        conversation_id = _open(gateway.base_url)
        status, body, _ = _raw(
            gateway.base_url,
            f"/v1/conversation/{conversation_id}/message",
            "POST",
            None,
        )
        status, body, _ = _raw(
            gateway.base_url,
            f"/v1/conversation/{conversation_id}/stream",
            "POST",
            {"message": ""},
        )
        assert status == 400
        assert b"non-empty string" in body


class TestReopenPersistedConversation:
    def _save_one(self, gateway) -> str:
        conversation_id = _open(gateway.base_url)
        _json(
            gateway.base_url,
            f"/v1/conversation/{conversation_id}/message",
            "POST",
            {"message": ARCHITECTURE},
        )
        _json(gateway.base_url, f"/v1/conversation/{conversation_id}/close", "POST", {})
        _, payload, _ = _json(gateway.base_url, "/v1/conversations")
        assert payload["saved_conversations"]
        return payload["saved_conversations"][0]

    def test_reopen_restores_the_persisted_conversation(self, gateway):
        saved = self._save_one(gateway)
        status, payload, _ = _json(
            gateway.base_url, "/v1/conversation/reopen", "POST", {"file": saved}
        )
        assert status == 200 and payload["reopened"] is True
        reopened = payload["conversation_id"]
        assert reopened
        # the reopened conversation accepts new turns through the same surfaces
        status, answer, _ = _json(
            gateway.base_url,
            f"/v1/conversation/{reopened}/message",
            "POST",
            {"message": ARCHITECTURE},
        )
        assert status == 200
        assert "Responsibility:" in answer["content"]
        # the reopened conversation behaves normally for new turns: the enforcing
        # question above re-establishes the subject, so a follow-up reference
        # resolves from THIS conversation's own new turn (the persisted artifact
        # carries the message history, not the live reference state)
        status, follow_up, _ = _json(
            gateway.base_url,
            f"/v1/conversation/{reopened}/message",
            "POST",
            {"message": REFERENCE},
        )
        assert status == 200
        assert follow_up["metadata"].get("reference_field") == "current_subject"

    def test_reopen_is_refused_while_another_conversation_is_active(self, gateway):
        saved = self._save_one(gateway)
        _open(gateway.base_url)
        status, payload, _ = _json(
            gateway.base_url, "/v1/conversation/reopen", "POST", {"file": saved}
        )
        assert status == 409 and payload["reopened"] is False
        assert "ONE active conversation" in payload["reason"]

    @pytest.mark.parametrize(
        "path",
        ["/etc/passwd", "config.toml", "../config.toml", "/", ""],
    )
    def test_reopen_refuses_paths_outside_the_persisted_list(self, gateway, path):
        status, payload, _ = _json(
            gateway.base_url, "/v1/conversation/reopen", "POST", {"file": path}
        )
        assert status == 409 and payload["reopened"] is False
        assert payload["conversation_id"] == ""

    def test_reopen_does_not_leak_the_previous_session(self, gateway):
        first = self._save_one(gateway)  # conversation with an architecture subject
        conversation_id = _open(gateway.base_url)
        _json(
            gateway.base_url,
            f"/v1/conversation/{conversation_id}/message",
            "POST",
            {"message": "Add a capability that summarises the reopened leak probe."},
        )
        _json(gateway.base_url, f"/v1/conversation/{conversation_id}/close", "POST", {})

        status, payload, _ = _json(
            gateway.base_url, "/v1/conversation/reopen", "POST", {"file": first}
        )
        assert status == 200
        reopened = payload["conversation_id"]
        # the reopened (older) conversation must not surface the OTHER session's
        # development intent
        status, intent, _ = _json(
            gateway.base_url,
            f"/v1/conversation/{reopened}/message",
            "POST",
            {"message": "what is the current development intent?"},
        )
        assert status == 200
        assert "reopened leak probe" not in intent["content"]
        # and it still answers normally
        status, answer, _ = _json(
            gateway.base_url,
            f"/v1/conversation/{reopened}/message",
            "POST",
            {"message": ARCHITECTURE},
        )
        assert status == 200 and "Responsibility:" in answer["content"]


class TestInvariantsPreserved:
    def test_no_authority_route_exists(self, gateway):
        for path in ("/v1/approve", "/v1/authorize", "/v1/execute", "/v1/promote"):
            status, payload, _ = _json(gateway.base_url, path, "POST", {})
            assert status == 404
            assert "unknown gateway route" in payload["error"]

    def test_session_boundary_and_single_active_conversation_intact(self, gateway):
        first = _open(gateway.base_url)
        status, payload, _ = _json(gateway.base_url, "/v1/conversation", "POST")
        assert status == 409 and payload["created"] is False
        _json(gateway.base_url, f"/v1/conversation/{first}/close", "POST", {})
        second = _open(gateway.base_url)
        assert second != first
        status, reference, _ = _json(
            gateway.base_url,
            f"/v1/conversation/{second}/message",
            "POST",
            {"message": REFERENCE},
        )
        assert status == 200
        assert reference["metadata"].get("reference_field") is None

    def test_no_external_network_is_used(self, gateway, monkeypatch):
        original = socket.socket.connect

        def _connect(self, address, *args, **kwargs):
            host = str(address[0]) if isinstance(address, tuple) and address else ""
            if host not in ("127.0.0.1", "localhost", "::1"):
                raise AssertionError(f"external network connect attempted: {address}")
            return original(self, address, *args, **kwargs)

        monkeypatch.setattr(socket.socket, "connect", _connect)
        conversation_id = _open(gateway.base_url)
        status, payload, _ = _json(
            gateway.base_url,
            f"/v1/conversation/{conversation_id}/message",
            "POST",
            {"message": ARCHITECTURE},
        )
        assert status == 200
        assert payload["metadata"].get("model_used") is False
        static_status, _static_body, _static_headers = _raw(gateway.base_url, "/")
        assert static_status == 200


class TestStaticRootLocation:
    def test_static_root_is_the_gateway_web_directory(self):
        from atlas.cli import gateway as gateway_module

        root = Path(gateway_module.STATIC_ROOT)
        assert root.name == "web"
        assert root.parent.name == "cli"
        assert (root / "index.html").is_file()
        assert REPO_ROOT in root.parents
