"""Atlas Research - Web Source Adapter (Phase F8).

Normalizes bounded, deterministic HTTP(S) retrieval into the shared
SourceProfile surface so the existing research pipeline treats web
content exactly like file/workspace/codebase sources.

SECURITY CONTRACT (web content is DATA, never instructions):
  * Only ``http`` and ``https`` schemes are accepted.
  * SSRF protection: loopback, private, link-local, multicast, reserved,
    cloud-metadata (169.254.x.x) and documented special-use ranges are
    rejected. IP literals are validated directly; hostnames are validated
    AFTER DNS resolution (injectable resolver).
  * Host policy is injectable and defaults to DENY-BY-DEFAULT: without an
    explicit allowlist entry (or ``allow_unlisted=True``) no host is
    fetchable - there is no unrestricted arbitrary-URL access.
  * Redirects: maximum 3; every hop is revalidated with the same policy.
  * Timeout <= ``timeout_seconds`` (default 10); transport is injected.
  * Response body bounded to ``max_bytes`` (default 512 KiB).
  * Only ``text/*`` and ``application/json`` content types are accepted.
  * Credentials are never sent or echoed: URLs containing userinfo are
    rejected; stored/final URIs are sanitized.
  * Retrieved content is never evaluated, executed, or treated as
    instructions.

Transport is dependency-injected so isolated tests never hit the live
network. Follows the existing source-adapter conventions: malformed/unsafe
URIs raise ``ValueError`` before any I/O; network-level failures return a
SourceProfile with empty text and a bounded ``metadata["load_error"]``.
"""

from __future__ import annotations

import ipaddress
import re
import socket
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Protocol, Sequence, runtime_checkable
from urllib.parse import urljoin, urlsplit, urlunsplit

from atlas.research.models import ResearchSource, SourceKind, SourceProfile
from atlas.research.source_catalog import WEB_SCHEMES
from atlas.research.sources._read import (
    build_profile,
    estimate_line_count,
    estimate_tokens,
)

#: Default response cap (512 KiB). Read incrementally by the default transport.
DEFAULT_MAX_BYTES: int = 512 * 1024
#: Default request/socket timeout (seconds).
DEFAULT_TIMEOUT_SECONDS: float = 10.0
#: Maximum redirect hops allowed for a single source request.
DEFAULT_MAX_REDIRECTS: int = 3

_REDIRECT_STATUSES: frozenset[int] = frozenset({301, 302, 303, 307, 308})

_WHITESPACE_RE: re.Pattern[str] = re.compile(r"\s+")


@runtime_checkable
class WebTransport(Protocol):
    """Raw single-hop HTTP GET transport (injected; never follows redirects)."""

    def get(
        self,
        url: str,
        timeout: float,
        max_bytes: int,
    ) -> tuple[int, list[tuple[str, str]], bytes]:
        """Perform ONE HTTP GET and return ``(status, headers, body)``.

        Redirect following is the adapter's responsibility, never the
        transport's. The transport must not read more than ``max_bytes``
        of body and may raise ``Exception`` for network/timeout failures
        (the adapter fails closed).
        """
        ...


@dataclass(frozen=True, slots=True)
class WebHostPolicy:
    """Deterministic, injectable host allow-policy (SSRF governance).

    ``allowed_hosts`` is the explicit safe allowlist. ``allow_unlisted``
    permits any host not otherwise blocked by IP validation; when ``False``
    (the default) the policy is deny-by-default - no unlisted host is
    ever fetched by the adapter without an explicit allowlist entry.
    """

    allowed_hosts: frozenset[str] = frozenset()
    allow_unlisted: bool = False

    def permits(self, host: str) -> bool:
        """True when ``host`` is explicitly allowlisted or unlisted is allowed."""
        normalized = host.lower().rstrip(".")
        if normalized in self.allowed_hosts:
            return True
        return self.allow_unlisted


#: Module-level deny-by-default policy (no host fetchable by default).
DENY_ALL_HOSTS: WebHostPolicy = WebHostPolicy()


def web_host_policy_from_hosts(hosts: Sequence[str]) -> WebHostPolicy:
    """Build a deny-by-default policy allowing exactly ``hosts``.

    Deterministic and injectable: empty/blank entries are ignored; hosts
    are lowercased with trailing dots stripped (matching the policy's own
    normalization). All SSRF/IP protections remain mandatory regardless of
    the allowlist.
    """
    allowed = frozenset(
        h.lower().rstrip(".") for h in hosts if isinstance(h, str) and h.strip()
    )
    return WebHostPolicy(allowed_hosts=allowed, allow_unlisted=False)


def sanitize_url(url: str) -> str:
    """Return a credential-free representation of ``url``.

    Removes ``userinfo`` (``user:pass@``) from the netloc so stored/final
    URIs never leak credentials. Non-URL input is returned unchanged.
    """
    if not url or "://" not in url:
        return url
    try:
        parts = urlsplit(url)
    except ValueError:
        return url
    if parts.username is None and parts.password is None:
        return url
    host = parts.hostname or ""
    if parts.port is not None:
        host = f"{host}:{parts.port}"
    return urlunsplit(
        (parts.scheme, host, parts.path or "/", parts.query, parts.fragment)
    )


_BLOCKED_NETWORKS: tuple = tuple(
    ipaddress.ip_network(net)
    for net in (
        "0.0.0.0/8",
        "100.64.0.0/10",
        "127.0.0.0/8",
        "169.254.0.0/16",
        "192.0.0.0/24",
        "192.0.2.0/24",
        "192.88.99.0/24",
        "198.18.0.0/15",
        "198.51.100.0/24",
        "203.0.113.0/24",
        "224.0.0.0/4",
        "240.0.0.0/4",
    )
)


def _is_global_address(address: str) -> bool:
    """Return True only for globally routable, unblocked IP addresses."""
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    if (
        ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_private
        or ip.is_unspecified
        or not ip.is_global
    ):
        return False
    for network in _BLOCKED_NETWORKS:
        if ip in network:
            return False
    return True


def _is_ip_literal(host: str) -> bool:
    """True when ``host`` is a literal IP address (v4 or v6)."""
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return False
    return True


def _default_resolve_host(host: str) -> tuple[str, ...]:
    """Resolve ``host`` to a deterministic tuple of unique IP strings."""
    try:
        infos = socket.getaddrinfo(
            host,
            None,
            socket.AF_UNSPEC,
            socket.SOCK_STREAM,
        )
    except OSError:
        return ()
    return tuple(dict.fromkeys(item[4][0] for item in infos))


def _header_value(headers: list[tuple[str, str]], name: str) -> str:
    """Case-insensitive header lookup returning the first match value."""
    lowered = name.lower()
    for key, value in headers:
        if key.lower() == lowered:
            return value
    return ""


def _content_type_allowed(content_type: str) -> bool:
    """True only for ``text/*`` and ``application/json``."""
    base = _WHITESPACE_RE.sub("", content_type).split(";", 1)[0].lower()
    return base.startswith("text/") or base == "application/json"


class DefaultHTTPTransport:
    """Standard-library single-hop transport (manual/offline demonstration).

    Uses ``urllib.request`` with redirects disabled so the adapter owns every
    hop, plus a hard socket ``timeout``. Reads are incremental (chunked bytes)
    and stop at ``max_bytes + 1``. Never used by the isolated test suite.
    """

    def __init__(self) -> None:
        import urllib.request

        self._urlopen = urllib.request.urlopen
        self._redirect_handler_class = _no_redirect_handler()

    def get(
        self,
        url: str,
        timeout: float,
        max_bytes: int,
    ) -> tuple[int, list[tuple[str, str]], bytes]:
        import urllib.request

        opener = urllib.request.build_opener(self._redirect_handler_class)
        with opener.open(url, timeout=float(timeout)) as response:
            status: int = int(getattr(response, "status", getattr(response, "code", 0)))
            headers: list[tuple[str, str]] = [
                (str(key), str(value)) for key, value in response.headers.items()
            ]
            chunks: list[bytes] = []
            remaining: int = int(max_bytes) + 1
            while remaining > 0:
                chunk: bytes = response.read(min(65536, remaining))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            return status, headers, b"".join(chunks)


def _no_redirect_handler():
    """Return an ``HTTPRedirectHandler`` class that never follows redirects."""
    import urllib.request

    class _NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ARG002
            return None

    return _NoRedirect


class WebSourceAdapter:
    """Bounded, deterministic, fail-closed HTTP(S) source adapter.

    Args:
        transport: Injected single-hop transport (never follows redirects).
            Defaults to ``DefaultHTTPTransport`` for manual/offline use; tests
            always inject a fake so no live network is ever touched.
        host_policy: Injectable host allow-policy. Defaults to
            ``DENY_ALL_HOSTS`` (deny-by-default, no host fetchable).
        resolver: Callable resolving a hostname to a tuple of IP strings.
            Defaults to a ``socket.getaddrinfo``-based resolver. IP literals
            are validated directly without the resolver.
        timeout_seconds: Hard per-request timeout (default 10).
        max_bytes: Maximum response body size (default 512 KiB).
        max_redirects: Maximum redirect hops (default 3).
    """

    def __init__(
        self,
        transport: WebTransport | None = None,
        host_policy: WebHostPolicy | None = None,
        resolver: Callable[[str], tuple[str, ...]] | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        max_bytes: int = DEFAULT_MAX_BYTES,
        max_redirects: int = DEFAULT_MAX_REDIRECTS,
    ) -> None:
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        if max_bytes <= 0:
            raise ValueError("max_bytes must be positive")
        if max_redirects < 0:
            raise ValueError("max_redirects must be >= 0")
        self._transport: WebTransport = transport or DefaultHTTPTransport()
        if callable(transport) and not hasattr(transport, "get"):
            self._transport = _CallableTransport(transport)
        self._host_policy: WebHostPolicy = host_policy or DENY_ALL_HOSTS
        self._resolve: Callable[[str], tuple[str, ...]] = (
            resolver or _default_resolve_host
        )
        self._timeout: float = timeout
        self._max_bytes: int = max_bytes
        self._max_redirects: int = max_redirects

    @property
    def timeout(self) -> float:
        """Configured request timeout in seconds."""
        return self._timeout

    @property
    def max_bytes(self) -> int:
        """Configured maximum response body size in bytes."""
        return self._max_bytes

    @property
    def max_redirects(self) -> int:
        """Configured maximum redirect hops."""
        return self._max_redirects

    def supports(self, uri: str) -> bool:
        """True when ``uri`` is an http/https URI this adapter may load.

        The check is cheap and deterministic: scheme allowlist, presence of
        a network host, host-policy allow verdict, and direct rejection of
        IP-literal / 'localhost' hosts that are blocked by SSRF rules. DNS
        resolution is intentionally NOT performed here.
        """
        parsed = self._parse(uri)
        if parsed is None:
            return False
        if parsed.username is not None or parsed.password is not None:
            return False
        host = parsed.hostname or ""
        if not host:
            return False
        if host.lower() in ("localhost",) or _is_ip_literal(host):
            return _is_global_address(host) and self._host_allowed(host)
        return self._host_allowed(host)

    def load(self, uri: str) -> SourceProfile:
        """Retrieve ``uri`` and return a normalized web SourceProfile.

        Raises ``ValueError`` before any I/O for malformed/unsafe URIs
        (scheme, userinfo, missing host, host-policy/IP-blocked). Network,
        size, content-type and redirect failures fail closed: a SourceProfile
        with empty text and a bounded ``metadata["load_error"]``.
        """
        parsed = self._parse(uri)
        if parsed is None:
            raise ValueError(f"unsupported web source URI: {sanitize_url(uri)!r}")
        host = parsed.hostname or ""
        if not host:
            raise ValueError("web source URI must include a host")
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("web source URI must not contain userinfo (credentials)")
        reason = self._host_rejection_reason(host)
        if reason:
            raise ValueError(f"web source host is not permitted: {host!r} ({reason})")
        sanitized = sanitize_url(uri)
        profile = self._fetch(sanitized, host, parsed.scheme, self._max_redirects)
        return profile

    def metadata(self, uri: str) -> ResearchSource:
        """Return a ResearchSource handle for ``uri`` (web)."""
        parsed = self._parse(uri)
        if parsed is None:
            raise ValueError(f"unsupported web source scheme: {uri!r}")
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("web source URI must not contain userinfo (credentials)")
        host = parsed.hostname or ""
        if not host:
            raise ValueError("web source URI must have a host")
        if host.lower() in ("localhost",) or _is_ip_literal(host):
            if not _is_global_address(host):
                raise ValueError(f"web source host is not allowed: {host!r}")
        sanitized = sanitize_url(uri)
        now = datetime.now(timezone.utc)
        return ResearchSource(
            uri=sanitized,
            kind=SourceKind.WEB,
            title=host,
            retrieved_at=now,
            metadata={
                "uri": sanitized,
                "retrieved_at": now.isoformat(),
                "host": host,
            },
        )

    @staticmethod
    def _parse(uri: str):
        """Return a ``SplitResult`` for accepted web URIs, else None."""
        if not isinstance(uri, str) or not uri:
            return None
        try:
            parts = urlsplit(uri)
        except ValueError:
            return None
        if parts.scheme.lower() not in WEB_SCHEMES:
            return None
        if not parts.netloc:
            return None
        return parts

    # ------------------------------------------------------------------
    # Host / SSRF validation
    # ------------------------------------------------------------------

    def _host_allowed(self, host: str) -> bool:
        """True when the host passes the injectable host policy."""
        return self._host_policy.permits(host)

    def _host_rejection_reason(self, host: str) -> str:
        """Return a bounded reason why ``host`` is blocked, or ``""``.

        IP literals are validated directly. Hostnames are validated after
        resolution; an unresolvable host fails closed (blocked).
        """
        normalized = host.lower()
        if not self._host_allowed(normalized):
            return "host not permitted by policy"
        if normalized in ("localhost",):
            return "loopback host rejected"
        if _is_ip_literal(normalized):
            if not _is_global_address(normalized):
                return "non-global IP address rejected"
            return ""
        addresses = self._resolve(normalized)
        if not addresses:
            return "host resolution failed (fail closed)"
        for address in addresses:
            if not _is_global_address(address):
                return f"resolved non-global address rejected: {address}"
        return ""

    # ------------------------------------------------------------------
    # Failure profile (bounded, fail-closed SourceProfile)
    # ------------------------------------------------------------------

    def _error_profile(self, uri: str, host: str, error: str) -> SourceProfile:
        return build_profile(
            uri=uri,
            kind=SourceKind.WEB,
            text="",
            byte_size=0,
            tokens_estimate=0,
            title=host,
            content_type="",
            language="",
            line_count=0,
            load_error=_bounded(error),
        )

    # ------------------------------------------------------------------
    # Retrieval (redirect-aware, bounded)
    # ------------------------------------------------------------------

    def _fetch(
        self,
        uri: str,
        host: str,
        scheme: str,
        redirects_left: int,
    ) -> SourceProfile:
        current: str = uri
        hops: int = 0
        while True:
            if hops > self._max_redirects:
                return self._error_profile(uri, host, "too many redirects")
            try:
                status, headers, body = self._transport.get(
                    current, self._timeout, self._max_bytes
                )
            except Exception as exc:
                return self._error_profile(
                    uri, host, f"net transport failure: {_bounded(exc)}"
                )
            if len(body) > self._max_bytes:
                return self._error_profile(uri, host, "response exceeds size limit")
            if status in _REDIRECT_STATUSES:
                location = _header_value(headers, "location")
                if not location:
                    return self._error_profile(
                        uri, host, f"redirect status {status} without Location"
                    )
                hops += 1
                next_url = urljoin(current, location)
                next_ok, next_reason = self._validate_next_url(next_url)
                if not next_ok:
                    return self._error_profile(
                        uri, host, f"redirect target rejected: {next_reason}"
                    )
                current = sanitize_url(next_url)
                continue

            content_type = _header_value(headers, "content-type")
            if content_type and not _content_type_allowed(content_type):
                return self._error_profile(
                    uri, host, f"unsupported content type: {content_type}"
                )
            try:
                text = body.decode("utf-8")
            except UnicodeDecodeError:
                return self._error_profile(uri, host, "unsupported binary body")
            final_url = sanitize_url(current)
            return SourceProfile(
                uri=uri,
                kind=SourceKind.WEB,
                text=text,
                title=host,
                language="html",
                content_type=(content_type.split(";", 1)[0] if content_type else ""),
                byte_size=len(text.encode("utf-8", errors="replace")),
                tokens_estimate=estimate_tokens(text),
                line_count=estimate_line_count(text),
                loaded_at=datetime.now(timezone.utc),
                metadata={
                    "final_url": final_url,
                    "http_status": status,
                    "host": host,
                    "scheme": scheme,
                    "retrieved_at": datetime.now(timezone.utc).isoformat(),
                },
            )

    def _validate_next_url(self, url: str) -> tuple[bool, str]:
        """Revalidate a redirect target with the full policy (no I/O)."""
        parts = self._parse(url)
        if parts is None:
            return False, "unsupported scheme or malformed URL"
        if parts.username is not None or parts.password is not None:
            return False, "credentials not allowed"
        host = parts.hostname or ""
        if not host:
            return False, "missing host"
        reason = self._host_rejection_reason(host)
        if reason:
            return False, reason
        return True, ""


def _bounded(exc: Exception, limit: int = 200) -> str:
    """Return a bounded, secret-free error message for a failure."""
    text = str(exc).strip() or type(exc).__name__
    return text[:limit]


class _CallableTransport:
    """Adapt a raw ``(url, timeout, max_bytes)`` callable to WebTransport."""

    __slots__ = ("_call",)

    def __init__(self, call: Callable) -> None:
        self._call = call

    def get(self, url: str, timeout: float, max_bytes: int):
        return self._call(url, timeout, max_bytes)
