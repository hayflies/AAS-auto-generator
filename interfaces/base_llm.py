"""LLM Adapter 인터페이스.

Semantic Node 보강, entity matching, 문서 추출 같은 단계에서 LLM을 붙일 때
특정 벤더 API에 직접 결합하지 않기 위한 최소 계약이다.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class BaseLLM(ABC):
    """prompt 기반 텍스트 생성을 수행하는 LLM adapter 계약."""

    @abstractmethod
    def generate(self, prompt: str, **kwargs: object) -> str:
        """입력 prompt와 옵션을 받아 모델 응답 문자열을 반환한다."""
        raise NotImplementedError
