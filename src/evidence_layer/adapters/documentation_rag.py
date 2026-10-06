"""No-op adapter for technical-documentation / RAG evidence.

This adapter is the *baseline* for the Phase 1 evaluation dataset. It performs
only trivial, deterministic operations:

* normalizes raw documentation passages into :class:`EvidenceCandidate`;
* applies a greedy "first-N within budget" policy.

It does **not** implement Jev, reranking, LLM calls, connectors, or cost
calculation. Its output is used to sanity-check the pipeline, not to claim
quality.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from evidence_layer.adapters.base import EvidenceAdapter
from evidence_layer.schemas import (
    EvidenceCandidate,
    EvidenceSelectionResult,
    Policy,
    Task,
)

_TASK_TYPES = {
    "support_ticket",
    "coding_task",
    "compliance_check",
    "contract_review",
    "knowledge_query",
    "research",
    "custom",
}


def estimate_tokens(text: str) -> int:
    """A deliberately naive token estimate (whitespace-split word count).

    This is *not* a real tokenizer and must not be used as one. It exists only
    so the no-op adapter can compare against ``context_budget_tokens`` without
    calling any model or tokenizer.
    """
    return max(1, len(text.split()))


class DocumentationRAGAdapter(EvidenceAdapter):
    """No-op adapter for the technical-documentation domain."""

    domain = "technical_documentation"

    def normalize_task(self, raw: Any) -> Task:
        if isinstance(raw, Task):
            return raw
        if not isinstance(raw, Mapping):
            raise TypeError("raw task must be a mapping or a Task")

        task_type = raw.get("task_type", "knowledge_query")
        if task_type not in _TASK_TYPES:
            task_type = "custom"

        return Task(
            task_id=str(raw["task_id"]),
            task_type=task_type,
            domain=str(raw.get("domain", self.domain)),
            input=str(raw["input"]),
            language=str(raw.get("language", "en")),
            metadata=dict(raw.get("metadata", {}) or {}),
        )

    def normalize_candidates(self, raw: Any) -> list[EvidenceCandidate]:
        if raw is None:
            return []
        if isinstance(raw, EvidenceCandidate):
            return [raw]
        if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
            raise TypeError("raw candidates must be a sequence")

        normalized: list[EvidenceCandidate] = []
        for item in raw:
            if isinstance(item, EvidenceCandidate):
                normalized.append(item)
                continue
            if not isinstance(item, Mapping):
                raise TypeError("each candidate must be a mapping or EvidenceCandidate")
            normalized.append(
                EvidenceCandidate(
                    candidate_id=str(item["candidate_id"]),
                    source_id=str(item.get("source_id", "unknown")),
                    source_url=str(item.get("source_url", "")),
                    text=str(item["text"]),
                    metadata=dict(item.get("metadata", {}) or {}),
                )
            )
        return normalized

    def apply_policy(
        self,
        task: Task,
        candidates: list[EvidenceCandidate],
        policy: Policy,
    ) -> EvidenceSelectionResult:
        # Greedy baseline: keep candidates in retrieval order until the token
        # budget or max_evidence is reached. No scoring, no reranking, no LLM.
        selected: list[str] = []
        rejected: list[str] = []
        used = 0

        for candidate in candidates:
            tokens = estimate_tokens(candidate.text)
            if len(selected) < policy.max_evidence and used + tokens <= policy.context_budget_tokens:
                selected.append(candidate.candidate_id)
                used += tokens
            else:
                rejected.append(candidate.candidate_id)

        tokens_before = sum(estimate_tokens(c.text) for c in candidates)

        if len(selected) < policy.min_evidence:
            decision = "insufficient_evidence"
            reason_codes = ["below_min_evidence"]
        else:
            decision = "answer_with_context"
            reason_codes = ["within_budget"]

        return EvidenceSelectionResult(
            request_id=f"req-{task.task_id}",
            task_id=task.task_id,
            selected_candidate_ids=selected,
            rejected_candidate_ids=rejected,
            decision=decision,
            reason_codes=reason_codes,
            context_tokens_before=tokens_before,
            context_tokens_after=used,
            policy_version=policy.policy_version,
        )

    def interpret_result(self, result: EvidenceSelectionResult) -> dict[str, Any]:
        return {
            "decision": result.decision,
            "selected_count": len(result.selected_candidate_ids),
            "rejected_count": len(result.rejected_candidate_ids),
            "tokens_before": result.context_tokens_before,
            "tokens_after": result.context_tokens_after,
            "reason_codes": result.reason_codes,
        }
