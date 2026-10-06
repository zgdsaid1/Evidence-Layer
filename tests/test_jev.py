"""Fake-client tests for the optional Jev scorer and benchmark scaffolding."""

from __future__ import annotations

import csv
import io
import logging
from types import SimpleNamespace

import pytest

from evidence_layer.jev_benchmark import parse_benchmark_config
from evidence_layer.schemas import EvidenceCandidate
from evidence_layer.scoring.base import Scorer
from evidence_layer.scoring.jev import (
    DEFAULT_JEV_MODEL,
    JevConfigurationError,
    JevDependencyError,
    JevEvidenceScorer,
    JevProviderError,
    JevResponseError,
    RetryPolicy,
    render_benchmark_csv,
    write_benchmark_csv,
)
from evidence_layer.scoring import jev as jev_module
from evidence_layer.selection import select_top_k


class FakeNoul:
    def __init__(self, *, instructions: str) -> None:
        self.instructions = instructions


class FakeResponse:
    def __init__(
        self,
        score: object,
        *,
        model: object = DEFAULT_JEV_MODEL,
        usage: object = None,
        nouls: object = None,
    ) -> None:
        self.nouls = (
            {"candidate_0": SimpleNamespace(noul=score)}
            if nouls is None
            else nouls
        )
        self.model = model
        self.usage = usage


class FakeClient:
    def __init__(
        self,
        response: object | None = None,
        error: Exception | None = None,
    ) -> None:
        self.response = response or FakeResponse(0.75)
        self.error = error
        self.calls: list[tuple[dict[str, object], dict[str, object], dict[str, object]]] = []

    def system_one(self, state, questions, **kwargs):
        self.calls.append((state, questions, kwargs))
        if self.error is not None:
            raise self.error
        if callable(self.response):
            return self.response(state, questions, kwargs)
        return self.response


def make_scorer(
    client: FakeClient, *, retry_policy: RetryPolicy = RetryPolicy(0, 0)
) -> JevEvidenceScorer:
    return JevEvidenceScorer(
        client=client,
        noul_factory=lambda instructions: FakeNoul(instructions=instructions),
        retry_policy=retry_policy,
    )


def test_scorer_implements_interface_and_extracts_score_and_usage():
    client = FakeClient(
        FakeResponse(
            "0.625",
            usage=SimpleNamespace(input_tokens=120, output_tokens=4),
        )
    )
    scorer = make_scorer(client)

    assert isinstance(scorer, Scorer)
    assert scorer.score("query", "candidate evidence") == 0.625
    assert scorer.last_record is not None
    assert scorer.last_record.model_requested == "jev-latest"
    assert scorer.last_record.model_returned == "jev-latest"
    assert scorer.last_record.sdk_version is None or scorer.last_record.sdk_version
    assert scorer.last_record.timestamp_utc.endswith("+00:00")
    assert (
        scorer.last_record.git_commit_sha is None
        or len(scorer.last_record.git_commit_sha) in {40, 64}
    )
    assert scorer.last_record.input_tokens == 120
    assert scorer.last_record.output_tokens == 4
    assert scorer.last_record.estimated_input_cost_usd == pytest.approx(
        120 * 0.042 / 1_000_000
    )
    assert (
        scorer.last_record.input_cost_label
        == "estimate from vendor-published pricing; not an invoice"
    )


@pytest.mark.parametrize("value", [-0.01, 1.01, float("nan"), float("inf"), True, "nope"])
def test_score_rejects_invalid_provider_relevance_values(value):
    scorer = make_scorer(FakeClient(FakeResponse(value)))

    with pytest.raises(JevResponseError) as error:
        scorer.score("query", "candidate")

    assert str(error.value) == "The Jev provider returned an invalid relevance response."
    assert scorer.last_record is not None
    assert scorer.last_record.failure_category == "invalid_response"


@pytest.mark.parametrize(
    "response",
    [
        SimpleNamespace(),
        FakeResponse(0.5, nouls={}),
        FakeResponse(0.5, nouls={"candidate_0": object()}),
        SimpleNamespace(nouls=None),
    ],
)
def test_missing_or_malformed_nouls_response_is_a_safe_error(response):
    scorer = make_scorer(FakeClient(response))

    with pytest.raises(JevResponseError):
        scorer.score("query", "candidate")

    assert scorer.last_record is not None
    assert scorer.last_record.failure_category == "invalid_response"


def test_missing_model_and_usage_metadata_do_not_discard_valid_score():
    scorer = make_scorer(
        FakeClient(
            SimpleNamespace(
                nouls={"candidate_0": SimpleNamespace(noul=0.5)}
            )
        )
    )

    assert scorer.score("query", "candidate") == 0.5
    assert scorer.last_record is not None
    assert scorer.last_record.model_returned is None
    assert scorer.last_record.input_tokens is None
    assert scorer.last_record.output_tokens is None
    assert scorer.last_record.estimated_input_cost_usd is None
    assert scorer.last_record.input_cost_label is None


def test_explicit_model_override_and_concrete_returned_model_are_recorded():
    client = FakeClient(FakeResponse(0.5, model="jev-4.2.1"))
    scorer = JevEvidenceScorer(
        client=client,
        noul_factory=lambda instructions: FakeNoul(instructions=instructions),
        model="jev-latest",
    )

    assert scorer.score("query", "candidate") == 0.5
    assert client.calls[0][2]["model"] == "jev-latest"
    assert scorer.last_record is not None
    assert scorer.last_record.model_requested == "jev-latest"
    assert scorer.last_record.model_returned == "jev-4.2.1"


def test_arbitrary_valid_model_override_is_passed_and_recorded():
    model = "custom-valid-model"
    client = FakeClient(FakeResponse(0.5, model=model))
    scorer = JevEvidenceScorer(
        client=client,
        noul_factory=lambda instructions: FakeNoul(instructions=instructions),
        model=model,
    )

    assert scorer.score("query", "candidate") == 0.5
    assert client.calls[0][2]["model"] == model
    assert scorer.last_record is not None
    assert scorer.last_record.model_requested == model
    assert scorer.last_record.model_returned == model


def test_runtime_metadata_uses_local_values_when_available(monkeypatch):
    monkeypatch.setattr(jev_module, "_local_sdk_version", lambda: "0.7.2")
    monkeypatch.setattr(jev_module, "_git_commit_sha", lambda: "a" * 40)
    scorer = make_scorer(FakeClient())

    assert scorer.score("query", "candidate") == 0.75
    assert scorer.last_record is not None
    assert scorer.last_record.sdk_version == "0.7.2"
    assert scorer.last_record.git_commit_sha == "a" * 40
    assert scorer.last_record.timestamp_utc.endswith("+00:00")


def test_missing_api_key_fails_before_import_or_network(monkeypatch):
    monkeypatch.setattr(
        jev_module.os.environ,
        "get",
        lambda key, default=None: default if key == "TYPESAFE_API_KEY" else None,
    )

    def unexpected_import(name):
        assert name == "typesafe_sdk"
        raise AssertionError("The SDK must not be imported without an API key")

    monkeypatch.setattr("evidence_layer.scoring.jev.importlib.import_module", unexpected_import)
    scorer = JevEvidenceScorer()

    with pytest.raises(JevConfigurationError) as error:
        scorer.score("query", "candidate")

    assert str(error.value) == "TYPESAFE_API_KEY is required for live Jev scoring."
    assert scorer.last_record is not None
    assert scorer.last_record.failure_category == "configuration_error"


def test_missing_optional_dependency_is_safe_and_lazy(monkeypatch):
    synthetic_secret = "SYNTHETIC_SECRET_DO_NOT_EMIT"
    monkeypatch.setattr(
        jev_module.os.environ,
        "get",
        lambda key, default=None: synthetic_secret
        if key == "TYPESAFE_API_KEY"
        else default,
    )
    import_module = __import__("importlib").import_module

    def missing_sdk(name):
        if name == "typesafe_sdk":
            raise ModuleNotFoundError(synthetic_secret)
        return import_module(name)

    monkeypatch.setattr("evidence_layer.scoring.jev.importlib.import_module", missing_sdk)
    scorer = JevEvidenceScorer()

    with pytest.raises(JevDependencyError) as error:
        scorer.score("query", "candidate")

    assert synthetic_secret not in str(error.value)
    assert scorer.last_record is not None
    assert scorer.last_record.failure_category == "dependency_missing"


def test_fixed_question_uses_state_for_untrusted_query_and_candidate():
    query = "SYNTHETIC_QUERY_DO_NOT_EMIT"
    text = "SYNTHETIC_CANDIDATE_DO_NOT_EMIT"
    client = FakeClient()
    scorer = make_scorer(client)

    scorer.score(query, text)

    state, questions, options = client.calls[0]
    assert state == {"query": query, "candidates": {"candidate_0": text}}
    assert list(questions) == ["candidate_0"]
    assert isinstance(questions["candidate_0"], FakeNoul)
    instructions = questions["candidate_0"].instructions
    assert "useful evidence needed to answer the task query" in instructions
    assert "candidate_0" in instructions
    assert query not in instructions
    assert text not in instructions
    assert options["model"] == DEFAULT_JEV_MODEL
    assert options["timeout"] == 10.0


def test_retry_is_not_locally_repeated_and_error_does_not_leak_input(caplog):
    query = "SYNTHETIC_QUERY_DO_NOT_EMIT"
    text = "SYNTHETIC_CANDIDATE_DO_NOT_EMIT"
    synthetic_secret = "SYNTHETIC_SECRET_DO_NOT_EMIT"
    client = FakeClient(error=RuntimeError(f"{query} {text} {synthetic_secret}"))
    scorer = make_scorer(client, retry_policy=RetryPolicy(2, 0))

    with caplog.at_level(logging.DEBUG):
        with pytest.raises(JevProviderError) as error:
            scorer.score(query, text)

    assert len(client.calls) == 1
    assert client.calls[0][2]["retry"] is None
    assert scorer.last_record is not None
    assert scorer.last_record.retry_count is None
    assert scorer.last_record.failure_category == "provider_failure"
    serialized = str(scorer.last_record.to_dict())
    for sensitive in (query, text, synthetic_secret):
        assert sensitive not in str(error.value)
        assert sensitive not in serialized
        assert sensitive not in caplog.text
        assert sensitive not in render_benchmark_csv([scorer.last_record])


def test_neutral_retry_settings_fail_closed_without_sdk_constructor_fields(
    monkeypatch,
):
    class FakeSDKClient(FakeClient):
        def __init__(self, *, api_key):
            if not api_key:
                raise AssertionError("Expected fake client credential")
            super().__init__()

    class FakeSDKNoul:
        def __init__(self, *, instructions):
            self.instructions = instructions

    def fake_sdk_import(name):
        assert name == "typesafe_sdk"
        return SimpleNamespace(TypeSafeClient=FakeSDKClient, Noul=FakeSDKNoul)

    monkeypatch.setattr(
        jev_module.os.environ,
        "get",
        lambda key, default=None: "SYNTHETIC_SECRET_DO_NOT_EMIT"
        if key == "TYPESAFE_API_KEY"
        else default,
    )
    monkeypatch.setattr(jev_module.importlib, "import_module", fake_sdk_import)
    scorer = JevEvidenceScorer(retry_policy=RetryPolicy(2, 0))

    assert scorer.score("query", "candidate") == 0.75
    assert scorer.last_record is not None
    assert scorer.last_record.retry_count is None


def test_untrusted_or_unexpected_returned_model_is_not_recorded():
    query = "SYNTHETIC_QUERY_DO_NOT_EMIT"
    text = "SYNTHETIC_CANDIDATE_DO_NOT_EMIT"
    synthetic_secret = "SYNTHETIC_SECRET_DO_NOT_EMIT"
    scorer = make_scorer(
        FakeClient(FakeResponse(0.5, model=synthetic_secret))
    )

    assert scorer.score(query, text) == 0.5
    assert scorer.last_record is not None
    serialized = str(scorer.last_record.to_dict())
    for sensitive in (query, text, synthetic_secret):
        assert sensitive not in serialized
        assert sensitive not in render_benchmark_csv([scorer.last_record])


def test_selector_order_remains_deterministic_for_fixed_fake_scores():
    def response(state, questions, kwargs):
        scores = {"body-a": 0.8, "body-b": 0.8, "body-c": 0.4}
        text = state["candidates"]["candidate_0"]
        assert list(questions) == ["candidate_0"]
        assert kwargs["model"] == DEFAULT_JEV_MODEL
        return FakeResponse(scores[text])

    scorer = make_scorer(FakeClient(response))
    candidates = [
        EvidenceCandidate(
            candidate_id="z",
            source_id="s1",
            source_url="https://example.invalid/1",
            text="body-a",
        ),
        EvidenceCandidate(
            candidate_id="a",
            source_id="s2",
            source_url="https://example.invalid/2",
            text="body-b",
        ),
        EvidenceCandidate(
            candidate_id="m",
            source_id="s3",
            source_url="https://example.invalid/3",
            text="body-c",
        ),
    ]

    assert select_top_k(candidates, scorer, "query", 3) == ["a", "z", "m"]
    assert select_top_k(candidates, scorer, "query", 3) == ["a", "z", "m"]


def test_csv_schema_contains_only_safe_record_metadata():
    query = "SYNTHETIC_QUERY_DO_NOT_EMIT"
    text = "SYNTHETIC_CANDIDATE_DO_NOT_EMIT"
    synthetic_secret = "SYNTHETIC_SECRET_DO_NOT_EMIT"
    client = FakeClient(error=RuntimeError(synthetic_secret))
    scorer = make_scorer(client)
    with pytest.raises(JevProviderError):
        scorer.score(query, text)
    assert scorer.last_record is not None

    rendered = render_benchmark_csv([scorer.last_record])
    rows = list(csv.DictReader(io.StringIO(rendered)))
    assert len(rows) == 1
    assert "query" not in rows[0]
    assert "text" not in rows[0]
    for sensitive in (query, text, synthetic_secret):
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
