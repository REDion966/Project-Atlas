"""STEP 1 — the Atlas language foundation (lexical representation + resolution).

Covers the language primitives, lexical resolution, normalization, the provider
seam, language routing, ambiguity preservation, and the kernel integration.

Everything here is deterministic and model-free; no provider is contacted and no
governance boundary is reachable.
"""

from __future__ import annotations

import pathlib

import pytest

from atlas.language import (
    LanguageService,
    LexicalEntry,
    Lexicon,
    NullLexicalProvider,
    RelationKind,
    VocabularyStatus,
    detect_language,
    entry,
    lemma_set,
    lemmatize,
    normalize,
    relation,
    route_language,
    sense,
    tokenize,
    vocabulary_from_sources,
)
from atlas.language.providers import (
    MAX_PROVIDERS,
    LexicalProviderRegistry,
)

PLAIN = ("investigate", "investigation", "plan", "verify", "report", "research")


def _service():
    return LanguageService.from_sources({"operational_capability": PLAIN})


# ---------------------------------------------------------------------------
# 1. Lexical primitives
# ---------------------------------------------------------------------------


class TestLexicalPrimitives:
    def test_entry_builds_and_is_serializable(self):
        built = entry(
            "investigate",
            aliases=("investigation",),
            lemmas=("investigate",),
            atlas_concepts=("investigate",),
            domains=("investigation",),
            provenance="atlas:declared",
        )
        assert isinstance(built, LexicalEntry)
        payload = built.to_dict()
        assert payload["canonical_term"] == "investigate"
        assert payload["aliases"] == ["investigation"]
        assert payload["ambiguous"] is False
        assert payload["atlas_concepts"] == ["investigate"]

    def test_ambiguity_is_computed_not_declared(self):
        ambiguous = entry("research", atlas_concepts=("cap_a", "cap_b"))
        assert ambiguous.ambiguous is True
        single = entry("plan", atlas_concepts=("plan",))
        assert single.ambiguous is False

    def test_senses_contribute_concepts_and_relations(self):
        built = entry(
            "memory",
            senses=(
                sense("s1", atlas_concepts=("memory_service",), confidence=0.5),
                sense(
                    "s2",
                    atlas_concepts=("memory_store",),
                    relations=(relation(RelationKind.HYPONYM, "storage"),),
                ),
            ),
        )
        assert set(built.concepts()) == {"memory_service", "memory_store"}
        assert built.ambiguous is True
        assert built.senses[1].relations[0].kind is RelationKind.HYPONYM

    def test_unknown_relation_kind_falls_back_to_related(self):
        assert relation("nonsense", "x").kind is RelationKind.RELATED

    def test_confidence_is_clamped(self):
        assert sense("s", confidence=9.9).confidence == 1.0
        assert sense("s", confidence=-3).confidence == 0.0
        assert entry("x", frequency=9.9).frequency == 1.0

    def test_malformed_input_is_bounded_not_raised(self):
        assert entry(None).canonical_term == ""
        assert entry("x", atlas_concepts=(None, "", "ok")).atlas_concepts == ("ok",)
        assert relation("synonym", None).target == ""


class TestLexicon:
    def test_add_lookup_and_size(self):
        lex = Lexicon([entry("investigate", aliases=("investigation",))])
        assert lex.size() == 1
        assert lex.lookup("investigate") is not None
        assert lex.lookup("investigation") is not None  # alias is indexed
        assert lex.lookup("INVESTIGATE") is not None  # case-insensitive
        assert lex.lookup("zzz") is None

    def test_duplicate_term_is_refused_deterministically(self):
        lex = Lexicon()
        assert lex.add(entry("a")) is True
        assert lex.add(entry("a")) is False
        assert lex.size() == 1

    def test_non_entry_is_refused(self):
        lex = Lexicon()
        assert lex.add("not-an-entry") is False  # type: ignore[arg-type]
        assert lex.size() == 0

    def test_from_sources_records_provenance_and_is_deterministic(self):
        first = vocabulary_from_sources({"component": ("evolution_memory",)})
        second = vocabulary_from_sources({"component": ("evolution_memory",)})
        assert first.to_dict() == second.to_dict()
        found = first.lookup("evolution_memory")
        assert found is not None and found.provenance == "atlas:component"


# ---------------------------------------------------------------------------
# 2. Normalization (delegates to the existing primitives)
# ---------------------------------------------------------------------------


class TestNormalization:
    def test_whitespace_is_collapsed(self):
        assert normalize("  investigate   the   problem  ") == "investigate the problem"

    def test_normalization_delegates_to_the_existing_pipeline(self):
        from atlas.conversation.normalization import canonicalize_surface

        assert normalize("  hello   there ") == canonicalize_surface("  hello   there ")

    def test_tokenize_and_lemmatize(self):
        # The EXISTING shared tokenizer already normalizes: its tokens are
        # lemmas ("capabilities" -> "capability"), so the foundation never
        # produces a second, divergent reading.
        assert tokenize("Investigate the capabilities!") == (
            "investigate", "the", "capability",
        )
        assert lemmatize("capabilities") == ("capability",)
        # The existing module's OWN documented examples.
        assert lemma_set("researching") == frozenset({"research"})
        assert lemma_set("handled") == frozenset({"handle"})
        assert lemmatize(["capabilities", "ran"]) == ("capability", "run")

    def test_non_text_is_empty_not_raised(self):
        assert normalize(None) == ""
        assert tokenize(None) == ()
        assert lemmatize(None) == ()


# ---------------------------------------------------------------------------
# 3. Language identification and routing
# ---------------------------------------------------------------------------


class TestLanguageRouting:
    def test_english_is_supported(self):
        profile = detect_language("investigate the problem")
        assert profile.language == "en" and profile.script == "latin"
        assert route_language(profile) == "supported"

    def test_non_latin_script_is_routed_unsupported_not_assumed_english(self):
        profile = detect_language("\u0906\u092a \u0915\u0948\u0938\u0947 \u0939\u0948\u0902")
        assert profile.language != "en"
        assert route_language(profile) == "unsupported"

    def test_rtl_script_reports_direction(self):
        assert detect_language("\u0645\u0631\u062d\u0628\u0627").direction == "rtl"

    def test_digits_only_is_unknown(self):
        profile = detect_language("12345 !!!")
        assert profile.language == "und" and route_language(profile) == "unknown"

    def test_empty_is_unknown(self):
        assert route_language(detect_language("")) == "unknown"
        assert route_language(detect_language(None)) == "unknown"


# ---------------------------------------------------------------------------
# 4. Provider seam (optional, bounded, fail-closed)
# ---------------------------------------------------------------------------


class _GoodProvider:
    name = "test-good"

    def lookup(self, term, *, context=None):
        if term == "widgetish":
            return {"canonical_term": "widget", "atlas_concepts": ["widget_concept"]}
        return None


class _RaisingProvider:
    name = "test-boom"

    def lookup(self, term, *, context=None):
        raise RuntimeError("provider exploded")


class _MalformedProvider:
    name = "test-bad"

    def lookup(self, term, *, context=None):
        return 12345  # not an entry, not a mapping


class TestProviderSeam:
    def test_absent_provider_yields_nothing_not_a_guess(self):
        registry = LexicalProviderRegistry()
        assert registry.names() == ()
        assert registry.lookup("anything") == ()

    def test_null_provider_is_honest(self):
        assert NullLexicalProvider().lookup("x") is None

    def test_optional_provider_supplies_evidence(self):
        registry = LexicalProviderRegistry([_GoodProvider()])
        found = registry.lookup("widgetish")
        assert found and found[0].canonical_term == "widget"

    def test_raising_provider_is_skipped(self):
        registry = LexicalProviderRegistry([_RaisingProvider(), _GoodProvider()])
        assert registry.lookup("widgetish")  # second provider still used

    def test_malformed_provider_output_is_not_evidence(self):
        registry = LexicalProviderRegistry([_MalformedProvider()])
        assert registry.lookup("anything") == ()

    def test_registry_is_bounded_and_deduplicated_by_name(self):
        registry = LexicalProviderRegistry()
        for index in range(MAX_PROVIDERS + 4):
            provider = _GoodProvider()
            provider.name = f"p{index}"
            registry.register(provider)
        assert len(registry.names()) == MAX_PROVIDERS
        assert registry.register(_GoodProvider()) is False  # duplicate name

    def test_non_provider_is_refused(self):
        assert LexicalProviderRegistry().register(object()) is False


# ---------------------------------------------------------------------------
# 5. Vocabulary resolution
# ---------------------------------------------------------------------------


class TestVocabularyResolution:
    def test_resolved(self):
        resolution = _service().resolve("investigation")
        assert resolution.status is VocabularyStatus.RESOLVED
        assert resolution.canonical_concept == "investigation"
        assert resolution.resolved is True

    def test_unresolved_never_guesses(self):
        resolution = _service().resolve("zorblax")
        assert resolution.status is VocabularyStatus.UNRESOLVED
        assert resolution.candidates == ()

    def test_ambiguous_preserves_all_candidates(self):
        service = LanguageService.from_sources({})
        service.lexicon.add(entry("research", atlas_concepts=("a", "b")))
        resolution = service.resolve("research")
        assert resolution.status is VocabularyStatus.AMBIGUOUS
        assert set(resolution.candidates) == {"a", "b"}

    def test_declared_atlas_fact_wins_over_a_provider(self):
        service = LanguageService(
            vocabulary_from_sources({"operational_capability": ("investigate",)}),
            providers=[_GoodProvider()],
        )
        assert service.resolve("investigate").canonical_concept == "investigate"

    def test_empty_and_non_text(self):
        assert _service().resolve("").status is VocabularyStatus.UNRESOLVED
        assert _service().resolve(None).status is VocabularyStatus.UNRESOLVED


# ---------------------------------------------------------------------------
# 6. The cohesive service
# ---------------------------------------------------------------------------


class TestLanguageService:
    def test_analyse_reports_tokens_lemmas_and_concepts(self):
        annotation = _service().analyse("Please investigate the problem")
        assert annotation.profile.language == "en"
        assert "investigate" in annotation.tokens
        assert "investigate" in annotation.concepts

    def test_analyse_is_deterministic(self):
        service = _service()
        assert service.analyse("investigate the problem").to_dict() == (
            service.analyse("investigate the problem").to_dict()
        )

    def test_empty_input_is_honest(self):
        annotation = _service().analyse("")
        assert annotation.concepts == ()
        assert annotation.provenance == ("empty-or-non-text",)

    def test_unknown_text_is_not_fabricated(self):
        annotation = _service().analyse("zorblax the unexplainable")
        assert annotation.concepts == ()
        assert annotation.ambiguous is False

    def test_annotation_is_serializable(self):
        payload = _service().analyse("investigate").to_dict()
        assert set(payload) >= {"surface", "profile", "tokens", "concepts", "ambiguous"}


# ---------------------------------------------------------------------------
# 7. Conversation interaction classes (uncertainty preserved, never guessed)
# ---------------------------------------------------------------------------

CONVERSATION_CLASSES = (
    "Can you do that?",
    "No, the second one.",
    "Actually, don't do it.",
    "Why did that happen?",
    "Make it like before.",
    "Okay, now fix that.",
    "Wait, I meant the other module.",
    "Explain it simply.",
    "Compare those two.",
    "Now forget that and do the other thing.",
)


class TestConversationClasses:
    @pytest.mark.parametrize("text", CONVERSATION_CLASSES)
    def test_every_class_analyses_deterministically_and_invents_nothing(self, text):
        service = _service()
        first = service.analyse(text)
        second = service.analyse(text)
        assert first.to_dict() == second.to_dict()
        # No concept is ever reported that the lexicon does not declare.
        declared = {c for e in service.lexicon.entries() for c in e.concepts()}
        assert set(first.concepts) <= declared

    @pytest.mark.parametrize("text", CONVERSATION_CLASSES)
    def test_analysis_grants_no_authority(self, text):
        service = _service()
        payload = service.analyse(text).to_dict()
        for forbidden in ("approval", "authorization", "execute", "promote", "authority"):
            assert forbidden not in payload


# ---------------------------------------------------------------------------
# 8. Development language reaches the existing structured layer
# ---------------------------------------------------------------------------

DEVELOPMENT_REQUESTS = (
    "I want you to improve the development gap module while preserving its "
    "existing interface and behavior.",
    "Improve this module.",
    "Add a new capability.",
    "Change the existing implementation but preserve compatibility.",
    "Investigate the problem first; don't change anything yet.",
)


class TestDevelopmentLanguage:
    @pytest.mark.parametrize("text", DEVELOPMENT_REQUESTS)
    def test_development_language_is_analysed_deterministically(self, text):
        service = _service()
        annotation = service.analyse(text)
        assert annotation.tokens, text
        assert annotation.profile.language == "en"
        assert service.analyse(text).to_dict() == annotation.to_dict()

    def test_a_named_target_resolves_to_its_atlas_concept(self):
        service = LanguageService.from_sources(
            {"component": ("development_gap", "development_gap_module")}
        )
        annotation = service.analyse(
            "I want you to improve the development gap module while preserving "
            "its existing interface and behavior."
        )
        assert "development_gap" in annotation.concepts


# ---------------------------------------------------------------------------
# 9. Kernel integration
# ---------------------------------------------------------------------------


class TestKernelIntegration:
    def test_language_service_projects_atlas_own_vocabularies(self, kernel):
        service = kernel.language_service()
        assert service is not None
        assert service.lexicon.size() > 0
        # The operational catalogue is the same authority used elsewhere.
        assert service.resolve("investigate").canonical_concept == "investigate"
        assert service.resolve("investigation").resolved is True

    def test_language_service_is_cache_only_and_deterministic(self, kernel):
        first = kernel.language_service()
        assert kernel.language_service() is first

    def test_language_analysis_is_a_bounded_dict(self, kernel):
        payload = kernel.language_analysis("investigate the problem")
        assert isinstance(payload, dict)
        assert payload["profile"]["language"] == "en"
        assert "investigate" in payload["concepts"]

    def test_language_analysis_of_empty_is_honest(self, kernel):
        assert kernel.language_analysis("")["concepts"] == []

    def test_language_analysis_creates_no_approval_or_promotion_state(self, kernel):
        before = kernel.pending_promotion_reviews()
        kernel.language_analysis("improve the development gap module")
        assert kernel.pending_promotion_reviews() == before


@pytest.fixture(scope="module")
def kernel():
    import pkgutil
    import tempfile

    import atlas.storage as storage_pkg

    tmp = pathlib.Path(tempfile.mkdtemp())
    db = tmp / "language.db"
    saved = []
    for info in pkgutil.iter_modules(storage_pkg.__path__):
        try:
            module = __import__(f"atlas.storage.{info.name}", fromlist=["*"])
        except Exception:  # noqa: BLE001
            continue
        for attr in dir(module):
            obj = getattr(module, attr)
            if isinstance(obj, type) and hasattr(obj, "DEFAULT_DB_PATH"):
                saved.append((obj, obj.DEFAULT_DB_PATH))
                obj.DEFAULT_DB_PATH = db
    from atlas.kernel.atlas import Atlas

    atlas = Atlas()
    atlas.start()
    try:
        yield atlas
    finally:
        atlas.shutdown()
        for obj, original in saved:
            obj.DEFAULT_DB_PATH = original


# ---------------------------------------------------------------------------
# 10. Architectural quality — leaf boundary, no model, no authority
# ---------------------------------------------------------------------------


class TestArchitecturalBoundary:
    def test_the_foundation_is_a_stdlib_only_leaf(self):
        import ast

        package = pathlib.Path(__file__).resolve().parents[1] / "atlas" / "language"
        imported: set[str] = set()
        for path in package.glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.update(a.name.split(".")[0] for a in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported.add(node.module.split(".")[0])
        for forbidden in ("openai", "anthropic", "requests", "spacy", "nltk",
                          "torch", "transformers", "numpy", "sklearn"):
            assert forbidden not in imported
        assert "atlas" in imported  # only the shared conversation primitives

    def test_the_foundation_imports_no_kernel_or_registry(self):
        import ast

        package = pathlib.Path(__file__).resolve().parents[1] / "atlas" / "language"
        for path in package.glob("*.py"):
            source = path.read_text(encoding="utf-8")
            for forbidden in ("atlas.kernel", "atlas.evolution", "atlas.storage"):
                assert forbidden not in source
