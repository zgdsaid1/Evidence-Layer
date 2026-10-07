"""Provider-agnostic scorer interface.

The interface is intentionally tiny so that a local lexical scorer, Jev, a
cross-encoder reranker, or any other provider can be swapped in later without
changing the selection or evaluation code.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class Scorer(ABC):
    """Assigns a relevance score to a passage for a given query.

    Higher scores mean "more relevant". Local scorers (such as the lexical
    baselines) are expected to be deterministic and side-effect free for a given
    input. Provider-backed scorers may perform network I/O and keep non-sensitive
    operational metadata (for example the last request record); their scores are
    not guaranteed to be reproducible, so callers must not assume determinism
    unless the concrete scorer documents it.
    """

    #: Human-readable name used in reports.
    name: str = "scorer"

    @abstractmethod
    def score(self, query: str, text: str) -> float:
        """Return a relevance score for ``text`` given ``query``."""
