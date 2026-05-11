from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


def _compact(value: dict[str, Any]) -> dict[str, Any]:
    """JSON 출력에서 값이 없는 선택 필드를 제거해 결과를 읽기 쉽게 만든다."""
    return {key: item for key, item in value.items() if item is not None}


@dataclass
class AssetPackage:
    """Input Layer가 만든 표준 자산 입력 묶음.

    이미지, 문서, 사용자 입력을 하나의 JSON 친화적인 구조로 묶어 이후
    추출/매핑/생성 단계가 같은 입력 계약을 바라보게 한다.
    """

    asset_id: str
    asset_name: str
    asset_type: str
    manufacturer: str | None = None
    model_name: str | None = None
    images: list[str] = field(default_factory=list)
    documents: list[str] = field(default_factory=list)
    user_inputs: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """파이프라인 결과 저장을 위한 dict 표현을 반환한다."""
        return _compact(asdict(self))


@dataclass
class CVOutput:
    """Optional CV Module의 출력 구조.

    현재 기본 구현은 비어 있을 수 있지만, 추후 분류/세그멘테이션 모델이
    들어와도 이 데이터 계약은 유지된다.
    """

    predicted_type: str | None = None
    confidence: float = 0.0
    segmented_images: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return _compact(asdict(self))


@dataclass
class ExtractedEntity:
    """Information Extraction Layer가 추출한 원천 속성.

    이 단계는 AAS 구조를 만들지 않고, OCR/문서/수동 입력/LLM에서 얻은
    raw attribute만 담는다.
    """

    raw_name: str
    raw_value: Any
    raw_unit: str | None = None
    source: str = "manual_input"
    confidence: float = 1.0
    source_reference: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return _compact(asdict(self))


@dataclass
class SemanticNode:
    """AAS 매핑 전 단계의 의미 중간 표현.

    논문 구조의 Semantic Node 개념을 코드로 표현한 것으로, 후보 검색과
    entity matching의 기준 입력이 된다.
    """

    semantic_node_id: str
    name: str
    value: Any
    unit: str | None
    value_type: str
    conceptual_definition: str
    affordance: str
    source_description: str
    source_reference: str | None = None
    confidence: float = 1.0
    eclass_irdi: str | None = None  # ECLASS 사전 조회로 채워짐

    def to_dict(self) -> dict[str, Any]:
        return _compact(asdict(self))


@dataclass
class AASPropertyCandidate:
    """Semantic Node와 매칭될 수 있는 AAS Property 후보."""

    candidate_id: str
    idShort: str
    description: str
    submodel: str
    semantic_id: str | None = None
    preferred_unit: str | None = None
    aliases: list[str] = field(default_factory=list)
    similarity_score: float = 0.0
    eclass_irdi: str | None = None  # properties.json에서 로드됨
    source: str = "project_repository"
    path: str | None = None
    element_type: str = "Property"
    value_type: str | None = None
    cardinality: str | None = None
    definition: str | None = None
    template_id: str | None = None
    allowed_values: list[str] = field(default_factory=list)
    source_priority: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return _compact(asdict(self))


@dataclass
class MatchResult:
    """Semantic Node와 후보 AAS Property의 비교 결과."""

    semantic_node_id: str
    selected_candidate_id: str | None
    match: bool
    match_score: float
    reason: str
    candidate: AASPropertyCandidate | None = None

    def to_dict(self) -> dict[str, Any]:
        data = _compact(asdict(self))
        if self.candidate is not None:
            data["candidate"] = self.candidate.to_dict()
        return data


@dataclass
class MatchedProperty:
    """최종 선택된 AAS Property 매핑 결과.

    AAS Mapping Engine은 이 구조를 받아 Submodel별 배치를 수행한다.
    """

    semantic_node_id: str
    aas_property_id: str
    submodel: str
    idShort: str
    value: Any
    unit: str | None
    match_score: float
    semantic_id: str | None = None
    eclass_irdi: str | None = None
    source: str | None = None
    path: str | None = None
    element_type: str = "Property"
    value_type: str | None = None
    cardinality: str | None = None
    definition: str | None = None
    template_id: str | None = None
    review_required: bool = False
    mapping_status: str = "mapped"
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return _compact(asdict(self))


@dataclass
class ModelInfo:
    """DT 환경에 연결할 3D 모델 참조 정보."""

    model_path: str
    model_format: str
    generation_method: str
    scale: list[float] = field(default_factory=lambda: [1.0, 1.0, 1.0])
    position: list[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    rotation: list[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])

    def to_dict(self) -> dict[str, Any]:
        return _compact(asdict(self))


@dataclass
class DTRegistrationResult:
    """DT Integration Layer의 자산 등록 결과."""

    dt_asset_id: str
    registration_status: str
    viewer_url: str

    def to_dict(self) -> dict[str, Any]:
        return _compact(asdict(self))


@dataclass
class ValidationResult:
    """임의 센서값 기반 DT 동작 검증 결과."""

    movement_test: bool
    state_change_test: bool
    visual_update_test: bool
    overall_status: str

    def to_dict(self) -> dict[str, Any]:
        return _compact(asdict(self))


@dataclass
class PipelineResult:
    """전체 파이프라인 실행 결과.

    각 단계 산출물을 모두 보존해 디버깅, 평가 지표 계산, 사용자 검토 UI에
    활용할 수 있게 한다.
    """

    asset_package: AssetPackage
    cv_output: CVOutput | None
    extracted_entities: list[ExtractedEntity]
    semantic_nodes: list[SemanticNode]
    candidates_by_node: dict[str, list[AASPropertyCandidate]]
    match_results: list[MatchResult]
    matched_properties: list[MatchedProperty]
    aas_mapping_plan: dict[str, Any]
    model_info: ModelInfo
    aas_json: dict[str, Any]
    aas_validation: dict[str, Any]
    dt_registration: DTRegistrationResult
    dt_validation: ValidationResult

    def to_dict(self) -> dict[str, Any]:
        return {
            "asset_package": self.asset_package.to_dict(),
            "cv_output": self.cv_output.to_dict() if self.cv_output else None,
            "extracted_entities": [item.to_dict() for item in self.extracted_entities],
            "semantic_nodes": [item.to_dict() for item in self.semantic_nodes],
            "candidates_by_node": {
                key: [candidate.to_dict() for candidate in candidates]
                for key, candidates in self.candidates_by_node.items()
            },
            "match_results": [item.to_dict() for item in self.match_results],
            "matched_properties": [item.to_dict() for item in self.matched_properties],
            "aas_mapping_plan": self.aas_mapping_plan,
            "model_info": self.model_info.to_dict(),
            "aas_json": self.aas_json,
            "aas_validation": self.aas_validation,
            "dt_registration": self.dt_registration.to_dict(),
            "dt_validation": self.dt_validation.to_dict(),
        }
