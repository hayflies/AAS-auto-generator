"""Embedding 모델 인터페이스.

현재 MVP는 토큰 기반 검색을 쓰지만, 추후 sentence-transformers, OpenAI
embedding, FAISS/Chroma 연동으로 교체할 때 이 계약을 기준으로 삼는다.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class BaseEmbeddingModel(ABC):
    """문장을 벡터로 변환하는 embedding adapter 계약."""

    @abstractmethod
    def embed(self, text: str) -> list[float]:
        """입력 텍스트의 embedding 벡터를 반환한다."""
        raise NotImplementedError
