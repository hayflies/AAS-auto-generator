# AAS-auto-generator Code Guide

이 문서는 현재 코드 기준의 프로젝트 구조와 파이프라인 흐름을 설명합니다. 과거 MVP용 mapper/retriever 설명은 제외하고, 현재 사용 중인 최종 구조만 정리합니다.

## Core Flow

```text
raw payload
→ DefaultInputLayer
→ DocumentProcessor
→ Extractor
→ LLMSemanticNodeBuilder + ValueNormalizer
→ HybridStandardsCandidateRetriever
→ LLMMatcher.match_candidates
→ Best Match Selection
→ TemplateAwareAASMapper
→ JsonAASGenerator
→ DefaultMappingValidator
→ InMemoryDTAdapter + DefaultDTValidator (auxiliary)
```

## Data Contracts

주요 데이터 구조는 [app/models.py](/Users/hayfly/PycharmProjects/AAS-auto-generator/app/models.py)에 있습니다.

| Model | 역할 |
|---|---|
| `AssetPackage` | 이미지, 문서 텍스트, 사용자 입력을 묶은 표준 입력 |
| `ExtractedEntity` | LLM/manual extractor가 추출한 raw property |
| `SemanticNode` | 매칭 전 의미 중간 표현, `eclass_irdi` 포함 |
| `AASPropertyCandidate` | Submodel Template/ECLASS/IEC CDD에서 로드된 후보 |
| `MatchResult` | Semantic Node와 후보 property의 일치 판단 결과 |
| `MatchedProperty` | 최종 선택된 AAS property 매핑 결과 |
| `PipelineResult` | 전체 단계 산출물을 보존하는 실행 결과 |

## app/

- [app/pipeline.py](/Users/hayfly/PycharmProjects/AAS-auto-generator/app/pipeline.py): 전체 composition root와 실행 순서를 정의합니다.
- [app/main.py](/Users/hayfly/PycharmProjects/AAS-auto-generator/app/main.py): CLI 진입점입니다. `--pipeline default|llm|yolo|llm-yolo`를 선택합니다.
- [app/config.py](/Users/hayfly/PycharmProjects/AAS-auto-generator/app/config.py): 경로, top-k, threshold, output directory 설정입니다.
- [app/models.py](/Users/hayfly/PycharmProjects/AAS-auto-generator/app/models.py): 단계 간 dataclass 계약입니다.
- [app/text.py](/Users/hayfly/PycharmProjects/AAS-auto-generator/app/text.py): label normalization, tokenization, slug/idShort 유틸입니다.

## interfaces/

각 단계 교체를 위한 추상 계약입니다.

| Interface | 구현 예 |
|---|---|
| `BaseInputLayer` | `DefaultInputLayer` |
| `BaseInformationExtractor` | `ManualInputExtractor`, `LLMExtractor` |
| `BaseSemanticNodeBuilder` | `LLMSemanticNodeBuilder` |
| `BaseCandidateRetriever` | `HybridStandardsCandidateRetriever` |
| `BaseEntityMatcher` | `LLMMatcher` |
| `BaseAASMapper` | `TemplateAwareAASMapper` |
| `BaseAASGenerator` | `JsonAASGenerator` |
| `BaseLLM`, `BaseEmbeddingModel` | `GeminiClient`, `OllamaClient` |

`BaseEntityMatcher`는 단건 `match()`와 후보군 `match_candidates()`를 모두 제공합니다. LLM 경로는 `match_candidates()`로 top-k 후보를 batch reranking합니다.

## modules/input_layer/

- `default_input_layer.py`
  - payload alias를 `AssetPackage`로 정규화합니다.
  - `documents`, `manual_files`, 이미지/PDF 경로, 자유 텍스트 필드를 처리합니다.
  - 자유 텍스트 필드: `text`, `input_text`, `free_text`, `manual_text`, `user_text`, `raw_text`
- `document_processor.py`
  - PDF: `pdfplumber`
  - Image OCR: `easyocr`
  - OCR/PDF text cleaning: Gemini API strict mode에서 수행

## modules/extraction/

- `manual_input_extractor.py`: 외부 의존 없는 default extractor입니다. AssetPackage의 기본 자산 필드와 수동 입력 속성을 `ExtractedEntity`로 만듭니다.
- `llm_extractor.py`: LLM으로 텍스트에서 property JSON array를 추출합니다. OCR 노이즈, 낮은 confidence, 단위-only 값, encoder resolution 오인식을 필터링합니다.

## modules/semantic_node/

- `llm_semantic_builder.py`
  - `ExtractedEntity`를 `SemanticNode`로 변환합니다.
  - Gemini API로 conceptual definition과 affordance를 생성합니다.
  - `fail_fast=True`이면 LLM 실패 시 fallback 문장 대신 예외를 전파합니다.
  - `repositories/eclass_dictionary/eclass_properties.json`의 alias로 `eclass_irdi`를 보강합니다.

## modules/normalization/

- `value_normalizer.py`: 값/단위/value type을 후속 매칭에 맞게 정규화합니다.

## modules/standards/

- `candidate_sources.py`
  - `SubmodelTemplateRepository`: `published/**/*.json`에서 Submodel element 후보를 로드합니다.
  - `EclassDictionaryRepository`: 로컬 ECLASS seed를 후보로 로드합니다.
  - `IecCddDictionaryRepository`: 로컬 IEC CDD cache를 보조 후보로 로드합니다.
  - `CandidateSourceRegistry`: 위 후보들을 통합하고 중복을 제거합니다.

## modules/retrieval/

- `hybrid_retriever.py`: 현재 표준 후보 검색 엔진입니다.
  - exact `eclass_irdi`/`semantic_id` 우선
  - lexical score
  - qwen3-embedding:4b Ollama embedding
  - source priority, unit compatibility, value type compatibility 기반 rerank
- `embedding_retriever.py`, `in_memory_retriever.py`: 이전/대체 구현체입니다. 현재 기본 composition에는 `HybridStandardsCandidateRetriever`가 사용됩니다.

## modules/matching/

- `llm_matcher.py`
  - `skip_llm=True`: 후보 similarity score로 threshold matching
  - `skip_llm=False`: top-k 후보군을 LLM에 넘겨 batch reranking
  - score가 threshold 이상인 후보만 `MatchResult.match=True`

## modules/aas_mapping/

- `template_aware_mapper.py`: 현재 AAS mapping engine입니다.
  - 낮은 match score는 reject/review 처리합니다.
  - Submodel 후보를 생성합니다.
    - 현재 후보의 submodel
    - semanticId/eclassIrdi/idShort가 존재하는 Submodel Template
    - core submodel heuristic
  - default/llm pipeline에서는 Gemini API 기반 LLM Submodel Template selector를 사용합니다.
  - 오프라인 테스트에서만 `allow_module_fallback=True`로 deterministic selector fallback을 명시합니다.
  - 결과에 `diagnostics`, `reviewQueue`, `placement` 근거를 남깁니다.
- `default_mapper.py`, `semantic_mapper.py`: 대체/이전 mapper입니다. 현재 기본 composition에는 사용하지 않습니다.

## modules/aas_generation/

- `json_generator.py`
  - mapping plan을 AAS JSON으로 변환합니다.
  - `assetAdministrationShells`, `submodels`, `conceptDescriptions`를 생성합니다.
  - `eclassIrdi`는 `supplementalSemanticIds`와 ConceptDescription에 반영합니다.
  - 필수 필드 중심의 lightweight validation을 수행합니다.

## modules/cv/

- `noop_cv.py`: default CV adapter입니다.
- `yolo_part_detector.py`: YOLOv8 기반 부품 탐지/crop adapter입니다. `ultralytics`와 weight 파일이 필요하며 YOLO pipeline에서 실패 시 fail-fast로 중단합니다.

## Runtime Entrypoints

- [api.py](/Users/hayfly/PycharmProjects/AAS-auto-generator/api.py): FastAPI 업로드/생성/조회/삭제 API와 정적 UI 서빙
- [run_from_image.py](/Users/hayfly/PycharmProjects/AAS-auto-generator/run_from_image.py): 이미지/PDF 폴더 또는 파일 지정 실행
- [main.py](/Users/hayfly/PycharmProjects/AAS-auto-generator/main.py): CLI wrapper

## repositories/

```text
repositories/
  eclass_dictionary/eclass_properties.json
  iec_cdd_dictionary/iec_cdd_properties.json
  submodel_templates/default_submodels.json
  submodel_templates/admin_shell_io_submodel_templates/
```

`admin_shell_io_submodel_templates/published`는 IDTA Submodel Template 후보 공간입니다. 전체 snapshot은 약 130MB이며 JSON/AASX/PDF를 포함합니다.

## Tests

- `tests/test_pipeline.py`: default pipeline end-to-end
- `tests/test_llm_client.py`: Gemini/Ollama client/parsing mock
- `tests/test_llm_extractor.py`: extractor conversion/filtering
- `tests/test_llm_matcher.py`: matcher threshold/reranking behavior
- `tests/test_template_aware_mapper.py`: LLM Submodel placement correction

실행:

```bash
python3 -m unittest
```
