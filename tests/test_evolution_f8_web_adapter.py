"""Phase F8 - Web Source Adapter tests.

Focused deterministic coverage of the bounded, fail-closed HTTP(S) adapter.
No live network is ever touched: every test injects a fake transport (and a
fake DNS resolver where hostnames are used).

Covers: scheme allowlist, SSRF (loopback/private/link-local/metadata/resolved
addresses), host-policy deny-by-default, redirects (safe/revalidation/limit),
size limit, content-type validation, malformed responses, provenance,
sanitization, and deterministic repeated retrieval.
"""

import pytest

from atlas.research.models import SourceKind
from atlas.research.sources.web import (
    DENY_ALL_HOSTS,
    WebHostPolicy,
    WebSourceAdapter,
    sanitize_url,
)

OPEN = WebHostPolicy(allowed_hosts={"example.com"})
OPEN_ALL = WebHostPolicy(allow_unlisted=True)

GLOBAL_IP = "93.184.216.34"
BODY = b"Atlas is an operating framework. It is deterministic."


def _adapter(factory=None, host_policy=None, resolver=None, **kwargs):
    return WebSourceAdapter(
        transport=factory or _ok(),
        host_policy=host_policy if host_policy is not None else OPEN,
        resolver=resolver or (lambda host: (GLOBAL_IP,)),
        **kwargs,
    )


def _ok(response_body=BODY):
    def _handler(url, timeout, max_bytes):
        return 200, [("Content-Type", "text/plain")], response_body

    return _handler


class TestSchemeAllowlist:
    def test_http_and_https_supported(self):
        for url in ("https://example.com/index.md", "http://example.com/"):
            assert _adapter().supports(url)

    def test_unsupported_schemes_rejected(self):
        adapter = _adapter()
        for url in (
            "ftp://example.com/x",
            "file:///etc/passwd",
            "data:text/plain,hi",
            "gopher://example.com/",
            "wss://example.com/",
        ):
            assert not adapter.supports(url)
        with pytest.raises(ValueError):
            adapter.load("ftp://example.com/x")

    def test_malformed_urls_rejected(self):
        adapter = _adapter()
        assert not adapter.supports("")
        assert not adapter.supports("http://")
        assert not adapter.supports("not a url")


class TestSSRF:
    @pytest.mark.parametrize(
        "url",
        (
            "http://127.0.0.1/x",
            "http://localhost/x",
            "http://localhost.",
            "http://10.0.0.1/x",
            "http://192.168.1.1/x",
            "http://172.16.0.1/x",
            "http://169.254.169.254/latest/meta-data/",
            "http://169.254.0.1/x",
            "http://100.64.0.1/x",
            "http://[::1]/x",
            "http://[fe80::1]/x",
            "http://[fd00::1]/x",
            "http://0.0.0.0/x",
        ),
    )
    def test_blocked_literal_hosts(self, url):
        adapter = _adapter()
        assert not adapter.supports(url)
        with pytest.raises(ValueError):
            adapter.load(url)

    def test_resolved_private_ip_rejected(self):
        adapter = _adapter(resolver=lambda host: ("10.0.0.5",))
        assert adapter.supports("http://example.com/")
        with pytest.raises(ValueError):
            adapter.load("http://example.com/")

    def test_resolved_global_permits_fetch(self):
        calls = []

        def handler(url, timeout, max_bytes):
            calls.append(url)
            return 200, [("Content-Type", "text/plain")], b"ok"

        profile = _adapter(handler, resolver=lambda host: (GLOBAL_IP,)).load(
            "http://example.com/ok"
        )
        assert profile.text == "ok"
        assert calls == ["http://example.com/ok"]

    def test_unresolvable_host_fails_closed(self):
        adapter = _adapter(resolver=lambda host: ())
        assert adapter.supports("http://example.com/")
        with pytest.raises(ValueError):
            adapter.load("http://example.com/")

    def test_deny_by_default_host_policy(self):
        adapter = _adapter(host_policy=DENY_ALL_HOSTS)
        assert not adapter.supports("https://example.com/")
        with pytest.raises(ValueError):
            adapter.load("https://example.com/")

    def test_allow_unlisted_but_ip_blocking_remains(self):
        adapter = _adapter(host_policy=OPEN_ALL)
        assert adapter.supports("https://anything.example/")
        assert not adapter.supports("https://127.0.0.1/")
class TestTransportBehavior:
    def test_success_profile_and_provenance(self):
        profile = _adapter().load("http://example.com/doc.md")
        assert profile.kind is SourceKind.WEB
        assert profile.uri == "http://example.com/doc.md"
        assert profile.text == BODY.decode("utf-8")
        assert profile.metadata["http_status"] == 200
        assert profile.metadata["host"] == "example.com"
        assert profile.metadata["scheme"] == "http"
        assert profile.metadata["final_url"].startswith("http://")
        assert "retrieved_at" in profile.metadata

    def test_timeout_failure_fails_closed(self):
        def boom(url, timeout, max_bytes):
            raise TimeoutError("timed out")

        profile = _adapter(boom).load("http://example.com/")
        assert profile.text == ""
        assert "net transport failure" in profile.metadata["load_error"]

    def test_response_size_limit(self):
        big = b"x" * (512 * 1024 + 10)

        def send(url, timeout, max_bytes):
            return 200, [("Content-Type", "text/plain")], big

        profile = _adapter(send).load("http://example.com/big")
        assert "size limit" in profile.metadata["load_error"]

    def test_content_type_rejected(self):
        def send(url, timeout, max_bytes):
            return 200, [("Content-Type", "application/octet-stream")], b"data"

        profile = _adapter(send).load("http://example.com/")
        assert "unsupported content type" in profile.metadata["load_error"]

    def test_application_json_allowed(self):
        def send(url, timeout, max_bytes):
            return 200, [("Content-Type", "application/json")], b'{"a": 1}'

        profile = _adapter(send).load("http://example.com/")
        assert profile.text == '{"a": 1}'

    def test_missing_content_type_text_ok(self):
        def send(url, timeout, max_bytes):
            return 200, [], b"plain body"

        profile = _adapter(send).load("http://example.com/")
        assert profile.text == "plain body"

    def test_binary_body_rejected(self):
        def send(url, timeout, max_bytes):
            return 200, [("Content-Type", "text/plain")], b"\x00\xff\xfe\xffbinary"

        profile = _adapter(send).load("http://example.com/")
        assert "binary body" in profile.metadata["load_error"]
class TestRedirects:
    def test_safe_redirects_are_followed(self):
        calls = []

        def handler(url, timeout, max_bytes):
            calls.append(url)
            if url == "http://example.com/a":
                return 301, [("Location", "/b")], b""
            if url == "http://example.com/b":
                return 302, [("Location", "https://example.com/c")], b""
            return 200, [("Content-Type", "text/plain")], b"final"

        profile = _adapter(handler, resolver=lambda host: (GLOBAL_IP,)).load(
            "http://example.com/a"
        )
        assert profile.text == "final"
        assert calls == [
            "http://example.com/a",
            "http://example.com/b",
            "https://example.com/c",
        ]

    def test_redirect_target_rewritten_to_blocked_host(self):
        def handler(url, timeout, max_bytes):
            if url == "http://example.com/a":
                return 302, [("Location", "http://192.168.1.5/x")], b""
            return 200, [("Content-Type", "text/plain")], b"nope"

        profile = _adapter(handler).load("http://example.com/a")
        assert "redirect target rejected" in profile.metadata["load_error"]

    def test_redirect_to_metadata_host_rejected(self):
        def handler(url, timeout, max_bytes):
            if url == "http://example.com/a":
                return 302, [("Location", "https://169.254.169.254/x")], b""
            return 200, [("Content-Type", "text/plain")], b"nope"

        profile = _adapter(handler).load("http://example.com/a")
        assert "redirect target rejected" in profile.metadata["load_error"]

    def test_redirect_limit(self):
        def handler(url, timeout, max_bytes):
            if url.startswith("http://example.com/r"):
                return 302, [("Location", "http://example.com/r2")], b""
            return 200, [("Content-Type", "text/plain")], b"x"

        profile = _adapter(handler, max_redirects=3).load("http://example.com/r0")
        assert "too many redirects" in profile.metadata["load_error"]

    def test_redirect_with_userinfo_rejected(self):
        def handler(url, timeout, max_bytes):
            return 307, [("Location", "https://user:secret@example.com/x")], b""

        profile = _adapter(handler).load("http://example.com/a")
        assert "redirect target rejected" in profile.metadata["load_error"]

    def test_redirect_without_location_fails_closed(self):
        profile = _adapter(lambda url, t, m: (302, [], b"")).load(
            "http://example.com/a"
        )
        assert "without Location" in profile.metadata["load_error"]


class TestCredentialsAndDeterminism:
    def test_sanitize_url_strips_userinfo(self):
        assert (
            sanitize_url("http://user:secret@example.com/a?b=1")
            == "http://example.com/a?b=1"
        )

    def test_urls_with_userinfo_rejected(self):
        adapter = _adapter()
        assert not adapter.supports("https://user:secret@example.com/")
        with pytest.raises(ValueError):
            adapter.load("https://user:secret@example.com/")

    def test_metadata_method_returns_research_source(self):
        source = _adapter().metadata("https://example.com/doc")
        assert source.kind is SourceKind.WEB
        assert source.uri == "https://example.com/doc"
        assert source.title == "example.com"
        assert source.retrieved_at is not None

    def test_deterministic_repeated_retrieval(self):
        adapter = _adapter()
        p1 = adapter.load("https://example.com/doc")
        p2 = adapter.load("https://example.com/doc")
        assert p1.text == p2.text
        assert p1.uri == p2.uri

    def test_invalid_bounds_rejected(self):
        with pytest.raises(ValueError):
            WebSourceAdapter(timeout=0)
        with pytest.raises(ValueError):
            WebSourceAdapter(max_bytes=0)
        with pytest.raises(ValueError):
            WebSourceAdapter(max_redirects=-1)