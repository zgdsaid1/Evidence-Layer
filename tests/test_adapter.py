"""Unit tests for the adapter interface and the no-op documentation adapter."""

from evidence_layer.adapters import DocumentationRAGAdapter
from evidence_layer.schemas import (
    EvidenceCandidate,
    Policy,
    Task,
)


def _candidate(cid: str, text: str) -> EvidenceCandidate:
    return EvidenceCandidate(candidate_id=cid, source_id="s", source_url="https://x/doc", text=text)


def test_normalize_task_from_mapping():
    adapter = DocumentationRAGAdapter()
    task = adapter.normalize_task({"task_id": "t1", "input": "what is WAL?", "domain": "x"})
    assert isinstance(task, Task)
    assert task.task_id == "t1"
    assert task.task_type == "knowledge_query"
    assert task.language == "en"


def test_normalize_task_passthrough():
    adapter = DocumentationRAGAdapter()
    task = Task(task_id="t1", task_type="research", domain="docs", input="q")
    assert adapter.normalize_task(task) is task


def test_normalize_candidates_from_mappings():
    adapter = DocumentationRAGAdapter()
    candidates = adapter.normalize_candidates(
        [{"candidate_id": "c1", "source_url": "https://x/doc", "text": "hello"}]
    )
    assert len(candidates) == 1
    assert candidates[0].candidate_id == "c1"


def test_apply_policy_selects_within_budget():
    adapter = DocumentationRAGAdapter()
    task = Task(task_id="t1", task_type="knowledge_query", domain="docs", input="q")
    candidates = [
        _candidate("c1", "one two three"),        # 3 tokens
        _candidate("c2", " ".join("w" for _ in range(50))),  # 50 tokens
        _candidate("c3", " ".join("w" for _ in range(50))),  # 50 tokens
    ]
    policy = Policy(context_budget_tokens=60, min_evidence=1, max_evidence=3)
    result = adapter.apply_policy(task, candidates, policy)

    assert result.selected_candidate_ids == ["c1", "c2"]
    assert result.rejected_candidate_ids == ["c3"]
    assert result.decision == "answer_with_context"
    assert result.context_tokens_before == 103
    assert result.context_tokens_after == 53


def test_apply_policy_insufficient_evidence():
    adapter = DocumentationRAGAdapter()
    task = Task(task_id="t1", task_type="knowledge_query", domain="docs", input="q")
    candidates = [_candidate("c1", "just one word")]
    policy = Policy(context_budget_tokens=100, min_evidence=2, max_evidence=5)
    result = adapter.apply_policy(task, candidates, policy)

    assert result.decision == "insufficient_evidence"
    assert "below_min_evidence" in result.reason_codes


def test_interpret_result():
    adapter = DocumentationRAGAdapter()
    task = Task(task_id="t1", task_type="knowledge_query", domain="docs", input="q")
    result = adapter.apply_policy(
        task,
        [_candidate("c1", "hello world")],
        Policy(context_budget_tokens=10, min_evidence=1, max_evidence=2),
    )
    interpretation = adapter.interpret_result(result)
    assert interpretation["decision"] == "answer_with_context"
    assert interpretation["selected_count"] == 1
