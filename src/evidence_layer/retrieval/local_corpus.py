"""Local, lexical-first retrieval over a JSONL passage corpus.

Pipeline (each stage is a separate method):

1. **Retrieval** (``_retrieve_candidates``): keep only corpus records that share
   at least one normalized (stopword-filtered) token with the query. Loading the
   corpus is not retrieval; records without lexical overlap are never candidates.
2. **Ranking** (``_rank``): order the candidates with the existing
   ``select_top_k`` and ``LexicalScorer`` (unchanged).
3. **Budget filtering** (``_apply_budget``): walk the ranked list, keep evidence
   that fits the remaining ``budget_words``, skip ones that do not, and stop at
   ``top_k``.

``budget_words`` counts ``text.split()`` words of the selected evidence only. It
is an estimate, not a token count. This is a local reader only: no network, not a
production connector, and not an MCP server.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from evidence_layer.schemas import EvidenceCandidate
from evidence_layer.scoring.lexical import LexicalScorer
from evidence_layer.selection import select_top_k

DEFAULT_CORPUS_PATH = (
    Path(__file__).resolve().parents[3] / "data" / "corpus" / "postgresql_passages.jsonl"
)

STATUS_OK = "ok"
STATUS_NO_RESULTS = "no_results"
STATUS_BUDGET_EXHAUSTED = "budget_exhausted"


@dataclass(frozen=True)
class LocalEvidence:
    """One selected passage with the citation fields of its source record."""

    evidence_id: str
    text: str
    source_id: str
    source_url: str
    section: str | None
    score: float
    word_count: int


@dataclass(frozen=True)
class LocalRetrievalResult:
    """Outcome of one retrieval. ``status`` is ok, no_results or budget_exhausted."""

    status: str
    query: str
    top_k: int
    budget_words: int
    evidence: list[LocalEvidence] = field(default_factory=list)
    candidate_count: int = 0
    used_words: int = 0


def _require_positive_int(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer, got {type(value).__name__}")
    if value < 1:
        raise ValueError(f"{name} must be >= 1, got {value}")
    return value


class LocalCorpusRetriever:
    """Retrieve ranked, budgeted evidence from a local JSONL corpus."""

    def __init__(self, corpus_path: Path | str = DEFAULT_CORPUS_PATH) -> None:
        self._scorer = LexicalScorer()
        self._records = self._load(Path(corpus_path))

    @staticmethod
    def _load(path: Path) -> dict[str, dict]:
        records: dict[str, dict] = {}
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path.name}:{lineno}: invalid JSON") from exc
            for key in ("passage_id", "source_id", "source_url", "text"):
                if not isinstance(rec.get(key), str) or not rec[key]:
                    raise ValueError(f"{path.name}:{lineno}: missing or invalid '{key}'")
            if rec["passage_id"] in records:
                raise ValueError(f"{path.name}:{lineno}: duplicate passage_id")
            records[rec["passage_id"]] = rec
        return records

    def _retrieve_candidates(self, query: str) -> list[EvidenceCandidate]:
        query_tokens = set(self._scorer.normalize(query))
        if not query_tokens:
            return []
        return [
            EvidenceCandidate(
                candidate_id=rec["passage_id"],
                source_id=rec["source_id"],
                source_url=rec["source_url"],
                text=rec["text"],
            )
            for rec in self._records.values()
            if query_tokens & set(self._scorer.normalize(rec["text"]))
        ]

    def _rank(self, candidates: list[EvidenceCandidate], query: str) -> list[str]:
        if not candidates:
            return []
        return select_top_k(candidates, self._scorer, query, len(candidates))

    def _apply_budget(
        self, ranked_ids: list[str], query: str, top_k: int, budget_words: int
    ) -> list[LocalEvidence]:
        selected: list[LocalEvidence] = []
        remaining = budget_words
        for passage_id in ranked_ids:
            if len(selected) >= top_k:
                break
            rec = self._records[passage_id]
            words = len(rec["text"].split())
            if words == 0 or words > remaining:
                continue
            remaining -= words
            selected.append(
                LocalEvidence(
                    evidence_id=passage_id,
                    text=rec["text"],
                    source_id=rec["source_id"],
                    source_url=rec["source_url"],
                    section=rec.get("section"),
                    score=self._scorer.score(query, rec["text"]),
                    word_count=words,
                )
            )
        return selected

    def retrieve(
        self, query: str, *, top_k: int = 5, budget_words: int = 500
    ) -> LocalRetrievalResult:
        if not isinstance(query, str):
            raise TypeError(f"query must be a string, got {type(query).__name__}")
        query = query.strip()
        if not query:
            raise ValueError("query must not be empty")
        _require_positive_int("top_k", top_k)
        _require_positive_int("budget_words", budget_words)

        candidates = self._retrieve_candidates(query)
        ranked_ids = self._rank(candidates, query)
        evidence = self._apply_budget(ranked_ids, query, top_k, budget_words)

        if evidence:
            status = STATUS_OK
        elif candidates:
            status = STATUS_BUDGET_EXHAUSTED
        else:
            status = STATUS_NO_RESULTS
        return LocalRetrievalResult(
            status=status,
            query=query,
            top_k=top_k,
            budget_words=budget_words,
            evidence=evidence,
            candidate_count=len(candidates),
            used_words=sum(e.word_count for e in evidence),
        )
