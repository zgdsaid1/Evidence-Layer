"""Transport-free, deterministic local ``retrieve_evidence`` tool adapter.

This module wraps ``evidence_layer.retrieval.local_corpus.LocalCorpusRetriever``
behind a strict, JSON-safe, read-only function boundary. It is *not* an MCP
server and performs no network, provider, database, or filesystem-write I/O.

Inputs are typed as ``object`` on purpose so runtime validation can reject
wrongly-typed or non-JSON-safe values safely before any core work happens.
"""

from __future__ import annotations

from evidence_layer.retrieval.local_corpus import LocalCorpusRetriever

_TOP_K_MIN = 1
_TOP_K_MAX = 20
_BUDGET_WORDS_MIN = 1
_BUDGET_WORDS_MAX = 20000


def _error(code: str, message: str) -> dict[str, object]:
    return {"error": {"code": code, "message": message}}


def _validate_query(query: object) -> str | None:
    if not isinstance(query, str):
        return None
    stripped = query.strip()
    if not stripped:
        return None
    return stripped


def _validate_int(value: object, minimum: int, maximum: int) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    if value < minimum or value > maximum:
        return None
    return value


def retrieve_evidence(
    query: object,
    top_k: object = 5,
    budget_words: object = 500,
) -> dict[str, object]:
    """Retrieve ranked, budgeted local evidence for ``query``.

    Returns a JSON-compatible dict on success, or a structured error dict on
    validation, corpus, or unexpected failure. Deterministic and read-only.
    """
    stripped_query = _validate_query(query)
    if stripped_query is None:
        return _error("invalid_argument", "query must be a non-empty string")

    validated_top_k = _validate_int(top_k, _TOP_K_MIN, _TOP_K_MAX)
    if validated_top_k is None:
        return _error("invalid_argument", "top_k must be an integer between 1 and 20")

    validated_budget = _validate_int(
        budget_words, _BUDGET_WORDS_MIN, _BUDGET_WORDS_MAX
    )
    if validated_budget is None:
        return _error(
            "invalid_argument", "budget_words must be an integer between 1 and 20000"
        )

    try:
        retriever = LocalCorpusRetriever()
    except (ValueError, OSError):
        return _error("corpus_unavailable", "local corpus is unavailable")
    except Exception:
        return _error("internal_error", "retrieve_evidence failed")

    try:
        result = retriever.retrieve(
            stripped_query,
            top_k=validated_top_k,
            budget_words=validated_budget,
        )
    except Exception:
        return _error("internal_error", "retrieve_evidence failed")

    return {
        "status": result.status,
        "query": result.query,
        "top_k": result.top_k,
        "budget_words": result.budget_words,
        "evidence": [
            {
                "evidence_id": evidence.evidence_id,
                "text": evidence.text,
                "source_id": evidence.source_id,
                "source_url": evidence.source_url,
                "section": evidence.section,
                "score": evidence.score,
                "word_count": evidence.word_count,
            }
            for evidence in result.evidence
        ],
        "candidate_count": result.candidate_count,
        "used_words": result.used_words,
    }
