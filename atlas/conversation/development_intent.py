"""Atlas Conversation — structured CHANGE-REQUEST meaning (Command 4: L1/L3/L6).

Why this exists
---------------
The deterministic intake decided ``DEVELOPMENT_REQUEST`` from a maintained list of
accepted surface cue FORMS ("add", "fix", "implement", ...). That is a *lexical*
gate: it recognises the WORDS, not the MEANING. A request phrased with a
different modality carried exactly the same meaning and was classified as
ordinary conversation or a question — "Can you implement X?", "I need X
implemented.", "Please add X.", "I want Atlas to support X." — so semantically
equivalent requests did NOT converge on the same Atlas representation.

This module supplies the missing layer: a pure, bounded, deterministic
STRUCTURED analysis that decides the meaning from its STRUCTURE —

  * the request MODALITY      (imperative / request / need / question / statement)
  * the change ACTION CLASS   (create / modify / remove / repair / document)
  * whether ATLAS is addressed
  * the concrete TARGET surfaces the request itself names
  * whether the change is NEGATED

— instead of from a phrase list. Equivalent phrasings converge because the
ACTION CLASS is the invariant, not the wording.

Authority
---------
This module is PURE and INTERPRETIVE. It reads a string, returns a bounded
frozen dataclass, and does nothing else: no model, no I/O, no repository access,
no execution, no approval, no authority of any kind. It is L1 (internal meaning
representation) material — the input to Atlas's own reasoning, never a decision.

Standard library only. Deterministic. Bounded.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum

#: Bounds (audit here, never per request).
MAX_TEXT_CHARS: int = 4_000
MAX_TARGETS: int = 8
MAX_EVIDENCE: int = 8
MAX_TARGET_CHARS: int = 200


class RequestModality(str, Enum):
    """HOW the human asks, independent of what they ask for (L3)."""

    #: "Add a helper." — the sentence opens with the action.
    IMPERATIVE = "imperative"
    #: "Can you add X?" / "Could you ...?" / "Please add X." — directed request.
    REQUEST = "request"
    #: "I need X." / "I want X." / "I would like X." — stated need.
    NEED = "need"
    #: "How do I add X?" / "What is X?" — asks for knowledge, not for action.
    QUESTION = "question"
    #: "There is a bug in X." — a report with no request for action.
    STATEMENT = "statement"
    UNKNOWN = "unknown"


class ChangeAction(str, Enum):
    """The CLOSED semantic action classes a change request may express (L3)."""

    CREATE = "create"
    MODIFY = "modify"
    REMOVE = "remove"
    REPAIR = "repair"
    DOCUMENT = "document"
    UNKNOWN = "unknown"


class MeaningStatus(str, Enum):
    """L6 — how well Atlas actually understands the turn (never a guess)."""

    #: An unambiguous change request that names a concrete repository target.
    KNOWN = "known"
    #: A change request whose target is only a general code unit.
    INFERRED = "inferred"
    #: A change request whose target is only an unresolved pronoun/demonstrative.
    AMBIGUOUS = "ambiguous"
    #: Not a change request (or no action could be recognised at all).
    UNKNOWN = "unknown"
    #: A change request whose action is outside Atlas's closed action vocabulary.
    UNSUPPORTED = "unsupported"


class TargetKind(str, Enum):
    """The KIND of target surface a request names (L4 evidence)."""

    #: A repository path/named file ("atlas/research/relevance.py").
    PATH = "path"
    #: A dotted module name ("atlas.research.relevance").
    MODULE = "module"
    #: A quoted/backticked identifier ("`describe_ranking_constants`").
    SYMBOL = "symbol"
    #: An ordinary CODE UNIT noun ("a helper", "the function", "the tests").
    CODE_UNIT = "code_unit"


#: Action FORM -> class. Whole-word forms only (never a substring test), and the
#: CLASS is what the rest of Atlas reasons about — a new surface form for an
#: existing class is data, not a new rule.
_ACTION_FORMS: tuple[tuple[ChangeAction, frozenset[str]], ...] = (
    (
        ChangeAction.CREATE,
        frozenset(
            {
                "add", "adds", "added", "adding",
                "build", "builds", "built", "building", "rebuild", "rebuilds",
                "create", "creates", "created", "creating",
                "implement", "implements", "implemented", "implementing",
                "insert", "inserts", "inserted", "inserting",
                "introduce", "introduces", "introduced", "introducing",
                "make", "makes", "made", "making",
                "provide", "provides", "provided", "providing",
                "support", "supports", "supported", "supporting",
                "write", "writes", "wrote", "written", "writing",
                "enable", "enables", "enabled", "enabling",
            }
        ),
    ),
    (
        ChangeAction.MODIFY,
        frozenset(
            {
                "adjust", "adjusts", "adjusted", "adjusting",
                "change", "changes", "changed", "changing",
                "clean", "cleans", "cleaned", "cleaning",
                "extend", "extends", "extended", "extending",
                "improve", "improves", "improved", "improving",
                "modify", "modifies", "modified", "modifying",
                "move", "moves", "moved", "moving",
                "refactor", "refactors", "refactored", "refactoring",
                "rename", "renames", "renamed", "renaming",
                "replace", "replaces", "replaced", "replacing",
                "rewrite", "rewrites", "rewrote", "rewritten", "rewriting",
                "simplify", "simplifies", "simplified", "simplifying",
                "update", "updates", "updated", "updating",
            }
        ),
    ),
    (
        ChangeAction.REMOVE,
        frozenset(
            {
                "delete", "deletes", "deleted", "deleting",
                "drop", "drops", "dropped", "dropping",
                "remove", "removes", "removed", "removing",
            }
        ),
    ),
    (
        ChangeAction.REPAIR,
        frozenset(
            {
                "correct", "corrects", "corrected", "correcting",
                "debug", "debugs", "debugged", "debugging",
                "fix", "fixes", "fixed", "fixing",
                "repair", "repairs", "repaired", "repairing",
                "resolve", "resolves", "resolved", "resolving",
            }
        ),
    ),
    (
        ChangeAction.DOCUMENT,
        frozenset(
            {
                "document", "documents", "documented", "documenting",
                "docstring", "docstrings", "readme", "readmes",
            }
        ),
    ),
)

#: The closed CODE UNIT nouns. These are ordinary code units, NOT architectural
#: identities: naming one is EVIDENCE that a code change is meant, never a claim
#: about which component.
_CODE_UNIT_NOUNS: frozenset[str] = frozenset(
    {
        "bug", "bugs", "class", "classes", "code", "docstring", "docstrings",
        "documentation", "file", "files", "function", "functions", "helper",
        "helpers", "implementation", "method", "methods", "module", "modules",
        "package", "readme", "repo", "repository", "test", "tests", "unit test",
        "unit tests",
    }
)

#: Closed function-word patterns (no content vocabulary, no phrase list).
_PLEASE_RE = re.compile(r"\bplease\b")
_REQUEST_AUX_RE = re.compile(r"\b(?:can|could|would|will)\s+(?:you|atlas)\b")
_NEED_RE = re.compile(r"\b(?:i|we)\s+(?:need|want|require|would\s+like|d\s+like)\b")
_WH_RE = re.compile(r"\b(?:how|what|why|when|where|which|who)\b")
_NEGATION_RE = re.compile(r"\b(?:not|never|no\s+longer)\b|n['\u2019]t\b")
_PRONOUN_RE = re.compile(r"\b(?:it|its|this|these|that|those|them|they)\b")

#: Syntactic target SHAPES (not words): a file with a known extension, a dotted
#: module path, or a quoted identifier.
_PATH_RE = re.compile(
    r"\b[\w][\w./-]*\.(?:py|toml|md|json|txt|ya?ml|cfg|ini|sql|sh)\b"
)
_MODULE_RE = re.compile(
    r"\b[a-z_][a-z0-9_]*(?:\.[a-z_][a-z0-9_]*){2,}\b"
)
_SYMBOL_RE = re.compile(r"[`'\"]([A-Za-z_][A-Za-z0-9_.]*)[`'\"]")

#: Leading conversational filler that may precede an imperative action.
_LEADING_FILLER: frozenset[str] = frozenset(
    {"ok", "okay", "so", "now", "then", "hey", "hi", "hello", "atlas", "um"}
)

#: Irregular past/participle forms from the action vocabulary that cannot open an
#: imperative (the regular "-ed"/"-ing" cases are handled morphologically).
_NON_BASE_FORMS: frozenset[str] = frozenset(
    {"built", "made", "rewrote", "written", "wrote", "rewritten"}
)

#: LIGHT verb forms. "make" is a light verb: on its own it says nothing about a
#: CODE change, so its object decides. "make that simpler" (a demonstrative
#: object — usually the previous RESPONSE) is a conversational follow-up, while
#: "make X work" names an object and is a change request. This keeps
#: "Can you make that simpler?" out of the development route WITHOUT removing the
#: genuine "Could you make X work?".
_LIGHT_FORMS: frozenset[str] = frozenset({"make", "makes", "made", "making"})

#: Object pronouns/demonstratives that carry no code information on their own.
_DEMONSTRATIVE_OBJECTS: frozenset[str] = frozenset(
    {"it", "its", "this", "that", "these", "those", "them"}
)

_WORD_RE = re.compile(r"[a-z0-9_]+")


@dataclass(frozen=True, slots=True)
class TargetSurface:
    """One target surface the request NAMES (L4 evidence, not a claim)."""

    kind: TargetKind
    value: str = ""

    def to_dict(self) -> dict[str, str]:
        return {"kind": self.kind.value, "value": self.value}


@dataclass(frozen=True, slots=True)
class DevelopmentIntent:
    """Atlas-owned structured meaning of a possible CHANGE REQUEST.

    This is L1/L3 material: a bounded, deterministic representation of what the
    turn MEANS. It is not a decision, not permission, and not a plan — it grants
    nothing and executes nothing.
    """

    text: str = ""
    modality: RequestModality = RequestModality.UNKNOWN
    action: ChangeAction = ChangeAction.UNKNOWN
    status: MeaningStatus = MeaningStatus.UNKNOWN
    is_change_request: bool = False
    negated: bool = False
    #: True when the turn addresses Atlas ("you", "Atlas", or a bare imperative).
    addressed_to_atlas: bool = False
    targets: tuple[TargetSurface, ...] = ()
    constraints: tuple[str, ...] = ()
    evidence: tuple[str, ...] = ()
    #: The surface form that carried the action class (auditable provenance).
    action_surface: str = ""

    @property
    def concrete_targets(self) -> tuple[TargetSurface, ...]:
        """Targets that name something specific (path/module/symbol)."""
        return tuple(
            target
            for target in self.targets
            if target.kind in (TargetKind.PATH, TargetKind.MODULE, TargetKind.SYMBOL)
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "modality": self.modality.value,
            "action": self.action.value,
            "status": self.status.value,
            "is_change_request": self.is_change_request,
            "negated": self.negated,
            "addressed_to_atlas": self.addressed_to_atlas,
            "action_surface": self.action_surface,
            "targets": [target.to_dict() for target in self.targets],
            "constraints": list(self.constraints),
            "evidence": list(self.evidence),
        }


def _words(lowered: str) -> tuple[str, ...]:
    return tuple(_WORD_RE.findall(lowered))


def _classify_action(lowered: str, words: tuple[str, ...]) -> tuple[ChangeAction, str, int]:
    """Earliest whole-word action form -> ``(class, surface, word index)``."""
    for index, word in enumerate(words):
        for action, forms in _ACTION_FORMS:
            if word in forms:
                return action, word, index
    return ChangeAction.UNKNOWN, "", -1


def _addressed_to_atlas(lowered: str, modality: RequestModality, words: tuple[str, ...]) -> bool:
    """Whether the turn asks ATLAS to do something (never a bare statement).

    ``please`` is an explicit addressee marker: "Please add X." is a request
    directed at the recipient even though it carries no auxiliary and no need
    construction. A bare report ("There is a bug in X.") is NOT addressed.
    """
    if modality is RequestModality.IMPERATIVE:
        return True
    if _REQUEST_AUX_RE.search(lowered) or _PLEASE_RE.search(lowered):
        return True
    return bool(_NEED_RE.search(lowered))


def _resolve_modality(lowered: str, words: tuple[str, ...], action_index: int) -> RequestModality:
    """Modality from closed function-word structure, deterministic and ordered."""
    if _PLEASE_RE.search(lowered) or _REQUEST_AUX_RE.search(lowered):
        return RequestModality.REQUEST
    if _NEED_RE.search(lowered):
        return RequestModality.NEED
    if action_index >= 0 and _is_leading_action(words, action_index):
        return RequestModality.IMPERATIVE
    if _WH_RE.search(lowered):
        return RequestModality.QUESTION
    return RequestModality.STATEMENT


def _is_base_form(word: str) -> bool:
    """True when a verb form can HEAD an imperative (not a gerund or a past form).

    "Fixing the capability is important." and "Built the capability." are
    STATEMENTS: a gerund or a past/participle form cannot open an imperative.
    Treating them as imperatives would read a report as a change request, so the
    leading-action test accepts a base form only.
    """
    if not word:
        return False
    if word.endswith("ing") or word.endswith("ed"):
        return False
    return word not in _NON_BASE_FORMS


def _is_leading_action(words: tuple[str, ...], action_index: int) -> bool:
    """True when a BASE-form action opens the instruction (only filler first)."""
    if action_index < 0 or action_index >= len(words):
        return False
    if not _is_base_form(words[action_index]):
        return False
    for word in words[:action_index]:
        if word not in _LEADING_FILLER:
            return False
    return True


def _light_action_object_is_demonstrative(
    words: tuple[str, ...], action_index: int, action_surface: str
) -> bool:
    """True when a LIGHT verb's object is a bare demonstrative/pronoun.

    "Can you make that simpler?" asks about the previous RESPONSE; "Could you
    make X work?" names an object. Only the first is disqualified as a change
    request, and only for the closed set of light forms.
    """
    if action_surface not in _LIGHT_FORMS:
        return False
    following = action_index + 1
    if following >= len(words):
        return False
    return words[following] in _DEMONSTRATIVE_OBJECTS


def _is_negated(lowered: str, action_surface: str) -> bool:
    """True when a negation occurs BEFORE the action that carries the class."""
    if not action_surface:
        return False
    marker = re.search(rf"\b{re.escape(action_surface)}\b", lowered)
    if marker is None:
        return False
    return bool(_NEGATION_RE.search(lowered[: marker.start()]))


def _extract_targets(normalized: str, lowered: str) -> tuple[TargetSurface, ...]:
    """Bounded, deterministic target surfaces NAMED by the request (L4)."""
    found: list[TargetSurface] = []
    seen: set[tuple[str, str]] = set()

    def _add(kind: TargetKind, value: str) -> None:
        value = value.strip()[:MAX_TARGET_CHARS]
        if not value:
            return
        key = (kind.value, value)
        if key in seen or len(found) >= MAX_TARGETS:
            return
        seen.add(key)
        found.append(TargetSurface(kind=kind, value=value))

    for match in _PATH_RE.finditer(lowered):
        _add(TargetKind.PATH, match.group(0))
    for match in _MODULE_RE.finditer(lowered):
        _add(TargetKind.MODULE, match.group(0))
    for match in _SYMBOL_RE.finditer(normalized):
        _add(TargetKind.SYMBOL, match.group(1))
    for word in _words(lowered):
        if word in _CODE_UNIT_NOUNS:
            _add(TargetKind.CODE_UNIT, word)
    return tuple(found)


def _constraints(lowered: str) -> tuple[str, ...]:
    """Preservation constraints the request ACTUALLY states (closed cues)."""
    out: list[str] = []
    for cue in (
        "preserve", "preserving", "without breaking", "do not break",
        "don't break", "backward compatible", "backwards compatible",
        "unchanged", "no behaviour change", "no behavior change",
    ):
        if cue in lowered and cue not in out:
            out.append(cue)
    return tuple(out[:MAX_EVIDENCE])


def _status(
    *,
    action: ChangeAction,
    is_change_request: bool,
    concrete: tuple[TargetSurface, ...],
    code_units: tuple[TargetSurface, ...],
    has_pronoun: bool,
) -> MeaningStatus:
    """L6 — the honest understanding status of this turn (never a guess)."""
    if not is_change_request:
        return MeaningStatus.UNKNOWN
    if action is ChangeAction.UNKNOWN:
        return MeaningStatus.UNSUPPORTED
    if concrete:
        return MeaningStatus.KNOWN
    if code_units:
        return MeaningStatus.INFERRED
    if has_pronoun:
        return MeaningStatus.AMBIGUOUS
    return MeaningStatus.INFERRED


def interpret_development_intent(text: object) -> DevelopmentIntent:
    """Interpret ``text`` as a possible CHANGE REQUEST (pure; never raises).

    Returns a bounded :class:`DevelopmentIntent`. Anything that is not a
    non-negated change request addressed to Atlas yields
    ``is_change_request=False`` so callers continue on their existing path.
    """
    if not isinstance(text, str):
        return DevelopmentIntent(status=MeaningStatus.UNKNOWN)
    normalized = text.strip()[:MAX_TEXT_CHARS]
    if not normalized:
        return DevelopmentIntent(status=MeaningStatus.UNKNOWN)
    lowered = normalized.lower()
    words = _words(lowered)

    action, action_surface, action_index = _classify_action(lowered, words)
    modality = _resolve_modality(lowered, words, action_index)
    negated = _is_negated(lowered, action_surface)
    targets = _extract_targets(normalized, lowered)
    concrete = tuple(
        t for t in targets
        if t.kind in (TargetKind.PATH, TargetKind.MODULE, TargetKind.SYMBOL)
    )
    code_units = tuple(t for t in targets if t.kind is TargetKind.CODE_UNIT)

    addressed = _addressed_to_atlas(lowered, modality, words)
    light_object = _light_action_object_is_demonstrative(
        words, action_index, action_surface
    )
    is_change_request = (
        action is not ChangeAction.UNKNOWN
        and not negated
        and not light_object
        and modality
        in (RequestModality.IMPERATIVE, RequestModality.REQUEST, RequestModality.NEED)
        and addressed
    )

    evidence: list[str] = [f"modality={modality.value}"]
    if light_object:
        evidence.append("light_action_with_demonstrative_object")
    if action_surface:
        evidence.append(f"action={action.value}({action_surface})")
    else:
        evidence.append("action=unrecognised")
    if negated:
        evidence.append("negated")
    if addressed:
        evidence.append("addressed_to_atlas")
    if concrete:
        evidence.append(f"concrete_targets={len(concrete)}")
    elif code_units:
        evidence.append(f"code_unit_targets={len(code_units)}")

    return DevelopmentIntent(
        text=normalized,
        modality=modality,
        action=action,
        status=_status(
            action=action,
            is_change_request=is_change_request,
            concrete=concrete,
            code_units=code_units,
            has_pronoun=bool(_PRONOUN_RE.search(lowered)),
        ),
        is_change_request=is_change_request,
        negated=negated,
        addressed_to_atlas=addressed,
        targets=targets,
        constraints=_constraints(lowered),
        evidence=tuple(evidence[:MAX_EVIDENCE]),
        action_surface=action_surface,
    )


def action_forms() -> dict[str, tuple[str, ...]]:
    """The closed action vocabulary, as ``class -> surface forms`` (auditable)."""
    return {action.value: tuple(sorted(forms)) for action, forms in _ACTION_FORMS}


__all__ = [
    "ChangeAction",
    "DevelopmentIntent",
    "MAX_TARGETS",
    "MeaningStatus",
    "RequestModality",
    "TargetKind",
    "TargetSurface",
    "action_forms",
    "interpret_development_intent",
]
