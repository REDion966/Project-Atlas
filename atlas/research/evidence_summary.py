"""Atlas Research — Evidence Summary — Stage F1.

A bounded, deterministic, JSON-safe projection of one F8
``AcquisitionResult`` for attachment to improvement plans and planning
context (Stage F — Research → Development Intelligence bridge).

Design contract:

* **Pure**: stdlib only; no storage, filesystem, subprocess, git, network.
* **Fail-soft**: malformed / duck-typed inputs yield a safe partial or
  empty summary — never an exception.
* **Bounded**: sources and findings are capped; timestamps are strings.
* **Deterministic**: identical results produce identical summaries.

Reuses ``AcquisitionResult.to_dict()`` as the canonical shape rather than
re-inventing a research representation.

Pure logic. No AI. No gateway. No storage. No kernel access.
"""

from __future__ import annotations

from typing import Any

DEFAULT_MAX_SOURCES: int = 5
DEFAULT_MAX_FINDINGS_CHARS: int = 500


def empty_summary(question: str = "") -> dict[str, Any]:
    """The safe neutral summary (also the malformed-input fallback)."""
    return {
        "question": question,
        "status": "",
        "decision": "",
        "confidence": 0.0,
        "findings": "",
        "sources": [],
        "claim_count": 0,
        "report_id": "",
        "truncated_sources": False,
    }


def summarize_acquisition(
    acquisition: Any,
    max_sources: int = DEFAULT_MAX_SOURCES,
    max_findings_chars: int = DEFAULT_MAX_FINDINGS_CHARS,
) -> dict[str, Any]:
    """
    Summarize one ``AcquisitionResult`` into a bounded JSON-safe dict.

    Delegates shape ownership to ``AcquisitionResult.to_dict()`` and adds
    only bounding (sources cap, findings truncation). Deterministic:
    identical acquisitions produce identical summaries.

    Args:
        acquisition: An ``AcquisitionResult`` (duck-typed: anything whose
            ``to_dict()`` yields the canonical keys).
        max_sources: Maximum number of source entries kept.
        max_findings_chars: Findings text truncation length.

    Returns:
        A bounded summary dict; ``empty_summary()`` on hostile input.
    """
    if max_sources < 0 or max_findings_chars < 1:
        return empty_summary()

    try:
        data = acquisition.to_dict()
        if not isinstance(data, dict):
            return empty_summary(_safe_str(data.get("question")))
    except Exception:
        try:
            question = _safe_str(getattr(acquisition, "question", ""))
        except Exception:
            question = ""
        return empty_summary(question)

    sources = data.get("sources", []) or []
    if not isinstance(sources, list):
        sources = []
    findings = _safe_str(data.get("findings"))

    return {
        "acquisition_id": _safe_str(data.get("acquisition_id")),
        "question": _safe_str(data.get("question")),
        "status": _safe_str(data.get("status")),
        "decision": _safe_str(data.get("decision")),
        "confidence": _safe_float(data.get("confidence")),
        "findings": findings[:max_findings_chars],
        "sources": [
            _safe_str(source)
            for source in sources[:max_sources]
        ],
        "truncated_sources": len(sources) > max_sources,
        "claim_count": _safe_int(data.get("claim_count")),
        "verification_count": _safe_int(data.get("verification_count")),
        "report_id": _safe_str(data.get("report_id")),
        "completed_at": _safe_str(data.get("completed_at")),
    }


def _safe_str(value: Any) -> str:
    try:
        return str(value) if value is not None else ""
    except Exception:
        return ""


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _safe_float(value: Any) -> float:
    try:
        return round(float(value), 4)
    except (TypeError, ValueError):
        return 0.0