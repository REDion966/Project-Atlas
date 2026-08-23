"""Tests for Phase D3 — streaming fallback policy.

Covers the approved streaming fallback policy:
  - pre-first-token failures (5xx, ConnectionError, Timeout, 429) may fall
    back to an eligible candidate,
  - fatal pre-token failures never fall back,
  - post-first-token failures never switch provider/model and raise
    :class:`StreamInterruptedError`,
  - cancellation (GeneratorExit) never falls back,
  - clean completion returns normally,
  - the attempt cap, duplicate prevention, and capability guard remain in
    force,
  - audit records distinguish pre-token fallback from post-token
    interruption,
  - the existing non-streaming chat behavior remains unchanged.
"""

from __future__ import annotations

import unittest

import requests

from atlas.ai.fallback import (
    FallbackExecutor,
    StreamInterruptedError,
)
from atlas.ai.routing.models import ModelProfile, RoutingDecision, RoutingRequest
from atlas.ai.routing.registry import ModelProfileRegistry


def _registry():
    registry = ModelProfileRegistry()
    registry.register(
        ModelProfile(
            provider_name="Mock Provider",
            model_name="atlas-mock-v1",
            complexity_score=0.3,
            priority=10,
        )
    )
    registry.register(
        ModelProfile(
            provider_name="Ollama",
            model_name="qwen3:8b",
            complexity_score=0.8,
            priority=20,
        )
    )
    return registry


def _decision(chain=None) -> RoutingDecision:
    return RoutingDecision(
        provider_name="Ollama",
        model_name="qwen3:8b",
        fallback_chain=chain
        or [("Mock Provider", "atlas-mock-v1")],
    )


def _http_error(status_code):
    response = requests.Response()
    response.status_code = status_code
    return requests.HTTPError(f"HTTP {status_code}", response=response)


def _gen_raising(exc):
    """Return a generator that raises ``exc`` before producing any chunk."""

    def _g():
        raise exc
        yield ""  # pragma: no cover

    return _g()


def _gen_chunks(chunks):
    """Return a generator yielding ``chunks`` then completing normally."""

    def _g():
        for chunk in chunks:
            yield chunk

    return _g()


def _gen_chunks_then_raise(chunks, exc):
    """Return a generator yielding ``chunks`` then raising ``exc``."""

    def _g():
        for chunk in chunks:
            yield chunk
        raise exc

    return _g()


def _primary_fails_before_first(exc, fallback_chunks=("fb-chunk",)):
    """A stream_call where the primary (Ollama) fails before the first token
    and the fallback (Mock Provider) streams ``fallback_chunks``."""

    def call(provider, model):
        if provider == "Ollama":
            return _gen_raising(exc)
        return _gen_chunks(fallback_chunks)

    return call


def _primary_fails_after_first(exc, chunks=("first", "second")):
    """A stream_call where the primary yields ``chunks`` then fails with
    ``exc`` (no fallback to a different provider)."""

    def call(provider, model):
        return _gen_chunks_then_raise(chunks, exc)

    return call


class TestPreTokenFallback(unittest.TestCase):
    """Transient failures before the first token may fall back."""

    def _exec(self, stream_call, complexity=0.2):
        executor = FallbackExecutor(_registry())
        stream = executor.execute_stream(
            RoutingRequest(complexity=complexity, allow_fallback=True),
            _decision(),
            stream_call,
        )
        return list(stream)

    def test_http_5xx_falls_back(self):
        chunks = self._exec(
            _primary_fails_before_first(_http_error(503))
        )
        self.assertEqual(chunks, ["fb-chunk"])

    def test_connection_error_falls_back(self):
        chunks = self._exec(
            _primary_fails_before_first(requests.ConnectionError("down"))
        )
        self.assertEqual(chunks, ["fb-chunk"])

    def test_timeout_falls_back(self):
        chunks = self._exec(
            _primary_fails_before_first(requests.Timeout("slow"))
        )
        self.assertEqual(chunks, ["fb-chunk"])

    def test_429_falls_back(self):
        chunks = self._exec(_primary_fails_before_first(_http_error(429)))
        self.assertEqual(chunks, ["fb-chunk"])

    def test_fatal_pre_tok_does_not_fallback(self):
        fatal = RuntimeError("API key is required")
        call = _primary_fails_before_first(fatal)
        executor = FallbackExecutor(_registry())
        with self.assertRaises(RuntimeError):
            list(
                executor.execute_stream(
                    RoutingRequest(complexity=0.2, allow_fallback=True),
                    _decision(),
                    call,
                )
            )


class TestPostTokenPolicy(unittest.TestCase):
    """After the first token, providers/models are never switched."""

    def test_failure_after_one_chunk_raises_interrupted_no_fallback(self):
        executor = FallbackExecutor(_registry())
        stream = executor.execute_stream(
            RoutingRequest(complexity=0.2, allow_fallback=True),
            _decision(),
            _primary_fails_after_first(
                requests.ConnectionError("stream cut"),
                chunks=("first",),
            ),
        )
        # First chunk is emitted, then the failure is surfaced.
        iterator = iter(stream)
        self.assertEqual(next(iterator), "first")
        with self.assertRaises(StreamInterruptedError) as ctx:
            next(iterator)
        self.assertEqual(ctx.exception.provider, "Ollama")
        self.assertEqual(ctx.exception.model, "qwen3:8b")
        self.assertIsInstance(
            ctx.exception.underlying,
            requests.ConnectionError,
        )

    def test_failure_after_multiple_chunks_raises_interrupted(self):
        executor = FallbackExecutor(_registry())
        stream = executor.execute_stream(
            RoutingRequest(complexity=0.2, allow_fallback=True),
            _decision(),
            _primary_fails_after_first(
                requests.Timeout("mid-stream"),
                chunks=("first", "second"),
            ),
        )
        iterator = iter(stream)
        self.assertEqual(next(iterator), "first")
        self.assertEqual(next(iterator), "second")
        with self.assertRaises(StreamInterruptedError):
            next(iterator)

    def test_no_fallback_attempted_after_first_token(self):
        calls: list[tuple[str, str]] = []
        executor = FallbackExecutor(_registry())

        def _stream_call(provider, model):
            calls.append((provider, model))
            return _gen_chunks_then_raise(
                ("first",),
                requests.Timeout("boom"),
            )

        stream = executor.execute_stream(
            RoutingRequest(complexity=0.2, allow_fallback=True),
            _decision(),
            _stream_call,
        )
        iterator = iter(stream)
        next(iterator)
        with self.assertRaises(StreamInterruptedError):
            next(iterator)
        # Only the primary was ever attempted.
        self.assertEqual(calls, [("Ollama", "qwen3:8b")])


class TestCancellationAndClean(unittest.TestCase):
    """Cancellation never falls back; clean completion returns normally."""

    def test_generator_exit_never_falls_back(self):
        executor = FallbackExecutor(_registry())
        calls: list[tuple[str, str]] = []

        def _stream_call(provider, model):
            calls.append((provider, model))
            return _gen_raising(GeneratorExit())

        with self.assertRaises(GeneratorExit):
            executor.execute_stream(
                RoutingRequest(complexity=0.2, allow_fallback=True),
                _decision(),
                _stream_call,
            )
        # The fallback candidate is never attempted.
        self.assertEqual(calls, [("Ollama", "qwen3:8b")])

    def test_successful_stream_returns_all_chunks(self):
        executor = FallbackExecutor(_registry())
        stream = executor.execute_stream(
            RoutingRequest(complexity=0.2, allow_fallback=True),
            _decision(),
            _primary_fails_before_first(
                requests.ConnectionError("nope"),
                fallback_chunks=("alpha", "beta", "gamma"),
            ),
        )
        self.assertEqual(list(stream), ["alpha", "beta", "gamma"])

    def test_successful_primary_stream_no_fallback(self):
        executor = FallbackExecutor(_registry())
        calls: list[tuple[str, str]] = []

        def _stream_call(provider, model):
            calls.append((provider, model))
            return _gen_chunks(("x", "y"))

        stream = executor.execute_stream(
            RoutingRequest(complexity=0.2, allow_fallback=True),
            _decision(),
            _stream_call,
        )
        self.assertEqual(list(stream), ["x", "y"])
        self.assertEqual(calls, [("Ollama", "qwen3:8b")])


class TestGuards(unittest.TestCase):
    """Attempt cap, duplicate prevention, and capability filtering apply."""

    def _many_candidate_decision(self):
        return RoutingDecision(
            provider_name="P1",
            model_name="a",
            fallback_chain=[
                ("P2", "b"),
                ("P3", "c"),
                ("P4", "d"),
                ("P5", "e"),
            ],
        )

    def test_attempt_cap_enforced(self):
        profiles = [
            ModelProfile(
                provider_name=f"P{i}",
                model_name=name,
                complexity_score=0.5,
            )
            for i, name in enumerate(("a", "b", "c", "d", "e"), start=1)
        ]
        registry = ModelProfileRegistry()
        for profile in profiles:
            registry.register(profile)

        executor = FallbackExecutor(registry)
        calls: list[tuple[str, str]] = []

        def _stream_call(provider, model):
            calls.append((provider, model))
            return _gen_raising(requests.Timeout("down"))

        with self.assertRaises(BaseException):
            list(
                executor.execute_stream(
                    RoutingRequest(complexity=0.4, allow_fallback=True),
                    self._many_candidate_decision(),
                    _stream_call,
                )
            )
        self.assertLessEqual(len(calls), 3)

    def test_duplicate_candidate_never_attempted_twice(self):
        executor = FallbackExecutor(_registry())
        decision = RoutingDecision(
            provider_name="Ollama",
            model_name="qwen3:8b",
            fallback_chain=[
                ("Mock Provider", "atlas-mock-v1"),
                ("Mock Provider", "atlas-mock-v1"),
                ("Ollama", "qwen3:8b"),
            ],
        )
        calls: list[tuple[str, str]] = []

        def _stream_call(provider, model):
            calls.append((provider, model))
            if provider == "Ollama":
                return _gen_raising(requests.Timeout("x"))
            return _gen_chunks(("ok",))

        chunks = list(
            executor.execute_stream(
                RoutingRequest(complexity=0.2, allow_fallback=True),
                decision,
                _stream_call,
            )
        )
        self.assertEqual(chunks, ["ok"])
        self.assertEqual(calls.count(("Mock Provider", "atlas-mock-v1")), 1)

    def test_capability_filtering_still_applies(self):
        executor = FallbackExecutor(_registry())
        calls: list[tuple[str, str]] = []

        def _stream_call(provider, model):
            calls.append((provider, model))
            return _gen_raising(requests.Timeout("x"))

        with self.assertRaises(BaseException):
            list(
                executor.execute_stream(
                    RoutingRequest(complexity=0.5, allow_fallback=True),
                    _decision(),
                    _stream_call,
                )
            )
        # Only the primary was attempted; Mock was capability-filtered.
        self.assertEqual(calls, [("Ollama", "qwen3:8b")])


class TestStreamingAudit(unittest.TestCase):
    """Audit records distinguish pre-token fallback from post-token
    interruption."""

    def _capture(self):
        records: list[dict] = []
        return records, records.append

    def test_pre_token_fallback_is_audited_as_attempt_events(self):
        records, audit = self._capture()
        executor = FallbackExecutor(_registry(), audit_callback=audit)
        chunks = list(
            executor.execute_stream(
                RoutingRequest(complexity=0.2, allow_fallback=True),
                _decision(),
                _primary_fails_before_first(requests.Timeout("t")),
            )
        )
        self.assertEqual(chunks, ["fb-chunk"])
        attempts = [r for r in records if r["event"].endswith(".attempt")]
        self.assertEqual(
            [r["outcome"] for r in attempts],
            ["failure", "success"],
        )
        for record in attempts:
            self.assertEqual(record.get("mode"), "stream")

    def test_post_token_interruption_is_audited(self):
        records, audit = self._capture()
        executor = FallbackExecutor(_registry(), audit_callback=audit)
        stream = executor.execute_stream(
            RoutingRequest(complexity=0.2, allow_fallback=True),
            _decision(),
            _primary_fails_after_first(
                requests.ConnectionError("cut"),
                chunks=("first",),
            ),
        )
        iterator = iter(stream)
        next(iterator)
        with self.assertRaises(StreamInterruptedError):
            next(iterator)

        interrupted = [
            r for r in records if r["event"].endswith(".interrupted")
        ]
        self.assertEqual(len(interrupted), 1)
        self.assertEqual(interrupted[0]["provider"], "Ollama")
        self.assertEqual(interrupted[0]["model"], "qwen3:8b")
        self.assertEqual(interrupted[0]["outcome"], "interrupted")


class TestNonStreamingUnchanged(unittest.TestCase):
    """The existing non-streaming chat fallback still behaves."""

    def test_chat_execute_still_works(self):
        executor = FallbackExecutor(_registry())
        calls: list[tuple[str, str]] = []

        def _call(provider, model):
            calls.append((provider, model))
            if provider == "Ollama":
                raise requests.ConnectionError("down")
            return "chat-ok"

        result = executor.execute(
            RoutingRequest(complexity=0.2, allow_fallback=True),
            _decision(),
            _call,
        )
        self.assertEqual(result.response, "chat-ok")
        self.assertTrue(result.used_fallback)


if __name__ == "__main__":
    unittest.main()