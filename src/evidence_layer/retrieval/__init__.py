"""Local retrieval APIs with default-deny reads and one explicit synthetic fixture.

The fixture helper is for development/testing only and is not used by standard
MCP or the health-only HTTP service.
"""

from evidence_layer.retrieval.local_corpus import (
    LocalCorpusRetriever,
    LocalEvidence,
    LocalRetrievalResult,
)

__all__ = [
    "LocalCorpusRetriever",
    "LocalEvidence",
    "LocalRetrievalResult",
]
