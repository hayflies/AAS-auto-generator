from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.config import PipelineConfig
from app.models import (
    AASPropertyCandidate,
    CVOutput,
    MatchedProperty,
    MatchResult,
    PipelineResult,
)
from interfaces.base_aas_generator import BaseAASGenerator
from interfaces.base_cv import BaseCVModel
from interfaces.base_dt_adapter import BaseDTAdapter
from interfaces.base_extractor import BaseInformationExtractor
from interfaces.base_input import BaseInputLayer
from interfaces.base_mapper import BaseAASMapper
from interfaces.base_matcher import BaseEntityMatcher
from interfaces.base_model_generator import BaseModelGenerator
from interfaces.base_retriever import BaseCandidateRetriever
from interfaces.base_semantic_builder import BaseSemanticNodeBuilder
from interfaces.base_validator import BaseDTValidator
from modules.aas_generation import JsonAASGenerator
from modules.aas_mapping import TemplateAwareAASMapper
from modules.cv import NoOpCVModel, YOLOPartDetector
from modules.dt_integration import InMemoryDTAdapter
from modules.extraction import LLMExtractor, ManualInputExtractor
from modules.input_layer import DefaultInputLayer
from modules.semantic_node.llm_semantic_builder import LLMSemanticNodeBuilder
from modules.matching import LLMMatcher
from modules.model_3d import DefaultModelManager
from modules.normalization import ValueNormalizer
from modules.retrieval.hybrid_retriever import HybridStandardsCandidateRetriever
from modules.validation import DefaultDTValidator


@dataclass
class AASAutoGenerationPipeline:
    """description.md의 전체 시스템 흐름을 코드로 조립한 오케스트레이터.

    이 클래스는 각 단계의 구체 구현을 직접 알지 않고 interface만 호출한다.
    따라서 OCR, LLM, embedding retriever, DT adapter 같은 구현체를 바꿔도
    전체 실행 순서는 유지된다.
    """

    config: PipelineConfig
    input_layer: BaseInputLayer
    extractor: BaseInformationExtractor
    semantic_builder: BaseSemanticNodeBuilder
    retriever: BaseCandidateRetriever
    matcher: BaseEntityMatcher
    model_manager: BaseModelGenerator
    mapper: BaseAASMapper
    aas_generator: BaseAASGenerator
    dt_adapter: BaseDTAdapter
    validator: BaseDTValidator
    cv_model: BaseCVModel | None = None

    def run(
        self,
        payload: dict[str, Any],
        sensor_values: dict[str, Any] | None = None,
    ) -> PipelineResult:
        """입력 payload 하나를 AAS 생성과 DT 검증까지 순차 처리한다."""

        # 1~2. 입력 payload를 표준 AssetPackage로 정규화하고 파일 입력은 텍스트로 변환한다.
        asset_package = self.input_layer.collect(payload)

        # 선택 CV 모듈이다. 명판/OCR 흐름과 독립적으로 자산 유형 힌트만 보강한다.
        cv_output = self._run_optional_cv(asset_package.images)

        # 3. 원천 텍스트/입력에서 속성을 추출하고 Semantic Node로 구조화한다.
        extracted_entities = self.extractor.extract(asset_package, cv_output)
        semantic_nodes = ValueNormalizer().normalize_nodes(
            self.semantic_builder.build(extracted_entities)
        )

        candidates_by_node: dict[str, list[AASPropertyCandidate]] = {}
        match_results: list[MatchResult] = []
        matched_properties: list[MatchedProperty] = []

        # 4~6. 표준 후보군을 top-k로 찾고, matcher가 후보군을 재랭킹해 property/eclass를 고른다.
        for node in semantic_nodes:
            candidates = self.retriever.retrieve(node, self.config.top_k_candidates)
            candidates_by_node[node.semantic_node_id] = candidates
            node_matches = self.matcher.match_candidates(node, candidates)
            match_results.extend(node_matches)

            best_match = self._best_match(node_matches)
            if best_match and best_match.candidate:
                candidate = best_match.candidate
                matched_properties.append(
                    MatchedProperty(
                        semantic_node_id=node.semantic_node_id,
                        aas_property_id=candidate.candidate_id,
                        submodel=candidate.submodel,
                        idShort=candidate.idShort,
                        value=node.value,
                        unit=node.unit or candidate.preferred_unit,
                        match_score=best_match.match_score,
                        semantic_id=candidate.semantic_id,
                        eclass_irdi=candidate.eclass_irdi or node.eclass_irdi,
                        source=candidate.source,
                        path=candidate.path,
                        element_type=candidate.element_type,
                        value_type=candidate.value_type,
                        cardinality=candidate.cardinality,
                        definition=candidate.definition,
                        template_id=candidate.template_id,
                        review_required=best_match.match_score < self.config.human_review_threshold,
                        reason=best_match.reason,
                    )
                )

        # 선택 산출물이다. 3D 모델은 AAS 안에 넣지 않고 파일 참조 정보만 준비한다.
        model_info = self.model_manager.generate_model(
            asset_package.images,
            asset_package.to_dict(),
        )

        # 7~9. Submodel Template-aware mapping plan을 만들고 ConceptDescription 포함 AAS를 생성한다.
        mapping_plan = self.mapper.map(asset_package, matched_properties, model_info)
        aas_json = self.aas_generator.generate(mapping_plan)
        aas_validation = self.aas_generator.validate(aas_json)

        # 생성된 AAS와 모델 참조를 DT adapter에 등록하고 mock 센서값으로 검증한다.
        dt_registration = self.dt_adapter.register_asset(aas_json, model_info.to_dict())
        dt_validation = self.validator.validate(
            dt_registration,
            sensor_values or self._default_sensor_values(asset_package.user_inputs),
        )

        return PipelineResult(
            asset_package=asset_package,
            cv_output=cv_output,
            extracted_entities=extracted_entities,
            semantic_nodes=semantic_nodes,
            candidates_by_node=candidates_by_node,
            match_results=match_results,
            matched_properties=matched_properties,
            aas_mapping_plan=mapping_plan,
            model_info=model_info,
            aas_json=aas_json,
            aas_validation=aas_validation,
            dt_registration=dt_registration,
            dt_validation=dt_validation,
        )

    def _run_optional_cv(self, images: list[str]) -> CVOutput | None:
        """Optional CV Module을 실행한다.

        현재는 NoOp 구현체가 기본값이지만, 추후 YOLO/SAM/Vision LLM adapter로
        교체해도 pipeline.run의 나머지 코드는 바뀌지 않는다.
        """

        if not self.cv_model or not images:
            return None
        cv_output = self.cv_model.classify(images)
        cv_output.segmented_images = self.cv_model.segment(images)
        return cv_output

    def _best_match(self, results: list[MatchResult]) -> MatchResult | None:
        """한 Semantic Node에 대한 match 결과 중 점수가 가장 높은 것을 고른다."""
        valid_results = [item for item in results if item.match]
        if not valid_results:
            return None
        return max(valid_results, key=self._match_rank)

    def _match_rank(self, item: MatchResult) -> tuple[float, int]:
        source = item.candidate.source if item.candidate else ""
        source_rank = {
            "submodel_template": 4,
            "project_repository": 3,
            "iec_cdd_dictionary": 2,
            "eclass_dictionary": 1,
        }.get(source, 0)
        return (item.match_score, source_rank)

    def _default_sensor_values(self, user_inputs: dict[str, Any]) -> dict[str, Any]:
        """사용자 입력에 테스트 센서값이 없을 때 DT 검증용 기본값을 제공한다."""
        return dict(
            user_inputs.get(
                "test_sensor_values",
                {
                    "rotation_angle": 30,
                    "temperature": 80,
                    "status": "running",
                },
            )
        )


def create_default_pipeline(config: PipelineConfig | None = None) -> AASAutoGenerationPipeline:
    """외부 의존성 없이 실행 가능한 기본 파이프라인을 조립한다.

    이 함수가 현재 MVP의 composition root이다. 실제 OCR/LLM/vector DB/DT
    구현을 붙일 때는 여기에서 해당 adapter만 교체하면 된다.
    """

    config = config or PipelineConfig()
    project_property_path = (
        config.project_root
        / "repositories"
        / "aas_property_repository"
        / "properties.json"
    )
    template_path = (
        config.project_root
        / "repositories"
        / "submodel_templates"
        / "default_submodels.json"
    )
    template_root = (
        config.project_root
        / "repositories"
        / "submodel_templates"
        / "admin_shell_io_submodel_templates"
        / "published"
    )
    eclass_path = (
        config.project_root
        / "repositories"
        / "eclass_dictionary"
        / "eclass_properties.json"
    )
    iec_cdd_path = (
        config.project_root
        / "repositories"
        / "iec_cdd_dictionary"
        / "iec_cdd_properties.json"
    )
    dt_adapter = InMemoryDTAdapter(config)
    return AASAutoGenerationPipeline(
        config=config,
        input_layer=DefaultInputLayer(),
        cv_model=NoOpCVModel(),
        extractor=ManualInputExtractor(),
        semantic_builder=LLMSemanticNodeBuilder(skip_enrichment=True),
        retriever=HybridStandardsCandidateRetriever(
            template_root=template_root,
            eclass_path=eclass_path,
            iec_cdd_path=iec_cdd_path,
            project_property_path=project_property_path,
            use_embeddings=False,
        ),
        matcher=LLMMatcher(threshold=config.match_threshold, skip_llm=True),
        model_manager=DefaultModelManager(config),
        mapper=TemplateAwareAASMapper(
            default_submodels_path=template_path,
            template_root=template_root,
            review_threshold=config.human_review_threshold,
        ),
        aas_generator=JsonAASGenerator(),
        dt_adapter=dt_adapter,
        validator=DefaultDTValidator(dt_adapter),
    )


def create_llm_pipeline(config: PipelineConfig | None = None) -> AASAutoGenerationPipeline:
    """Ollama extraction/enrichment pipeline with the same standards-aware mapping."""

    config = config or PipelineConfig()
    pipeline = create_default_pipeline(config)
    ollama_available = False
    try:
        from modules.llm import OllamaClient

        client = OllamaClient()
        ollama_available = client.is_available()
    except Exception:
        client = None

    if not ollama_available:
        print("[Pipeline] Ollama unavailable, llm pipeline falls back to deterministic matching.")

    pipeline.extractor = LLMExtractor(client=client) if ollama_available and client else ManualInputExtractor()
    pipeline.semantic_builder = LLMSemanticNodeBuilder(
        client=client,
        skip_enrichment=not ollama_available,
    )
    pipeline.matcher = LLMMatcher(
        client=client,
        threshold=config.match_threshold,
        skip_llm=not ollama_available,
    )
    pipeline.mapper = TemplateAwareAASMapper(
        default_submodels_path=config.project_root
        / "repositories"
        / "submodel_templates"
        / "default_submodels.json",
        template_root=config.project_root
        / "repositories"
        / "submodel_templates"
        / "admin_shell_io_submodel_templates"
        / "published",
        review_threshold=config.human_review_threshold,
        llm_client=client,
        use_llm_template_selection=ollama_available,
    )
    try:
        pipeline.retriever = HybridStandardsCandidateRetriever(
            template_root=config.project_root
            / "repositories"
            / "submodel_templates"
            / "admin_shell_io_submodel_templates"
            / "published",
            eclass_path=config.project_root / "repositories" / "eclass_dictionary" / "eclass_properties.json",
            iec_cdd_path=config.project_root / "repositories" / "iec_cdd_dictionary" / "iec_cdd_properties.json",
            project_property_path=config.project_root
            / "repositories"
            / "aas_property_repository"
            / "properties.json",
            embedding_model=client,
            use_embeddings=ollama_available and client is not None,
        )
    except Exception as exc:
        print(f"[Pipeline] Ollama embedding retriever unavailable, lexical fallback kept: {exc}")
    return pipeline


def create_yolo_pipeline(config: PipelineConfig | None = None) -> AASAutoGenerationPipeline:
    """Compatibility factory for CLI modes that want CV later."""

    pipeline = create_default_pipeline(config)
    try:
        pipeline.cv_model = YOLOPartDetector()
    except Exception as exc:
        print(f"[Pipeline] YOLO unavailable, NoOpCVModel kept: {exc}")
    return pipeline


def create_llm_yolo_pipeline(config: PipelineConfig | None = None) -> AASAutoGenerationPipeline:
    """Compatibility factory for LLM + CV mode."""

    pipeline = create_llm_pipeline(config)
    try:
        pipeline.cv_model = YOLOPartDetector()
    except Exception as exc:
        print(f"[Pipeline] YOLO unavailable, NoOpCVModel kept: {exc}")
    return pipeline
