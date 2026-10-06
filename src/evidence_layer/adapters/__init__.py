"""Adapter layer for future domains.

Each domain adapter normalizes raw inputs into the domain-agnostic schemas,
applies a selection policy, and interprets results. Phase 1 ships a single
no-op ``DocumentationRAGAdapter``.
"""

from evidence_layer.adapters.base import EvidenceAdapter
from evidence_layer.adapters.documentation_rag import DocumentationRAGAdapter

__all__ = ["EvidenceAdapter", "DocumentationRAGAdapter"]
