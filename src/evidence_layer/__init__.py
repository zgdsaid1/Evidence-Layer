"""Evidence Layer.

A provider-agnostic evidence-selection and context-reduction layer between an
AI agent, its retrieval/RAG system, and a large language model.

The default core is local: domain-agnostic data schemas, an adapter interface,
a no-op documentation-RAG adapter, a lexical scorer, top-k selection, and an
evaluation harness over a dataset built from public PostgreSQL documentation.
It makes no network calls. An optional Jev scorer/benchmark integration exists
(requires the optional extra and an API key, and may call an external paid API,
including usage/cost recording); no reranker, connector, or batched Jev scorer
is implemented.
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
