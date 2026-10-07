"""Evidence Layer.

A provider-agnostic evidence-selection and context-reduction layer between an
AI agent, its retrieval/RAG system, and a large language model.

Phase 1 contains only the domain-agnostic data schemas, an adapter interface,
one no-op documentation-RAG adapter, and an evaluation dataset built from public
PostgreSQL documentation. It intentionally does NOT implement any Jev /
reranker / LLM calls / connectors / cost calculation.
"""

from evidence_layer.schemas import (
    EvidenceCandidate,
    EvidenceSelectionRequest,
    EvidenceSelectionResult,
    EvaluationCase,
    Policy,
    Task,
)

__all__ = [
    "EvidenceCandidate",
    "EvidenceSelectionRequest",
    "EvidenceSelectionResult",
    "EvaluationCase",
    "Policy",
    "Task",
]

__version__ = "0.1.0"
