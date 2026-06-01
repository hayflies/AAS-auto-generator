from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from app.config import DEFAULT_EMBEDDING_MODEL, PipelineConfig, SEMANTIC_NODE_LLM_MODEL
from app.models import (
    AASPropertyCandidate,
    CVOutput,
    MatchedProperty,
    MatchResult,
    PipelineResult,
)
from interfaces.base_aas_generator import BaseAASGenerator
from interfaces.base_embedding import BaseEmbeddingModel
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
from interfaces.base_llm import BaseLLM
from modules.aas_generation import JsonAASGenerator
from modules.aas_mapping import TemplateAwareAASMapper
from modules.cv import NoOpCVModel, YOLOPartDetector
from modules.dt_integration import InMemoryDTAdapter
from modules.extraction import LLMExtractor, ManualInputExtractor
from modules.input_layer import DefaultInputLayer
from modules.input_layer.document_processor import DocumentProcessor
from modules.semantic_node.default_builder import DefaultSemanticNodeBuilder
from modules.semantic_node.llm_semantic_builder import LLMSemanticNodeBuilder
from modules.matching import LLMMatcher
from modules.model_3d import DefaultModelManager
from modules.normalization import ValueNormalizer
from modules.retrieval.hybrid_retriever import HybridStandardsCandidateRetriever
from modules.dt_validation import DefaultDTValidator
from modules.validation import DefaultMappingValidator


class PipelineConfigurationError(RuntimeError):
    """Raised when a configured concrete pipeline module is unavailable."""


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
    mapping_validator: DefaultMappingValidator
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
        mapping_validation = self.mapping_validator.validate(
            semantic_nodes=semantic_nodes,
            candidates_by_node=candidates_by_node,
            match_results=match_results,
            matched_properties=matched_properties,
            mapping_plan=mapping_plan,
        )
        aas_json = self.aas_generator.generate(mapping_plan)
        aas_validation = self.aas_generator.validate(aas_json)

        # 생성된 AAS와 모델 참조를 DT adapter에 등록하고 mock 센서값으로 보조 검증한다.
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
            mapping_validation=mapping_validation,
            model_info=model_info,
            aas_json=aas_json,
            aas_validation=aas_validation,
            dt_registration=dt_registration,
            dt_validation=dt_validation,
        )

    def _run_optional_cv(self, images: list[str]) -> CVOutput | None:
        """Optional CV Module을 실행한다.

        CV 모듈이 연결된 경우에만 실행한다. YOLO/SAM/Vision LLM adapter로
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
    """구체 모듈을 연결한다.

    기본 정책은 fail-fast이다. Ollama/embedding처럼 설정된 구체 모듈이 준비되지
    않았으면 default 구현으로 조용히 내려가지 않고 안내 예외를 발생시킨다.
    테스트나 오프라인 데모가 필요할 때만 config.allow_module_fallback=True를
    명시해 이전 fallback 동작을 사용할 수 있다.
    """

    config = config or PipelineConfig()
    paths = _pipeline_paths(config)
    llm_client = _create_llm_client(config)
    embedding_model = _create_embedding_model(config)
    llm_available = llm_client is not None
    embedding_available = embedding_model is not None
    dt_adapter = InMemoryDTAdapter(config)

    if config.allow_module_fallback and not llm_available:
        print("[Pipeline] LLM unavailable, default modules kept for LLM-dependent stages.")
    if config.allow_module_fallback and not embedding_available:
        print("[Pipeline] Embedding unavailable, lexical retrieval fallback kept.")

    return AASAutoGenerationPipeline(
        config=config,
        input_layer=DefaultInputLayer(
            processor=DocumentProcessor(
                client=llm_client,
                skip_llm_cleaning=not llm_available,
                fail_fast=not config.allow_module_fallback,
            )
        ),
        cv_model=_create_cv_model(config),
        extractor=LLMExtractor(
            client=llm_client,
            fail_fast=not config.allow_module_fallback,
        ) if llm_available else ManualInputExtractor(),
        semantic_builder=_create_semantic_builder(config, llm_client, llm_available),
        retriever=HybridStandardsCandidateRetriever(
            template_root=paths["template_root"],
            eclass_path=paths["eclass_path"],
            iec_cdd_path=paths["iec_cdd_path"],
            embedding_model=embedding_model,
            use_embeddings=embedding_available,
            fail_on_embedding_error=not config.allow_module_fallback,
        ),
        matcher=LLMMatcher(
            client=llm_client,
            threshold=config.match_threshold,
            skip_llm=not llm_available,
            fail_fast=not config.allow_module_fallback,
        ),
        model_manager=DefaultModelManager(config),
        mapper=TemplateAwareAASMapper(
            default_submodels_path=paths["default_submodels_path"],
            template_root=paths["template_root"],
            review_threshold=config.human_review_threshold,
            llm_client=llm_client,
            use_llm_template_selection=llm_available,
            fail_fast=not config.allow_module_fallback,
        ),
        aas_generator=JsonAASGenerator(),
        mapping_validator=DefaultMappingValidator(top_k=config.top_k_candidates),
        dt_adapter=dt_adapter,
        validator=DefaultDTValidator(dt_adapter),
    )


def _pipeline_paths(config: PipelineConfig) -> dict[str, Any]:
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
    return {
        "default_submodels_path": template_path,
        "template_root": template_root,
        "eclass_path": eclass_path,
        "iec_cdd_path": iec_cdd_path,
    }


def _create_llm_client(config: PipelineConfig) -> BaseLLM | None:
    if not config.require_llm and config.allow_module_fallback:
        return None

    provider = config.llm_provider.strip().lower()
    try:
        if provider != "ollama":
            raise PipelineConfigurationError(
                "Only Ollama llama3.2 is enabled for semantic node generation. "
                "Set llm_provider='ollama'."
            )
        if config.ollama_llm_model_name != SEMANTIC_NODE_LLM_MODEL:
            raise PipelineConfigurationError(
                "Semantic node generation is fixed to Ollama llama3.2. "
                f"Set ollama_llm_model_name='{SEMANTIC_NODE_LLM_MODEL}'."
            )

        from modules.llm import OllamaClient

        embedding_model_name = config.embedding_model_name or DEFAULT_EMBEDDING_MODEL
        client = OllamaClient(
            model=SEMANTIC_NODE_LLM_MODEL,
            embedding_model=embedding_model_name,
        )
        if client.is_available() and client.has_model(SEMANTIC_NODE_LLM_MODEL):
            return client
        raise PipelineConfigurationError(
            "Ollama LLM server/model is unavailable. Start Ollama and run "
            f"`ollama pull {SEMANTIC_NODE_LLM_MODEL}`."
        )
    except PipelineConfigurationError:
        if config.allow_module_fallback:
            return None
        raise


def _create_semantic_builder(
    config: PipelineConfig,
    llm_client: BaseLLM | None,
    llm_available: bool,
) -> BaseSemanticNodeBuilder:
    if not llm_available or llm_client is None:
        return DefaultSemanticNodeBuilder()

    return LLMSemanticNodeBuilder(
        client=llm_client,
        skip_enrichment=False,
        fail_fast=not config.allow_module_fallback,
        semantic_batch_size=config.semantic_batch_size,
    )


def _create_embedding_model(config: PipelineConfig) -> BaseEmbeddingModel | None:
    if not config.require_embedding and config.allow_module_fallback:
        return None

    try:
        from modules.llm import OllamaClient

        embedding_model_name = config.embedding_model_name or DEFAULT_EMBEDDING_MODEL
        client = OllamaClient(
            model=SEMANTIC_NODE_LLM_MODEL,
            embedding_model=embedding_model_name,
        )
        if client.is_available() and client.has_model(embedding_model_name):
            return client
        raise PipelineConfigurationError(
            "Ollama embedding server/model is unavailable. Start Ollama and run "
            f"`ollama pull {embedding_model_name}`."
        )
    except PipelineConfigurationError:
        if config.allow_module_fallback:
            return None
        raise


def _create_cv_model(config: PipelineConfig) -> BaseCVModel | None:
    try:
        return YOLOPartDetector()
    except Exception as exc:
        if config.require_cv_model:
            raise PipelineConfigurationError(
                "YOLO CV module was requested but is unavailable. "
                "Install ultralytics and configure weights, or run a non-YOLO pipeline."
            ) from exc
        if not config.allow_module_fallback:
            return None
        print(f"[Pipeline] YOLO unavailable, NoOpCVModel kept: {exc}")
        return NoOpCVModel()


def create_llm_pipeline(config: PipelineConfig | None = None) -> AASAutoGenerationPipeline:
    """Compatibility factory: default composition already activates LLM modules when available."""

    return create_default_pipeline(config)


def create_yolo_pipeline(config: PipelineConfig | None = None) -> AASAutoGenerationPipeline:
    """Compatibility factory for CLI modes that want CV later."""

    config = replace(config or PipelineConfig(), require_cv_model=True)
    return create_default_pipeline(config)


def create_llm_yolo_pipeline(config: PipelineConfig | None = None) -> AASAutoGenerationPipeline:
    """Compatibility factory for LLM + CV mode."""

    config = replace(config or PipelineConfig(), require_cv_model=True)
    return create_default_pipeline(config)
