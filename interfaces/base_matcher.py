"""Entity Matching Engine 인터페이스.

Semantic Node와 AAS Property 후보가 실제로 같은 의미인지 판정하는 단계다.
LLM matcher, cross-encoder, rule-based matcher가 모두 이 계약을 구현할 수 있다.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.models import AASPropertyCandidate, MatchResult, SemanticNode


class BaseEntityMatcher(ABC):
    """Semantic Node와 후보 property의 의미 일치를 판단하는 계약."""

    @abstractmethod
    def match(
        self,
        source_entity: SemanticNode,
        target_entity: AASPropertyCandidate,
    ) -> MatchResult:
        """source와 target의 match 여부, 점수, 사유를 반환한다."""
        raise NotImplementedError

    def match_candidates(
        self,
        source_entity: SemanticNode,
        candidates: list[AASPropertyCandidate],
    ) -> list[MatchResult]:
        """후보군 전체를 재랭킹한다.

        기본 구현은 기존 단건 match 계약을 반복 호출한다. LLM matcher처럼
        후보군을 한 번에 판단할 수 있는 구현체는 이 메서드를 override한다.
        """
        return [self.match(source_entity, candidate) for candidate in candidates]
