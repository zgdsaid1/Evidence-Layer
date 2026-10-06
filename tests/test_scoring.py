"""Tests for the deterministic lexical scorer and the Scorer interface."""

import pytest

from evidence_layer.scoring.base import Scorer
from evidence_layer.scoring.lexical import LexicalNoStopwordScorer, LexicalScorer


def test_lexical_scorer_implements_scorer_interface():
    assert isinstance(LexicalScorer(), Scorer)


def test_lexical_scorer_is_deterministic():
    scorer = LexicalScorer()
    a = scorer.score("what is the range of the integer type", "the integer range is big")
    b = scorer.score("what is the range of the integer type", "the integer range is big")
    assert a == b


def test_identical_content_scores_one():
    scorer = LexicalScorer()
    assert scorer.score("integer range", "integer range") == pytest.approx(1.0)



def test_no_overlap_scores_zero():
    scorer = LexicalScorer()
    assert scorer.score("apple", "banana") == 0.0


def test_empty_query_scores_zero():
    scorer = LexicalScorer()
    assert scorer.score("", "some passage text") == 0.0


def test_stopword_only_query_scores_zero():
    scorer = LexicalScorer()
    assert scorer.score("the of and", "some passage text") == 0.0


def test_normalize_lowercases_and_drops_stopwords():
    scorer = LexicalScorer()
    tokens = scorer.normalize("What IS the Range of the INTEGER type?")
    assert tokens == ["range", "integer", "type"]


def test_no_stopword_scorer_is_deterministic():
    scorer = LexicalNoStopwordScorer()
    a = scorer.score("the integer range", "the integer range is big")
    b = scorer.score("the integer range", "the integer range is big")
    assert a == b


def test_variants_differ_only_in_stopword_treatment():
    filtered = LexicalScorer()
    no_filter = LexicalNoStopwordScorer()
    # Same tokenization and ordering; only stopword retention differs.
    assert filtered.normalize("the quick fox") == ["quick", "fox"]
    assert no_filter.normalize("the quick fox") == ["the", "quick", "fox"]
    assert no_filter.normalize("THE Quick fox") == ["the", "quick", "fox"]


def test_variant_names_are_explicit_and_distinct():
    assert LexicalScorer().name == "lexical_stopword_filtered"
    assert LexicalNoStopwordScorer().name == "lexical_no_stopword_filter"

