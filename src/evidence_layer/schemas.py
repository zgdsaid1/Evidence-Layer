"""Domain-agnostic Pydantic v2 schemas for the Evidence Layer.

These schemas are intentionally provider-agnostic: they do not reference any
specific model vendor, vector database, or retriever. Domains (support tickets,
coding, compliance, contracts, knowledge search, research, ...) are expressed
through ``Task.task_type`` and ``Task.domain`` and through adapters.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

#: Allowed ``task_type`` values. ``custom`` is the escape hatch for domains not
#: yet covered by the explicit enumerations.
TaskType = Literal[
    "support_ticket",
    "coding_task",
    "compliance_check",
    "contract_review",
    "knowledge_query",
    "research",
    "custom",
]

#: Allowed final decisions produced by an evidence-selection policy.
Decision = Literal[
    "answer_with_context",
    "abstain",
    "escalate_for_review",
    "insufficient_evidence",
]

#: Evaluation dataset case types (the target distribution for Phase 1).
CaseType = Literal[
    "direct_factual",
    "multi_source",
    "false_premise",
    "ambiguous",
    "prompt_injection",
]


class Task(BaseModel):
    """A unit of work an agent is trying to complete."""

    model_config = ConfigDict(extra="forbid")

    task_id: str
    task_type: TaskType
    domain: str
    input: str
    language: str = "en"
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvidenceCandidate(BaseModel):
    """A single retrieved passage that may (or may not) be relevant evidence."""

    model_config = ConfigDict(extra="forbid")

    candidate_id: str
    source_id: str
    source_url: str
    text: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class Policy(BaseModel):
    """Constraints the selection step must respect."""

    model_config = ConfigDict(extra="forbid")

    context_budget_tokens: int = Field(gt=0)
    min_evidence: int = Field(ge=0)
    max_evidence: int = Field(ge=1)
    languages: list[str] = Field(default_factory=lambda: ["en"])
    abstain_when_uncertain: bool = True
    policy_version: str = "1.0"

    @model_validator(mode="after")
    def _validate_bounds(self) -> "Policy":
        if self.min_evidence > self.max_evidence:
            raise ValueError("min_evidence must be less than or equal to max_evidence")
        return self


class EvidenceSelectionRequest(BaseModel):
    """A full request: a task plus the candidate evidence to select from."""

    model_config = ConfigDict(extra="forbid")

    request_id: str
    task: Task
    candidates: list[EvidenceCandidate] = Field(default_factory=list)
    policy: Policy


class EvidenceSelectionResult(BaseModel):
    """The output of the evidence-selection step."""

    model_config = ConfigDict(extra="forbid")

    request_id: str
    task_id: str
    selected_candidate_ids: list[str] = Field(default_factory=list)
    rejected_candidate_ids: list[str] = Field(default_factory=list)
    decision: Decision
    reason_codes: list[str] = Field(default_factory=list)
    context_tokens_before: int = Field(ge=0)
    context_tokens_after: int = Field(ge=0)
    policy_version: str


class EvaluationCase(BaseModel):
    """A single evaluation example.

    ``candidates`` is the full retrieved set the selector sees. ``gold_candidate_ids``
    is the subset that a correct selection must include. ``untrusted_candidate_ids``
    marks candidates whose content is injected / untrusted and must never be
    selected (used by the prompt-injection case type).
    """

    model_config = ConfigDict(extra="forbid")

    case_id: str
    case_type: CaseType
    task: Task
    candidates: list[EvidenceCandidate]
    gold_candidate_ids: list[str]
    required_facts: list[str]
    source_urls: list[str]
    untrusted_candidate_ids: list[str] = Field(default_factory=list)
