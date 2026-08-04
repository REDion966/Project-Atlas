"""Phase 17.4 — Knowledge Extractor tests."""

import pytest

from atlas.research.extractor import KnowledgeExtractor
from atlas.research.models import ResearchSource, SourceKind, SourceProfile


def make_source(text, uri="s1", kind=SourceKind.DOCUMENT, title=""):
    return SourceProfile(
        uri=uri, kind=kind, text=text, title=title, language="text"
    )


class TestChunking:
    def test_empty_text_has_no_chunks(self):
        extractor = KnowledgeExtractor()
        assert extractor.chunk("") == []

    def test_short_text_is_one_chunk(self):
        extractor = KnowledgeExtractor()
        text = "Atlas stores experiences in SQLite."
        assert extractor.chunk(text) == [text]

    def test_chunks_respect_size_bound(self):
        extractor = KnowledgeExtractor(chunk_size=50)
        text = (
            "First sentence about storage persistence. "
            "Second sentence about indexing. "
            "Third sentence about retrieval."
        )
        chunks = extractor.chunk(text)
        assert len(chunks) >= 2
        assert all(len(c) <= 60 for c in chunks)  # single over-long sentence allowed

    def test_chunking_is_deterministic(self):
        extractor = KnowledgeExtractor(chunk_size=40)
        text = "One sentence here. Another sentence there. A third sentence now."
        assert extractor.chunk(text) == extractor.chunk(text)

    def test_over_long_sentence_gets_own_chunk(self):
        extractor = KnowledgeExtractor(chunk_size=20)
        long_sentence = "A very long single sentence that exceeds the chunk size."
        chunks = extractor.chunk(long_sentence)
        assert chunks == [long_sentence]

    def test_chunk_size_validation(self):
        with pytest.raises(ValueError):
            KnowledgeExtractor(chunk_size=0)


class TestNormalization:
    def test_punctuation_stripped(self):
        extractor = KnowledgeExtractor()
        claims = extractor.extract(make_source("Atlas uses SQLite!"))
        assert claims[0].statement == "Atlas uses SQLite"

    def test_whitespace_collapsed(self):
        extractor = KnowledgeExtractor()
        claims = extractor.extract(make_source("Atlas   uses\n\tSQLite."))
        assert claims[0].statement.startswith("Atlas uses SQLite")


class TestDuplicateRemoval:
    def test_identical_statements_deduplicated(self):
        extractor = KnowledgeExtractor()
        text = "Atlas uses SQLite. Atlas uses SQLite."
        claims = extractor.extract(make_source(text))
        assert len(claims) == 1

    def test_punctuation_variant_deduplicated(self):
        extractor = KnowledgeExtractor()
        text = "Atlas uses SQLite. Atlas uses SQLite!"
        claims = extractor.extract(make_source(text))
        assert len(claims) == 1

    def test_stable_ordering(self):
        extractor = KnowledgeExtractor()
        text = "Alpha claim here. Beta claim here."
        claims = extractor.extract(make_source(text))
        assert [c.statement for c in claims] == [
            "Alpha claim here",
            "Beta claim here",
        ]


class TestClaimIds:
    def test_ids_are_stable_across_extractions(self):
        extractor = KnowledgeExtractor()
        text = "Atlas uses SQLite for storage."
        first = extractor.extract(make_source(text, uri="a"))
        second = extractor.extract(make_source(text, uri="b"))
        assert first[0].claim_id == second[0].claim_id

    def test_ids_are_deterministic(self):
        extractor = KnowledgeExtractor()
        claims = extractor.extract(make_source("Atlas uses SQLite for storage."))
        assert claims[0].claim_id.startswith("claim:")
        assert len(claims[0].claim_id) == 6 + 16


class TestProvisionalConfidence:
    def test_found_in_source_scores_higher(self):
        extractor = KnowledgeExtractor()
        text = "Atlas uses SQLite for persistent storage across sessions."
        claims = extractor.extract(make_source(text))
        assert 0.6 <= claims[0].confidence <= 0.8

    def test_confidence_never_exceeds_cap(self):
        extractor = KnowledgeExtractor()
        text = "Atlas uses SQLite for persistent storage across many sessions."
        claims = extractor.extract(make_source(text))
        assert all(c.confidence <= 0.8 for c in claims)


class TestProviderMocking:
    class FakeModel:
        def __init__(self, responses):
            self.responses = list(responses)
            self.calls = []

        def complete(self, prompt):
            self.calls.append(prompt)
            if not self.responses:
                raise AssertionError("no response queued")
            return self.responses.pop(0)

    def test_model_produces_claims(self):
        model = self.FakeModel(["Atlas uses SQLite.\nAtlas has a kernel."])
        extractor = KnowledgeExtractor(model=model)
        claims = extractor.extract(make_source("irrelevant text here"))
        assert [c.statement for c in claims] == [
            "Atlas uses SQLite",
            "Atlas has a kernel",
        ]
        assert len(model.calls) == 1

    def test_no_model_is_fully_deterministic(self):
        extractor = KnowledgeExtractor()
        text = "First claim sentence here. Second claim sentence here."
        claims = extractor.extract(make_source(text))
        assert [c.statement for c in claims] == [
            "First claim sentence here",
            "Second claim sentence here",
        ]

    def test_model_raising_falls_back_to_sentences(self):
        class ExplodingModel:
            def complete(self, prompt):
                raise RuntimeError("provider down")

        extractor = KnowledgeExtractor(model=ExplodingModel())
        text = "Fallback sentence one. Fallback sentence two."
        claims = extractor.extract(make_source(text))
        assert [c.statement for c in claims] == [
            "Fallback sentence one",
            "Fallback sentence two",
        ]

    def test_model_empty_response_falls_back(self):
        model = self.FakeModel(["   "])
        extractor = KnowledgeExtractor(model=model)
        text = "Fallback sentence one."
        claims = extractor.extract(make_source(text))
        assert claims[0].statement == "Fallback sentence one"

    def test_prompt_builder(self):
        extractor = KnowledgeExtractor()
        prompt = extractor.build_extraction_request("chunk text here")
        assert "Extract factual claims" in prompt
        assert "chunk text here" in prompt

    def test_duplicate_claims_from_model_deduplicated(self):
        model = self.FakeModel(["Atlas uses SQLite.\nAtlas uses SQLite!"])
        extractor = KnowledgeExtractor(model=model)
        claims = extractor.extract(make_source("ignored"))
        assert len(claims) == 1


class TestMalformedSourceHandling:
    def test_minimal_research_source_without_text(self):
        extractor = KnowledgeExtractor()
        source = ResearchSource(uri="docs/x.md", kind=SourceKind.DOCUMENT)
        assert extractor.extract(source) == []

    def test_source_profile_carries_text(self):
        extractor = KnowledgeExtractor()
        source = make_source("Atlas uses SQLite for storage.")
        claims = extractor.extract(source)
        assert len(claims) == 1
        assert claims[0].metadata["source_uri"] == "s1"

    def test_citation_records_source(self):
        extractor = KnowledgeExtractor()
        source = make_source("Atlas uses SQLite.", uri="docs/db.md")
        claims = extractor.extract(source)
        citation = claims[0].citations[0]
        assert citation.source_uri == "docs/db.md"
        assert citation.source_kind == SourceKind.DOCUMENT
