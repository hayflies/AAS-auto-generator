# AAS Auto Generator

명판 이미지, PDF, 자유 텍스트를 입력받아 AAS(Asset Administration Shell) JSON을 생성하는 파이프라인입니다.

핵심 원칙은 LLM이 최종 AAS JSON을 직접 쓰지 않게 하는 것입니다. LLM은 텍스트 정제, 속성 추출, Semantic Node 보강, 후보 재랭킹, 선택적 Submodel 배치 판단에만 사용하고, 최종 AAS 구조는 코드 기반 generator가 생성합니다.

## Architecture

```text
Input
- nameplate image
- PDF datasheet/manual
- free text

        |
        v

DefaultInputLayer
Output: AssetPackage
- 입력 필드 alias 정규화
- image/PDF/free text 수집
- 파일 입력은 DocumentProcessor로 텍스트화

        |
        v

DocumentProcessor
Output: cleaned text
- PDF: pdfplumber
- Image OCR: easyocr
- OCR/PDF text cleaning: Gemini API

        |
        v

Extractor
Output: ExtractedEntity[]
- default/llm: LLMExtractor with Gemini API
- allow_module_fallback=True 테스트 경로: ManualInputExtractor

        |
        v

LLMSemanticNodeBuilder + ValueNormalizer
Output: SemanticNode[]
- name/value/unit/value_type 정규화
- Gemini API로 conceptual_definition, affordance 생성
- ECLASS alias 사전으로 eclass_irdi 보강

        |
        v

HybridStandardsCandidateRetriever
Input: SemanticNode
Sources:
- repositories/submodel_templates/admin_shell_io_submodel_templates/published/**/*.json
- repositories/eclass_dictionary/eclass_properties.json
- repositories/iec_cdd_dictionary/iec_cdd_properties.json
Output: top-k AASPropertyCandidate[]
- ECLASS/semanticId exact match 우선
- lexical search
- nomic-embed-text embedding search via Ollama

        |
        v

LLMMatcher.match_candidates
Input: SemanticNode + top-k candidates
Output: MatchResult[]
- Gemini API top-k 후보군 batch reranking
- allow_module_fallback=True 테스트 경로: similarity_score threshold

        |
        v

Best Match Selection
Output: MatchedProperty[]
- AAS property
- semanticId
- eclassIrdi
- templateId/source/path

        |
        v

TemplateAwareAASMapper
Output: AAS mapping plan
- Submodel 후보 생성
- Gemini API 기반 Submodel Template selector
- allow_module_fallback=True 테스트 경로: deterministic template selector
- diagnostics/reviewQueue 생성

        |
        v

JsonAASGenerator
Output:
- AAS JSON
- ConceptDescriptions
- supplementalSemanticIds for ECLASS IRDI
- validation result

        |
        v

DefaultMappingValidator
Output:
- DDMS-style Hit@K / MRR@K / coverage
- template support ratio
- source grounding warnings
```

## Pipeline Modes

| Mode | Factory | 외부 의존 | 설명 |
|---|---|---|---|
| default | `create_default_pipeline()` | Gemini API key, Ollama embedding | Gemini 추출/의미생성/재랭킹 + nomic embedding. 준비 안 되면 fail-fast |
| llm | `create_llm_pipeline()` | Gemini API key, Ollama embedding | default와 동일한 strict composition |
| yolo | `create_yolo_pipeline()` | default 의존 + ultralytics | YOLO를 요청하므로 사용 불가 시 fail-fast |
| llm-yolo | `create_llm_yolo_pipeline()` | default 의존 + ultralytics | LLM + YOLO strict composition |

## Input Payload

```json
{
  "asset_id": "robot_arm_a",
  "asset_name": "Robot Arm A",
  "manufacturer": "ROBOTIS",
  "asset_type": "robot_arm",
  "asset_images": ["data/input/nameplate.jpg"],
  "manual_files": ["data/input/datasheet.pdf"],
  "free_text": "Rated voltage: 24 V\nPayload: 3 kg"
}
```

지원하는 자유 텍스트 필드:

```text
text, input_text, free_text, manual_text, user_text, raw_text
```

## Run

### Web UI

```bash
python3 -m uvicorn api:app --reload
```

```text
http://localhost:8000
```

### CLI

```bash
python3 main.py --input-json data/input/sample_asset.json
python3 main.py --pipeline llm --input-json data/input/sample_asset.json
python3 main.py --pipeline llm-yolo --input-json data/input/sample_asset.json
```

### Image/PDF Folder Runner

```bash
python3 run_from_image.py
python3 run_from_image.py --files data/input/nameplate.jpg --name "Robot Arm" --manufacturer "ROBOTIS"
```

## Dependencies

필수 테스트 경로는 표준 라이브러리 중심으로 동작합니다. 기능별 의존성은 아래처럼 설치합니다.

```bash
export GEMINI_API_KEY=...
ollama pull nomic-embed-text

python3 -m pip install fastapi uvicorn
python3 -m pip install pdfplumber easyocr pillow numpy
python3 -m pip install -e ".[cv]"
```

현재 `requirements.txt`는 없습니다. 기본 실행은 strict mode라서 Gemini API key 또는 Ollama embedding 서버가 없으면 안내 예외와 함께 중단합니다. 오프라인 테스트만 `PipelineConfig(allow_module_fallback=True, require_llm=False, require_embedding=False)`로 fallback을 명시합니다.

## Outputs

| Output | Path |
|---|---|
| Web DB | `data/aas_database.db` |
| AAS JSON | `data/generated_aas/{asset_id}.aas.json` |
| Pipeline result | `data/output/{asset_id}_pipeline_result.json` |
| YOLO crops | `data/output/cv_crops/` |

## Local Standards Repository

- `repositories/submodel_templates/admin_shell_io_submodel_templates/`: admin-shell-io Submodel Templates `main` snapshot
- `repositories/submodel_templates/default_submodels.json`: core submodel set used by the generator
- `repositories/eclass_dictionary/eclass_properties.json`: local ECLASS alias/IRDI seed
- `repositories/iec_cdd_dictionary/iec_cdd_properties.json`: local IEC CDD cache rebuilt from IDTA template IEC references and optional official exports

## Test

```bash
python3 -m unittest
```

현재 검증 기준: `32 tests OK`.
