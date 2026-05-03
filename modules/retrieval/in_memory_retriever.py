from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.models import AASPropertyCandidate, SemanticNode
from app.text import tokenize
from interfaces.base_retriever import BaseCandidateRetriever


class InMemoryCandidateRetriever(BaseCandidateRetriever):
    """로컬 JSON repository를 사용하는 후보 검색 기본 구현.

    실제 embedding/vector DB가 들어오기 전까지 DDMS의 candidate retrieval
    역할을 흉내 낸다. 이 단계는 recall을 높이는 것이 목적이며 최종 매칭을
    확정하지 않는다.
    """

    def __init__(self, repository_path: Path) -> None:
        """AAS Property 후보 저장소를 메모리에 로드한다."""
        self.repository_path = repository_path
        self._properties = self._load_properties(repository_path)

    def retrieve(
        self,
        semantic_node: SemanticNode,
        top_k: int,
    ) -> list[AASPropertyCandidate]:
        """Semantic Node와 유사한 후보 Top-K를 점수순으로 반환한다."""

        # 이름, 개념 정의, affordance, 단위를 함께 사용해 검색 query를 만든다.
        query_text = " ".join(
            [
                semantic_node.name,
                semantic_node.conceptual_definition,
                semantic_node.affordance,
                semantic_node.unit or "",
            ]
        )
        query_tokens = tokenize(query_text)

        candidates: list[AASPropertyCandidate] = []
        for item in self._properties:
            candidate = self._candidate_from_item(item)
            corpus_text = " ".join(
                [
                    candidate.idShort,
                    candidate.description,
                    candidate.submodel,
                    " ".join(candidate.aliases),
                    candidate.preferred_unit or "",
                ]
            )
            score = self._score(query_tokens, tokenize(corpus_text))
            # 단위가 정확히 맞는 후보는 실제 매핑 가능성이 높으므로 소폭 가산한다.
            if semantic_node.unit and candidate.preferred_unit == semantic_node.unit:
                score += 0.1
            candidate.similarity_score = min(score, 1.0)
            candidates.append(candidate)

        candidates.sort(key=lambda item: item.similarity_score, reverse=True)
        return candidates[:top_k]

    def _load_properties(self, repository_path: Path) -> list[dict[str, Any]]:
        """JSON 파일에서 AAS Property 후보 목록을 읽는다."""
        with repository_path.open("r", encoding="utf-8") as file:
            data = json.load(file)
        return list(data.get("properties", []))

    def _candidate_from_item(self, item: dict[str, Any]) -> AASPropertyCandidate:
        """repository record를 내부 후보 dataclass로 변환한다."""
        return AASPropertyCandidate(
            candidate_id=item["candidate_id"],
            idShort=item["idShort"],
            description=item["description"],
            submodel=item["submodel"],
            semantic_id=item.get("semantic_id"),
            preferred_unit=item.get("preferred_unit"),
            aliases=list(item.get("aliases", [])),
        )

    def _score(self, query_tokens: set[str], candidate_tokens: set[str]) -> float:
        """간단한 Jaccard overlap으로 후보 유사도를 계산한다."""
        if not query_tokens or not candidate_tokens:
            return 0.0
        intersection = query_tokens & candidate_tokens
        union = query_tokens | candidate_tokens
        return len(intersection) / len(union)
