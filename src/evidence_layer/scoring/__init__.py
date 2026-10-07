"""Scoring package for ranking candidate evidence against a query.

This package holds provider-agnostic scorer interfaces and local, deterministic
implementations. A future scorer can wrap Jev, a reranker, or any other
provider behind the same ``Scorer.score(query, text)`` contract.
"""

from evidence_layer.scoring.base import Scorer
from evidence_layer.scoring.jev import JevEvidenceScorer
from evidence_layer.scoring.lexical import LexicalNoStopwordScorer, LexicalScorer

__all__ = [
    "Scorer",
    "LexicalScorer",
    "LexicalNoStopwordScorer",
    "JevEvidenceScorer",
]
