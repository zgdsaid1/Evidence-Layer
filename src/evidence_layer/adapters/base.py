"""Adapter interface that all future domain adapters must implement.

The interface is deliberately minimal and technology-agnostic. It does not
prescribe *how* evidence is ranked or selected; it only prescribes the boundary
between a raw domain payload and the domain-agnostic Evidence Layer schemas.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from evidence_layer.schemas import (
    EvidenceCandidate,
    EvidenceSelectionResult,
    Policy,
    Task,
)


class EvidenceAdapter(ABC):
    """Contract for turning raw domain data into Evidence Layer objects.

    Subclasses implement four steps:

    1. ``normalize_task``      -> :class:`~evidence_layer.schemas.Task`
    2. ``normalize_candidates`` -> ``list[EvidenceCandidate]``
    3. ``apply_policy``        -> :class:`~evidence_layer.schemas.EvidenceSelectionResult`
    4. ``interpret_result``    -> a human-readable mapping
    """

    #: Human-readable domain identifier (e.g. "technical_documentation").
    domain: str = "custom"

    @abstractmethod
    def normalize_task(self, raw: Any) -> Task:
        """Convert a raw domain task payload into a ``Task``."""

    @abstractmethod
    def normalize_candidates(self, raw: Any) -> list[EvidenceCandidate]:
        """Convert raw candidate passages into ``EvidenceCandidate`` objects."""

    @abstractmethod
    def apply_policy(
        self,
        task: Task,
        candidates: list[EvidenceCandidate],
        policy: Policy,
    ) -> EvidenceSelectionResult:
        """Select evidence under the given policy.

        This is the one place a real domain adapter would later plug in ranking /
        reranking / scoring. The Phase 1 adapters must remain no-op baselines.
        """

    @abstractmethod
    def interpret_result(self, result: EvidenceSelectionResult) -> dict[str, Any]:
        """Render a selection result into a human/agent-readable mapping."""
