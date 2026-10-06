"""Atlas Language — the linguistic foundation (STEP 1).

This package is the Atlas-owned language foundation that sits UNDER the existing
L0–L10 conversation architecture. It introduces NO parallel pipeline: the
existing architecture remains the single authoritative path, and this foundation
supplies the meaning-facing contracts that were previously expressed only as
flat word classes.

What it owns
------------
* **lexical representation** (:mod:`atlas.language.lexicon`) — ``LexicalEntry``,
  ``Sense``, ``SemanticRelation``, ``LinguisticAnnotation``, ``LanguageProfile``
  and the bounded ``Lexicon`` resource;
* **normalization** (:mod:`atlas.language.normalizer`) — one facade over the
  EXISTING shared primitives (whitespace/surface canonicalization and bounded
  morphology), so the foundation and the pipeline can never drift apart;
* **language identification and routing** (:mod:`atlas.language.routing`) —
  deterministic script evidence, with ``unknown``/``unsupported`` reported
  honestly instead of assuming English;
* **optional provider seam** (:mod:`atlas.language.providers`) — the
  Atlas-owned interface through which a specialist resource (WordNet, wordfreq,
  spaCy, fastText, GLiNER, ConceptNet, multilingual-E5, ...) may contribute
  evidence. Optional, bounded, fail-closed, and never authoritative;
* **vocabulary resolution** (:mod:`atlas.language.vocabulary`) — surface term ->
  Atlas concept(s) over a lexicon projected from Atlas's EXISTING authoritative
  vocabularies, preserving ambiguity instead of guessing;
* **the cohesive entry point** (:mod:`atlas.language.service`).

L0–L10 mapping
--------------
L0 boundaries — this package is a leaf: standard library only, no kernel, no
registry, no model, no I/O. L1 representation — ``LexicalEntry``/``Sense``/
``LinguisticAnnotation``. L2 normalization — :mod:`atlas.language.normalizer`.
L3/L4 vocabulary and reference — :mod:`atlas.language.vocabulary`. L5/L6 —
ambiguity is represented (``AMBIGUOUS``), never collapsed. L7–L10 are served by
the EXISTING conversation, development and evidence layers, which this
foundation feeds rather than replaces.

Authority
---------
Nothing in this package routes, approves, authorizes, executes, promotes or
mutates anything. An annotation is EVIDENCE. External providers are optional
specialists behind an Atlas-owned interface — never Atlas's meaning authority.
"""

from __future__ import annotations

from atlas.language.lexicon import (
    MAX_ANNOTATION_TOKENS,
    MAX_ENTRIES,
    LexicalEntry,
    Lexicon,
    LinguisticAnnotation,
    LanguageProfile,
    RelationKind,
    SemanticRelation,
    Sense,
    entry,
    relation,
    sense,
)
from atlas.language.normalizer import (
    NORMALIZATION_STAGES,
    lemma_set,
    lemmatize,
    normalize,
    tokenize,
)
from atlas.language.providers import (
    MAX_PROVIDERS,
    LexicalProvider,
    LexicalProviderRegistry,
    NullLexicalProvider,
)
from atlas.language.routing import (
    SUPPORTED_LANGUAGES,
    detect_language,
    route_language,
)
from atlas.language.service import LanguageService
from atlas.language.vocabulary import (
    VocabularyResolution,
    VocabularyResolver,
    VocabularyStatus,
    vocabulary_from_sources,
)

__all__ = [
    # lexicon
    "LexicalEntry",
    "Lexicon",
    "LinguisticAnnotation",
    "LanguageProfile",
    "RelationKind",
    "SemanticRelation",
    "Sense",
    "entry",
    "relation",
    "sense",
    # normalization
    "NORMALIZATION_STAGES",
    "lemma_set",
    "lemmatize",
    "normalize",
    "tokenize",
    # routing
    "SUPPORTED_LANGUAGES",
    "detect_language",
    "route_language",
    # providers
    "LexicalProvider",
    "LexicalProviderRegistry",
    "NullLexicalProvider",
    # vocabulary
    "VocabularyResolution",
    "VocabularyResolver",
    "VocabularyStatus",
    "vocabulary_from_sources",
    # service
    "LanguageService",
    # bounds
    "MAX_ANNOTATION_TOKENS",
    "MAX_ENTRIES",
    "MAX_PROVIDERS",
]
