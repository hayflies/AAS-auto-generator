# AAS-auto-generator 코드 가이드

이 문서는 `AAS-auto-generator` 저장소의 하위 디렉토리와 주요 소스코드가 어떤 역할을 하는지 설명합니다.

## 전체 구조

이 프로젝트는 **입력 자산 정보 → 의미 노드 생성 → AAS 속성 매칭 → AAS JSON 생성 → DT 등록/검증** 흐름을 가진 MVP 파이프라인입니다.

전체 실행 흐름은 다음과 같습니다.

```text
Input Layer
→ Optional CV Module
→ Information Extraction Layer
→ Semantic Node Builder
→ Candidate Retrieval Engine
→ Entity Matching Engine
→ AAS Mapping Engine
→ 3D Model Manager
→ AAS Generator
→ DT Integration Layer
→ DT Validation Layer
```

핵심 오케스트레이터는 `app/pipeline.py`입니다. `interfaces/`는 교체 가능한 추상 계약을 정의하고, `modules/`는 현재 외부 서비스 없이 동작하는 기본 구현체를 제공합니다.

## 최상위 파일

- `main.py`: CLI 실행 진입점입니다. 실제 실행 로직은 `app/main.py`에 있습니다.
- `README.md`: 프로젝트 개요, 실행 방법, 테스트 방법, 교체 가능한 모듈 설명이 정리되어 있습니다.
- `pyproject.toml`: 프로젝트 메타데이터와 테스트 설정입니다. 현재 외부 의존성은 없습니다.
- `description.md`: 시스템 설계 설명 문서입니다.
- `code_guide.md`: 저장소 구조와 코드 역할을 설명하는 현재 문서입니다.

## app/

애플리케이션의 중심 계층입니다. 파이프라인 조립, 실행 설정, 데이터 모델, CLI 처리, 샘플 데이터, 문자열 유틸리티가 들어 있습니다.

- `app/pipeline.py`: 전체 파이프라인을 조립하고 순서대로 실행하는 오케스트레이터입니다. `create_default_pipeline()`에서 기본 구현체들을 연결합니다.
- `app/main.py`: CLI 인자 처리, 입력 JSON 로드, 파이프라인 실행, 결과 파일 저장을 담당합니다.
- `app/models.py`: `AssetPackage`, `SemanticNode`, `MatchedProperty`, `ModelInfo`, `PipelineResult` 등 전 단계에서 공유하는 데이터 모델을 정의합니다.
- `app/config.py`: 출력 경로, 후보 개수, 매칭 임계값, DT viewer URL 같은 실행 설정을 관리합니다.
- `app/sample_data.py`: 외부 OCR, LLM, 3D 생성기 없이도 전체 흐름을 테스트할 수 있는 샘플 Robot Arm 입력 데이터를 제공합니다.
- `app/text.py`: 라벨 정규화, 토큰화, slug 생성, AAS `idShort` 생성 같은 문자열 유틸리티를 제공합니다.

## interfaces/

각 기능의 추상 인터페이스를 정의하는 디렉토리입니다.

현재 구현체가 바뀌더라도 전체 파이프라인 구조가 유지되도록 `BaseInputLayer`, `BaseInformationExtractor`, `BaseCandidateRetriever`, `BaseEntityMatcher`, `BaseAASMapper`, `BaseAASGenerator`, `BaseModelGenerator`, `BaseDTAdapter`, `BaseDTValidator` 등을 제공합니다.

향후 OCR, LLM, Vector DB, 3D 생성기, DT 서버 연동을 붙일 때는 이 인터페이스를 구현한 클래스로 교체하면 됩니다.

주요 파일은 다음과 같습니다.

- `base_input.py`: 입력 수집 계층 계약입니다.
- `base_cv.py`: 이미지 분류/세그멘테이션 같은 선택적 CV 계층 계약입니다.
- `base_extractor.py`: 정보 추출 계층 계약입니다.
- `base_semantic_builder.py`: 추출된 raw entity를 semantic node로 바꾸는 계층 계약입니다.
- `base_retriever.py`: AAS Property 후보 검색 계층 계약입니다.
- `base_matcher.py`: semantic node와 후보 property의 의미 매칭 계약입니다.
- `base_mapper.py`: 매칭 결과를 AAS mapping plan으로 바꾸는 계층 계약입니다.
- `base_aas_generator.py`: mapping plan에서 최종 AAS 산출물을 생성하는 계층 계약입니다.
- `base_model_generator.py`: 3D 모델 생성 또는 참조 정보 생성 계약입니다.
- `base_dt_adapter.py`: 디지털 트윈 등록 및 센서값 적용 계약입니다.
- `base_validator.py`: DT 동작 검증 계약입니다.
- `base_llm.py`, `base_embedding.py`: 향후 LLM/임베딩 기반 확장을 위한 계약입니다.

## modules/

`interfaces/`에 정의된 계약의 기본 구현체들이 들어 있습니다. 현재는 외부 서비스 없이 동작하는 MVP 구현입니다.

### modules/input_layer/

입력 payload를 내부 표준 모델인 `AssetPackage`로 정규화합니다.

- `default_input_layer.py`: `raw_asset_package`, `user_inputs`, `asset_images`, `manual_files` 같은 입력 형태를 받아 자산 ID, 이름, 타입, 이미지, 문서, 사용자 입력을 표준 구조로 만듭니다.

### modules/cv/

선택적 CV 단계입니다.

- `noop_cv.py`: 실제 CV 모델 없이 이미지 파일명에서 `robot`, `pump`, `motor`, `conveyor` 같은 힌트를 찾아 자산 타입을 약하게 추론합니다. 세그멘테이션은 현재 수행하지 않습니다.

### modules/extraction/

입력 데이터에서 AAS 매핑 후보가 될 원천 속성을 추출합니다.

- `manual_input_extractor.py`: 사용자 입력 필드에서 `ExtractedEntity` 목록을 만듭니다. OCR, 문서 파서, LLM extractor가 붙기 전의 기본 구현입니다.

### modules/semantic_node/

추출된 속성을 AAS 매핑 전 중간 표현인 `SemanticNode`로 변환합니다.

- `default_builder.py`: 각 속성에 개념 정의, affordance, value type, confidence 같은 의미 정보를 붙입니다. 현재는 사전 기반 규칙으로 동작합니다.

### modules/retrieval/

Semantic Node와 유사한 AAS Property 후보를 검색합니다.

- `in_memory_retriever.py`: `repositories/aas_property_repository/properties.json`을 메모리에 로드한 뒤, 토큰 겹침 기반 점수로 후보 Top-K를 반환합니다.

### modules/matching/

검색된 후보 중 실제 매칭 여부를 판단합니다.

- `rule_based_matcher.py`: 후보 검색 점수, 이름 토큰 겹침, 단위 일치 여부를 조합해 match 여부와 점수를 계산합니다.

### modules/aas_mapping/

매칭된 속성을 AAS Submodel 구조에 배치하는 mapping plan을 만듭니다.

- `default_mapper.py`: `MatchedProperty` 목록과 `ModelInfo`를 받아 `DigitalNameplate`, `TechnicalData`, `ProvisionOf3DModels`, `OperationalData` 같은 Submodel에 property를 배치합니다. 이 단계에서는 아직 최종 AAS JSON을 직접 만들지 않습니다.

### modules/aas_generation/

Mapping plan을 실제 AAS JSON 구조로 변환합니다.

- `json_generator.py`: `assetAdministrationShells`, `submodels`, `conceptDescriptions` 구조를 생성합니다. 또한 필수 필드가 존재하는지 간단히 검증합니다.

### modules/model_3d/

DT 환경에 연결할 3D 모델 참조 정보를 준비합니다.

- `default_model_manager.py`: 기존 모델 경로가 있으면 해당 파일을 참조하고, 없으면 추후 3D 생성 adapter가 채울 `.glb` 대상 경로를 만듭니다.

### modules/dt_integration/

생성된 AAS와 3D 모델 정보를 디지털 트윈 계층에 등록합니다.

- `in_memory_adapter.py`: 실제 Three.js, Unity, Isaac Sim 서버 없이도 동작하도록 메모리 registry에 DT 자산을 등록합니다. 센서값 적용 결과도 mock 방식으로 계산합니다.

### modules/validation/

DT 등록 결과에 mock sensor 값을 적용해 동작 검증을 수행합니다.

- `default_validator.py`: movement, state change, visual update 검증 결과를 `ValidationResult`로 감쌉니다.

## repositories/

파이프라인이 참조하는 로컬 지식 저장소입니다.

- `repositories/aas_property_repository/properties.json`: AAS Property 후보 목록입니다. 예를 들어 `AssetName`, `ManufacturerName`, `NominalVoltage`, `RatedCurrent`, `Weight`, `OperationalStatus` 같은 후보가 정의되어 있습니다.
- `repositories/submodel_templates/default_submodels.json`: 기본 Submodel 템플릿입니다. 현재 `DigitalNameplate`, `TechnicalData`, `ProvisionOf3DModels`, `OperationalData`가 정의되어 있습니다.
- `repositories/concept_descriptions/`: 향후 ConceptDescription 데이터를 넣기 위한 확장 위치입니다.
- `repositories/eclass_dictionary/`: 향후 ECLASS 사전 데이터를 넣기 위한 확장 위치입니다.

## schemas/

주요 입력과 중간 산출물의 JSON Schema를 보관합니다.

- `asset_package.schema.json`: 표준 자산 입력 묶음 구조입니다.
- `semantic_node.schema.json`: Semantic Node 구조입니다.
- `matched_property.schema.json`: 최종 매칭된 property 구조입니다.
- `aas_mapping_plan.schema.json`: AAS mapping plan 구조입니다.
- `model_info.schema.json`: 3D 모델 참조 정보 구조입니다.

이 스키마들은 입력 검증, 중간 결과 검증, API 문서화에 활용할 수 있습니다.

## data/

실행 입력과 생성 결과가 저장되는 작업 데이터 디렉토리입니다.

- `data/input/`: 샘플 입력 JSON 또는 이미지/문서 경로가 들어가는 위치입니다.
- `data/output/`: 전체 파이프라인 실행 결과 JSON이 저장됩니다. 예: `{asset_id}_pipeline_result.json`
- `data/generated_aas/`: 생성된 AAS JSON 파일이 저장됩니다. 예: `{asset_id}.aas.json`
- `data/generated_models/`: 생성 또는 참조되는 3D 모델 파일 위치입니다.

## tests/

파이프라인 동작을 검증하는 테스트 코드가 들어 있습니다.

- `tests/test_pipeline.py`: 샘플 입력이 전체 MVP 파이프라인을 통과하는지 확인합니다. AAS JSON 생성, 주요 속성 매칭, 3D 모델 참조 포함, DT 검증 통과 여부를 테스트합니다.

## 기타 디렉토리

- `.venv/`: Python 가상환경입니다. 애플리케이션 소스코드는 아닙니다.
- `.idea/`: PyCharm IDE 설정입니다. 애플리케이션 로직과 직접 관련 없습니다.

## 핵심 실행 흐름 상세

1. `DefaultInputLayer`가 입력 payload를 `AssetPackage`로 정규화합니다.
2. 이미지가 있으면 `NoOpCVModel`이 선택적으로 자산 타입 힌트를 반환합니다.
3. `ManualInputExtractor`가 사용자 입력에서 `ExtractedEntity`를 추출합니다.
4. `DefaultSemanticNodeBuilder`가 `ExtractedEntity`를 `SemanticNode`로 변환합니다.
5. `InMemoryCandidateRetriever`가 각 Semantic Node에 대해 AAS Property 후보를 검색합니다.
6. `RuleBasedEntityMatcher`가 후보와 Semantic Node의 의미 일치 점수를 계산합니다.
7. `DefaultModelManager`가 3D 모델 참조 정보를 만듭니다.
8. `DefaultAASMapper`가 매칭된 property와 모델 정보를 AAS mapping plan으로 배치합니다.
9. `JsonAASGenerator`가 mapping plan에서 최종 AAS JSON을 생성하고 검증합니다.
10. `InMemoryDTAdapter`가 AAS와 모델 정보를 mock DT registry에 등록합니다.
11. `DefaultDTValidator`가 mock sensor 값으로 DT 동작 검증 결과를 만듭니다.

## 확장 포인트

현재 구현은 MVP 골격이므로 다음 기능들은 기존 인터페이스를 구현한 새 클래스로 교체할 수 있습니다.

- OCR/문서 파서/LLM 추출기: `interfaces/base_extractor.py`
- Semantic Node 보강기: `interfaces/base_semantic_builder.py`
- Embedding/Vector DB 후보 검색기: `interfaces/base_retriever.py`
- LLM matcher 또는 cross-encoder matcher: `interfaces/base_matcher.py`
- AASX 또는 공식 schema 기반 AAS 생성기: `interfaces/base_aas_generator.py`
- TripoSR, Blender, Meshy 같은 3D 모델 생성기: `interfaces/base_model_generator.py`
- Three.js, Unity, Isaac Sim, Omniverse 연동 adapter: `interfaces/base_dt_adapter.py`
- 실제 센서/MQTT/REST/WebSocket 기반 검증기: `interfaces/base_validator.py`

## 요약

`AAS-auto-generator`는 `app/pipeline.py`를 중심으로 전체 흐름을 조립하고, `interfaces/`를 통해 각 단계를 교체 가능하게 유지합니다. `modules/`는 현재 동작 가능한 기본 구현을 제공하고, `repositories/`는 매칭용 로컬 지식베이스, `schemas/`는 데이터 계약, `data/`는 입력/출력 저장소, `tests/`는 MVP 파이프라인 검증 역할을 합니다.
