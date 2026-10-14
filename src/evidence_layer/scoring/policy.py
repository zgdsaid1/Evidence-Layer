"""Request-scoped JEV scoring selection with whole-request lexical fallback."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Literal

from evidence_layer.scoring.base import Scorer
from evidence_layer.scoring.jev import (
    JevConfigurationError,
    JevDependencyError,
    JevEvidenceScorer,
    JevResponseError,
    JevScorerError,
)
from evidence_layer.scoring.lexical import LexicalScorer

ProviderName = Literal["lexical", "jev"]


def _validate_policy_flag(name: str, value: bool) -> None:
    if not isinstance(value, bool):
        raise TypeError(f"{name} must be a boolean")


@dataclass(frozen=True)
class ProviderFailure:
    """Sanitized reason a requested Jev scorer was not used successfully."""

    category: Literal[
        "configuration_error",
        "dependency_missing",
        "provider_failure",
        "invalid_response",
    ]


@dataclass(frozen=True)
class ScoringOutcome:
    """Scores and safe provider metadata for one complete request."""

    scores: tuple[float, ...]
    provider: ProviderName
    fallback_reason: ProviderFailure | None = None


class ProviderSelectionPolicy:
    """Select JEV only when explicitly enabled and allowed by both policies.

    JEV is the primary provider in the approved evidence-scoring architecture.
    This policy preserves explicit enablement and request/plan permission gates.
    Lexical scoring is always instantiated locally. If any JEV candidate fails,
    all scores for the request are recomputed lexically so rankings never mix
    providers and no partial JEV output is presented as a successful result.
    """

    def __init__(
        self,
        *,
        jev_enabled: bool = False,
        jev_permitted_by_request: bool = False,
        jev_permitted_by_plan: bool = False,
        jev_scorer: Scorer | None = None,
        lexical_scorer: Scorer | None = None,
    ) -> None:
        for name, value in (
            ("jev_enabled", jev_enabled),
            ("jev_permitted_by_request", jev_permitted_by_request),
            ("jev_permitted_by_plan", jev_permitted_by_plan),
        ):
            _validate_policy_flag(name, value)
        self._lexical = (
            lexical_scorer if lexical_scorer is not None else LexicalScorer()
        )
        self._jev = jev_scorer
        self._jev_allowed = (
            jev_enabled and jev_permitted_by_request and jev_permitted_by_plan
        )

    @property
    def jev_selected(self) -> bool:
        """Whether an explicitly permitted Jev scorer was supplied."""
        return self._jev_allowed and self._jev is not None

    @property
    def default_provider(self) -> ProviderName:
        """Provider chosen before requests, excluding operational failure state."""
        return "jev" if self.jev_selected else "lexical"

    def score(self, query: str, texts: list[str]) -> ScoringOutcome:
        """Score one complete candidate set; safely fall back on known Jev errors."""
        if not texts or not self.jev_selected:
            return ScoringOutcome(
                scores=tuple(self._lexical.score(query, text) for text in texts),
                provider="lexical",
            )

        assert self._jev is not None
        scores: list[float] = []
        try:
            for text in texts:
                score = self._jev.score(query, text)
                if isinstance(score, bool) or not isinstance(score, (int, float)):
                    raise JevResponseError(
                        "The Jev provider returned an invalid relevance response."
                    )
                try:
                    numeric_score = float(score)
                except (OverflowError, TypeError, ValueError):
                    raise JevResponseError(
                        "The Jev provider returned an invalid relevance response."
                    ) from None
                if not math.isfinite(numeric_score) or not 0.0 <= numeric_score <= 1.0:
                    raise JevResponseError(
                        "The Jev provider returned an invalid relevance response."
                    )
                scores.append(numeric_score)
        except Exception as error:
            if isinstance(error, JevConfigurationError):
                category = "configuration_error"
            elif isinstance(error, JevDependencyError):
                category = "dependency_missing"
            elif isinstance(error, JevResponseError):
                category = "invalid_response"
            else:
                # Provider-compatible implementations can raise untyped errors;
                # collapse them to a stable category without exposing details.
                category = "provider_failure"
            return ScoringOutcome(
                scores=tuple(self._lexical.score(query, text) for text in texts),
                provider="lexical",
                fallback_reason=ProviderFailure(category=category),
            )

        return ScoringOutcome(scores=tuple(scores), provider="jev")


def build_provider_selection_policy(
    *,
    jev_enabled: bool = False,
    jev_permitted_by_request: bool = False,
    jev_permitted_by_plan: bool = False,
    jev_scorer: Scorer | None = None,
    lexical_scorer: Scorer | None = None,
) -> ProviderSelectionPolicy:
    """Build policy; lazily construct JEV only if enabled and permitted.

    Configuration, credentials, or optional SDK availability are checked by
    ``JevEvidenceScorer.score`` and become safe lexical fallback outcomes.
    """
    for name, value in (
        ("jev_enabled", jev_enabled),
        ("jev_permitted_by_request", jev_permitted_by_request),
        ("jev_permitted_by_plan", jev_permitted_by_plan),
    ):
        _validate_policy_flag(name, value)
    allowed = jev_enabled and jev_permitted_by_request and jev_permitted_by_plan
    if allowed and jev_scorer is None:
        jev_scorer = JevEvidenceScorer()
    return ProviderSelectionPolicy(
        jev_enabled=jev_enabled,
        jev_permitted_by_request=jev_permitted_by_request,
        jev_permitted_by_plan=jev_permitted_by_plan,
        jev_scorer=jev_scorer,
        lexical_scorer=lexical_scorer,
    )