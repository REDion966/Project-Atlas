"""Atlas Research — Evidence Relevance Gate (NLU-2).

A bounded, deterministic check that distinguishes "evidence exists" from
"evidence addresses the requested research objective".

The problem it solves: Atlas's research path can acquire claims from
authorized sources that are *technically* valid but unrelated to the subject
the user asked about (for example, local ``code://`` sources selected by a
coincidental token match for a smartphone-review question). Claim count alone
must therefore never be treated as objective satisfaction.

Design contract:
  * Pure: standard library only (reuses :mod:`atlas.research._text`). No AI,
    no network, no storage, no kernel, no execution, no authorization surface.
  * Deterministic: identical inputs yield identical output; no clock, no
    randomness.
  * Conservative: evidence is IRRELEVANT only when the objective's SUBJECT has
    no significant token in common with the acquired sources at all. A single
    shared subject token keeps the evidence RELEVANT, so the gate never blocks
    a genuinely related acquisition. When the objective carries no subject
    token at all (e.g. a degenerate question), relevance cannot be judged and
    the evidence is not blocked.
  * Bounded: it is a token-coverage test over existing structures (the
    objective text and the acquired source URIs). It is deliberately NOT a
    semantic ranking engine and uses no embeddings.
"""

from __future__ import annotations

from enum import Enum

from atlas.research._text import significant_tokens

#: Request/purpose/abstraction tokens that describe WHY the user is asking or
#: how the material should be organized, rather than WHAT is being researched.
#: They are excluded from the objective's SUBJECT token set so a coincidental
#: overlap on one of them (e.g. "…for a detailed review" matching a repository
#: module named ``…review…``) can never make unrelated evidence look relevant.
_PURPOSE_TOKENS: frozenset[str] = frozenset(
    {
        "research", "researches", "investigate", "investigation", "acquire",
        "find", "search", "lookup", "look", "latest", "news", "about",
        "please", "tell", "show", "give", "provide", "information", "info",
        "review", "reviews", "reviewing", "reviewed", "detailed", "detail",
        "organize", "organise", "organizing", "organising", "findings",
        "categories", "category", "matters", "matter", "important",
        "compare", "comparison", "compared", "differences", "difference",
        "versus", "gather", "summarize", "summarise", "summarizing", "turn",
        "into", "explain", "describe", "including", "include", "uses",
        "use", "using", "need", "needs", "want", "wants", "would", "like",
        "capabilities", "capability", "features", "feature", "technologies",
        "technology", "technological",
    }
)


class Relevance(str, Enum):
    """Deterministic relevance classification of acquired evidence."""

    RELEVANT = "relevant"
    IRRELEVANT = "irrelevant"
    NO_EVIDENCE = "no_evidence"


def objective_subject_tokens(question: str) -> frozenset[str]:
    """Return the objective's significant SUBJECT tokens.

    ``significant_tokens`` already removes stopwords and short tokens; this
    additionally removes the bounded purpose/abstraction vocabulary so the
    result names what is being researched rather than why it is being asked
    for.
    """
    return frozenset(
        token
        for token in significant_tokens(question or "")
        if token not in _PURPOSE_TOKENS
    )


def _source_tokens(uri: str) -> set[str]:
    """Significant tokens of a source URI (scheme/path/filename fragments)."""
    return set(significant_tokens(uri.replace("://", " ").replace("/", " ")))


def evidence_tokens(sources) -> set[str]:
    """Significant tokens attested by the acquired source URIs."""
    tokens: set[str] = set()
    for uri in sources or ():
        if isinstance(uri, str) and uri.strip():
            tokens |= _source_tokens(uri)
    return tokens


def classify_relevance(question: str, sources) -> Relevance:
    """Classify acquired evidence against the requested research objective.

    Returns:
        ``NO_EVIDENCE`` when no usable source was acquired; ``IRRELEVANT`` when
        sources exist but the objective's subject shares no significant token
        with them; ``RELEVANT`` otherwise (including when the objective carries
        no subject token and relevance therefore cannot be judged — the gate
        never blocks on the absence of a subject).
    """
    usable = tuple(
        uri for uri in (sources or ()) if isinstance(uri, str) and uri.strip()
    )
    if not usable:
        return Relevance.NO_EVIDENCE
    subject = objective_subject_tokens(question)
    if not subject:
        return Relevance.RELEVANT
    return (
        Relevance.RELEVANT
        if subject & evidence_tokens(usable)
        else Relevance.IRRELEVANT
    )
