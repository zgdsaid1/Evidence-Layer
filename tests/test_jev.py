"""JEV parser and fail-closed boundary tests; clients are always fake."""

from __future__ import annotations

import csv
import io
import os
from types import SimpleNamespace

import pytest

from evidence_layer.jev_benchmark import parse_benchmark_config
from evidence_layer.scoring.base import Scorer
from evidence_layer.scoring.jev import (
    DEFAULT_JEV_MODEL,
    JevEvidenceScorer,
    JevResponseError,
    JevTransferDeniedError,
    RetryPolicy,
    _extract_score,
    render_benchmark_csv,
    write_benchmark_csv,
)
from evidence_layer.scoring import jev as jev_module


class FakeClient:
    def __init__(self):
        self.calls = []

    def system_one(self, state, questions, **kwargs):
        self.calls.append((state, questions, kwargs))
        return SimpleNamespace()


def make_scorer(client: FakeClient | None = None) -> JevEvidenceScorer:
    return JevEvidenceScorer(
        client=client,
        noul_factory=lambda instructions: object(),
    )


@pytest.mark.parametrize("value", [0, 0.625, 1, "0.625", "1e-1"])
def test_score_parser_accepts_valid_scores_without_invoking_provider(value):
    response = SimpleNamespace(
        nouls={"candidate_0": SimpleNamespace(noul=value)}
    )
    assert _extract_score(response, "candidate_0") == float(value)


@pytest.mark.parametrize(
    "value", [-0.01, 1.01, float("nan"), float("inf"), True, "not-a-score"]
)
def test_score_parser_rejects_invalid_scores_without_provider_access(value):
    response = SimpleNamespace(
        nouls={"candidate_0": SimpleNamespace(noul=value)}
    )
    with pytest.raises(JevResponseError) as error:
        _extract_score(response, "candidate_0")
    assert str(error.value) == "The Jev provider returned an invalid relevance response."


@pytest.mark.parametrize(
    "response",
    [
        SimpleNamespace(),
        SimpleNamespace(nouls={}),
        SimpleNamespace(nouls={"candidate_0": object()}),
        SimpleNamespace(nouls=None),
    ],
)
def test_score_parser_rejects_missing_or_malformed_results(response):
    with pytest.raises(JevResponseError):
        _extract_score(response, "candidate_0")


def test_direct_scorer_denies_before_using_credentials_sdk_or_injected_client(
    monkeypatch,
):
    query = "PRIVATE_QUERY_TEXT"
    candidate = "PRIVATE_CANDIDATE_TEXT"
    secret = "SYNTHETIC_API_SECRET"
    client = FakeClient()
    scorer = make_scorer(client)
    monkeypatch.setenv("TYPESAFE_API_KEY", secret)

    def unexpected_resolve():
        raise AssertionError("credential resolution must not occur on denial")

    monkeypatch.setattr(scorer, "_resolve_client", unexpected_resolve)
    with pytest.raises(JevTransferDeniedError) as error:
        scorer.score(query, candidate)

    assert "trusted authorization boundary" in str(error.value)
    assert scorer.last_record is not None
    assert scorer.last_record.failure_category == "transfer_denied"
    serialized = repr(scorer.last_record.to_dict())
    for sensitive in (query, candidate, secret):
        assert sensitive not in str(error.value)
        assert sensitive not in serialized
    assert client.calls == []


def test_default_scorer_denies_without_reading_environment_or_importing_sdk(
    monkeypatch,
):
    scorer = JevEvidenceScorer()

    def unexpected_get(*args, **kwargs):
        raise AssertionError("environment must not be read on denial")

    def unexpected_import(*args, **kwargs):
        raise AssertionError("SDK must not be imported on denial")

    monkeypatch.setattr(os.environ, "get", unexpected_get)
    monkeypatch.setattr(jev_module.importlib, "import_module", unexpected_import)
    with pytest.raises(JevTransferDeniedError):
        scorer.score("query", "candidate")


def test_client_resolution_is_disabled_even_with_credentials_and_injected_client(
    monkeypatch,
):
    client = FakeClient()
    scorer = make_scorer(client)
    monkeypatch.setenv("TYPESAFE_API_KEY", "SYNTHETIC_API_SECRET")
    monkeypatch.setattr(
        jev_module,
        "_load_sdk",
        lambda: (_ for _ in ()).throw(AssertionError("SDK must remain unused")),
    )

    with pytest.raises(JevTransferDeniedError):
        scorer._resolve_client()
    assert client.calls == []


def test_final_system_one_guard_denies_immediately_before_fake_client_call():
    client = FakeClient()
    with pytest.raises(JevTransferDeniedError):
        JevEvidenceScorer._system_one(
            client,
            {"query": "PRIVATE_QUERY"},
            {"candidate_0": "PRIVATE_PAYLOAD"},
            model=DEFAULT_JEV_MODEL,
            retry=None,
            timeout=1.0,
        )
    assert client.calls == []


def test_caller_flags_and_attached_scorers_are_not_transfer_authorization():
    class InjectedScorer(Scorer):
        def __init__(self):
            self.calls = []

        def score(self, query, text):
            self.calls.append((query, text))
            return 1.0

    injected = InjectedScorer()
    from evidence_layer.scoring.policy import build_provider_selection_policy

    policy = build_provider_selection_policy(
        jev_enabled=True,
        jev_permitted_by_request=True,
        jev_permitted_by_plan=True,
        jev_scorer=injected,
    )
    outcome = policy.score("query", ["candidate"])

    assert outcome.provider == "lexical"
    assert outcome.fallback_reason is not None
    assert outcome.fallback_reason.category == "transfer_denied"
    assert injected.calls == []


def test_retry_policy_is_configuration_only_while_transfer_is_disabled():
    retry_policy = RetryPolicy(max_retries=2, backoff_seconds=0)
    client = FakeClient()
    scorer = JevEvidenceScorer(client=client, retry_policy=retry_policy)

    with pytest.raises(JevTransferDeniedError):
        scorer.score("query", "candidate")
    assert client.calls == []
    assert scorer.last_record is not None
    assert scorer.last_record.retry_count is None


def test_denial_audit_record_and_csv_contain_no_sensitive_payload():
    query = "PRIVATE_QUERY_TEXT"
    candidate = "PRIVATE_CANDIDATE_TEXT"
    secret = "SYNTHETIC_API_SECRET"
    scorer = make_scorer(FakeClient())

    with pytest.raises(JevTransferDeniedError):
        scorer.score(query, candidate)
    assert scorer.last_record is not None

    rendered = render_benchmark_csv([scorer.last_record])
    rows = list(csv.DictReader(io.StringIO(rendered)))
    assert len(rows) == 1
    assert "query" not in rows[0]
    assert "text" not in rows[0]
    for sensitive in (query, candidate, secret):
        assert sensitive not in rendered


def test_report_writer_rejects_paths_outside_reports():
    with pytest.raises(ValueError):
        write_benchmark_csv([], "../outside.csv")


def test_benchmark_configuration_defaults_and_test_split_gate():
    config = parse_benchmark_config([])

    assert config.split == "dev"
    assert config.allow_test is False
    assert config.max_cases == 10
    assert config.max_candidates_per_case == 5
    assert config.model == DEFAULT_JEV_MODEL
    assert config.timeout == 10.0
    assert config.retry_policy.max_retries == 2
    with pytest.raises(SystemExit):
        parse_benchmark_config(["--split", "test"])
    assert parse_benchmark_config(["--split", "test", "--allow-test"]).split == "test"
