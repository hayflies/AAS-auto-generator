"""Production LLM entity matcher.

It implements ``BaseEntityMatcher`` and supports both an individual candidate
comparison and batch reranking of a retrieved top-k candidate set.
"""

from __future__ import annotations

from app.models import AASPropertyCandidate, MatchResult, SemanticNode
from interfaces.base_matcher import BaseEntityMatcher
from interfaces.base_llm import BaseLLM, LLMConnectionError, LLMResponseFormatError
from modules.llm.ollama_client import OllamaClient
from modules.llm.prompts import build_batch_matching_prompt, build_matching_prompt


DEFAULT_MATCH_THRESHOLD = 0.5


class LLMMatcher(BaseEntityMatcher):
    """LLM을 사용해 SemanticNode와 AAS Property 후보의 의미 일치를 판단한다.

    Args:
        client: BaseLLM 인스턴스. 기본값은 새 OllamaClient 인스턴스.
        threshold: 이 점수 미만이면 match=False로 처리한다. 기본값 0.5.
        fail_fast: True이면 LLM 실패 시 match=False fallback 대신 예외를 전파한다.
    """

    def __init__(
        self,
        client: BaseLLM | None = None,
        threshold: float = DEFAULT_MATCH_THRESHOLD,
        skip_llm: bool = False,
        fail_fast: bool = False,
    ):
        self.client = client or OllamaClient()
        self.threshold = threshold
        self.skip_llm = skip_llm
        self.fail_fast = fail_fast

    def match(
        self,
        source_entity: SemanticNode,
        target_entity: AASPropertyCandidate,
    ) -> MatchResult:
        """source SemanticNode와 target AASPropertyCandidate의 의미 일치 여부를 판단한다.

        LLM에 두 속성을 보내고 match/score/reason을 받아 MatchResult로 반환한다.
        fail_fast=False이면 LLM 연결 실패 시 match=False인 MatchResult를 반환한다.
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
        except LLMConnectionError as e:
            if self.fail_fast:
                raise
            print(f"[LLMMatcher] LLM 연결 실패: {e}")
            return MatchResult(
                semantic_node_id=source_entity.semantic_node_id,
                selected_candidate_id=None,
                match=False,
                match_score=0.0,
                reason="LLM connection failed",
                candidate=None,
            )

        if self.fail_fast and "score" not in response:
            raise LLMResponseFormatError("LLM matching response must include a score field.")

        score = self._score(response.get("score"))
        reason = str(response.get("reason", ""))

        # boolean match 필드보다 calibration 가능한 score를 기준으로 결정한다.
        is_match = score >= self.threshold

        return MatchResult(
            semantic_node_id=source_entity.semantic_node_id,
            selected_candidate_id=target_entity.candidate_id if is_match else None,
            match=is_match,
            match_score=score,
            reason=reason,
            candidate=target_entity if is_match else None,
        )

    def match_candidates(
        self,
        source_entity: SemanticNode,
        candidates: list[AASPropertyCandidate],
    ) -> list[MatchResult]:
        """후보군을 LLM에 한 번에 넘겨 재랭킹한다.

        skip_llm=True인 기본/오프라인 경로에서는 후보의 similarity_score를
        그대로 thresholding한다. LLM 경로에서는 top-k 후보군 전체를 한 번의
        prompt로 판단해 호출 횟수를 줄이고 후보 간 상대 비교가 가능하게 한다.
        """
        if not candidates:
            return []
        if self.skip_llm:
            return [self.match(source_entity, candidate) for candidate in candidates]

        prompt = build_batch_matching_prompt(
            self._node_to_dict(source_entity),
            [self._candidate_to_dict(candidate) for candidate in candidates],
        )

        try:
            response = self.client.generate_json_list(prompt, fallback=[])
        except LLMConnectionError as e:
            if self.fail_fast:
                raise
            print(f"[LLMMatcher] LLM 후보군 재랭킹 실패: {e}")
            return [
                MatchResult(
                    semantic_node_id=source_entity.semantic_node_id,
                    selected_candidate_id=None,
                    match=False,
                    match_score=0.0,
                    reason="LLM connection failed during batch reranking",
                    candidate=None,
                )
                for _ in candidates
            ]

        if self.fail_fast and not response:
            raise LLMResponseFormatError("LLM batch reranking returned an empty JSON array.")

        scored_by_key = self._response_index(response)
        results: list[MatchResult] = []
        for candidate in candidates:
            item = (
                scored_by_key.get(candidate.candidate_id)
                or scored_by_key.get(candidate.idShort)
                or scored_by_key.get(candidate.idShort.lower())
            )
            if item is None:
                if self.fail_fast:
                    raise LLMResponseFormatError(
                        f"LLM batch response omitted candidate {candidate.candidate_id}."
                    )
                results.append(
                    MatchResult(
                        semantic_node_id=source_entity.semantic_node_id,
                        selected_candidate_id=None,
                        match=False,
                        match_score=0.0,
                        reason="LLM batch response omitted this candidate",
                        candidate=None,
                    )
                )
                continue

            score = self._score(item.get("score"))
            is_match = score >= self.threshold
            results.append(
                MatchResult(
                    semantic_node_id=source_entity.semantic_node_id,
                    selected_candidate_id=candidate.candidate_id if is_match else None,
                    match=is_match,
                    match_score=score,
                    reason=str(item.get("reason") or "LLM batch reranking"),
                    candidate=candidate if is_match else None,
                )
            )
        return results

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
            "eclass_irdi": candidate.eclass_irdi,
            "source": candidate.source,
            "path": candidate.path,
        }

    def _response_index(self, response: list) -> dict[str, dict]:
        indexed: dict[str, dict] = {}
        for item in response:
            if not isinstance(item, dict):
                continue
            for key in ("candidate_id", "idShort", "id_short"):
                value = item.get(key)
                if value:
                    indexed[str(value)] = item
                    indexed[str(value).lower()] = item
        return indexed

    def _score(self, value: object) -> float:
        try:
            score = float(value or 0.0)
        except (TypeError, ValueError):
            return 0.0
        return max(0.0, min(1.0, score))
