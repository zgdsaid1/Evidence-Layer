"""Unit tests for the domain-agnostic Pydantic schemas."""

import pytest
from pydantic import ValidationError

from evidence_layer.schemas import (
    EvidenceCandidate,
    EvidenceSelectionRequest,
    EvidenceSelectionResult,
    EvaluationCase,
    Policy,
    Task,
)


def test_task_valid_defaults():
    task = Task(task_id="t1", task_type="knowledge_query", domain="docs", input="What is WAL?")
    assert task.language == "en"
    assert task.metadata == {}


def test_task_invalid_task_type_rejected():
    with pytest.raises(ValidationError):
        Task(task_id="t1", task_type="not_a_type", domain="docs", input="x")


def test_task_extra_field_rejected():
    with pytest.raises(ValidationError):
        Task(task_id="t1", task_type="custom", domain="d", input="x", bogus=1)


def test_policy_valid():
    policy = Policy(context_budget_tokens=1000, min_evidence=1, max_evidence=5)
    assert policy.languages == ["en"]
    assert policy.policy_version == "1.0"


def test_policy_min_greater_than_max_rejected():
    with pytest.raises(ValidationError):
        Policy(context_budget_tokens=1000, min_evidence=5, max_evidence=1)


def test_policy_zero_budget_rejected():
    with pytest.raises(ValidationError):
        Policy(context_budget_tokens=0, min_evidence=0, max_evidence=1)


def test_selection_request_and_result_roundtrip():
    candidate = EvidenceCandidate(
        candidate_id="c1",
        source_id="src",
        source_url="https://example.com/doc",
        text="Some evidence text.",
    )
    request = EvidenceSelectionRequest(
        request_id="r1",
        task=Task(task_id="t1", task_type="research", domain="docs", input="q"),
        candidates=[candidate],
        policy=Policy(context_budget_tokens=100, min_evidence=1, max_evidence=2),
    )
    result = EvidenceSelectionResult(
        request_id="r1",
        task_id="t1",
        selected_candidate_ids=["c1"],
        rejected_candidate_ids=[],
        decision="answer_with_context",
        reason_codes=["within_budget"],
        context_tokens_before=3,
        context_tokens_after=3,
        policy_version="1.0",
    )
    assert result.decision == "answer_with_context"


def test_evaluation_case_valid():
    case = EvaluationCase(
        case_id="case_0000",
        case_type="direct_factual",
        task=Task(task_id="task_0000", task_type="knowledge_query", domain="docs", input="q"),
        candidates=[
            EvidenceCandidate(
                candidate_id="p1",
                source_id="src",
                source_url="https://example.com/doc",
                text="passage",
            )
        ],
        gold_candidate_ids=["p1"],
        required_facts=["a fact"],
        source_urls=["https://example.com/doc"],
    )
    assert case.gold_candidate_ids == ["p1"]
