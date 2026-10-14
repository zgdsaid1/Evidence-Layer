"""Local retrieval APIs; the default source-read boundary denies content reads."""

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
