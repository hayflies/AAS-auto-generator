"""LLM 기반 엔티티 매처.

interfaces/base_matcher.py의 BaseEntityMatcher를 구현한다.
파이프라인은 RuleBasedEntityMatcher 대신 이 클래스를 꽂아 쓸 수 있다.

파이프라인 호출 방식 (pipeline.py 85번 줄):
    node_matches = [self.matcher.match(node, candidate) for candidate in candidates]
즉 후보를 하나씩 넘겨서 MatchResult 하나씩 받는 구조다.
"""

from __future__ import annotations

from app.models import AASPropertyCandidate, MatchResult, SemanticNode
from interfaces.base_matcher import BaseEntityMatcher
from modules.llm.ollama_client import OllamaClient, OllamaConnectionError
from modules.llm.prompts import build_matching_prompt


DEFAULT_MATCH_THRESHOLD = 0.5


class LLMMatcher(BaseEntityMatcher):
    """Ollama LLM을 사용해 SemanticNode와 AAS Property 후보의 의미 일치를 판단한다.

    Args:
        client: OllamaClient 인스턴스. 기본값은 새 인스턴스 생성.
        threshold: 이 점수 미만이면 match=False로 처리한다. 기본값 0.5.
    """

    def __init__(
        self,
        client: OllamaClient | None = None,
        threshold: float = DEFAULT_MATCH_THRESHOLD,
        skip_llm: bool = False,
    ):
        self.client = client or OllamaClient()
        self.threshold = threshold
        self.skip_llm = skip_llm

    def match(
        self,
        source_entity: SemanticNode,
        target_entity: AASPropertyCandidate,
    ) -> MatchResult:
        """source SemanticNode와 target AASPropertyCandidate의 의미 일치 여부를 판단한다.

        LLM에 두 속성을 보내고 match/score/reason을 받아 MatchResult로 반환한다.
        Ollama 연결 실패 시 match=False인 MatchResult를 반환한다 (예외 전파 안 함).
        """
        # skip_llm=True이면 임베딩 유사도로만 판단한다.
        # similarity_score가 EMBED_THRESHOLD 이상일 때만 match=True 처리.
        if self.skip_llm:
            embed_score = getattr(target_entity, "similarity_score", 0.0)
            _EMBED_THRESHOLD = 0.65
            is_match = embed_score >= _EMBED_THRESHOLD
            return MatchResult(
                semantic_node_id=source_entity.semantic_node_id,
                selected_candidate_id=target_entity.candidate_id if is_match else None,
                match=is_match,
                match_score=embed_score,
                reason=f"Embedding similarity={embed_score:.3f} ({'matched' if is_match else 'below threshold'})",
                candidate=target_entity if is_match else None,
            )

        node_dict = self._node_to_dict(source_entity)
        candidate_dict = self._candidate_to_dict(target_entity)

        prompt = build_matching_prompt(node_dict, candidate_dict)

        try:
            response = self.client.generate_json(prompt, fallback={})
        except OllamaConnectionError as e:
            print(f"[LLMMatcher] Ollama 연결 실패: {e}")
            return MatchResult(
                semantic_node_id=source_entity.semantic_node_id,
                selected_candidate_id=None,
                match=False,
                match_score=0.0,
                reason="Ollama connection failed",
                candidate=None,
            )

        score = float(response.get("score") or 0.0)
        reason = str(response.get("reason", ""))

        # score를 기준으로 판단 (llama3.2는 boolean과 score를 모순되게 반환하는 경우가 있어
        # boolean match 필드 대신 score로 결정한다)
        is_match = score >= self.threshold

        return MatchResult(
            semantic_node_id=source_entity.semantic_node_id,
            selected_candidate_id=target_entity.candidate_id if is_match else None,
            match=is_match,
            match_score=score,
            reason=reason,
            candidate=target_entity if is_match else None,
        )

    def _node_to_dict(self, node: SemanticNode) -> dict:
        return {
            "semantic_node_id": node.semantic_node_id,
            "name": node.name,
            "value": node.value,
            "unit": node.unit,
            "conceptual_definition": node.conceptual_definition,
            "affordance": node.affordance,
        }

    def _candidate_to_dict(self, candidate: AASPropertyCandidate) -> dict:
        return {
            "candidate_id": candidate.candidate_id,
            "idShort": candidate.idShort,
            "description": candidate.description,
            "submodel": candidate.submodel,
            "semantic_id": candidate.semantic_id,
            "preferred_unit": candidate.preferred_unit,
        }
