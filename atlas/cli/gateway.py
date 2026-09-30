"""Atlas Local Gateway — a loopback-only transport adapter for the local instance.

Purpose
-------
Expose the EXISTING ``Atlas.chat()`` and ``Atlas.stream()`` entry points over a
local HTTP interface so a future frontend (terminal, desktop or browser UI) can
talk to the local Atlas instance.

Architectural rule (transport only)
-----------------------------------
This module is a TRANSPORT/INTERFACE ADAPTER and nothing else. It contains no
intelligence, no reasoning, no routing, no knowledge, no research, no
development, no approval, no authorization, no execution, no verification and no
promotion logic. Every message is handed to the EXISTING Atlas APIs and the
EXISTING Atlas answer (including any refusal or error) is returned unchanged.

It never approves, authorizes, executes, promotes, mutates permissions, changes
source authorization, bypasses the sandbox, verification or promotion gates, and
it never reinterprets or softens an Atlas refusal: refusals arrive as ordinary
Atlas content (HTTP 200) and genuine Atlas exceptions become HTTP 500 carrying
the exception's own type and message verbatim.

Model independence
------------------
No AI model, no external provider and no model-routing logic is added here. The
gateway only forwards text; Atlas decides everything else.

Local only
----------
The server binds to loopback only (``127.0.0.1``). A non-loopback host is
rejected at construction time, so the gateway cannot expose Atlas to the LAN or
the Internet. There is no authentication, no tenancy and no public surface.

Concurrency and session strategy (honest limitation)
---------------------------------------------------
The smallest safe approach supported by the existing architecture: the gateway
serves ONE active conversation at a time, serialized through a lock, so a second
HTTP request waits rather than interleaving with a running turn. A request for a
second *active* conversation is refused with an explicit ``409`` (fail-closed).

Kernel construction has exactly ONE authoritative, race-safe install path
(``_ensure_kernel``), which takes the lock itself; no other code constructs or
installs a kernel, so two kernels can never be built for one gateway, an installed
kernel cannot be overwritten or orphaned, and the kernel attached to the active
conversation cannot be replaced by another request. The read-only
saved-conversation listing never constructs or starts a kernel: it reads through
the SAME existing persistence abstraction the kernel delegates to.

A conversation identifier IS a real conversation boundary: ending a conversation
(``POST /v1/conversation/{id}/close``) persists it with the EXISTING
``Atlas.save_conversation()`` and then ends its session with the EXISTING
``Atlas.shutdown()`` lifecycle call; the next conversation therefore starts from
a NEWLY constructed kernel, so it cannot inherit the previous conversation's
history, references, subjects, ambiguity state or conversational world state.
Nothing inside ``ConversationService`` is inspected or reset, and no conversation
state is manipulated directly. The cost is honest and bounded: starting a
conversation after a previous one closed constructs a fresh Atlas kernel (a few
seconds), which is why concurrent conversations are deliberately not offered in
this first private version.

Endpoints
---------
``GET /`` and ``GET /index.html``
    The single static private page (read-only, same-origin, served only from
    ``STATIC_ROOT`` = ``atlas/cli/web``; nothing outside that directory is ever
    reachable and no CORS support is needed because the page is same-origin).
``POST /v1/conversation``
    Create a conversation identifier. Refused with ``409`` while another
    conversation is active.
``POST /v1/conversation/reopen``
    JSON ``{"file": "..."}`` -> reopen a PERSISTED conversation that the existing
    saved-conversation list already contains, via the existing
    ``Atlas.load_conversation()``. Refused with ``409`` while another conversation
    is active, and for any path that is not a persisted Atlas conversation.
``GET /v1/conversation``
    Pure lifecycle query: the active conversation identifier, if any.
``POST /v1/conversation/{id}/message``
    JSON ``{"message": "..."}`` -> JSON response with the Atlas answer and its
    own metadata.
``POST /v1/conversation/{id}/stream``
    Same input, streamed as chunked ``text/plain`` using ``Atlas.stream()``.
``GET /v1/conversations``
    List the EXISTING saved conversations (read-only; the same persistence
    abstraction ``Atlas.saved_conversations()`` delegates to — no kernel is
    constructed or started).
``POST /v1/conversation/{id}/close``
    End the active conversation: persist it with the EXISTING
    ``Atlas.save_conversation()`` and end its session with the EXISTING
    ``Atlas.shutdown()``, so the next conversation starts fresh. The identifier
    is then released.

There is deliberately no approve/authorize/execute/promote/configure route.
"""

from __future__ import annotations

import argparse
import json
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from atlas.kernel.atlas import Atlas
from atlas.storage.conversation_storage import ConversationStorage

#: The only host this gateway will ever bind to.
LOOPBACK_HOST: str = "127.0.0.1"

#: The single read-only directory this gateway will ever serve files from. Static
#: serving is confined to it: nothing outside it (repository sources, stores,
#: configuration) is reachable, and requests are read-only.
STATIC_ROOT: Path = (Path(__file__).resolve().parent / "web")

#: Content types for the (bounded) static asset kinds this gateway serves.
_STATIC_TYPES: dict[str, str] = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
}


#: Default local port (override with ``--port``; ``0`` selects an ephemeral port).
DEFAULT_PORT: int = 8765

#: Upper bound on a request body (a bounded transport, not a data channel).
MAX_BODY_BYTES: int = 1_048_576

#: Bounded, JSON-safe projection of Atlas's own response metadata. Values that are
#: not JSON-native are rendered with ``str`` for transport only — the gateway never
#: changes what Atlas returned, it only serializes it.
_METADATA_MAX_ITEMS: int = 64


def sanitize_metadata(metadata: Any) -> dict[str, Any]:
    """Return a bounded, JSON-serializable view of Atlas's own metadata."""
    if not isinstance(metadata, dict):
        return {}
    out: dict[str, Any] = {}
    for index, (key, value) in enumerate(metadata.items()):
        if index >= _METADATA_MAX_ITEMS:
            break
        text_key = str(key)
        try:
            json.dumps(value)
        except (TypeError, ValueError):
            out[text_key] = str(value)
        else:
            out[text_key] = value
    return out


class AtlasGateway:
    """A loopback-only HTTP transport in front of one local Atlas kernel.

    The instance owns the kernel lifecycle (``Atlas()`` -> ``start()`` ->
    ``tick()`` after each completed turn -> ``save_conversation()`` ->
    ``shutdown()``) exactly as the existing interactive CLI contract does.
    """

    def __init__(self, host: str = LOOPBACK_HOST, port: int = DEFAULT_PORT) -> None:
        if host not in ("127.0.0.1", "localhost", "::1"):
            raise ValueError(
                "Atlas gateway binds to loopback only; refusing host "
                f"{host!r} (no LAN or Internet exposure)"
            )
        self._host = LOOPBACK_HOST
        self._requested_port = int(port)
        self._atlas: Atlas | None = None
        self._server: ThreadingHTTPServer | None = None
        #: Reentrant: ``_ensure_kernel`` is the single install path and takes this
        #: lock itself, while callers like ``create_conversation`` already hold it.
        self._lock = threading.RLock()
        self._conversation_id: str | None = None
        self._counter = 0
        self._thread: threading.Thread | None = None
        #: Existing Atlas persistence abstraction, used ONLY for read-only listing
        #: so that listing never constructs or starts a kernel.
        self._storage: ConversationStorage | None = None

    # -- lifecycle ---------------------------------------------------------

    def start(self) -> None:
        """Start the kernel, bind the loopback server and begin serving.

        Serving runs on a bounded daemon thread so callers (and tests) can use the
        gateway immediately; ``stop()`` shuts the loop down cleanly. The kernel is
        constructed, started and (on ``stop``) shut down exactly as the existing
        interactive CLI contract does.
        """
        if self._atlas is None:
            self._ensure_kernel()
        if self._server is None:
            handler = _make_handler(self)
            self._server = ThreadingHTTPServer(
                (self._host, self._requested_port), handler
            )
            self._server.daemon_threads = True
            self._thread = threading.Thread(
                target=self._server.serve_forever,
                name="atlas-gateway",
                daemon=True,
            )
            self._thread.start()

    @property
    def address(self) -> tuple[str, int]:
        """The bound address; raises when the gateway has not been started."""
        if self._server is None:
            raise RuntimeError("Atlas gateway has not been started.")
        return tuple(self._server.server_address[:2])  # type: ignore[return-value]

    @property
    def base_url(self) -> str:
        host, port = self.address
        return f"http://{host}:{port}"

    def wait(self) -> None:
        """Block while the serving loop runs (used by the manual entry point)."""
        thread = self._thread
        if thread is None:
            raise RuntimeError("Atlas gateway has not been started.")
        thread.join()

    def stop(self) -> None:
        """Stop serving, persist the conversation and shut the kernel down."""
        if self._server is not None:
            self._server.shutdown()  # safe: the serve loop runs on our thread
            self._server.server_close()
            self._server = None
        if self._thread is not None:
            self._thread.join(timeout=5.0)
            self._thread = None
        if self._atlas is not None:
            with self._lock:
                if self._conversation_id is not None:
                    try:
                        self._atlas.save_conversation()
                    except Exception:  # fail-soft: shutdown must still happen
                        pass
                    self._conversation_id = None
                try:
                    self._atlas.shutdown()
                finally:
                    self._atlas = None

    # -- conversation handling --------------------------------------------

    def _ensure_kernel(self) -> Atlas:
        """The SINGLE authoritative Atlas Kernel-install path (race-safe).

        Contract: this is the only place a kernel is constructed and installed.
        It acquires the gateway lock itself (the lock is reentrant), so concurrent
        callers can never build two kernels, overwrite an installed kernel, orphan
        a kernel, or move an active conversation onto a different kernel. Every
        caller — ``start()`` and ``create_conversation()`` — goes through it.

        Building a NEW kernel through the documented lifecycle (``Atlas()`` ->
        ``start()``) is what gives a new conversation a genuinely fresh boundary;
        no internal conversation state is inspected or manipulated here.
        """
        with self._lock:
            if self._atlas is None:
                kernel = Atlas()
                kernel.start()
                self._atlas = kernel
            return self._atlas

    @property
    def atlas(self) -> Atlas:
        if self._atlas is None:
            raise RuntimeError("Atlas gateway has not been started.")
        return self._atlas

    @property
    def conversation_id(self) -> str | None:
        return self._conversation_id

    @property
    def busy(self) -> bool:
        """True while a turn is executing (used for honest status reporting)."""
        return self._lock.locked()

    def create_conversation(self) -> tuple[bool, str, str]:
        """Create the single active conversation with FRESH Atlas state.

        Returns ``(created, conversation_id, reason)``. A second conversation is
        refused rather than silently sharing the active conversation state. When
        the previous conversation was closed (its kernel was shut down through the
        existing lifecycle), a fresh kernel is started first, so the new
        conversation begins with no inherited history, referent, ambiguity or
        world state.
        """
        with self._lock:
            if self._conversation_id is not None:
                return (
                    False,
                    self._conversation_id,
                    "this gateway serves ONE active conversation at a time; "
                    "close the current conversation before starting another",
                )
            self._ensure_kernel()
            self._counter += 1
            self._conversation_id = f"conv-{self._counter:04d}"
            return (True, self._conversation_id, "")

    def close_conversation(self, conversation_id: str) -> tuple[bool, str]:
        """Persist the active conversation and END its session (fresh boundary).

        Persistence uses the EXISTING ``Atlas.save_conversation()`` and the
        conversational state is then ended with the EXISTING ``Atlas.shutdown()``
        lifecycle call, so the next conversation cannot inherit this one's
        history, references, subjects, ambiguity or world state. No internal
        conversation state is inspected or reset directly.
        """
        with self._lock:
            if self._conversation_id != conversation_id:
                return (False, "unknown or inactive conversation identifier")
            saved = ""
            try:
                saved = str(self.atlas.save_conversation())
            except Exception as exc:  # fail-soft: the session still ends
                saved = f"(not saved: {type(exc).__name__})"
            try:
                self.atlas.shutdown()
            finally:
                self._conversation_id = None
                self._atlas = None
            return (True, saved)

    def _check_conversation(self, conversation_id: str) -> str:
        if self._conversation_id is None:
            return "no active conversation; create one first"
        if self._conversation_id != conversation_id:
            return "unknown or inactive conversation identifier"
        return ""

    def send_message(self, conversation_id: str, text: str) -> dict[str, Any]:
        """Run ONE turn through the EXISTING ``Atlas.chat()``."""
        problem = self._check_conversation(conversation_id)
        if problem:
            raise _GatewayRefusal(HTTPStatus.CONFLICT, problem)
        with self._lock:
            problem = self._check_conversation(conversation_id)
            if problem:
                raise _GatewayRefusal(HTTPStatus.CONFLICT, problem)
            message = self.atlas.chat(text)
            self.atlas.tick()
        return {
            "conversation_id": conversation_id,
            "role": str(getattr(message, "role", "assistant")),
            "content": str(getattr(message, "content", "") or ""),
            "metadata": sanitize_metadata(getattr(message, "metadata", {})),
        }

    def stream_message(self, conversation_id: str, text: str):
        """Stream ONE turn through the EXISTING ``Atlas.stream()`` (chunks).

        The conversation check runs EAGERLY, so an invalid conversation is reported
        as an honest HTTP status before any response headers are sent; the lock is
        held inside the returned generator for the duration of the stream.
        """
        problem = self._check_conversation(conversation_id)
        if problem:
            raise _GatewayRefusal(HTTPStatus.CONFLICT, problem)
        return self._stream_turns(conversation_id, text)

    def _stream_turns(self, conversation_id: str, text: str):
        with self._lock:
            problem = self._check_conversation(conversation_id)
            if problem:
                raise _GatewayRefusal(HTTPStatus.CONFLICT, problem)
            for chunk in self.atlas.stream(text):
                yield str(chunk)
            self.atlas.tick()

    def saved_conversations(self) -> list[str]:
        """The EXISTING saved-conversation list — genuinely read-only.

        Uses the SAME existing persistence abstraction the kernel's
        ``saved_conversations()`` delegates to (``ConversationStorage``, whose
        ``list()`` is what ``Atlas.saved_conversations()`` returns). It therefore
        constructs NO Atlas kernel, starts nothing, creates no conversation,
        cannot replace an active kernel, and mutates no conversational state.
        """
        storage = self._storage
        if storage is None:
            storage = ConversationStorage()
            self._storage = storage
        return [str(path) for path in storage.list()]

    def active_conversation(self) -> dict[str, Any]:
        """Pure lifecycle query: the active conversation, if any (no side effects)."""
        with self._lock:
            conversation_id = self._conversation_id
            return {
                "conversation_id": conversation_id,
                "active": conversation_id is not None,
                "kernel_installed": self._atlas is not None,
            }

    def reopen_conversation(self, file_path: str) -> tuple[bool, str, str]:
        """Reopen a PERSISTED conversation through the EXISTING Atlas API.

        Returns ``(reopened, conversation_id, reason)``. The requested file must be
        one of the conversations the existing persistence abstraction already
        lists (so no arbitrary path can ever be loaded), and no conversation may be
        active (a second active conversation is refused, exactly like ``create``).
        Reopening adopts that persisted conversation with the existing
        ``Atlas.load_conversation()``; when no kernel is live a fresh kernel is
        started first, so nothing from an earlier session can leak into it.
        ConversationService internals are never touched, and no second persistence
        layer exists.
        """
        with self._lock:
            if self._conversation_id is not None:
                return (
                    False,
                    self._conversation_id,
                    "this gateway serves ONE active conversation at a time; "
                    "close the current conversation before reopening another",
                )
            requested = str(file_path or "").strip()
            if not requested:
                return (False, "", "'file' must be the path of a saved conversation")
            allowed = {str(Path(item)) for item in self.saved_conversations()}
            normalised = str(Path(requested))
            if normalised not in allowed:
                return (
                    False,
                    "",
                    "that path is not a persisted Atlas conversation; only the "
                    "existing saved-conversation list may be reopened",
                )
            self._ensure_kernel()
            try:
                self.atlas.load_conversation(Path(normalised))
            except Exception as exc:
                return (False, "", f"{type(exc).__name__}: {exc}")
            self._counter += 1
            self._conversation_id = f"conv-{self._counter:04d}"
            return (True, self._conversation_id, "")


class _GatewayRefusal(Exception):
    """A transport-level refusal (never used to soften an Atlas answer)."""

    def __init__(self, status: HTTPStatus, reason: str) -> None:
        super().__init__(reason)
        self.status = status
        self.reason = reason


def _make_handler(gateway: AtlasGateway):
    """Build the request handler bound to ``gateway`` (no handler state beyond it)."""

    class _Handler(BaseHTTPRequestHandler):
        server_version = "AtlasLocalGateway/1.0"
        protocol_version = "HTTP/1.1"

        # -- plumbing ------------------------------------------------------

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
            """Keep the transport quiet; the gateway prints its own banner."""

        def _send_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(int(status))
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _read_body(self) -> dict[str, Any]:
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except (TypeError, ValueError):
                raise _GatewayRefusal(
                    HTTPStatus.BAD_REQUEST, "malformed Content-Length"
                )
            if length <= 0:
                return {}
            if length > MAX_BODY_BYTES:
                raise _GatewayRefusal(
                    HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "request body too large"
                )
            raw = self.rfile.read(length)
            try:
                parsed = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                raise _GatewayRefusal(
                    HTTPStatus.BAD_REQUEST, "request body must be JSON"
                )
            if not isinstance(parsed, dict):
                raise _GatewayRefusal(
                    HTTPStatus.BAD_REQUEST, "request body must be a JSON object"
                )
            return parsed

        @staticmethod
        def _message_text(payload: dict[str, Any]) -> str:
            text = payload.get("message")
            if not isinstance(text, str) or not text.strip():
                raise _GatewayRefusal(
                    HTTPStatus.BAD_REQUEST, "'message' must be a non-empty string"
                )
            return text

        # -- routes --------------------------------------------------------

        def do_GET(self) -> None:  # noqa: N802
            path = urlparse(self.path).path or "/"
            try:
                if path.rstrip("/") == "/v1/conversation":
                    self._send_json(HTTPStatus.OK, gateway.active_conversation())
                    return
                if path.rstrip("/") == "/v1/conversations":
                    self._send_json(
                        HTTPStatus.OK,
                        {"saved_conversations": gateway.saved_conversations()},
                    )
                    return
                if path.startswith("/v1/"):
                    self._not_found()
                    return
                # Everything else is a read-only static asset request, confined to
                # the designated static root (no repository, store or config file
                # is reachable, and nothing outside the root can be addressed).
                self._serve_static("index.html" if path in ("/", "") else path)
            except _GatewayRefusal as refusal:
                self._send_json(refusal.status, {"error": refusal.reason})
            except Exception as exc:  # Atlas error passes through verbatim
                self._send_json(
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                    {"error": f"{type(exc).__name__}: {exc}"},
                )

        def do_POST(self) -> None:  # noqa: N802
            path = urlparse(self.path).path.rstrip("/") or "/"
            parts = [part for part in path.split("/") if part]
            try:
                if parts == ["v1", "conversation", "reopen"]:
                    payload = self._read_body()
                    file_path = payload.get("file")
                    if not isinstance(file_path, str):
                        raise _GatewayRefusal(
                            HTTPStatus.BAD_REQUEST,
                            "'file' must be the path of a saved conversation",
                        )
                    reopened, conversation_id, reason = gateway.reopen_conversation(
                        file_path
                    )
                    self._send_json(
                        HTTPStatus.OK if reopened else HTTPStatus.CONFLICT,
                        {
                            "reopened": reopened,
                            "conversation_id": conversation_id,
                            "reason": reason,
                        },
                    )
                    return
                if parts == ["v1", "conversation"]:
                    created, conversation_id, reason = gateway.create_conversation()
                    self._send_json(
                        HTTPStatus.OK if created else HTTPStatus.CONFLICT,
                        {
                            "conversation_id": conversation_id,
                            "created": created,
                            "reason": reason,
                        },
                    )
                    return
                if (
                    len(parts) == 4
                    and parts[0] == "v1"
                    and parts[1] == "conversation"
                    and parts[3] == "message"
                ):
                    payload = self._read_body()
                    result = gateway.send_message(
                        parts[2], self._message_text(payload)
                    )
                    self._send_json(HTTPStatus.OK, result)
                    return
                if (
                    len(parts) == 4
                    and parts[0] == "v1"
                    and parts[1] == "conversation"
                    and parts[3] == "stream"
                ):
                    payload = self._read_body()
                    chunks = gateway.stream_message(
                        parts[2], self._message_text(payload)
                    )
                    self._stream(chunks)
                    return
                if (
                    len(parts) == 4
                    and parts[0] == "v1"
                    and parts[1] == "conversation"
                    and parts[3] == "close"
                ):
                    closed, detail = gateway.close_conversation(parts[2])
                    self._send_json(
                        HTTPStatus.OK if closed else HTTPStatus.CONFLICT,
                        {"closed": closed, "detail": detail},
                    )
                    return
                self._not_found()
            except _GatewayRefusal as refusal:
                self._send_json(refusal.status, {"error": refusal.reason})
            except Exception as exc:  # Atlas error passes through verbatim
                self._send_json(
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                    {"error": f"{type(exc).__name__}: {exc}"},
                )

        def _stream(self, chunks) -> None:
            """Stream Atlas chunks as chunked text (no framing innovation)."""
            started = False
            try:
                self.send_response(int(HTTPStatus.OK))
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Transfer-Encoding", "chunked")
                self.end_headers()
                for chunk in chunks:
                    started = True
                    data = chunk.encode("utf-8")
                    if not data:
                        continue
                    self.wfile.write(f"{len(data):X}\r\n".encode("ascii"))
                    self.wfile.write(data + b"\r\n")
                    self.wfile.flush()
                self.wfile.write(b"0\r\n\r\n")
                self.wfile.flush()
            except Exception:
                # An Atlas error mid-stream cannot change an already-sent status;
                # the stream simply ends (the transport does not invent an answer).
                if started:
                    from contextlib import suppress

                    with suppress(Exception):
                        self.wfile.write(b"0\r\n\r\n")
                return

        def _serve_static(self, requested_path: str) -> None:
            """Serve one READ-ONLY file confined to ``STATIC_ROOT``.

            The request path is URL-decoded, normalised and resolved against the
            static root; anything that escapes the root (`..`, absolute paths,
            symlinked escapes, directory requests) is refused with 404. Only the
            bounded asset kinds in ``_STATIC_TYPES`` are served, so repository
            sources, stores and configuration can never be reached.
            """
            relative = unquote(requested_path).replace("\\", "/").lstrip("/")
            if not relative or ".." in relative.split("/"):
                self._not_found()
                return
            root = STATIC_ROOT.resolve()
            candidate = (root / relative).resolve()
            if root not in candidate.parents or not candidate.is_file():
                self._not_found()
                return
            content_type = _STATIC_TYPES.get(candidate.suffix.lower())
            if content_type is None:
                self._not_found()
                return
            try:
                body = candidate.read_bytes()
            except OSError:
                self._not_found()
                return
            self.send_response(int(HTTPStatus.OK))
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _not_found(self) -> None:
            self._send_json(
                HTTPStatus.NOT_FOUND,
                {
                    "error": "unknown gateway route",
                    "routes": [
                        "GET  /",
                        "GET  /v1/conversation",
                        "GET  /v1/conversations",
                        "POST /v1/conversation",
                        "POST /v1/conversation/reopen",
                        "POST /v1/conversation/{id}/message",
                        "POST /v1/conversation/{id}/stream",
                        "POST /v1/conversation/{id}/close",
                    ],
                },
            )

    return _Handler


def main(argv: list[str] | None = None) -> int:
    """Run the loopback gateway until interrupted (Ctrl+C)."""
    parser = argparse.ArgumentParser(
        prog="atlas-gateway",
        description="Local loopback-only HTTP transport for the local Atlas instance.",
    )
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args(argv)

    gateway = AtlasGateway(port=args.port)
    gateway.start()
    print("Atlas local gateway (loopback only; transport adapter; no authority)")
    print(f"  listening: {gateway.base_url}")
    print("  create   : POST /v1/conversation")
    print("  message  : POST /v1/conversation/{id}/message")
    print("  stream   : POST /v1/conversation/{id}/stream")
    print("  close    : POST /v1/conversation/{id}/close")
    print("  saved    : GET  /v1/conversations")
    print("  Press Ctrl+C to stop.")
    try:
        gateway.wait()
    except KeyboardInterrupt:
        print("\nStopping Atlas local gateway.")
    finally:
        gateway.stop()
    return 0


if __name__ == "__main__":  # pragma: no cover - manual entry point
    raise SystemExit(main())
