"""Fail-closed provider selection with local lexical scoring by default.

Phase 1 defines and tests transfer-authorization seams, but has no trusted host
or grant issuer. Consequently this module never invokes a JEV scorer. A future
trusted-host change must replace the explicit Phase 1 denial and retain the
whole-candidate recomputation implemented by
``_lexical_recompute_after_provider_failure``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Sequence

from evidence_layer.authorization import (
    DenyAllTransferAuthorizer,
    RequestOperationContext,
    TransferAuthorizer,
    TransferDenial,
    TransferGrant,
    TransferIntent,
    grant_matches,
)
from evidence_layer.schemas import EvidenceCandidate
from evidence_layer.scoring.base import Scorer
from evidence_layer.scoring.lexical import LexicalNoStopwordScorer, LexicalScorer

ProviderName = Literal["lexical", "jev"]
FailureCategory = Literal[
    "configuration_error",
    "dependency_missing",
    "provider_failure",
    "invalid_response",
    "transfer_denied",
    "transfer_disabled",
    "invalid_authorization",
]


def _validate_policy_flag(name: str, value: bool) -> None:
    if not isinstance(value, bool):
        raise TypeError(f"{name} must be a boolean")


@dataclass(frozen=True)
class ProviderFailure:
    """Sanitized reason a requested provider was not used successfully."""

    category: FailureCategory


@dataclass(frozen=True)
class ScoringOutcome:
    """Scores and safe provider metadata for one complete request."""

    scores: tuple[float, ...]
    provider: ProviderName
    fallback_reason: ProviderFailure | None = None


def _lexical_recompute_after_provider_failure(
    query: str,
    texts: Sequence[str],
    lexical_scorer: Scorer,
    category: FailureCategory,
) -> ScoringOutcome:
    """Recompute the entire operation locally after a provider-side failure.

    This helper performs no provider calls. Phase 1 has no enabled provider
    orchestration; a later approved host may call this after its guarded JEV
    operation fails, discarding every partial provider result.
    """
    return ScoringOutcome(
        scores=tuple(lexical_scorer.score(query, text) for text in texts),
        provider="lexical",
        fallback_reason=ProviderFailure(category=category),
    )


class ProviderSelectionPolicy:
    """Keep JEV disabled until a separately approved trusted host exists.

    The feature and plan flags remain configuration gates, not authorization.
    Even a caller-supplied grant or authorizer cannot enable the live JEV path
    in Phase 1. Local lexical scoring remains available.
    """

    def __init__(
        self,
        *,
        jev_enabled: bool = False,
        jev_permitted_by_request: bool = False,
        jev_permitted_by_plan: bool = False,
        jev_scorer: Scorer | None = None,
        lexical_scorer: Scorer | None = None,
        request_context: RequestOperationContext | None = None,
        transfer_authorizer: TransferAuthorizer | None = None,
    ) -> None:
        for name, value in (
            ("jev_enabled", jev_enabled),
            ("jev_permitted_by_request", jev_permitted_by_request),
            ("jev_permitted_by_plan", jev_permitted_by_plan),
        ):
            _validate_policy_flag(name, value)
        if transfer_authorizer is not None:
            raise ValueError(
                "custom transfer authorizers are disabled until a trusted host exists"
            )
        if lexical_scorer is not None and type(lexical_scorer) not in {
            LexicalScorer,
            LexicalNoStopwordScorer,
        }:
            raise TypeError("lexical_scorer must be a built-in local lexical scorer")

        # Retained scorer/context arguments preserve the configuration shape.
        # Injected scorers are deliberately not retained or invoked. Custom
        # authorizers are rejected above because there is no trusted host.
        self._jev_requested = (
            jev_enabled and jev_permitted_by_request and jev_permitted_by_plan
        )
        self._lexical = (
            lexical_scorer if lexical_scorer is not None else LexicalScorer()
        )
        self._request_context = request_context

    @property
    def jev_selected(self) -> bool:
        """Whether JEV is active in this Phase 1 build (always false)."""
        return False

    @property
    def default_provider(self) -> ProviderName:
        """The only provider selectable before trusted-host authorization exists."""
        return "lexical"

    def _lexical_outcome(
        self,
        query: str,
        texts: Sequence[str],
        reason: FailureCategory | None = None,
    ) -> ScoringOutcome:
        if reason is not None:
            return _lexical_recompute_after_provider_failure(
                query, texts, self._lexical, reason
            )
        return ScoringOutcome(
            scores=tuple(self._lexical.score(query, text) for text in texts),
            provider="lexical",
        )

    def score(self, query: str, texts: list[str]) -> ScoringOutcome:
        """Compatibility entry point; unscoped calls remain local and lexical."""
        if not texts or not self._jev_requested:
            return self._lexical_outcome(query, texts)
        # Text-only callers cannot present an exact source/candidate scope. Even
        # complete flags or injected objects cannot turn this into remote egress.
        return self._lexical_outcome(query, texts, "transfer_denied")

    def score_candidates(
        self,
        query: str,
        candidates: Sequence[EvidenceCandidate],
    ) -> ScoringOutcome:
        """Preflight one complete candidate scope, then deny live JEV in Phase 1.

        The caller must already have retrieved only locally accessible data.
        This library has no source ACL or tenant resolver; the local corpus path
        is not a tenant-isolation boundary.
        """
        texts = [candidate.text for candidate in candidates]
        if not texts or not self._jev_requested:
            return self._lexical_outcome(query, texts)

        context = self._request_context
        if context is None:
            return self._lexical_outcome(query, texts, "transfer_denied")

        source_ids = frozenset(candidate.source_id for candidate in candidates)
        candidate_ids = frozenset(candidate.candidate_id for candidate in candidates)
        if (
            len(candidate_ids) != len(candidates)
            or any(not candidate_id for candidate_id in candidate_ids)
            or any(not source_id for source_id in source_ids)
        ):
            return self._lexical_outcome(query, texts, "invalid_authorization")
        intent = TransferIntent(
            provider="jev",
            purpose="evidence_scoring",
            source_ids=source_ids,
            candidate_ids=candidate_ids,
            candidate_source_pairs=frozenset(
                (candidate.candidate_id, candidate.source_id)
                for candidate in candidates
            ),
            data_categories=frozenset({"query_text", "candidate_text"}),
        )
        try:
            authorization = DenyAllTransferAuthorizer().authorize(context, intent)
        except Exception:
            return self._lexical_outcome(query, texts, "transfer_denied")

        if isinstance(authorization, TransferDenial):
            return self._lexical_outcome(query, texts, "transfer_denied")
        if not isinstance(authorization, TransferGrant) or not grant_matches(
            context, intent, authorization
        ):
            return self._lexical_outcome(query, texts, "invalid_authorization")

        # Phase 1 has no trusted issuer/validator. A structurally matching
        # caller-supplied grant is still not provenance and cannot enable JEV.
        return self._lexical_outcome(query, texts, "transfer_disabled")


def build_provider_selection_policy(
    *,
    jev_enabled: bool = False,
    jev_permitted_by_request: bool = False,
    jev_permitted_by_plan: bool = False,
    jev_scorer: Scorer | None = None,
    lexical_scorer: Scorer | None = None,
    request_context: RequestOperationContext | None = None,
    transfer_authorizer: TransferAuthorizer | None = None,
) -> ProviderSelectionPolicy:
    """Build a policy that remains lexical-only until trusted-host approval."""
    return ProviderSelectionPolicy(
        jev_enabled=jev_enabled,
        jev_permitted_by_request=jev_permitted_by_request,
        jev_permitted_by_plan=jev_permitted_by_plan,
        jev_scorer=jev_scorer,
        lexical_scorer=lexical_scorer,
        request_context=request_context,
        transfer_authorizer=transfer_authorizer,
    )
