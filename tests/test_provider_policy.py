"""Provider policy tests with local fakes only; no credentials or network."""

from __future__ import annotations

import pytest

from evidence_layer.scoring import jev as jev_module
from evidence_layer.retrieval.local_corpus import LocalCorpusRetriever
from evidence_layer.schemas import EvidenceCandidate
from evidence_layer.scoring.base import Scorer
from evidence_layer.scoring.jev import (
    JevDependencyError,
    JevProviderError,
    JevResponseError,
)
from evidence_layer.scoring.lexical import LexicalScorer
from evidence_layer.scoring.policy import build_provider_selection_policy
from evidence_layer.selection import select_top_k, select_top_k_scored


class FakeScorer(Scorer):
    def __init__(
        self,
        scores: dict[str, float],
        error: Exception | None = None,
        *,
        fail_after_calls: int | None = None,
    ):
        self.scores = scores
        self.error = error
        self.fail_after_calls = fail_after_calls
        self.calls: list[tuple[str, str]] = []

    def score(self, query: str, text: str) -> float:
        if self.error is not None and self.fail_after_calls == len(self.calls):
            raise self.error
        self.calls.append((query, text))
        if self.error is not None and self.fail_after_calls is None:
            raise self.error
        return self.scores[text]


def _candidates() -> list[EvidenceCandidate]:
    return [
        EvidenceCandidate(
            candidate_id="b", source_id="source", source_url="local:b", text="alpha"
        ),
        EvidenceCandidate(
            candidate_id="a", source_id="source", source_url="local:a", text="beta"
        ),
    ]


def test_jev_used_only_when_enabled_configured_and_permitted():
    jev = FakeScorer({"alpha": 0.1, "beta": 0.9})
    policy = build_provider_selection_policy(
        jev_enabled=True,
        jev_permitted_by_request=True,
        jev_permitted_by_plan=True,
        jev_scorer=jev,
    )

    outcome = policy.score("query", ["alpha", "beta"])
    assert outcome.provider == "jev"
    assert outcome.scores == (0.1, 0.9)
    assert outcome.fallback_reason is None
    assert jev.calls == [("query", "alpha"), ("query", "beta")]


def test_disabled_jev_uses_deterministic_local_lexical():
    jev = FakeScorer({"alpha": 0.0, "beta": 1.0})
    policy = build_provider_selection_policy(
        jev_enabled=False,
        jev_permitted_by_request=True,
        jev_permitted_by_plan=True,
        jev_scorer=jev,
    )
    expected = LexicalScorer().score("alpha", "alpha beta")

    first = policy.score("alpha", ["alpha beta"])
    second = policy.score("alpha", ["alpha beta"])

    assert first == second
    assert first.provider == "lexical"
    assert first.scores == (expected,)
    assert jev.calls == []


def test_missing_jev_configuration_falls_back_with_safe_metadata(monkeypatch):
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    policy = build_provider_selection_policy(
        jev_enabled=True,
        jev_permitted_by_request=True,
        jev_permitted_by_plan=True,
    )

    outcome = policy.score("alpha", ["alpha", "beta"])

    lexical = LexicalScorer()
    assert outcome.provider == "lexical"
    assert outcome.scores == tuple(
        lexical.score("alpha", text) for text in ("alpha", "beta")
    )
    assert outcome.fallback_reason is not None
    assert outcome.fallback_reason.category == "configuration_error"


def test_provider_is_not_even_constructed_when_disabled(monkeypatch):
    def unexpected_construction():
        raise AssertionError("Jev must not be constructed when disabled")

    monkeypatch.setattr(
        "evidence_layer.scoring.policy.JevEvidenceScorer", unexpected_construction
    )
    policy = build_provider_selection_policy(jev_enabled=False)
    assert policy.default_provider == "lexical"


def test_default_lexical_policy_never_imports_optional_jev_sdk(monkeypatch):
    original_import = jev_module.importlib.import_module
    calls: list[str] = []

    def guarded_import(name: str):
        calls.append(name)
        if name == "typesafe_sdk":
            raise AssertionError("default lexical scoring must not import TypeSafe")
        return original_import(name)

    monkeypatch.setattr(jev_module.importlib, "import_module", guarded_import)
    outcome = build_provider_selection_policy().score("alpha", ["alpha"])

    assert outcome.provider == "lexical"
    assert outcome.scores == (LexicalScorer().score("alpha", "alpha"),)
    assert "typesafe_sdk" not in calls


def test_missing_optional_dependency_falls_back_safely(monkeypatch):
    secret = "SYNTHETIC_PROVIDER_BODY_AND_SECRET_DO_NOT_LEAK"
    monkeypatch.setenv("TYPESAFE_API_KEY", "synthetic-test-key")
    import_module = __import__("importlib").import_module

    def missing_sdk(name: str):
        if name == "typesafe_sdk":
            raise ModuleNotFoundError(secret)
        return import_module(name)

    monkeypatch.setattr(
        "evidence_layer.scoring.jev.importlib.import_module", missing_sdk
    )
    policy = build_provider_selection_policy(
        jev_enabled=True,
        jev_permitted_by_request=True,
        jev_permitted_by_plan=True,
    )

    outcome = policy.score("query", ["alpha"])
    assert outcome.provider == "lexical"
    assert outcome.scores == (LexicalScorer().score("query", "alpha"),)
    assert outcome.fallback_reason is not None
    assert outcome.fallback_reason.category == "dependency_missing"
    assert secret not in repr(outcome)


def test_request_policy_prohibiting_jev_never_calls_provider():
    jev = FakeScorer({"alpha": 1.0})
    policy = build_provider_selection_policy(
        jev_enabled=True,
        jev_permitted_by_request=False,
        jev_permitted_by_plan=True,
        jev_scorer=jev,
    )

    outcome = policy.score("alpha", ["alpha"])
    assert outcome.provider == "lexical"
    assert outcome.fallback_reason is None
    assert jev.calls == []


def test_plan_policy_prohibiting_jev_never_calls_provider():
    jev = FakeScorer({"alpha": 1.0})
    policy = build_provider_selection_policy(
        jev_enabled=True,
        jev_permitted_by_request=True,
        jev_permitted_by_plan=False,
        jev_scorer=jev,
    )

    outcome = policy.score("alpha", ["alpha"])
    assert outcome.provider == "lexical"
    assert jev.calls == []


def test_jev_failure_discards_partial_scores_and_sanitizes_metadata():
    jev = FakeScorer(
        {"alpha": 1.0, "beta": 0.0},
        JevProviderError("SYNTHETIC_SECRET_RESPONSE_BODY"),
        fail_after_calls=1,
    )
    policy = build_provider_selection_policy(
        jev_enabled=True,
        jev_permitted_by_request=True,
        jev_permitted_by_plan=True,
        jev_scorer=jev,
    )
    texts = ["alpha", "beta"]

    outcome = policy.score("alpha", texts)
    expected = tuple(LexicalScorer().score("alpha", text) for text in texts)

    assert outcome.provider == "lexical"
    assert outcome.scores == expected
    assert outcome.fallback_reason is not None
    assert outcome.fallback_reason.category == "provider_failure"
    assert "SYNTHETIC" not in repr(outcome)
    assert jev.calls == [("alpha", "alpha")]


def test_invalid_jev_response_falls_back_with_category_only():
    jev = FakeScorer({}, JevResponseError("SYNTHETIC_INVALID_RESPONSE_BODY"))
    policy = build_provider_selection_policy(
        jev_enabled=True,
        jev_permitted_by_request=True,
        jev_permitted_by_plan=True,
        jev_scorer=jev,
    )

    outcome = policy.score("alpha", ["alpha"])
    assert outcome.provider == "lexical"
    assert outcome.fallback_reason is not None
    assert outcome.fallback_reason.category == "invalid_response"
    assert "SYNTHETIC" not in repr(outcome)


def test_out_of_range_jev_score_is_not_returned_as_success():
    jev = FakeScorer({"alpha": 1.5})
    policy = build_provider_selection_policy(
        jev_enabled=True,
        jev_permitted_by_request=True,
        jev_permitted_by_plan=True,
        jev_scorer=jev,
    )

    outcome = policy.score("alpha", ["alpha"])

    assert outcome.provider == "lexical"
    assert outcome.scores == (LexicalScorer().score("alpha", "alpha"),)
    assert outcome.fallback_reason is not None
    assert outcome.fallback_reason.category == "invalid_response"


def test_non_finite_jev_scores_fall_back_for_the_whole_set():
    jev = FakeScorer({"alpha": float("nan"), "beta": 1.0})
    policy = build_provider_selection_policy(
        jev_enabled=True,
        jev_permitted_by_request=True,
        jev_permitted_by_plan=True,
        jev_scorer=jev,
    )
    texts = ["alpha", "beta"]

    outcome = policy.score("alpha", texts)

    assert outcome.provider == "lexical"
    assert outcome.scores == tuple(
        LexicalScorer().score("alpha", text) for text in texts
    )
    assert outcome.fallback_reason is not None
    assert outcome.fallback_reason.category == "invalid_response"


def test_unexpected_jev_exception_is_sanitized_and_falls_back():
    jev = FakeScorer({}, RuntimeError("SYNTHETIC_SECRET_ERROR_BODY"))
    policy = build_provider_selection_policy(
        jev_enabled=True,
        jev_permitted_by_request=True,
        jev_permitted_by_plan=True,
        jev_scorer=jev,
    )

    outcome = policy.score("alpha", ["alpha"])

    assert outcome.provider == "lexical"
    assert outcome.scores == (LexicalScorer().score("alpha", "alpha"),)
    assert outcome.fallback_reason is not None
    assert outcome.fallback_reason.category == "provider_failure"
    assert "SYNTHETIC" not in repr(outcome)


def test_retriever_reports_actual_provider_and_fallback_category(tmp_path, monkeypatch):
    corpus = tmp_path / "corpus.jsonl"
    corpus.write_text(
        '{"passage_id":"a","source_id":"s","source_url":"local:a",'
        '"text":"alpha evidence"}\n',
        encoding="utf-8",
    )
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    policy = build_provider_selection_policy(
        jev_enabled=True,
        jev_permitted_by_request=True,
        jev_permitted_by_plan=True,
    )

    result = LocalCorpusRetriever(corpus, scoring_policy=policy).retrieve("alpha")

    assert result.evidence[0].score == LexicalScorer().score("alpha", "alpha evidence")
    assert result.scoring_provider == "lexical"
    assert result.scoring_failure_category == "configuration_error"


def test_retriever_reports_jev_when_jev_scores_candidates(tmp_path):
    corpus = tmp_path / "corpus.jsonl"
    corpus.write_text(
        '{"passage_id":"a","source_id":"s","source_url":"local:a",'
        '"text":"alpha evidence"}\n',
        encoding="utf-8",
    )
    jev = FakeScorer({"alpha evidence": 0.75})
    policy = build_provider_selection_policy(
        jev_enabled=True,
        jev_permitted_by_request=True,
        jev_permitted_by_plan=True,
        jev_scorer=jev,
    )

    result = LocalCorpusRetriever(corpus, scoring_policy=policy).retrieve("alpha")

    assert result.scoring_provider == "jev"
    assert result.scoring_failure_category is None
    assert result.evidence[0].score == 0.75


def test_jev_score_alignment_controls_retrieval_ranking_and_metadata(tmp_path):
    corpus = tmp_path / "corpus.jsonl"
    corpus.write_text(
        '{"passage_id":"b","source_id":"s","source_url":"local:b",'
        '"text":"alpha lower"}\n'
        '{"passage_id":"a","source_id":"s","source_url":"local:a",'
        '"text":"alpha higher"}\n',
        encoding="utf-8",
    )
    jev = FakeScorer({"alpha lower": 0.2, "alpha higher": 0.9})
    policy = build_provider_selection_policy(
        jev_enabled=True,
        jev_permitted_by_request=True,
        jev_permitted_by_plan=True,
        jev_scorer=jev,
    )

    result = LocalCorpusRetriever(corpus, scoring_policy=policy).retrieve(
        "alpha", top_k=2
    )

    assert [item.evidence_id for item in result.evidence] == ["a", "b"]
    assert [item.score for item in result.evidence] == [0.9, 0.2]
    assert jev.calls == [
        ("alpha", "alpha lower"),
        ("alpha", "alpha higher"),
    ]
    assert result.scoring_provider == "jev"
    assert result.scoring_failure_category is None


def test_default_local_retrieval_is_deterministic_without_remote_scoring(tmp_path):
    corpus = tmp_path / "corpus.jsonl"
    corpus.write_text(
        '{"passage_id":"b","source_id":"s","source_url":"local:b",'
        '"text":"alpha beta"}\n'
        '{"passage_id":"a","source_id":"s","source_url":"local:a",'
        '"text":"alpha"}\n',
        encoding="utf-8",
    )
    retriever = LocalCorpusRetriever(corpus)

    first = retriever.retrieve("alpha")
    second = retriever.retrieve("alpha")
    candidates = _candidates()

    assert first == second
    assert first.scoring_provider == "lexical"
    assert first.scoring_failure_category is None
    assert select_top_k(candidates, LexicalScorer(), "alpha", 2) == ["b", "a"]


def test_precomputed_scores_keep_candidate_alignment_and_tie_order():
    candidates = _candidates()

    assert select_top_k_scored(candidates, [0.5, 0.5], 2) == ["a", "b"]


def test_precomputed_score_count_must_match_candidate_count():
    with pytest.raises(ValueError, match="one value for each candidate"):
        select_top_k_scored(_candidates(), [0.5], 2)


def test_policy_flags_must_be_explicit_booleans():
    try:
        build_provider_selection_policy(jev_enabled=1)  # type: ignore[arg-type]
    except TypeError as error:
        assert "jev_enabled" in str(error)
    else:
        raise AssertionError("non-boolean enablement must be rejected")


def test_empty_candidate_set_does_not_claim_jev_was_used():
    jev = FakeScorer({})
    policy = build_provider_selection_policy(
        jev_enabled=True,
        jev_permitted_by_request=True,
        jev_permitted_by_plan=True,
        jev_scorer=jev,
    )

    outcome = policy.score("query", [])
    assert outcome.provider == "lexical"
    assert outcome.scores == ()
    assert jev.calls == []