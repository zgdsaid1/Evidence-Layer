"""Local retrieval over an authorized on-disk corpus."""

from evidence_layer.retrieval.local_corpus import (
    DEFAULT_CORPUS_PATH,
    LocalCorpusRetriever,
    LocalEvidence,
    LocalRetrievalResult,
)

__all__ = [
    "DEFAULT_CORPUS_PATH",
    "LocalCorpusRetriever",
    "LocalEvidence",
    "LocalRetrievalResult",
]
