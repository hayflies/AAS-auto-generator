"""임베딩 기반 Candidate Retriever.

interfaces/base_retriever.py의 BaseCandidateRetriever를 구현한다.
파이프라인은 InMemoryCandidateRetriever 대신 이 클래스를 꽂아 쓸 수 있다.

InMemoryCandidateRetriever는 Jaccard 토큰 겹침만 사용해 의미 유사도를 전혀 반영하지 못한다.
이 구현은 Ollama 임베딩 벡터의 코사인 유사도로 후보를 검색해 의미 기반 매칭이 가능하다.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from app.models import AASPropertyCandidate, SemanticNode
from interfaces.base_retriever import BaseCandidateRetriever
from modules.llm.ollama_client import OllamaClient, OllamaConnectionError


class EmbeddingCandidateRetriever(BaseCandidateRetriever):
    """Ollama 임베딩을 사용해 SemanticNode와 가장 유사한 AAS Property 후보를 검색한다.

    초기화 시 properties.json의 모든 후보에 대한 임베딩을 미리 계산해 캐싱한다.
    retrieve() 호출마다 쿼리 임베딩과 코사인 유사도를 계산해 Top-K를 반환한다.

    임베딩 모델은 nomic-embed-text를 기본으로 사용하며,
    설치되지 않은 경우 llama3.2로 자동 fallback한다.

    Args:
        repository_path: AAS Property 후보 JSON 파일 경로.
        client: OllamaClient 인스턴스. 기본값은 새 인스턴스 생성.
    """

    def __init__(
        self,
        repository_path: Path,
        client: OllamaClient | None = None,
    ):
        self.client = client or OllamaClient()
        self._properties = self._load_properties(repository_path)
        self._candidate_embeddings = self._precompute_embeddings()

    def retrieve(
        self,
        semantic_node: SemanticNode,
        top_k: int,
    ) -> list[AASPropertyCandidate]:
        """SemanticNode와 코사인 유사도가 높은 후보 Top-K를 반환한다."""
        query_text = self._build_query(semantic_node)

        try:
            query_embedding = self.client.embed(query_text)
        except OllamaConnectionError as e:
            print(f"[EmbeddingRetriever] Ollama 연결 실패, 빈 목록 반환: {e}")
            return []

        scored: list[tuple[AASPropertyCandidate, float]] = []
        for item, cand_embedding in zip(self._properties, self._candidate_embeddings):
            if cand_embedding is None:
                continue
            candidate = self._candidate_from_item(item)
            score = _cosine_similarity(query_embedding, cand_embedding)
            # 단위가 정확히 일치하면 소폭 가산
            if semantic_node.unit and candidate.preferred_unit == semantic_node.unit:
                score = min(score + 0.05, 1.0)
            candidate.similarity_score = score
            scored.append((candidate, score))

        scored.sort(key=lambda x: x[1], reverse=True)
        return [candidate for candidate, _ in scored[:top_k]]

    def _build_query(self, semantic_node: SemanticNode) -> str:
        """SemanticNode 정보를 임베딩용 쿼리 텍스트로 조합한다."""
        parts = [
            semantic_node.name,
            semantic_node.conceptual_definition,
            semantic_node.affordance,
        ]
        if semantic_node.unit:
            parts.append(semantic_node.unit)
        return " ".join(parts)

    def _precompute_embeddings(self) -> list[list[float] | None]:
        """모든 후보에 대한 임베딩을 초기화 시 미리 계산한다.

        실패한 후보는 None으로 저장해 retrieve에서 건너뛴다.
        """
        embeddings: list[list[float] | None] = []
        for item in self._properties:
            text = self._build_candidate_text(item)
            try:
                embedding = self.client.embed(text)
                embeddings.append(embedding)
            except Exception as e:
                print(f"[EmbeddingRetriever] 임베딩 실패 ({item.get('idShort', '?')}): {e}")
                embeddings.append(None)
        return embeddings

    def _build_candidate_text(self, item: dict[str, Any]) -> str:
        """후보 딕셔너리를 임베딩할 텍스트로 만든다."""
        parts = [
            item.get("idShort", ""),
            item.get("description", ""),
            item.get("submodel", ""),
            " ".join(item.get("aliases", [])),
        ]
        if item.get("preferred_unit"):
            parts.append(item["preferred_unit"])
        return " ".join(parts)

    def _load_properties(self, repository_path: Path) -> list[dict[str, Any]]:
        """JSON 파일에서 AAS Property 후보 목록을 읽는다."""
        with repository_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return list(data.get("properties", []))

    def _candidate_from_item(self, item: dict[str, Any]) -> AASPropertyCandidate:
        """repository record를 AASPropertyCandidate dataclass로 변환한다."""
        return AASPropertyCandidate(
            candidate_id=item["candidate_id"],
            idShort=item["idShort"],
            description=item["description"],
            submodel=item["submodel"],
            semantic_id=item.get("semantic_id"),
            preferred_unit=item.get("preferred_unit"),
            aliases=list(item.get("aliases", [])),
        )


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """두 벡터의 코사인 유사도를 계산한다. 범위: -1.0 ~ 1.0."""
    if len(a) != len(b) or not a:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)
