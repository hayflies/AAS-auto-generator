"""Optional CV Module 인터페이스.

이미지 기반 장비 유형 분류나 세그멘테이션이 필요할 때 사용하는 선택 계층이다.
구현체가 없어도 전체 파이프라인은 동작해야 한다.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.models import CVOutput


class BaseCVModel(ABC):
    """이미지 전처리/분류 모델이 따라야 하는 계약."""

    @abstractmethod
    def classify(self, images: list[str]) -> CVOutput:
        """이미지 목록으로부터 자산 유형을 보조 추론한다."""
        raise NotImplementedError

    @abstractmethod
    def segment(self, images: list[str]) -> list[str]:
        """3D 생성 등에 사용할 세그멘테이션 이미지 경로 목록을 반환한다."""
        raise NotImplementedError
