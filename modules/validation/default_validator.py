from __future__ import annotations

from collections import Counter
from statistics import mean
from typing import Any

from app.models import (
    AASPropertyCandidate,
    MappingValidationResult,
    MatchedProperty,
    MatchResult,
    SemanticNode,
)


class DefaultMappingValidator:
    """DDMS-style AAS mapping validator.

    DDMS의 평가 흐름처럼 후보 검색 결과의 top-k 재랭킹 품질과 최종 매핑의
    template 적합성을 함께 본다. gold label이 없는 운영 실행에서는 true
    precision/recall 대신 coverage, Hit@K, MRR@K, template support ratio를
    사용해 매핑 품질을 판단한다.
    """

    def __init__(
        self,
        top_k: int = 10,
        coverage_threshold: float = 0.80,
        mrr_threshold: float = 0.50,
        hit_at_k_threshold: float = 0.80,
        template_support_threshold: float = 0.70,
    ) -> None:
        self.top_k = top_k
        self.coverage_threshold = coverage_threshold
        self.mrr_threshold = mrr_threshold
        self.hit_at_k_threshold = hit_at_k_threshold
        self.template_support_threshold = template_support_threshold

    def validate(
        self,
        semantic_nodes: list[SemanticNode],
        candidates_by_node: dict[str, list[AASPropertyCandidate]],
        match_results: list[MatchResult],
        matched_properties: list[MatchedProperty],
        mapping_plan: dict[str, Any],
    ) -> MappingValidationResult:
        """Pipeline 산출물에서 AAS 매핑 품질 검증 결과를 계산한다."""
        del match_results

        node_count = len(semantic_nodes)
        matched_by_node = {
            item.semantic_node_id: item
            for item in matched_properties
            if item.semantic_node_id
        }
        ranks = [
            self._selected_rank(
                matched_by_node.get(node.semantic_node_id),
                candidates_by_node.get(node.semantic_node_id, []),
            )
            for node in semantic_nodes
        ]

        matched_count = sum(1 for node in semantic_nodes if node.semantic_node_id in matched_by_node)
        coverage = self._ratio(matched_count, node_count)
        hit_at_1 = self._ratio(sum(1 for rank in ranks if rank == 1), node_count)
        hit_at_k = self._ratio(
            sum(1 for rank in ranks if rank is not None and rank <= self.top_k),
            node_count,
        )
        mrr_at_k = self._ratio(
            sum((1.0 / rank) for rank in ranks if rank is not None and rank <= self.top_k),
            node_count,
        )
        mean_match_score = (
            mean([item.match_score for item in matched_by_node.values()])
            if matched_by_node else 0.0
        )
        semantic_id_coverage = self._ratio(
            sum(1 for item in matched_by_node.values() if item.semantic_id or item.eclass_irdi),
            node_count,
        )
        source_reference_coverage = self._ratio(
            sum(1 for node in semantic_nodes if node.source_reference),
            node_count,
        )

        diagnostics = [
            item for item in mapping_plan.get("diagnostics", [])
            if item.get("semantic_node_id")
        ]
        status_counts = Counter(str(item.get("status") or "unknown") for item in diagnostics)
        template_supported = status_counts["template_validated"] + status_counts["template_extension"]
        template_support_ratio = self._ratio(template_supported, len(diagnostics) or matched_count)
        review_queue_count = len(mapping_plan.get("reviewQueue", []))
        review_required_count = review_queue_count + sum(
            1 for item in matched_by_node.values() if item.review_required
        )
        manual_review_rate = self._ratio(review_required_count, node_count)
        source_distribution = Counter(str(item.source or "unknown") for item in matched_by_node.values())

        findings = self._findings(
            semantic_nodes=semantic_nodes,
            matched_by_node=matched_by_node,
            ranks=ranks,
            metrics={
                "coverage": coverage,
                "mrr_at_k": mrr_at_k,
                "hit_at_k": hit_at_k,
                "template_support_ratio": template_support_ratio,
                "source_reference_coverage": source_reference_coverage,
            },
            review_required_count=review_required_count,
            source_distribution=source_distribution,
        )
        overall_status = self._overall_status(findings)

        metrics = {
            "semantic_node_count": node_count,
            "matched_count": matched_count,
            "coverage": round(coverage, 4),
            "mean_match_score": round(mean_match_score, 4),
            "semantic_id_coverage": round(semantic_id_coverage, 4),
            "source_reference_coverage": round(source_reference_coverage, 4),
            "template_support_ratio": round(template_support_ratio, 4),
            "review_required_count": review_required_count,
            "manual_review_rate": round(manual_review_rate, 4),
            "source_distribution": dict(source_distribution),
            "mapping_status_counts": dict(status_counts),
        }
        ddms_metrics = {
            f"mrr_at_{self.top_k}": round(mrr_at_k, 4),
            "hit_at_1": round(hit_at_1, 4),
            f"hit_at_{self.top_k}": round(hit_at_k, 4),
            "candidate_coverage": round(coverage, 4),
            "template_support_ratio": round(template_support_ratio, 4),
            "manual_review_rate": round(manual_review_rate, 4),
        }

        return MappingValidationResult(
            overall_status=overall_status,
            metrics=metrics,
            ddms_metrics=ddms_metrics,
            findings=findings,
        )

    def _selected_rank(
        self,
        matched: MatchedProperty | None,
        candidates: list[AASPropertyCandidate],
    ) -> int | None:
        if matched is None:
            return None
        for index, candidate in enumerate(candidates[: self.top_k], start=1):
            if self._same_candidate(matched, candidate):
                return index
        return None

    @staticmethod
    def _same_candidate(matched: MatchedProperty, candidate: AASPropertyCandidate) -> bool:
        if matched.aas_property_id == candidate.candidate_id:
            return True
        if matched.semantic_id and matched.semantic_id == candidate.semantic_id:
            return True
        return matched.idShort.lower() == candidate.idShort.lower() and matched.submodel == candidate.submodel

    def _findings(
        self,
        semantic_nodes: list[SemanticNode],
        matched_by_node: dict[str, MatchedProperty],
        ranks: list[int | None],
        metrics: dict[str, float],
        review_required_count: int,
        source_distribution: Counter,
    ) -> list[dict[str, Any]]:
        findings: list[dict[str, Any]] = []
        if not semantic_nodes:
            findings.append(self._finding("error", "no_semantic_nodes", "No semantic nodes were generated."))
            return findings

        missing_nodes = [
            node for node in semantic_nodes
            if node.semantic_node_id not in matched_by_node
        ]
        if missing_nodes:
            findings.append(
                self._finding(
                    "warning",
                    "unmatched_semantic_nodes",
                    f"{len(missing_nodes)} semantic nodes were not mapped to AAS properties.",
                    examples=[node.name for node in missing_nodes[:5]],
                )
            )
        if any(rank is None for rank in ranks):
            findings.append(
                self._finding(
                    "warning",
                    "selected_candidate_outside_top_k",
                    "At least one mapped property was not found in the retrieved top-k candidate list.",
                )
            )
        if metrics["coverage"] < self.coverage_threshold:
            findings.append(
                self._finding(
                    "error",
                    "low_mapping_coverage",
                    f"Mapping coverage is below threshold {self.coverage_threshold:.2f}.",
                    value=round(metrics["coverage"], 4),
                )
            )
        if metrics["mrr_at_k"] < self.mrr_threshold:
            findings.append(
                self._finding(
                    "warning",
                    "low_candidate_mrr",
                    f"MRR@{self.top_k} is below threshold {self.mrr_threshold:.2f}.",
                    value=round(metrics["mrr_at_k"], 4),
                )
            )
        if metrics["hit_at_k"] < self.hit_at_k_threshold:
            findings.append(
                self._finding(
                    "warning",
                    "low_hit_at_k",
                    f"Hit@{self.top_k} is below threshold {self.hit_at_k_threshold:.2f}.",
                    value=round(metrics["hit_at_k"], 4),
                )
            )
        if metrics["template_support_ratio"] < self.template_support_threshold:
            findings.append(
                self._finding(
                    "warning",
                    "low_template_support",
                    f"Template support ratio is below threshold {self.template_support_threshold:.2f}.",
                    value=round(metrics["template_support_ratio"], 4),
                )
            )
        if metrics["source_reference_coverage"] < 0.50:
            findings.append(
                self._finding(
                    "warning",
                    "weak_source_grounding",
                    "Less than half of semantic nodes keep PDF/page source references.",
                    value=round(metrics["source_reference_coverage"], 4),
                )
            )
        if review_required_count:
            findings.append(
                self._finding(
                    "warning",
                    "manual_review_required",
                    f"{review_required_count} mapped properties require manual review.",
                )
            )
        if source_distribution.get("project_repository"):
            findings.append(
                self._finding(
                    "error",
                    "project_repository_candidate_detected",
                    "project_repository candidates must not participate in mapping.",
                )
            )
        return findings

    @staticmethod
    def _overall_status(findings: list[dict[str, Any]]) -> str:
        if any(item.get("severity") == "error" for item in findings):
            return "failed"
        if findings:
            return "review"
        return "passed"

    @staticmethod
    def _finding(severity: str, code: str, message: str, **extra: Any) -> dict[str, Any]:
        finding = {"severity": severity, "code": code, "message": message}
        finding.update(extra)
        return finding

    @staticmethod
    def _ratio(numerator: float, denominator: float) -> float:
        return float(numerator) / float(denominator) if denominator else 0.0
