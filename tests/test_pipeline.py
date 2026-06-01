from __future__ import annotations

import unittest
from unittest.mock import patch

from app.config import PipelineConfig
from app.pipeline import PipelineConfigurationError, create_default_pipeline
from app.sample_data import sample_payload


class PipelineTest(unittest.TestCase):
    """샘플 입력이 전체 MVP 파이프라인을 통과하는지 검증한다."""

    def setUp(self) -> None:
        """각 테스트에서 같은 샘플 실행 결과를 사용한다."""
        config = PipelineConfig(
            require_llm=False,
            require_embedding=False,
            allow_module_fallback=True,
        )
        self.result = create_default_pipeline(config).run(sample_payload())

    def test_default_pipeline_requires_configured_llm(self) -> None:
        """기본 실행은 Ollama llama3.2가 없으면 default fallback 없이 멈춘다."""
        config = PipelineConfig(
            require_embedding=False,
        )
        with patch("modules.llm.ollama_client.OllamaClient.is_available", return_value=False):
            with self.assertRaises(PipelineConfigurationError):
                create_default_pipeline(config)

    def test_default_pipeline_rejects_non_llama32_semantic_llm(self) -> None:
        """Semantic Node 생성 LLM은 llama3.2 외 모델로 바꿀 수 없다."""
        config = PipelineConfig(
            ollama_llm_model_name="llama3.1",
            require_embedding=False,
        )
        with self.assertRaises(PipelineConfigurationError):
            create_default_pipeline(config)

    def test_pipeline_generates_valid_aas(self) -> None:
        """AAS Generator가 필수 구조를 갖춘 JSON을 만드는지 확인한다."""
        self.assertTrue(self.result.aas_validation["is_valid"])
        self.assertIn("assetAdministrationShells", self.result.aas_json)
        self.assertIn("submodels", self.result.aas_json)

    def test_semantic_nodes_are_mapped_to_properties(self) -> None:
        """Semantic Node가 주요 AAS Property 후보와 매칭되는지 확인한다."""
        self.assertGreaterEqual(len(self.result.semantic_nodes), 7)
        id_shorts = {item.idShort for item in self.result.matched_properties}
        self.assertTrue(id_shorts & {"NominalVoltage", "RatedVoltage", "Voltage"})
        self.assertTrue(id_shorts & {"RatedCurrent", "RatedOperationalCurrent", "NominalCurrent", "Current"})
        self.assertTrue(id_shorts & {"ManufacturerName", "Manufacturer"})

    def test_project_repository_candidates_are_excluded(self) -> None:
        """프로젝트 자체 properties.json 후보는 후보군에서 제외된다."""
        sources = {
            candidate.source
            for candidates in self.result.candidates_by_node.values()
            for candidate in candidates
        }
        self.assertNotIn("project_repository", sources)

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

    def test_mapping_validation_reports_ddms_metrics(self) -> None:
        """AAS 매핑 품질 검증이 DDMS식 ranking 지표를 반환하는지 확인한다."""
        validation = self.result.mapping_validation
        self.assertIn(validation.overall_status, {"passed", "review", "failed"})
        self.assertIn("candidate_coverage", validation.ddms_metrics)
        self.assertIn("hit_at_10", validation.ddms_metrics)
        self.assertIn("mrr_at_10", validation.ddms_metrics)


if __name__ == "__main__":
    unittest.main()
