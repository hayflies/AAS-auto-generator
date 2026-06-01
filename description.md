# AAS Auto Generator 설계 문서

## 목적

본 프로젝트는 물리 자산의 비정형/반정형 정보를 AAS(Asset Administration Shell) JSON으로 변환하는 시스템이다.

입력은 명판 이미지, PDF, 자유 텍스트이며, 출력은 ConceptDescription과 ECLASS semantic reference를 포함한 AAS JSON이다. LLM은 판단과 구조화에 사용하고, 최종 AAS JSON은 코드 기반 generator가 생성한다.

## 최종 로직

```text
1. 명판 이미지, PDF, 자유 텍스트를 입력으로 받는다.
2. 파일 입력에서 텍스트를 추출하고, 자유 텍스트를 문서 텍스트로 통합한다.
3. LLM 또는 manual extractor가 raw property를 ExtractedEntity로 만든다.
4. LLM Semantic Node Builder가 SemanticNode를 생성하고 ECLASS IRDI를 보강한다.
5. ECLASS, IEC CDD, Submodel Templates에서 top-k 후보군을 검색한다.
6. 후보군을 LLM matcher에 넘겨 재랭킹한다. 기본 실행은 strict mode이며 LLM/embedding이 없으면 중단한다.
7. SemanticNode와 가장 알맞은 AAS property, semanticId, eclassIrdi를 매핑한다.
8. TemplateAwareAASMapper가 알맞은 Submodel Template/Submodel을 선택한다.
9. ConceptDescription을 생성한다.
10. AAS JSON을 최종 생성한다.
```

## 전체 아키텍처

```text
Input
- nameplate image path
- PDF path
- free text

        |
        v

DefaultInputLayer
Input:
- raw payload
Output:
- AssetPackage
Responsibilities:
- 입력 alias 정규화
- `asset_images`, `images`, `manual_files`, `documents` 수집
- `text`, `input_text`, `free_text`, `manual_text`, `user_text`, `raw_text` 수집
- 파일 경로는 DocumentProcessor로 전달

        |
        v

DocumentProcessor
Input:
- PDF/image path
Output:
- cleaned text
Responsibilities:
- PDF text extraction with pdfplumber
- image OCR with easyocr
- optional LLM text cleaning

        |
        v

Extractor
Input:
- AssetPackage
- optional CVOutput
Output:
- ExtractedEntity[]
Implementations:
- ManualInputExtractor for default mode
- LLMExtractor for llm mode

        |
        v

LLMSemanticNodeBuilder + ValueNormalizer
Input:
- ExtractedEntity[]
Output:
- SemanticNode[]
Responsibilities:
- name, value, unit, value_type 정규화
- Gemini API로 conceptual_definition 생성
- Gemini API로 affordance 생성
- ECLASS alias dictionary로 eclass_irdi 보강

        |
        v

HybridStandardsCandidateRetriever
Input:
- SemanticNode
Candidate Sources:
- Submodel Templates published JSON
- ECLASS dictionary
- IEC CDD dictionary
Output:
- top-k AASPropertyCandidate[]
Ranking Signals:
- exact eclass_irdi / semanticId
- lexical similarity
- optional embedding similarity
- source priority
- unit compatibility
- value type compatibility

        |
        v

LLMMatcher.match_candidates
Input:
- SemanticNode
- top-k AASPropertyCandidate[]
Output:
- MatchResult[]
Behavior:
- default: threshold over candidate similarity_score
- llm: batch prompt reranking by Gemini API

        |
        v

Best Match Selection
Input:
- MatchResult[]
Output:
- MatchedProperty[]
Responsibilities:
- highest valid match 선택
- source priority tie-break
- semanticId, eclassIrdi, templateId, path, element type 보존

        |
        v

TemplateAwareAASMapper
Input:
- AssetPackage
- MatchedProperty[]
- ModelInfo
Output:
- AAS mapping plan
- diagnostics
- reviewQueue
Responsibilities:
- Submodel 후보 생성
- deterministic 또는 LLM Submodel selector 실행
- template validation
- low confidence/reviewRequired 표시
- ProvisionOf3DModels model reference 추가

        |
        v

JsonAASGenerator
Input:
- AAS mapping plan
Output:
- AAS JSON
- validation result
Responsibilities:
- AssetAdministrationShell 생성
- Submodel 생성
- SubmodelElement 생성
- ConceptDescription 생성
- ECLASS IRDI를 supplementalSemanticIds로 보존

        |
        v

DT Adapter / Validator
Input:
- AAS JSON
- ModelInfo
- test sensor values
Output:
- DTRegistrationResult
- ValidationResult
```

## Pipeline Modes

### default

기본 실행은 구체 모듈을 strict하게 연결한다. Gemini API key 또는 Ollama embedding 서버가 없으면 default module로 내려가지 않고 `PipelineConfigurationError`로 중단한다.

```text
DefaultInputLayer
→ LLMExtractor(Gemini)
→ LLMSemanticNodeBuilder(Gemini)
→ HybridStandardsCandidateRetriever(qwen3-embedding:4b)
→ LLMMatcher(skip_llm=False)
→ TemplateAwareAASMapper(use_llm_template_selection=True)
→ JsonAASGenerator
```

### llm

default와 같은 strict composition이다. LLM provider는 `PipelineConfig.llm_provider`로 선택하며 기본값은 `gemini`이다.

```text
DefaultInputLayer
→ DocumentProcessor with optional LLM cleaning
→ LLMExtractor
→ LLMSemanticNodeBuilder(skip_enrichment=False)
→ HybridStandardsCandidateRetriever(use_embeddings=True)
→ LLMMatcher(skip_llm=False)
→ TemplateAwareAASMapper(use_llm_template_selection=True)
→ JsonAASGenerator
```

오프라인 테스트가 필요할 때만 `allow_module_fallback=True`를 명시하면 ManualInputExtractor, DefaultSemanticNodeBuilder, lexical retrieval, similarity threshold 경로로 내려간다.

### yolo / llm-yolo

YOLOPartDetector를 CV adapter로 연결한다. `ultralytics` 또는 weight 파일이 없으면 fail-fast로 중단한다.

## Submodel 배치 설계

Submodel 오배치를 줄이기 위해 배치는 단순히 후보의 `submodel` 필드를 따르지 않는다.

```text
MatchedProperty
→ option generation
   - current candidate submodel
   - template match by semanticId
   - template match by eclassIrdi
   - template match by idShort
   - core submodel heuristic
→ selector
   - deterministic selector in default mode
   - LLM selector in llm mode
→ placement result
   - selected submodel
   - confidence
   - source
   - reason
   - options
→ diagnostics/reviewQueue
```

LLM selector는 `build_submodel_template_selection_prompt()`를 사용한다. 허용된 후보 안에서만 선택할 수 있고, confidence가 낮으면 `reviewRequired=true`로 표시한다.

Core submodel 기준:

| Submodel | 배치 기준 |
|---|---|
| `DigitalNameplate` | 제조사, 모델명, 제품명, serial, certificate, 정적 명판 정보 |
| `TechnicalData` | 전압, 전류, 무게, payload, 속도, 치수, 성능, ECLASS/IEC 기술 속성 |
| `ProvisionOf3DModels` | GLB/GLTF/STEP 등 3D 모델 파일/geometry reference |
| `OperationalData` | runtime status, sensor value, telemetry, time-varying 상태 |

## Candidate Sources

```text
repositories/submodel_templates/admin_shell_io_submodel_templates/published/**/*.json
repositories/eclass_dictionary/eclass_properties.json
repositories/iec_cdd_dictionary/iec_cdd_properties.json
```

`SubmodelTemplateRepository`는 JSON template의 submodel elements와 concept descriptions를 읽어 `AASPropertyCandidate`로 변환한다. ECLASS/IEC dictionary도 같은 후보 구조로 통합된다.

## AAS 생성 원칙

1. LLM은 최종 AAS JSON을 직접 생성하지 않는다.
2. LLM 출력은 structured parser를 통과하며 strict mode에서는 형식 오류를 예외로 처리한다.
3. property matching과 submodel placement의 근거를 `diagnostics`와 `placement`에 남긴다.
4. `semanticId`와 `eclassIrdi`를 모두 보존한다.
5. AAS JSON 생성은 `JsonAASGenerator`가 deterministic하게 수행한다.

## Output Shape

```json
{
  "assetAdministrationShells": [],
  "submodels": [],
  "conceptDescriptions": []
}
```

`PipelineResult`에는 다음 디버깅 정보도 함께 남는다.

```text
asset_package
extracted_entities
semantic_nodes
candidates_by_node
match_results
matched_properties
aas_mapping_plan
mapping_validation
aas_json
aas_validation
dt_registration
dt_validation (auxiliary 3D/sensor line)
```

## Verification

현재 기본 검증 명령:

```bash
python3 -m unittest
```

현재 테스트는 default pipeline fallback 경로, Gemini/Ollama client mock, extractor, matcher, TemplateAwareAASMapper placement correction을 포함한다.
