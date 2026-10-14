"""Local retrieval over sources opened by a source-read boundary.

Construction is metadata-only and never opens or parses corpus content. A read
requires an explicit request context and a boundary that authorizes the whole
source scope before opening any source. The default boundary denies all reads;
Phase 1 has no trusted host, source catalog, ACL, or unprotected-corpus
classification. OS file permissions alone are not tenant isolation.

Local lexical scoring runs only after a source read has been authorized. A
source-read denial is an error and never falls through to lexical ranking.
Provider-transfer authorization remains a separate policy decision.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone

from evidence_layer.schemas import EvidenceCandidate
from evidence_layer.scoring.lexical import LexicalScorer
from evidence_layer.scoring.policy import ProviderSelectionPolicy, ScoringOutcome
from evidence_layer.selection import select_top_k_scored
from evidence_layer.source_access import (
    AuthorizedSourceReader,
    DenyAllSourceReadBoundary,
    SourceReadDenial,
    SourceReadDenialReason,
    SourceReadError,
    SourceReadIntent,
    SourceReadLease,
    SourceRequestContext,
    context_is_expired,
)

STATUS_OK = "ok"
STATUS_NO_RESULTS = "no_results"
STATUS_BUDGET_EXHAUSTED = "budget_exhausted"


def _require_positive_int(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer, got {type(value).__name__}")
    if value < 1:
        raise ValueError(f"{name} must be >= 1, got {value}")
    return value


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
    """Outcome of one authorized retrieval."""

    status: str
    query: str
    top_k: int
    budget_words: int
    evidence: list[LocalEvidence] = field(default_factory=list)
    candidate_count: int = 0
    used_words: int = 0
    scoring_provider: str = "lexical"
    scoring_failure_category: str | None = None


class LocalCorpusRetriever:
    """Retrieve evidence from source IDs through a default-deny read boundary.

    ``source_ids`` are identifiers only; they are not permission or storage
    locations. Phase 1 does not accept an injected boundary: it always uses the
    built-in deny-all implementation. A future trusted-host phase must change
    this composition after implementing provenance validation. No filesystem
    path or caller-supplied authorizer is accepted by this API.
    """

    def __init__(
        self,
        source_ids: Sequence[str] = (),
        *,
        scoring_policy: ProviderSelectionPolicy | None = None,
    ) -> None:
        if not isinstance(source_ids, Sequence) or isinstance(
            source_ids, (str, bytes)
        ):
            raise TypeError("source_ids must be a sequence of source identifiers")
        normalized_source_ids = tuple(source_ids)
        if any(
            not isinstance(source_id, str) or not source_id
            for source_id in normalized_source_ids
        ):
            raise ValueError("source_ids must contain non-empty identifiers")
        if len(set(normalized_source_ids)) != len(normalized_source_ids):
            raise ValueError("source_ids must be unique")
        if (
            scoring_policy is not None
            and type(scoring_policy) is not ProviderSelectionPolicy
        ):
            raise TypeError("scoring_policy must be a built-in ProviderSelectionPolicy")

        # This stores only identifiers and dependencies. It deliberately does
        # not resolve storage or open, read, or parse content during construction.
        self._source_ids = normalized_source_ids
        self._scoring_policy = (
            scoring_policy if scoring_policy is not None else ProviderSelectionPolicy()
        )
        self._retrieval_scorer = LexicalScorer()

    def _read_authorized_records(
        self, context: SourceRequestContext | None
    ) -> dict[str, dict[str, object]]:
        now = datetime.now(timezone.utc)
        if context is None:
            raise SourceReadError(
                SourceReadDenial(SourceReadDenialReason.MISSING_CONTEXT)
            )
        if type(context) is not SourceRequestContext:
            raise SourceReadError(
                SourceReadDenial(SourceReadDenialReason.SCOPE_MISMATCH)
            )
        if not all(
            isinstance(value, str) and value
            for value in (
                context.request_id,
                context.operation_id,
                context.principal_id,
                context.tenant_id,
                context.policy_version,
            )
        ) or not isinstance(context.expires_at, datetime):
            raise SourceReadError(
                SourceReadDenial(SourceReadDenialReason.SCOPE_MISMATCH)
            )
        if context_is_expired(context, now=now):
            raise SourceReadError(SourceReadDenial(SourceReadDenialReason.EXPIRED))
        if not self._source_ids:
            raise SourceReadError(
                SourceReadDenial(SourceReadDenialReason.UNKNOWN_SOURCE)
            )

        intents = tuple(
            SourceReadIntent(source_id=source_id, operation="retrieve")
            for source_id in self._source_ids
        )
        try:
            opened = DenyAllSourceReadBoundary().open_sources(context, intents)
        except Exception:
            # Boundary exceptions may contain paths, content, or internal details.
            raise SourceReadError(
                SourceReadDenial(SourceReadDenialReason.STORAGE_FAILURE)
            ) from None
        if isinstance(opened, SourceReadDenial):
            raise SourceReadError(opened)
        if not isinstance(opened, tuple) or len(opened) != len(intents):
            self._close_readers(opened if isinstance(opened, tuple) else ())
            raise SourceReadError(
                SourceReadDenial(SourceReadDenialReason.SCOPE_MISMATCH)
            )

        readers = opened
        expected_by_id = {intent.source_id: intent for intent in intents}
        leases: list[SourceReadLease] = []
        for reader in readers:
            try:
                lease = getattr(reader, "lease", None)
            except Exception:
                self._close_readers(readers)
                raise SourceReadError(
                    SourceReadDenial(SourceReadDenialReason.SCOPE_MISMATCH)
                ) from None
            if not isinstance(lease, SourceReadLease):
                self._close_readers(readers)
                raise SourceReadError(
                    SourceReadDenial(SourceReadDenialReason.SCOPE_MISMATCH)
                )
            intent = expected_by_id.get(lease.source_id)
            if (
                intent is None
                or not all(
                    isinstance(value, str) and value
                    for value in (
                        lease.request_id,
                        lease.operation_id,
                        lease.principal_id,
                        lease.tenant_id,
                        lease.source_id,
                        lease.operation,
                    )
                )
                or lease.request_id != context.request_id
                or lease.operation_id != context.operation_id
                or lease.principal_id != context.principal_id
                or lease.tenant_id != context.tenant_id
                or lease.operation != intent.operation
                or not isinstance(lease.source_version, str)
                or not lease.source_version
                or not isinstance(lease.expires_at, datetime)
                or lease.expires_at.tzinfo is None
                or lease.expires_at <= now
                or (
                    intent.expected_version is not None
                    and lease.source_version != intent.expected_version
                )
            ):
                self._close_readers(readers)
                reason = (
                    SourceReadDenialReason.EXPIRED
                    if isinstance(lease, SourceReadLease)
                    and isinstance(lease.expires_at, datetime)
                    and lease.expires_at.tzinfo is not None
                    and lease.expires_at <= now
                    else SourceReadDenialReason.SCOPE_MISMATCH
                )
                raise SourceReadError(SourceReadDenial(reason))
            leases.append(lease)
        if {lease.source_id for lease in leases} != set(self._source_ids):
            self._close_readers(readers)
            raise SourceReadError(
                SourceReadDenial(SourceReadDenialReason.SCOPE_MISMATCH)
            )

        records: dict[str, dict[str, object]] = {}
        try:
            for reader, lease in zip(readers, leases):
                source_id = lease.source_id
                for raw_record in reader.iter_records():
                    if not isinstance(raw_record, Mapping):
                        raise SourceReadError(
                            SourceReadDenial(
                                SourceReadDenialReason.INVALID_SOURCE_DATA
                            )
                        )
                    record = dict(raw_record)
                    for key in ("passage_id", "source_id", "source_url", "text"):
                        if not isinstance(record.get(key), str) or not record[key]:
                            raise SourceReadError(
                                SourceReadDenial(
                                    SourceReadDenialReason.INVALID_SOURCE_DATA
                                )
                            )
                    if record["source_id"] != source_id:
                        raise SourceReadError(
                            SourceReadDenial(SourceReadDenialReason.SCOPE_MISMATCH)
                        )
                    passage_id = record["passage_id"]
                    if passage_id in records:
                        raise SourceReadError(
                            SourceReadDenial(
                                SourceReadDenialReason.INVALID_SOURCE_DATA
                            )
                        )
                    records[passage_id] = record
        except SourceReadError:
            raise
        except Exception:
            # Suppress storage/parser exception text and paths.
            raise SourceReadError(
                SourceReadDenial(SourceReadDenialReason.STORAGE_FAILURE)
            ) from None
        finally:
            self._close_readers(readers)
        return records

    @staticmethod
    def _close_readers(readers: Sequence[object]) -> None:
        for reader in readers:
            try:
                close = getattr(reader, "close", None)
                if callable(close):
                    close()
            except Exception:
                pass

    def _retrieve_candidates(
        self, query: str, records: Mapping[str, Mapping[str, object]]
    ) -> list[EvidenceCandidate]:
        query_tokens = set(self._retrieval_scorer.normalize(query))
        if not query_tokens:
            return []
        return [
            EvidenceCandidate(
                candidate_id=str(record["passage_id"]),
                source_id=str(record["source_id"]),
                source_url=str(record["source_url"]),
                text=str(record["text"]),
            )
            for record in records.values()
            if query_tokens & set(self._retrieval_scorer.normalize(str(record["text"])))
        ]

    def _rank(
        self, candidates: list[EvidenceCandidate], query: str
    ) -> tuple[list[str], dict[str, float], ScoringOutcome]:
        outcome = self._scoring_policy.score_candidates(query, candidates)
        ranked_ids = (
            select_top_k_scored(candidates, outcome.scores, len(candidates) or 1)
            if candidates
            else []
        )
        scores_by_id = {
            candidate.candidate_id: score
            for candidate, score in zip(candidates, outcome.scores)
        }
        return ranked_ids, scores_by_id, outcome

    def _apply_budget(
        self,
        ranked_ids: list[str],
        scores_by_id: dict[str, float],
        records: Mapping[str, Mapping[str, object]],
        top_k: int,
        budget_words: int,
    ) -> list[LocalEvidence]:
        selected: list[LocalEvidence] = []
        remaining = budget_words
        for passage_id in ranked_ids:
            if len(selected) >= top_k:
                break
            record = records[passage_id]
            text = str(record["text"])
            words = len(text.split())
            if words == 0 or words > remaining:
                continue
            remaining -= words
            selected.append(
                LocalEvidence(
                    evidence_id=passage_id,
                    text=text,
                    source_id=str(record["source_id"]),
                    source_url=str(record["source_url"]),
                    section=(
                        str(record["section"])
                        if record.get("section") is not None
                        else None
                    ),
                    score=scores_by_id[passage_id],
                    word_count=words,
                )
            )
        return selected

    def retrieve(
        self,
        query: str,
        *,
        request_context: SourceRequestContext | None = None,
        top_k: int = 5,
        budget_words: int = 500,
    ) -> LocalRetrievalResult:
        if not isinstance(query, str):
            raise TypeError(f"query must be a string, got {type(query).__name__}")
        query = query.strip()
        if not query:
            raise ValueError("query must not be empty")
        _require_positive_int("top_k", top_k)
        _require_positive_int("budget_words", budget_words)

        # No lexical fallback is permitted on source-read denial. Content is
        # available to ranking only after the boundary returns scoped readers.
        records = self._read_authorized_records(request_context)
        candidates = self._retrieve_candidates(query, records)
        ranked_ids, scores_by_id, scoring_outcome = self._rank(candidates, query)
        evidence = self._apply_budget(
            ranked_ids, scores_by_id, records, top_k, budget_words
        )

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
            scoring_provider=scoring_outcome.provider,
            scoring_failure_category=(
                scoring_outcome.fallback_reason.category
                if scoring_outcome.fallback_reason is not None
                else None
            ),
        )
