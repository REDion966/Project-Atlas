"""Atlas Evolution — Development Test Selection (Phase 4.2).

A bounded, deterministic mapping from a development change set to the tests
that concern it, so the sandbox VERIFY step targets relevant tests rather than
an arbitrary path.

Design contract:

* **Pure logic**: stdlib only. No AI, no network, no storage, no subprocess,
  no filesystem access. Callers supply the candidate test paths they can see
  (e.g. the workload's authored test files); this module only *matches*.
* **Deterministic**: identical inputs always produce identical output
  (sorted, de-duplicated, capped).
* **Bounded**: at most ``max_tests`` results; over-matching is preferred to
  under-matching (a missed test is worse than an extra focused test).
* **Never raises** for malformed input; unusable entries are ignored.

Matching reuses the repository's test naming convention (``test_<name>.py``):
a test is related to a changed module when the test stem equals
``test_<module>``, starts with ``test_<module>_``, ends with ``_<module>``, or
contains ``_<module>_``.

No AI, no gateway, no storage, no execution.
"""

from __future__ import annotations

from typing import Iterable, Sequence

from pathlib import PurePosixPath

#: Prefix every test module in the repository uses.
TEST_FILE_PREFIX: str = "test_"

#: Default cap on selected tests (boundedness).
DEFAULT_MAX_TESTS: int = 20


def _normalized_parts(path: object) -> tuple[str, str] | None:
    """Return ``(stem, name)`` for a ``.py`` path, else ``None``.

    Accepts POSIX or Windows separators; never raises.
    """
    if not isinstance(path, str) or not path.strip():
        return None
    normalized = path.strip().replace("\\", "/")
    candidate = PurePosixPath(normalized)
    if candidate.suffix.lower() != ".py":
        return None
    return candidate.stem, candidate.name


def _module_stems(changed_files: Iterable[object]) -> tuple[str, ...]:
    """Ordered, de-duplicated stems of the changed ``.py`` files."""
    stems: list[str] = []
    seen: set[str] = set()
    for path in changed_files or ():
        parts = _normalized_parts(path)
        if parts is None:
            continue
        stem = parts[0]
        if not stem or stem in seen:
            continue
        seen.add(stem)
        stems.append(stem)
    return tuple(stems)


def _related(test_stem: str, module_stem: str) -> bool:
    """True when a test stem concerns a changed module stem (deterministic)."""
    if not test_stem or not module_stem:
        return False
    if test_stem == f"{TEST_FILE_PREFIX}{module_stem}":
        return True
    if test_stem.startswith(f"{TEST_FILE_PREFIX}{module_stem}_"):
        return True
    if test_stem.endswith(f"_{module_stem}"):
        return True
    return f"_{module_stem}_" in f"_{test_stem}_"


def select_relevant_tests(
    changed_files: Iterable[object],
    available_tests: Sequence[object] = (),
    max_tests: int = DEFAULT_MAX_TESTS,
) -> tuple[str, ...]:
    """Return the candidate tests that concern ``changed_files``.

    Args:
        changed_files: Repo-relative paths of the changed ``.py`` files.
        available_tests: Candidate test paths the caller can actually run
            (e.g. the sandbox workload's seeded test files). Only these are
            ever returned — the selector never fabricates a test path.
        max_tests: Hard cap on the number of returned tests.

    Returns:
        A sorted, de-duplicated tuple of at most ``max_tests`` test paths
        (the exact strings supplied in ``available_tests``). Empty when there
        is nothing relevant — an honest empty result, never a guess.
    """
    try:
        cap = int(max_tests)
    except (TypeError, ValueError):
        cap = DEFAULT_MAX_TESTS
    if cap < 1:
        return ()

    module_stems = _module_stems(changed_files)
    if not module_stems:
        return ()

    selected: list[str] = []
    seen: set[str] = set()
    for test in available_tests or ():
        parts = _normalized_parts(test)
        if parts is None:
            continue
        test_stem = parts[0]
        if not test_stem.startswith(TEST_FILE_PREFIX):
            continue
        if not any(_related(test_stem, stem) for stem in module_stems):
            continue
        key = str(test)
        if key in seen:
            continue
        seen.add(key)
        selected.append(key)

    selected.sort()
    return tuple(selected[:cap])
