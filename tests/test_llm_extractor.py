from __future__ import annotations

import unittest

from app.models import AssetPackage, CVOutput, ExtractedEntity
from modules.extraction.llm_extractor import LLMExtractor


class FakeExtractionClient:
    """LLM 서버 없이 extractor 변환 로직을 검증하기 위한 테스트 더블."""

    def generate_json_list(self, prompt: str, fallback: list | None = None) -> list:
        if "rated_voltage" not in prompt:
            return fallback or []
        return [
            {
                "raw_name": "Rated Voltage",
                "raw_value": "24",
                "raw_unit": "V",
                "confidence": 0.95,
            },
            {
                "raw_name": "Rated Current",
                "raw_value": "1.5",
                "raw_unit": "A",
                "confidence": 0.9,
            },
            {
                "raw_name": "Weight",
                "raw_value": "3.5",
                "raw_unit": "kg",
                "confidence": 0.88,
            },
            {
                "raw_name": "https",
                "raw_value": "1",
                "raw_unit": "/",
                "confidence": 0.99,
                "source_reference": "[PDF_PAGE 1] https://example.com/page/1",
            },
            {
                "raw_name": "USB cable",
                "raw_value": "1",
                "raw_unit": None,
                "confidence": 0.99,
                "source_reference": "[PDF_TABLE 2.1] Item | Qty",
            },
        ]


class LLMExtractorTest(unittest.TestCase):
    """LLMExtractor가 AssetPackage에서 ExtractedEntity를 올바르게 추출하는지 검증한다."""

    def setUp(self) -> None:
        self.extractor = LLMExtractor(FakeExtractionClient())
        self.sample_package = AssetPackage(
            asset_id="test_001",
            asset_name="Robot Arm A",
            asset_type="robot_arm",
            manufacturer="ROBOTIS",
            model_name="RM-P60-RH",
            user_inputs={
                "rated_voltage": "24V",
                "rated_current": "1.5A",
                "weight": "3.5kg",
                "max_torque": "2.5Nm",
            },
        )

    def test_extract_returns_list(self) -> None:
        """extract()가 리스트를 반환한다."""
        result = self.extractor.extract(self.sample_package)
        self.assertIsInstance(result, list)

    def test_extract_returns_extracted_entity_instances(self) -> None:
        """반환된 항목이 ExtractedEntity dataclass 인스턴스다."""
        result = self.extractor.extract(self.sample_package)
        self.assertGreater(len(result), 0, "최소 1개 이상의 속성이 추출되어야 합니다.")
        for entity in result:
            self.assertIsInstance(entity, ExtractedEntity)

    def test_extract_has_required_fields(self) -> None:
        """각 ExtractedEntity가 raw_name, raw_value를 가진다."""
        result = self.extractor.extract(self.sample_package)
        for entity in result:
            self.assertTrue(entity.raw_name, "raw_name이 비어있으면 안 됩니다.")
            self.assertIsNotNone(entity.raw_value, "raw_value가 None이면 안 됩니다.")

    def test_extract_source_is_llm(self) -> None:
        """LLM이 추출한 속성의 source가 'llm_extraction'이다."""
        result = self.extractor.extract(self.sample_package)
        for entity in result:
            self.assertEqual(entity.source, "llm_extraction")

    def test_extract_confidence_in_range(self) -> None:
        """confidence 값이 0.0~1.0 사이다."""
        result = self.extractor.extract(self.sample_package)
        for entity in result:
            self.assertGreaterEqual(entity.confidence, 0.0)
            self.assertLessEqual(entity.confidence, 1.0)

    def test_extract_empty_package_returns_empty_list(self) -> None:
        """user_inputs가 없고 기본 정보만 있는 패키지는 빈 리스트를 반환하거나 적게 추출된다."""
        empty_package = AssetPackage(
            asset_id="empty_001",
            asset_name="",
            asset_type="unknown",
        )
        result = self.extractor.extract(empty_package)
        self.assertIsInstance(result, list)

    def test_extract_accepts_cv_output(self) -> None:
        """cv_output 파라미터를 받아도 정상 동작한다."""
        cv = CVOutput(predicted_type="robot_arm", confidence=0.95)
        result = self.extractor.extract(self.sample_package, cv_output=cv)
        self.assertIsInstance(result, list)

    def test_extract_detects_voltage(self) -> None:
        """rated_voltage 입력에서 전압 관련 속성이 추출된다."""
        result = self.extractor.extract(self.sample_package)
        names = [e.raw_name.lower() for e in result]
        has_voltage = any("voltage" in n or "volt" in n for n in names)
        self.assertTrue(has_voltage, f"전압 속성이 추출되지 않았습니다. 추출된 속성: {names}")

    def test_extract_filters_pdf_web_and_bom_noise(self) -> None:
        """웹페이지 URL 조각과 BOM 수량 행은 entity에서 제거한다."""
        result = self.extractor.extract(self.sample_package)
        names = {e.raw_name.lower() for e in result}
        self.assertNotIn("https", names)
        self.assertNotIn("usb cable", names)


if __name__ == "__main__":
    unittest.main()
