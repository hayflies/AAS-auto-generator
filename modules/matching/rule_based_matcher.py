from __future__ import annotations

from app.models import AASPropertyCandidate, MatchResult, SemanticNode
from app.text import normalize_label, tokenize
from interfaces.base_matcher import BaseEntityMatcher


class RuleBasedEntityMatcher(BaseEntityMatcher):
    """LLM matcher를 대체하는 결정적 rule-based 기본 구현.

    후보 검색 점수, 이름 토큰 겹침, 단위 일치 여부를 조합해 match 여부를
    판단한다. 추후 fine-tuned LLM이나 cross-encoder로 교체 가능하다.
    """

    def __init__(self, threshold: float = 0.45) -> None:
        """match로 인정할 최소 점수를 설정한다."""
        self.threshold = threshold

    def match(
        self,
        source_entity: SemanticNode,
        target_entity: AASPropertyCandidate,
    ) -> MatchResult:
        """Semantic Node와 후보 AAS Property의 의미 일치 점수를 계산한다."""

        source_tokens = tokenize(source_entity.name)
        target_tokens = tokenize(target_entity.idShort) | set().union(
            *(tokenize(alias) for alias in target_entity.aliases)
        )
        name_overlap = self._overlap(source_tokens, target_tokens)

        score = (target_entity.similarity_score * 0.55) + (name_overlap * 0.35)
        normalized_source = normalize_label(source_entity.name).lower()
        normalized_targets = {
            normalize_label(target_entity.idShort).lower(),
            *(normalize_label(alias).lower() for alias in target_entity.aliases),
        }
        if normalized_source in normalized_targets:
            score += 0.25
        # 단위 일치는 전기/기계 스펙 매핑에서 강한 신호로 취급한다.
        if source_entity.unit and source_entity.unit == target_entity.preferred_unit:
            score += 0.1

        score = min(score, 1.0)
        matched = score >= self.threshold
        reason = (
            "Matched by lexical similarity, candidate retrieval score, and unit compatibility."
            if matched
            else "Rejected because similarity was below the configured threshold."
        )
        return MatchResult(
            semantic_node_id=source_entity.semantic_node_id,
            selected_candidate_id=target_entity.candidate_id if matched else None,
            match=matched,
            match_score=score,
            reason=reason,
            candidate=target_entity,
        )

    def _overlap(self, source_tokens: set[str], target_tokens: set[str]) -> float:
        """두 토큰 집합의 Jaccard overlap을 반환한다."""
        if not source_tokens or not target_tokens:
            return 0.0
        return len(source_tokens & target_tokens) / len(source_tokens | target_tokens)
