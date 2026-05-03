from __future__ import annotations

import unittest

from app.pipeline import create_default_pipeline
from app.sample_data import sample_payload


class PipelineTest(unittest.TestCase):
    """샘플 입력이 전체 MVP 파이프라인을 통과하는지 검증한다."""

    def setUp(self) -> None:
        """각 테스트에서 같은 샘플 실행 결과를 사용한다."""
        self.result = create_default_pipeline().run(sample_payload())

    def test_pipeline_generates_valid_aas(self) -> None:
        """AAS Generator가 필수 구조를 갖춘 JSON을 만드는지 확인한다."""
        self.assertTrue(self.result.aas_validation["is_valid"])
        self.assertIn("assetAdministrationShells", self.result.aas_json)
        self.assertIn("submodels", self.result.aas_json)

    def test_semantic_nodes_are_mapped_to_properties(self) -> None:
        """Semantic Node가 주요 AAS Property 후보와 매칭되는지 확인한다."""
        self.assertGreaterEqual(len(self.result.semantic_nodes), 7)
        id_shorts = {item.idShort for item in self.result.matched_properties}
        self.assertIn("NominalVoltage", id_shorts)
        self.assertIn("RatedCurrent", id_shorts)
        self.assertIn("ManufacturerName", id_shorts)

    def test_model_reference_is_in_mapping_plan(self) -> None:
        """3D 모델 참조 정보가 ProvisionOf3DModels Submodel에 포함되는지 확인한다."""
        provision = next(
            item
            for item in self.result.aas_mapping_plan["submodels"]
            if item["idShort"] == "ProvisionOf3DModels"
        )
        id_shorts = {item["idShort"] for item in provision["properties"]}
        self.assertIn("ModelFile", id_shorts)
        self.assertIn("ModelFormat", id_shorts)

    def test_dt_validation_passes_with_sample_sensor_values(self) -> None:
        """샘플 센서값으로 DT 등록/동작 검증이 성공하는지 확인한다."""
        self.assertEqual("success", self.result.dt_registration.registration_status)
        self.assertEqual("passed", self.result.dt_validation.overall_status)


if __name__ == "__main__":
    unittest.main()
