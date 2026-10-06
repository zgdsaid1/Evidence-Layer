"""Deterministic, fully-local lexical query-to-passage scorer.

This is a *lexical* baseline only. It measures word overlap, not meaning. It is
NOT semantic retrieval, Jev, a reranker, or an LLM, and it makes no network
calls (standard library only).

Normalization / tokenization / stopwords / formula
--------------------------------------------------

* **normalize**: lower-case the text.
* **tokenize**: extract runs of ASCII alphanumerics with ``[a-z0-9]+``.
* **stopwords**: a small fixed English stopword set is dropped from both the
  query and the passage before scoring.
* **score** (cosine similarity of raw term-frequency vectors)::

      score = sum_t tf_q(t) * tf_p(t)
              -------------------------------------------
              sqrt(sum_t tf_q(t)^2) * sqrt(sum_t tf_p(t)^2)

  where ``tf_x(t)`` is the raw count of token ``t`` in side ``x``. If either
  side normalizes to an empty token list (all stopwords or no alphanumerics),
  or if the vectors have zero overlap or zero norm, the score is ``0.0``.

For a fixed input the result is deterministic.
"""

from __future__ import annotations

import re
from collections import Counter
from math import sqrt

from evidence_layer.scoring.base import Scorer

DEFAULT_TOKEN_PATTERN = r"[a-z0-9]+"

# Small, fixed English stopword list. Kept intentionally modest; it only
# removes function words so that content words drive the overlap signal.
STOPWORDS = frozenset(
    {
        "a", "an", "and", "are", "as", "at", "be", "been", "but", "by",
        "can", "could", "did", "do", "does", "for", "from", "had", "has",
        "have", "he", "her", "his", "how", "i", "if", "in", "into", "is",
        "it", "its", "of", "on", "or", "our", "out", "over", "she",
        "should", "so", "than", "that", "the", "their", "them", "then",
        "there", "these", "they", "this", "to", "too", "under", "up",
        "was", "we", "were", "what", "when", "where", "which", "who",
        "why", "will", "with", "without", "would", "you", "your",
    }
)


class LexicalScorer(Scorer):
    """Cosine-similarity lexical scorer over stopword-filtered term frequencies.

    This is the named baseline ``lexical_stopword_filtered``.
    """

    name = "lexical_stopword_filtered"

    def __init__(
        self,
        stopwords: frozenset | set = STOPWORDS,
        token_pattern: str = DEFAULT_TOKEN_PATTERN,
    ) -> None:
        self._stopwords = frozenset(stopwords)
        self._token_pattern = token_pattern

    def normalize(self, text: str) -> list[str]:
        """Lower-case, tokenize, and drop stopwords."""
        return [
            token
            for token in re.findall(self._token_pattern, text.lower())
            if token not in self._stopwords
        ]

    def score(self, query: str, text: str) -> float:
        query_counts = Counter(self.normalize(query))
        text_counts = Counter(self.normalize(text))

        if not query_counts or not text_counts:
            return 0.0

        dot = sum(count * text_counts[token] for token, count in query_counts.items())
        if dot == 0.0:
            return 0.0

        norm_query = sqrt(sum(c * c for c in query_counts.values()))
        norm_text = sqrt(sum(c * c for c in text_counts.values()))
        if norm_query == 0.0 or norm_text == 0.0:
            return 0.0

        return dot / (norm_query * norm_text)


class LexicalNoStopwordScorer(LexicalScorer):
    """Same tokenization and cosine formula as ``LexicalScorer``, but retains
    stopwords (``stopwords=frozenset()``).

    This is a sensitivity-analysis comparison variant only. It is NOT the
    default baseline and is never selected automatically.
    """

    name = "lexical_no_stopword_filter"

    def __init__(self, token_pattern: str = DEFAULT_TOKEN_PATTERN) -> None:
        super().__init__(stopwords=frozenset(), token_pattern=token_pattern)

