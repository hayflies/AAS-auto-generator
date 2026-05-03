"""Candidate Retrieval Engine 인터페이스.

DDMS의 blocking 단계처럼 Semantic Node와 유사한 AAS Property 후보 Top-N을
넓게 찾는 계층이다. 이 단계는 최종 매핑을 확정하지 않는다.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.models import AASPropertyCandidate, SemanticNode


class BaseCandidateRetriever(ABC):
    """Semantic Node별 AAS Property 후보를 검색하는 계약."""

    @abstractmethod
    def retrieve(
        self,
        semantic_node: SemanticNode,
        top_k: int,
    ) -> list[AASPropertyCandidate]:
        """주어진 Semantic Node에 대한 상위 후보 목록을 반환한다."""
        raise NotImplementedError
