"""Atlas Conversation — G1 deterministic lexicon (word CLASSES, not phrase lists).

The G1 language-understanding layer needs to recognize *classes* of words
(an operation verb, a capability noun, a self reference) rather than enumerate
literal phrases. This module is that vocabulary: deterministic word classes plus
a bounded, rule-based morphological normalizer so a class matches the surface
inflections of its members ("capabilities" -> "capability", "handled" ->
"handle", "researching" -> "research").

Design contract (G1):
  * pure: standard library only — no clock, no randomness, no I/O, no network,
    no model, no embeddings, no kernel, no registry;
  * deterministic: identical input yields identical output;
  * bounded: fixed frozensets, fixed suffix rules, hard token/char caps;
  * advisory only: a class never routes, approves, executes, or promotes
    anything. Interpretation carries no authority.
"""

from __future__ import annotations

import re
from typing import Any

#: Hard bounds (a malformed/oversized turn can never produce unbounded work).
MAX_TOKENS: int = 64
MAX_TOKEN_CHARS: int = 32

_TOKEN_RE = re.compile(r"[a-z0-9]+")

#: Small, explicit irregular map (stem -> canonical lemma where the suffix rules
#: would be wrong). Deliberately tiny and audited.
_IRREGULAR: dict[str, str] = {
    "abilities": "ability",
    "capabilities": "capability",
    "children": "child",
    "did": "do",
    "does": "do",
    "done": "do",
    "found": "find",
    "got": "get",
    "gotten": "get",
    "is": "be",
    "am": "be",
    "are": "be",
    "was": "be",
    "were": "be",
    "has": "have",
    "had": "have",
    "learned": "learn",
    "learnt": "learn",
    "made": "make",
    "means": "mean",
    "meant": "mean",
    "ran": "run",
    "said": "say",
    "says": "say",
    "told": "tell",
    "understood": "understand",
    "went": "go",
    "abilities'": "ability",
    "you're": "be",
    "i'm": "be",
    "i'd": "would",
    "don't": "not",
    "can't": "can",
    "won't": "will",
    "didn't": "not",
    "doesn't": "not",
    "isn't": "not",
    "aren't": "not",
    "it's": "be",
    "that's": "be",
    "what's": "be",
    # Class-relevant gerunds whose stems are not verbs in this vocabulary.
    "morning": "morning",
    "evening": "evening",
    "everything": "everything",
    "something": "something",
    "anything": "anything",
    "nothing": "nothing",
    "thing": "thing",
    "going": "go",
    "doing": "do",
    "keeping": "keep",
    "proceed": "proceed",
    "need": "need",
    "agreed": "agree",
}

#: Verbs whose "-ing"/"-ed" form drops a trailing "e" ("using" -> "use").
_E_DROP_STEMS: frozenset[str] = frozenset(
    {
        "us", "handl", "develop", "implement", "extend", "introduc", "provid",
        "compar", "analyz", "analys", "defin", "describ", "continu", "caus",
        "creat", "updat", "leav", "mov", "tak", "mak", "writ", "giv", "hav",
        "authoriz", "authoris", "elevat", "promot", "approv", "bypas",
        "overrid", "requir", "decid", "ignor", "notic", "chang", "permission",
        "resolv", "evaluat", "indicat", "compli", "verifi",
    }
)


#: Contractions normalized before tokenizing (deterministic, bounded).
_CONTRACTIONS: dict[str, str] = {
    "let's": "let us",
    "it's": "it is",
    "that's": "that is",
    "what's": "what is",
    "whats": "what is",
    "i'm": "i am",
    "i'd": "i would",
    "i've": "i have",
    "you're": "you are",
    "you've": "you have",
    "we're": "we are",
    "don't": "do not",
    "doesn't": "does not",
    "didn't": "did not",
    "isn't": "is not",
    "aren't": "are not",
    "can't": "can not",
    "won't": "will not",
    "wouldn't": "would not",
    "couldn't": "could not",
    "shouldn't": "should not",
    "isnt": "is not",
    "dont": "do not",
}

#: Words whose trailing "s" is NOT a plural marker (never stripped).
_NO_STRIP: frozenset[str] = frozenset(
    {
        "this", "his", "its", "yes", "plus", "less", "class", "process",
        "status", "analysis", "basis", "atlas", "as", "was", "has", "does",
        "is", "us", "thus", "always", "perhaps", "access", "success", "focus",
        "campus", "consensus", "gas", "bus", "serious", "various", "our",
        "your", "their", "question", "person", "reason",
    }
)


def normalize_token(token: Any) -> str:
    """Return the bounded lowercase lemma of one surface token (or "")."""
    if not isinstance(token, str):
        return ""
    text = token.strip().lower().strip(".,!?;:\"'()[]{}<>*`")
    if not text or len(text) > MAX_TOKEN_CHARS:
        return text[:MAX_TOKEN_CHARS] if text else ""
    irregular = _IRREGULAR.get(text)
    if irregular is not None:
        return irregular
    return _lemma(text)


def _lemma(token: str) -> str:
    """Rule-based, deterministic lemma for a lowercase token."""
    if len(token) <= 3 or not token.isalpha() or token in _NO_STRIP:
        return token
    if token.endswith("ies") and len(token) > 4 and token[:-3].isalpha():
        return token[:-3] + "y"
    if token.endswith("ing") and len(token) > 4:
        stem = token[:-3]
        if stem.endswith(("nn", "tt", "ss", "gg", "mm", "pp")):
            return stem[:-1]
        candidate = token[:-3] + "e" if stem in _E_DROP_STEMS else stem
        return candidate if len(candidate) >= 2 else token
    if token.endswith("ed") and len(token) > 4:
        stem = token[:-2]
        if stem.endswith("i"):
            candidate = stem[:-1] + "y"
        else:
            candidate = token[:-2] + "e" if stem in _E_DROP_STEMS else stem
        return candidate if len(candidate) >= 3 else token
    if token.endswith("es") and len(token) > 4:
        if token[:-2].endswith(("s", "x", "z", "ch", "sh")):
            return token[:-2]
    if token.endswith("s") and not token.endswith(("ss", "us", "is", "as")):
        return token[:-1]
    return token


def tokens(text: Any) -> tuple[str, ...]:
    """Return the bounded lemma token stream of ``text`` (deterministic)."""
    if not isinstance(text, str) or not text:
        return ()
    lowered = text.lower()
    for contraction, expansion in _CONTRACTIONS.items():
        if contraction in lowered:
            lowered = lowered.replace(contraction, expansion)
    out: list[str] = []
    for tok in _TOKEN_RE.findall(lowered):
        lemma = normalize_token(tok)
        if not lemma:
            continue
        if len(lemma) == 1 and lemma not in {"a", "i", "x", "y", "z"}:
            continue
        out.append(lemma)
    return tuple(out)[:MAX_TOKENS]


def token_set(text: Any) -> frozenset[str]:
    """Return the bounded lemma token SET of ``text``."""
    return frozenset(tokens(text))


def count_lemma(text: Any, lemma: str) -> int:
    """Number of occurrences of ``lemma`` in the normalized token stream."""
    return tokens(text).count(lemma)


# ---------------------------------------------------------------------------
# Word classes (lemmas). A class is a *category*, so one entry generalizes to
# every surface inflection and to ordinary synonymy within the category.
# ---------------------------------------------------------------------------

#: Self reference: WHO the turn is about (Atlas vs something else).
SELF_WORDS: frozenset[str] = frozenset(
    {"you", "your", "yours", "yourself", "yourselves", "atlas", "we"}
)

#: Question / auxiliary surface (used to detect a question-shaped turn).
QUESTION_WORDS: frozenset[str] = frozenset(
    {
        "what", "which", "who", "whom", "whose", "how", "why", "when", "where",
        "can", "could", "will", "would", "should", "shall", "may", "might",
        "do", "be", "have", "is", "does",
    }
)

#: Capability NOUN class (inventory/detail objects).
CAPABILITY_NOUNS: frozenset[str] = frozenset(
    {
        "ability", "capability", "skill", "feature", "function", "functionality",
        "tool", "competence", "strength", "talent", "service",
        "capable", "able", "expertise", "support",
    }
)

#: Capability VERB class ("what can you handle/support/help with"). The bare
#: "do" is deliberately NOT a member: "what can you do" is already owned by the
#: help surface, and including it made any "does it do X" question a capability
#: question.
CAPABILITY_VERBS: frozenset[str] = frozenset(
    {"handle", "help", "support", "assist", "offer", "provide", "serve", "cover"}
)

#: Verb set for the "I want to know / tell me about X" information frame.
LEARN_VERBS: frozenset[str] = frozenset({"learn", "know", "hear"})

#: Information-seeking verb classes (lemmatized). Split by the EXISTING domain
#: distinction (research/knowledge vs investigation) so the G1 layer never
#: collapses them.
RESEARCH_VERBS: frozenset[str] = frozenset(
    {"research", "find", "search", "discover", "explore", "check", "dig", "look"}
)

INVESTIGATE_VERBS: frozenset[str] = frozenset(
    {
        "investigate", "analyze", "analyse", "diagnose", "inspect", "examine",
        "trace", "debug", "assess", "audit", "probe", "review", "study",
        "evaluate", "screen", "scan",
    }
)

DEVELOP_VERBS: frozenset[str] = frozenset(
    {
        "add", "build", "create", "develop", "implement", "extend", "introduce",
        "enable", "integrate", "write", "construct", "upgrade",
        "improve", "refactor", "code",
    }
)

EXPLAIN_VERBS: frozenset[str] = frozenset(
    {"explain", "describe", "clarify", "define", "summarize", "expand",
     "elaborate", "detail", "tell"}
)

COMPARE_VERBS: frozenset[str] = frozenset({"compare", "contrast", "differentiate"})

ACT_VERBS: frozenset[str] = frozenset(
    {"do", "perform", "run", "execute", "handle", "work", "take", "carry", "solve", "fix", "address"}
)

#: Knowledge NOUN class (what a knowledge request is about).
KNOWLEDGE_NOUNS: frozenset[str] = frozenset(
    {"information", "info", "knowledge", "fact", "detail", "status", "news",
     "update", "development", "report", "source"}
)

#: Interest/curiosity class ("I am interested in X", "curious about X").
INTEREST_WORDS: frozenset[str] = frozenset(
    {"interest", "interested", "curious", "keen"}
)

#: Self-knowledge CONCEPT classes — one per existing self-knowledge surface.
SELF_COMPONENT_CONCEPTS: frozenset[str] = frozenset(
    {"component", "module", "subsystem", "part", "service", "package", "layer",
     "class", "registry", "engine", "manager", "decision", "policy", "handler"}
)
SELF_ARCHITECTURE_CONCEPTS: frozenset[str] = frozenset(
    {"architecture", "structure", "dependency", "flow", "pipeline", "lifecycle",
     "codebase", "subsystem"}
)
SELF_GOVERNANCE_CONCEPTS: frozenset[str] = frozenset(
    {"approval", "approve", "owner", "authority", "authorize", "sandbox",
     "promotion", "governance", "permission", "authorization", "escalation"}
)
SELF_DEVELOPMENT_CONCEPTS: frozenset[str] = frozenset(
    {"development", "proposal", "sandbox", "extension", "extend"}
)

#: G1 — Atlas-specific self-knowledge CONCEPT classes. Each maps onto an
#: EXISTING self-knowledge topic, so the frame keeps the operational
#: distinction instead of collapsing every question into SELF_KNOWLEDGE.
SELF_EVIDENCE_CONCEPTS: frozenset[str] = frozenset(
    {"evidence", "failure", "fail", "enough", "insufficient", "lack", "unable",
     "cannot", "uncertainty", "uncertain", "missing", "verify", "validation"}
)

#: The FAILURE/INSUFFICIENCY words that must co-occur for the evidence/failure
#: family to fire. A subject that merely contains "evidence" (a device named
#: "Evidence Device") or "verify" is NOT an Atlas evidence question.
SELF_FAILURE_TRIGGERS: frozenset[str] = frozenset(
    {"failure", "fail", "enough", "insufficient", "lack", "cannot", "unable",
     "uncertainty", "uncertain", "missing", "limitation", "denied", "deny"}
)
SELF_RESEARCH_CONCEPTS: frozenset[str] = frozenset(
    {"research", "acquisition", "acquire", "source", "web", "search", "external",
     "internal", "crawl"}
)
SELF_FLOW_CONCEPTS: frozenset[str] = frozenset(
    {"request", "flow", "travel", "move", "journey", "pipeline", "intake", "turn"}
)
SELF_REFERENCE_RES_CONCEPTS: frozenset[str] = frozenset(
    {"reference", "pronoun", "refer", "antecedent", "coreference"}
)
SELF_SUFFICIENCY_CONCEPTS: frozenset[str] = frozenset(
    {"sufficiency", "sufficient", "decision", "decide", "necessary", "need"}
)
SELF_SANDBOX_CONCEPTS: frozenset[str] = frozenset(
    {"sandbox", "isolat", "disposable", "safe", "safely", "execute", "execution"}
)
SELF_APPROVAL_CONCEPTS: frozenset[str] = frozenset(
    {"approval", "approve", "owner", "promotion", "promote", "signoff"}
)
SELF_AUTHORIZATION_CONCEPTS: frozenset[str] = frozenset(
    {"authoriz", "authoris", "authority", "permission", "permit", "escalation"}
)
SELF_EXTENSION_CONCEPTS: frozenset[str] = frozenset(
    {"capability", "capabilities", "feature", "extension", "extend", "reuse",
     "fit", "test", "testing", "verify"}
)

#: Bounded semantic SUBJECT classes for self-knowledge families that already
#: exist inside Atlas (see the existing self-knowledge surfaces) but were not
#: reachable from natural language. Each class is a *subject family*, not a
#: phrase list, so ordinary synonymy/paraphrase converges on the same concept.
SELF_CAPABILITY_CONTRACT_CONCEPTS: frozenset[str] = frozenset(
    {"contract", "contracts", "interface", "interfaces", "schema", "schemas",
     "descriptor", "descriptors", "metadata"}
)
SELF_REPOSITORY_CONCEPTS: frozenset[str] = frozenset(
    {"symbol", "symbols", "signature", "signatures", "module_map", "map"}
)
SELF_EXTERNAL_RESEARCH_CONCEPTS: frozenset[str] = frozenset(
    {"github", "internet", "download", "downloads", "external", "acquire",
     "acquisition", "web"}
)
SELF_EVIDENCE_TRUST_CONCEPTS: frozenset[str] = frozenset(
    {"provenance", "trust", "trusted", "untrusted", "useful", "usefulness",
     "validated", "validation", "validat", "verif"}
)
SELF_GAP_CONCEPTS: frozenset[str] = frozenset(
    {"gap", "gaps", "absent", "missing", "lacking"}
)
SELF_MODEL_CONCEPTS: frozenset[str] = frozenset(
    {"model", "models", "llm", "provider", "ollama", "qwen", "embedding"}
)

#: Governance-sensitive verb class. Recognizing these NEVER grants authority.
GOVERNANCE_VERBS: frozenset[str] = frozenset(
    {"approve", "authorize", "authorise", "promote", "bypass", "skip", "grant",
     "permit", "escalate", "elevate", "override", "waive"}
)

#: Casual acknowledgement class (lemmas).
ACK_WORDS: frozenset[str] = frozenset(
    {"thank", "cheer", "ta", "ok", "okay", "get", "understand", "note",
     "alright", "right", "sure", "cool", "great", "nice", "perfect",
     "brilliant", "fine", "yes", "yep", "yup", "agree", "understood"}
)
#: Words that may legitimately appear inside an acknowledgement turn.
ACK_FILLERS: frozenset[str] = frozenset(
    {"that", "this", "it", "help", "make", "sense", "you", "lot", "so",
     "much", "very", "many", "no", "problem", "worry", "my", "mistake",
     "sorry", "well", "then", "good", "and", "please", "i", "hear",
     "see", "know", "thank", "cheer", "ok", "okay", "now", "all", "a"}
)

#: Recall class (the recent conversation itself).
RECALL_VERBS: frozenset[str] = frozenset(
    {"discuss", "talk", "say", "ask", "mention", "remind", "recall",
     "remember", "cover", "over"}
)
RECALL_NOUNS: frozenset[str] = frozenset({"topic", "subject", "question", "message"})

#: Continuation class.
CONTINUATION_VERBS: frozenset[str] = frozenset(
    {"continue", "proceed", "go", "keep", "carry", "resume", "next", "more"}
)
#: Function words tolerated inside a pure continuation turn.
CONTINUATION_FILLERS: frozenset[str] = frozenset(
    {"on", "ahead", "us", "let", "please", "with", "that", "this", "it", "the",
     "and", "then", "i", "you", "can", "and", "to", "some"}
)

#: Greeting class (a casual opening, not an objective).
GREETING_WORDS: frozenset[str] = frozenset(
    {"hello", "hi", "hey", "greeting", "morning", "afternoon", "evening", "howdy", "yo"}
)

#: Follow-up class (bounded references + "more/again/deeper").
FOLLOW_UP_VERBS: frozenset[str] = frozenset(
    {"expand", "elaborate", "continue", "deepen"}
)
FOLLOW_UP_WORDS: frozenset[str] = frozenset({"more", "again", "deeper", "further", "else"})

#: Reference tokens (bounded; never a general coreference engine).
REFERENCE_WORDS: frozenset[str] = frozenset({"that", "this", "it", "its", "these", "those", "same"})

#: Explicit replacement markers (a correction REPLACES the active reading).
REPLACEMENT_MARKERS: tuple[str, ...] = (
    "actually", "no", "sorry", "correction", "instead", "rather", "meant", "mean",
)
#: Explicit refinement markers (a clarification REFINES the reading).
REFINEMENT_MARKERS: tuple[str, ...] = (
    "specifically", "precisely", "clarify", "referring", "asking", "about",
)

#: Compound connectors (subrequest boundaries).
COMPOUND_CONNECTORS: tuple[tuple[str, ...], ...] = (
    ("and", "then"), ("then",), ("and", "also"), ("also",), ("finally",),
    ("after", "that"), ("and", "finally"), ("plus",), ("as", "well", "as"),
)


def has_any(words: frozenset[str] | set[str], lemmas: frozenset[str]) -> bool:
    """True when any lemma of ``lemmas`` occurs in ``words``."""
    return bool(words & lemmas)


def any_count(words: frozenset[str] | set[str], lemmas: frozenset[str]) -> int:
    """Number of distinct ``lemmas`` present in ``words``."""
    return len(words & lemmas)
