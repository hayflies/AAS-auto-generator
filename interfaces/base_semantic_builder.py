"""Semantic Node Builder 인터페이스.

추출된 raw entity를 AAS 매핑 전에 사용할 의미 중간 표현으로 정리하는
계층의 계약이다.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.models import ExtractedEntity, SemanticNode


class BaseSemanticNodeBuilder(ABC):
    """ExtractedEntity 목록을 SemanticNode 목록으로 변환하는 계약."""

    @abstractmethod
    def build(self, entities: list[ExtractedEntity]) -> list[SemanticNode]:
        """raw entity에 정의, affordance, confidence 등을 보강한다."""
        raise NotImplementedError
