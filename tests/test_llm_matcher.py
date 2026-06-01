from __future__ import annotations

import unittest

from app.models import AASPropertyCandidate, MatchResult, SemanticNode
from modules.matching.llm_matcher import LLMMatcher


class FakeMatchingClient:
    """LLM 서버 없이 matcher threshold/변환 로직을 검증하기 위한 테스트 더블."""

    def generate_json(self, prompt: str, fallback: dict | None = None) -> dict:
        if "ManufacturerName" in prompt:
            return {
                "match": False,
                "score": 0.1,
                "reason": "different concepts",
            }
        if "GrossWeight" in prompt:
            return {
                "match": True,
                "score": 0.7,
                "reason": "related weight concept",
            }
        return {
            "match": True,
            "score": 0.92,
            "reason": "same electrical voltage concept",
        }


def _make_node(name: str, value: str, unit: str | None = None) -> SemanticNode:
    return SemanticNode(
        semantic_node_id=f"SN_{name}",
        name=name,
        value=value,
        unit=unit,
        value_type="float",
        conceptual_definition=f"The {name} of the asset",
        affordance="measurement",
        source_description="user_input",
    )


def _make_candidate(id_short: str, description: str, submodel: str = "TechnicalData") -> AASPropertyCandidate:
    return AASPropertyCandidate(
        candidate_id=f"cand_{id_short}",
        idShort=id_short,
        description=description,
        submodel=submodel,
        similarity_score=0.8,
    )


class LLMMatcherTest(unittest.TestCase):
    """LLMMatcher가 SemanticNode와 AASPropertyCandidate를 올바르게 판정하는지 검증한다."""

    def setUp(self) -> None:
        self.matcher = LLMMatcher(client=FakeMatchingClient())

    def test_match_returns_match_result(self) -> None:
        """match()가 MatchResult 인스턴스를 반환한다."""
        node = _make_node("Rated Voltage", "24", "V")
        candidate = _make_candidate("NominalVoltage", "Nominal voltage of the asset")
        result = self.matcher.match(node, candidate)
        self.assertIsInstance(result, MatchResult)

    def test_match_result_has_required_fields(self) -> None:
        """MatchResult가 semantic_node_id, match, match_score, reason을 가진다."""
        node = _make_node("Rated Voltage", "24", "V")
        candidate = _make_candidate("NominalVoltage", "Nominal voltage of the asset")
        result = self.matcher.match(node, candidate)
        self.assertEqual(result.semantic_node_id, node.semantic_node_id)
        self.assertIsInstance(result.match, bool)
        self.assertIsInstance(result.match_score, float)
        self.assertIsInstance(result.reason, str)

    def test_match_score_in_range(self) -> None:
        """match_score가 0.0~1.0 사이다."""
        node = _make_node("Rated Voltage", "24", "V")
        candidate = _make_candidate("NominalVoltage", "Nominal voltage of the asset")
        result = self.matcher.match(node, candidate)
        self.assertGreaterEqual(result.match_score, 0.0)
        self.assertLessEqual(result.match_score, 1.0)

    def test_obvious_match(self) -> None:
        """같은 의미인 두 속성은 높은 점수를 받는다.

        모델별 boolean 보정 차이를 피하기 위해 score가 유의미하게 높은지 확인한다.
        """
        node = _make_node("Rated Voltage", "24", "V")
        candidate = _make_candidate("NominalVoltage", "Nominal operating voltage of the device in volts")
        result = self.matcher.match(node, candidate)
        self.assertGreaterEqual(
            result.match_score, 0.3,
            f"전압 관련 속성끼리 score가 너무 낮습니다: {result.match_score}, reason: {result.reason}"
        )

    def test_obvious_mismatch(self) -> None:
        """명백히 다른 의미인 두 속성은 match=False로 판정된다."""
        node = _make_node("Rated Voltage", "24", "V")
        candidate = _make_candidate("ManufacturerName", "Name of the manufacturer of the asset")
        result = self.matcher.match(node, candidate)
        self.assertFalse(result.match, f"전압과 제조사명이 매칭되면 안 됩니다. reason: {result.reason}")

    def test_match_false_when_score_below_threshold(self) -> None:
        """threshold보다 높게 설정하면 낮은 점수는 match=False가 된다."""
        strict_matcher = LLMMatcher(client=FakeMatchingClient(), threshold=0.99)
        node = _make_node("Weight", "3.5", "kg")
        candidate = _make_candidate("GrossWeight", "Total weight of the packaged asset")
        result = strict_matcher.match(node, candidate)
        # threshold가 0.99라 웬만해선 False여야 함
        if result.match_score < 0.99:
            self.assertFalse(result.match)

    def test_match_false_has_no_candidate(self) -> None:
        """match=False인 결과는 candidate 필드가 None이다."""
        node = _make_node("Rated Voltage", "24", "V")
        candidate = _make_candidate("ManufacturerName", "Name of the manufacturer of the asset")
        result = self.matcher.match(node, candidate)
        if not result.match:
            self.assertIsNone(result.candidate)

    def test_match_true_has_candidate(self) -> None:
        """match=True인 결과는 candidate 필드에 AASPropertyCandidate가 있다."""
        node = _make_node("Rated Voltage", "24", "V")
        candidate = _make_candidate("NominalVoltage", "Nominal operating voltage of the device in volts")
        result = self.matcher.match(node, candidate)
        if result.match:
            self.assertIsNotNone(result.candidate)
            self.assertEqual(result.selected_candidate_id, candidate.candidate_id)


if __name__ == "__main__":
    unittest.main()
