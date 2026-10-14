"""Provider-policy tests use local fixtures and test-only fakes."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import math

import pytest

from evidence_layer.authorization import (
    DenyAllTransferAuthorizer,
    RequestOperationContext,
    TransferDenial,
    TransferDenialReason,
    TransferGrant,
)
from evidence_layer.retrieval.local_corpus import LocalCorpusRetriever
from evidence_layer.schemas import EvidenceCandidate
from evidence_layer.scoring.base import Scorer
from evidence_layer.scoring.lexical import LexicalScorer
from evidence_layer.scoring.policy import (
    _lexical_recompute_after_provider_failure,
    build_provider_selection_policy,
)
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
        self.calls.append((query, text))
        if self.error is not None and len(self.calls) > (self.fail_after_calls or 0):
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


def _context() -> RequestOperationContext:
    return RequestOperationContext(
        request_id="request-1",
        operation_id="operation-1",
        principal_id="principal-1",
        tenant_id="tenant-1",
        policy_version="policy-v1",
    )


def _enabled_policy(*, scorer: Scorer, context=None):
    return build_provider_selection_policy(
        jev_enabled=True,
        jev_permitted_by_request=True,
        jev_permitted_by_plan=True,
        jev_scorer=scorer,
        request_context=context,
    )


def test_all_jev_flags_true_without_trusted_authorization_makes_zero_calls():
    jev = FakeScorer({"alpha": 0.9, "beta": 0.1})
    policy = _enabled_policy(scorer=jev)

    outcome = policy.score("alpha", ["alpha", "beta"])

    assert outcome.provider == "lexical"
    assert outcome.fallback_reason is not None
    assert outcome.fallback_reason.category == "transfer_denied"
    assert outcome.scores == tuple(
        LexicalScorer().score("alpha", text) for text in ("alpha", "beta")
    )
    assert jev.calls == []


def test_caller_supplied_authorizer_is_rejected_before_it_can_run():
    class SideEffectAuthorizer:
        def __init__(self):
            self.calls = 0

        def authorize(self, context, intent):
            self.calls += 1
            return object()

    authorizer = SideEffectAuthorizer()
    jev = FakeScorer({"alpha": 0.9})
    with pytest.raises(ValueError, match="custom transfer authorizers are disabled"):
        build_provider_selection_policy(
            jev_enabled=True,
            jev_permitted_by_request=True,
            jev_permitted_by_plan=True,
            jev_scorer=jev,
            transfer_authorizer=authorizer,
        )

    assert authorizer.calls == 0
    assert jev.calls == []


def test_injected_scorer_context_and_credentials_do_not_enable_provider_call(
    monkeypatch,
):
    jev = FakeScorer({"alpha": 0.9})
    monkeypatch.setenv("TYPESAFE_API_KEY", "SYNTHETIC_API_SECRET")
    policy = _enabled_policy(scorer=jev, context=_context())

    outcome = policy.score_candidates("alpha", _candidates()[:1])

    assert outcome.provider == "lexical"
    assert outcome.fallback_reason is not None
    assert outcome.fallback_reason.category == "transfer_denied"
    assert jev.calls == []


def test_policy_preflight_receives_complete_non_content_scope(monkeypatch):
    candidates = _candidates()
    context = _context()
    jev = FakeScorer({"alpha": 0.9, "beta": 0.1})
    calls = []

    def record_and_deny(self, received_context, intent):
        calls.append((received_context, intent))
        return TransferDenial(TransferDenialReason.DENY_ALL)

    monkeypatch.setattr(DenyAllTransferAuthorizer, "authorize", record_and_deny)
    outcome = _enabled_policy(scorer=jev, context=context).score_candidates(
        "PRIVATE_QUERY_TEXT", candidates
    )

    assert len(calls) == 1
    assert calls[0][0] == context
    intent = calls[0][1]
    assert intent.provider == "jev"
    assert intent.purpose == "evidence_scoring"
    assert intent.source_ids == frozenset({"source"})
    assert intent.candidate_ids == frozenset({"a", "b"})
    assert intent.candidate_source_pairs == frozenset(
        {("a", "source"), ("b", "source")}
    )
    assert intent.data_categories == frozenset({"query_text", "candidate_text"})
    assert "PRIVATE_QUERY_TEXT" not in repr(intent)
    assert all(candidate.text not in repr(intent) for candidate in candidates)
    assert outcome.provider == "lexical"
    assert outcome.fallback_reason is not None
    assert outcome.fallback_reason.category == "transfer_denied"
    assert jev.calls == []


def test_valid_fake_authorization_still_cannot_enable_jev(monkeypatch):
    candidates = _candidates()
    context = _context()
    jev = FakeScorer({"alpha": 0.9, "beta": 0.1})

    def grant_fake(self, received_context, intent):
        assert received_context == context
        assert intent.candidate_ids == frozenset({"a", "b"})
        # Even an exactly scoped caller-created object is not trusted
        # provenance and must not enable the Phase 1 provider path.
        return TransferGrant(
            grant_id="fake-grant",
            request_id=received_context.request_id,
            operation_id=received_context.operation_id,
            principal_id=received_context.principal_id,
            tenant_id=received_context.tenant_id,
            provider=intent.provider,
            purpose=intent.purpose,
            source_ids=intent.source_ids,
            candidate_ids=intent.candidate_ids,
            candidate_source_pairs=intent.candidate_source_pairs,
            data_categories=intent.data_categories,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=1),
            policy_version=received_context.policy_version,
        )

    monkeypatch.setattr(DenyAllTransferAuthorizer, "authorize", grant_fake)
    outcome = _enabled_policy(scorer=jev, context=context).score_candidates(
        "query", candidates
    )

    assert outcome.provider == "lexical"
    assert outcome.fallback_reason is not None
    assert outcome.fallback_reason.category == "transfer_disabled"
    assert jev.calls == []


def test_text_only_compatibility_method_never_invokes_injected_scorer():
    jev = FakeScorer({"alpha": 0.9})
    outcome = _enabled_policy(scorer=jev).score("alpha", ["alpha"])

    assert outcome.provider == "lexical"
    assert outcome.fallback_reason is not None
    assert outcome.fallback_reason.category == "transfer_denied"
    assert jev.calls == []


def test_partial_fake_provider_results_are_discarded_and_full_set_is_lexical():
    provider = FakeScorer(
        {"alpha": 0.99, "beta": 0.01},
        RuntimeError("SENSITIVE_PROVIDER_RESPONSE"),
        fail_after_calls=1,
    )
    lexical = LexicalScorer()

    partial_scores = []
    try:
        for text in ("alpha", "beta"):
            partial_scores.append(provider.score("alpha", text))
    except RuntimeError:
        # The test fake simulates a failed second attempt. The production
        # fallback helper receives the full original set, never partial scores.
        outcome = _lexical_recompute_after_provider_failure(
            "alpha", ["alpha", "beta"], lexical, "provider_failure"
        )

    assert partial_scores == [0.99]
    assert outcome.provider == "lexical"
    assert outcome.scores == tuple(
        lexical.score("alpha", text) for text in ("alpha", "beta")
    )
    assert outcome.fallback_reason is not None
    assert outcome.fallback_reason.category == "provider_failure"
    assert "SENSITIVE" not in repr(outcome)
    assert provider.calls == [("alpha", "alpha"), ("alpha", "beta")]


def test_invalid_partial_fake_scores_recompute_the_complete_set_lexically():
    class InvalidSecondScore(Scorer):
        def __init__(self):
            self.calls = []

        def score(self, query, text):
            self.calls.append((query, text))
            return 0.8 if len(self.calls) == 1 else float("nan")

    provider = InvalidSecondScore()
    lexical = LexicalScorer()
    observed_scores = []
    invalid = False
    for text in ("alpha", "beta"):
        score = provider.score("alpha", text)
        observed_scores.append(score)
        if not isinstance(score, (int, float)) or not math.isfinite(score) or not 0 <= score <= 1:
            invalid = True
            break
    assert invalid
    assert len(observed_scores) == 2
    assert observed_scores[0] == 0.8
    assert math.isnan(observed_scores[1])
    outcome = _lexical_recompute_after_provider_failure(
        "alpha", ["alpha", "beta"], lexical, "invalid_response"
    )

    assert outcome.provider == "lexical"
    assert outcome.scores == tuple(
        lexical.score("alpha", text) for text in ("alpha", "beta")
    )
    assert outcome.fallback_reason is not None
    assert outcome.fallback_reason.category == "invalid_response"
    assert provider.calls == [("alpha", "alpha"), ("alpha", "beta")]


def test_retriever_transfers_candidate_source_ids_to_default_deny_preflight(
    tmp_path, monkeypatch
):
    corpus = tmp_path / "corpus.jsonl"
    corpus.write_text(
        '{"passage_id":"candidate-1","source_id":"source-1",'
        '"source_url":"local:fixture","text":"alpha evidence"}\n',
        encoding="utf-8",
    )
    context = _context()
    jev = FakeScorer({"alpha evidence": 0.8})
    calls = []

    def record_and_deny(self, received_context, intent):
        calls.append((received_context, intent))
        return TransferDenial(TransferDenialReason.DENY_ALL)

    monkeypatch.setattr(DenyAllTransferAuthorizer, "authorize", record_and_deny)
    policy = _enabled_policy(scorer=jev, context=context)
    result = LocalCorpusRetriever(corpus, scoring_policy=policy).retrieve("alpha")

    assert result.scoring_provider == "lexical"
    assert result.scoring_failure_category == "transfer_denied"
    assert calls[0][1].source_ids == frozenset({"source-1"})
    assert calls[0][1].candidate_ids == frozenset({"candidate-1"})
    assert jev.calls == []


def test_local_retrieval_remains_deterministic_and_network_free(tmp_path):
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

    assert first == second
    assert first.scoring_provider == "lexical"
    assert first.scoring_failure_category is None
    assert select_top_k(_candidates(), LexicalScorer(), "alpha", 2) == ["b", "a"]


def test_custom_scoring_policy_cannot_be_injected_into_local_retriever(tmp_path):
    class CustomPolicy:
        def score_candidates(self, query, candidates):
            raise AssertionError("custom policy must not be invoked")

    corpus = tmp_path / "corpus.jsonl"
    corpus.write_text("", encoding="utf-8")
    with pytest.raises(TypeError, match="built-in ProviderSelectionPolicy"):
        LocalCorpusRetriever(corpus, scoring_policy=CustomPolicy())


def test_precomputed_scores_keep_candidate_alignment_and_tie_order():
    assert select_top_k_scored(_candidates(), [0.5, 0.5], 2) == ["a", "b"]


def test_precomputed_score_count_must_match_candidate_count():
    with pytest.raises(ValueError, match="one value for each candidate"):
        select_top_k_scored(_candidates(), [0.5], 2)


def test_policy_flags_must_be_explicit_booleans():
    with pytest.raises(TypeError, match="jev_enabled"):
        build_provider_selection_policy(jev_enabled=1)  # type: ignore[arg-type]


def test_empty_candidate_set_does_not_claim_jev_was_used():
    jev = FakeScorer({})
    outcome = _enabled_policy(scorer=jev).score("query", [])

    assert outcome.provider == "lexical"
    assert outcome.scores == ()
    assert outcome.fallback_reason is None
    assert jev.calls == []
