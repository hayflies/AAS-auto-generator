# 효율적인 디지털 트윈 자원 등록을 위한 LLM 기반 AAS 자동 생성 시스템

## 0. 문서 목적

이 문서는 Codex 또는 개발용 AI Agent가 본 프로젝트의 전체 구조와 로직을 이해하고, 각 모듈을 독립적으로 구현·수정·교체할 수 있도록 정리한 시스템 설계 문서이다.

본 프로젝트의 핵심 목표는 다음과 같다.

> 물리 자산에 대한 비정형/반정형 정보를 입력받아 LLM 기반 의미 구조화와 AAS 표준 매핑을 수행하고, 생성된 AAS와 3D 모델을 디지털 트윈 환경에 등록한 뒤, 임의 센서값 기반 동작 검증까지 수행하는 시스템을 구현한다.

---

## 1. 최종 주제명

**효율적인 디지털 트윈 자원 등록을 위한 LLM 기반 자산 관리 쉘 자동 생성 시스템**

---

## 2. 핵심 방향성

이 프로젝트는 단순히 AAS JSON을 생성하는 프로젝트가 아니다.

최종 목표는 다음 흐름 전체를 구현하는 것이다.

```text
자산 정보 입력
→ 의미 정보 구조화
→ AAS 표준 매핑
→ AAS 자동 생성
→ 3D 모델 연결 또는 생성
→ 디지털 트윈 환경 등록
→ 임의 센서값 기반 동작 검증
```

AAS는 최종 목적물이 아니라, 디지털 트윈 자원을 효율적으로 등록하기 위한 표준화된 중간 표현 수단이다.

---

## 3. Mother Paper 기반 차용 구조

본 프로젝트는 두 개의 Mother Paper 구조를 결합한다.

### 3.1 Mother Paper A: Generation of Asset Administration Shell With Large Language Model Agents

차용할 핵심 개념:

```text
Raw Technical Data
→ Semantic Node
→ LLM Agent System
→ AAS Instance Generation
```

활용 방향:

- LLM을 사용해 자산 정보를 의미 단위로 구조화한다.
- `Semantic Node` 개념을 중간 표현 구조로 차용한다.
- AAS 생성 결과를 평가할 때 effective generation rate, pass rate, helpfulness 등의 평가 방식을 참고한다.

한계:

- LLM이 직접 AAS 요소를 생성하는 경우 구조 오류, 필드 누락, 의미 불일치가 발생할 수 있다.
- 논문 기준 AAS 생성 정확도는 약 62~79% 수준으로 보고되었다.

본 프로젝트의 개선 방향:

- LLM 단독 생성 대신 DDMS 방식의 후보 검색과 정밀 매칭을 추가한다.
- 최종 AAS JSON 생성은 LLM이 아니라 코드 기반 Generator가 수행한다.

---

### 3.2 Mother Paper B: Dual Data Mapping System, DDMS

차용할 핵심 개념:

```text
Entity Extraction
→ Embedding-based Candidate Retrieval
→ Fine-tuned LLM Entity Matching
→ AAS Property Mapping
```

활용 방향:

- 자산 속성과 AAS Property 간의 매핑 문제를 entity matching 문제로 정의한다.
- Embedding 모델로 Top-N 후보를 검색한다.
- LLM matcher가 후보 간 match / not match를 판단한다.
- 최종 매핑 결과를 기반으로 AAS를 생성한다.

본 프로젝트의 개선 방향:

- Semantic Node 기반 구조화 결과를 DDMS식 매핑 엔진의 입력으로 사용한다.
- Mapping 정확도를 높여 기존 AAS 자동 생성 연구보다 높은 정확도를 목표로 한다.

---

## 4. 전체 시스템 로직

```text
[1] Input Layer
    - 장비 이미지
    - 명판 이미지
    - 사용자 부가 입력
    - 기존 문서 또는 사양서

        ↓

[1.5] Optional CV Module
    - 장비 유형 분류 (classification)
    - 객체 영역 추출 (segmentation)
    - background 제거 (3D 생성 보조)

    ※ 해당 모듈은 선택 사항이며, 없어도 전체 시스템 동작 가능

        ↓

[2] Information Extraction Layer
    - OCR
    - LLM 기반 속성 추출
    - 수동 입력 보완

        ↓

[3] Semantic Node Builder
    - name
    - value
    - unit
    - conceptual_definition
    - source_description
    - affordance
    - confidence

        ↓

[4] Candidate Retrieval Engine
    - Semantic Node를 query로 사용
    - AAS Property 후보 Top-N 검색
    - 필요 시 ECLASS / IEC CDD 후보 검색

        ↓

[5] Entity Matching Engine
    - Semantic Node ↔ AAS Property 후보 비교
    - match / not match 판단
    - ranking 및 confidence 계산

        ↓

[6] AAS Mapping Engine
    - 선택된 property를 AAS Submodel 구조에 배치
    - Digital Nameplate, Technical Data, Provision of 3D Models 등 구성

        ↓

[7] AAS Generator
    - AAS JSON 생성
    - Schema validation
    - 누락 필드 검사
    - 사용자 검토용 결과 생성

        ↓

[8] 3D Model Manager
    - 기존 USD / GLB / OBJ / Isaac Sim 모델 연결
    - 모델이 없으면 TripoSR 기반 생성
    - AAS에 3D 모델 참조 정보 기록

        ↓

[9] DT Integration Layer
    - DT Viewer 또는 시뮬레이션 환경에 자산 등록
    - AAS 정보와 3D 모델 연결

        ↓

[10] DT Validation Layer
    - 임의 센서값 입력
    - 3D 모델 이동, 회전, 색상 변화, 상태 변화 확인
    - DT 등록 성공 여부 판단
```

---

## 5. 설계 원칙: 모든 핵심 기능은 교체 가능해야 한다

본 시스템은 반드시 모듈형 구조로 설계한다.

각 기능은 독립 모듈, 엔진, 모델 단위로 분리되어야 하며, 특정 구현체에 종속되면 안 된다.

### 5.1 필수 설계 조건

1. 각 모듈은 명확한 입력과 출력을 가져야 한다.
2. 모듈 내부 구현이 바뀌어도 전체 파이프라인은 유지되어야 한다.
3. OCR 모델, LLM, Embedding 모델, Matcher, AAS Generator, 3D 모델 생성기, DT Viewer는 언제든 교체 가능해야 한다.
4. 각 모듈은 interface 또는 abstract class 형태로 정의하는 것이 바람직하다.
5. 모듈 간 데이터 교환은 JSON 기반 중간 포맷을 사용한다.
6. 특정 LLM API, 특정 3D 툴, 특정 DT 플랫폼에 강하게 결합하지 않는다.

---

## 6. 모듈별 상세 설계

## 6.1 Input Layer

### 역할

사용자로부터 자산 등록에 필요한 원천 데이터를 입력받는다.

### 입력

```json
{
  "asset_images": ["front.jpg", "side.jpg", "nameplate.jpg"],
  "manual_files": ["datasheet.pdf"],
  "user_inputs": {
    "asset_name": "Robot Arm A",
    "manufacturer": "ROBOTIS",
    "model_name": "example_model",
    "asset_type": "robot_arm"
  }
}
```

### 출력

```json
{
  "raw_asset_package": {
    "images": [],
    "documents": [],
    "user_inputs": {}
  }
}
```

### 교체 가능 요소

- Web UI
- CLI 입력
- 파일 업로드 API
- 모바일 앱 입력

---

## 6.2 Information Extraction Layer

### 역할

이미지, 명판, 문서, 사용자 입력으로부터 자산 속성을 추출한다.

### 구성 모듈

```text
OCRAdapter
DocumentParser
LLMExtractionAgent
ManualInputNormalizer
```

### 입력

```json
{
  "raw_asset_package": {
    "images": [],
    "documents": [],
    "user_inputs": {}
  }
}
```

### 출력

```json
{
  "extracted_entities": [
    {
      "raw_name": "Rated Voltage",
      "raw_value": "24",
      "raw_unit": "V",
      "source": "nameplate_ocr",
      "confidence": 0.91
    }
  ]
}
```

### 교체 가능 요소

- OCR: Tesseract, PaddleOCR, EasyOCR, GPT Vision, Gemini Vision
- 문서 파서: PyMuPDF, pdfplumber, LangChain loader
- LLM: GPT, Claude, Gemini, Qwen, Llama

### 설계 주의

이 단계에서는 AAS를 생성하지 않는다.
이 단계의 역할은 오직 원천 정보 추출이다.

---

## 6.2.1 Optional CV Module

### 역할

이미지 기반으로 자산의 유형을 보조적으로 추론하거나, 3D 모델 생성을 위한 전처리를 수행한다.

### 주요 기능

```text
- Device Type Classification (motor, robot arm, pump 등)
- Image Segmentation (배경 제거, 객체 영역 추출)
- Bounding Box Detection (관심 영역 강조)
```

### 입력

```json
{
  "images": ["front.jpg", "side.jpg"]
}
```

### 출력

```json
{
  "cv_outputs": {
    "predicted_type": "robot_arm",
    "confidence": 0.92,
    "segmented_images": ["seg_front.png", "seg_side.png"]
  }
}
```

### 교체 가능 요소

- YOLO
- Vision Transformer (ViT)
- Detectron2
- Segment Anything Model (SAM)
- OpenAI Vision / Gemini Vision

### 설계 원칙

1. 해당 모듈은 Optional이며 제거해도 전체 파이프라인이 동작해야 한다.
2. 결과는 반드시 IR 단계 이전에서만 사용된다.
3. LLM Extraction 결과와 충돌할 경우, 우선순위 정책을 별도로 정의한다.
4. 특정 CV 모델에 종속되지 않도록 Adapter 패턴을 적용한다.

---

## 6.3 Semantic Node Builder

### 역할

추출된 entity를 의미 단위로 정리한다.

Generation of AAS with LLM Agents 논문의 Semantic Node 구조를 참고한다.

### Semantic Node 스키마

```json
{
  "semantic_node_id": "SN_001",
  "name": "Rated Voltage",
  "value": "24",
  "unit": "V",
  "value_type": "float",
  "conceptual_definition": "The nominal voltage required for operating the asset.",
  "affordance": "Used to determine electrical compatibility and power supply requirements.",
  "source_description": "Extracted from nameplate image.",
  "source_reference": "nameplate.jpg",
  "confidence": 0.88
}
```

### 입력

```json
{
  "extracted_entities": []
}
```

### 출력

```json
{
  "semantic_nodes": []
}
```

### 교체 가능 요소

- Rule-based normalizer
- LLM-based semantic enricher
- Ontology-based enricher
- Hybrid semantic enricher

### 설계 주의

Semantic Node는 AAS 생성 전 중간 표현이다.
AAS JSON을 직접 만들지 않는다.

---

## 6.4 Candidate Retrieval Engine

### 역할

Semantic Node와 의미적으로 유사한 AAS Property 후보를 검색한다.

DDMS 논문의 blocking 구조를 차용한다.

### 입력

```json
{
  "semantic_node": {
    "name": "Rated Voltage",
    "unit": "V",
    "conceptual_definition": "..."
  },
  "candidate_space": "AAS_PROPERTY_REPOSITORY"
}
```

### 출력

```json
{
  "candidates": [
    {
      "candidate_id": "AAS_PROP_001",
      "idShort": "NominalVoltage",
      "description": "Nominal voltage of the asset",
      "submodel": "TechnicalData",
      "similarity_score": 0.87
    }
  ]
}
```

### 교체 가능 요소

- Embedding model: SFR-Embedding-Mistral, text-embedding-3-large, bge, e5, sentence-transformers
- Vector DB: FAISS, Chroma, Milvus, Weaviate
- Retrieval 방식: Top-K cosine similarity, hybrid search, BM25 + embedding

### 설계 주의

이 단계는 최종 매핑을 결정하지 않는다.
정확도보다 recall이 중요하다.
정답 후보가 Top-N 안에 들어오도록 설계한다.

---

## 6.5 Entity Matching Engine

### 역할

Semantic Node와 후보 AAS Property가 실제로 같은 의미인지 판단한다.

DDMS 논문의 fine-tuned LLM matcher 구조를 차용한다.

### 입력

```json
{
  "semantic_node": {
    "name": "Rated Voltage",
    "value": "24",
    "unit": "V",
    "conceptual_definition": "The nominal voltage required for operating the asset."
  },
  "candidate": {
    "idShort": "NominalVoltage",
    "description": "Nominal voltage of the asset",
    "submodel": "TechnicalData"
  }
}
```

### 출력

```json
{
  "match": true,
  "match_score": 0.94,
  "reason": "Both entities refer to the nominal voltage required by the asset.",
  "selected_candidate_id": "AAS_PROP_001"
}
```

### 교체 가능 요소

- Fine-tuned LLM classifier
- Prompt-based GPT matcher
- BERT/RoBERTa classifier
- Cross-encoder reranker
- Rule-based matcher

### 설계 주의

이 엔진은 프로젝트 정확도 향상의 핵심이다.
LLM이 AAS를 직접 생성하는 대신, AAS Property 선택을 판단한다.

---

## 6.6 AAS Mapping Engine

### 역할

선택된 AAS Property를 AAS Submodel 구조에 배치한다.

### 입력

```json
{
  "matched_properties": [
    {
      "semantic_node_id": "SN_001",
      "aas_property_id": "AAS_PROP_001",
      "submodel": "TechnicalData",
      "idShort": "NominalVoltage",
      "value": "24",
      "unit": "V"
    }
  ]
}
```

### 출력

```json
{
  "aas_mapping_plan": {
    "submodels": [
      {
        "idShort": "TechnicalData",
        "properties": []
      },
      {
        "idShort": "DigitalNameplate",
        "properties": []
      },
      {
        "idShort": "ProvisionOf3DModels",
        "properties": []
      }
    ]
  }
}
```

### 교체 가능 요소

- Rule-based mapper
- Template-based mapper
- Ontology-based mapper
- LLM-assisted mapper

### 설계 주의

AAS Mapping Engine은 AAS 구조를 결정하지만, 실제 JSON 파일 생성은 AAS Generator가 담당한다.

---

## 6.7 AAS Generator

### 역할

AAS Mapping Plan을 기반으로 AAS JSON을 생성한다.

### 입력

```json
{
  "aas_mapping_plan": {}
}
```

### 출력

```json
{
  "aas_json": {},
  "validation_result": {
    "is_valid": true,
    "errors": []
  }
}
```

### 교체 가능 요소

- 직접 구현한 Python Generator
- Eclipse BaSyx SDK
- AASX Package Explorer 호환 Generator
- JSON Schema 기반 Generator

### 설계 주의

이 단계는 반드시 코드 기반으로 구현한다.
LLM이 최종 AAS JSON을 직접 생성하면 안 된다.

---

## 6.8 3D Model Manager

### 역할

DT 환경에서 사용할 3D 모델을 준비한다.

### 처리 방식

```text
Case A: 기존 모델 존재
→ USD / GLB / OBJ / Isaac Sim 모델 연결

Case B: 기존 모델 없음
→ (Optional CV) segmentation 수행
→ 이미지 기반 3D 모델 생성 (TripoSR)
→ GLB 또는 OBJ로 변환
```

### 입력

```json
{
  "asset_images": [],
  "asset_type": "robot_arm",
  "existing_model_path": null
}
```

### 출력

```json
{
  "model_info": {
    "model_path": "models/asset_001.glb",
    "model_format": "glb",
    "generation_method": "TripoSR",
    "scale": [1.0, 1.0, 1.0],
    "position": [0, 0, 0],
    "rotation": [0, 0, 0]
  }
}
```

### 교체 가능 요소

- Existing USD / GLB loader
- TripoSR
- Meshy
- Luma AI
- Blender script
- Isaac Sim asset importer

### 설계 주의

3D 모델은 AAS 내부에 직접 저장하지 않고, AAS에는 파일 참조 정보만 기록한다.

---

## 6.9 DT Integration Layer

### 역할

AAS와 3D 모델을 디지털 트윈 환경에 등록한다.

### 입력

```json
{
  "aas_json": {},
  "model_info": {}
}
```

### 출력

```json
{
  "dt_asset_id": "DT_ASSET_001",
  "registration_status": "success",
  "viewer_url": "http://localhost:3000/assets/DT_ASSET_001"
}
```

### 교체 가능 요소

- Web-based Three.js viewer
- Unity
- Unreal Engine
- NVIDIA Isaac Sim
- NVIDIA Omniverse
- Custom DT Viewer

### 설계 주의

DT 플랫폼이 바뀌어도 `aas_json`과 `model_info` 입력 구조는 유지되어야 한다.

---

## 6.10 DT Validation Layer

### 역할

등록된 DT 자산이 임의 센서값에 따라 정상적으로 반응하는지 확인한다.

MQTT를 직접 구현할 필요는 없다.
단, 추후 MQTT 기반 연동이 가능하도록 센서값 입력 인터페이스는 분리한다.

### 입력

```json
{
  "dt_asset_id": "DT_ASSET_001",
  "test_sensor_values": {
    "rotation_angle": 30,
    "temperature": 80,
    "status": "running"
  }
}
```

### 출력

```json
{
  "validation_result": {
    "movement_test": true,
    "state_change_test": true,
    "visual_update_test": true,
    "overall_status": "passed"
  }
}
```

### 교체 가능 요소

- Manual test input
- Button-based control UI
- Mock sensor input
- MQTT adapter
- REST API input
- WebSocket input

### 설계 주의

현재 구현은 임의 센서값 기반 테스트만 수행한다.
실제 물리 자산과의 실시간 동기화는 확장 기능으로 둔다.

---

## 7. 공통 데이터 구조

## 7.1 Asset Package

```json
{
  "asset_id": "asset_001",
  "asset_name": "Robot Arm A",
  "asset_type": "robot_arm",
  "manufacturer": "ROBOTIS",
  "model_name": "example_model",
  "images": [],
  "documents": [],
  "user_inputs": {}
}
```

## 7.2 Semantic Node

```json
{
  "semantic_node_id": "SN_001",
  "name": "Rated Voltage",
  "value": "24",
  "unit": "V",
  "value_type": "float",
  "conceptual_definition": "The nominal voltage required for operating the asset.",
  "affordance": "Used to determine electrical compatibility.",
  "source_description": "Extracted from nameplate image.",
  "confidence": 0.88
}
```

## 7.3 Matched Property

```json
{
  "semantic_node_id": "SN_001",
  "aas_property_id": "AAS_PROP_001",
  "submodel": "TechnicalData",
  "idShort": "NominalVoltage",
  "value": "24",
  "unit": "V",
  "match_score": 0.94
}
```

## 7.4 Model Info

```json
{
  "model_path": "models/asset_001.glb",
  "model_format": "glb",
  "generation_method": "TripoSR",
  "scale": [1, 1, 1],
  "position": [0, 0, 0],
  "rotation": [0, 0, 0]
}
```

---

## 8. 권장 디렉터리 구조

```text
project-root/
│
├── app/
│   ├── main.py
│   ├── config.py
│   └── pipeline.py
│
├── interfaces/
│   ├── base_ocr.py
│   ├── base_llm.py
│   ├── base_embedding.py
│   ├── base_matcher.py
│   ├── base_aas_generator.py
│   ├── base_model_generator.py
│   └── base_dt_adapter.py
│
├── modules/
│   ├── input_layer/
│   ├── extraction/
│   ├── semantic_node/
│   ├── retrieval/
│   ├── matching/
│   ├── aas_mapping/
│   ├── aas_generation/
│   ├── model_3d/
│   ├── dt_integration/
│   └── validation/
│
├── schemas/
│   ├── asset_package.schema.json
│   ├── semantic_node.schema.json
│   ├── matched_property.schema.json
│   ├── aas_mapping_plan.schema.json
│   └── model_info.schema.json
│
├── repositories/
│   ├── aas_property_repository/
│   ├── submodel_templates/
│   ├── eclass_dictionary/
│   └── concept_descriptions/
│
├── data/
│   ├── input/
│   ├── output/
│   ├── generated_aas/
│   └── generated_models/
│
├── tests/
│   ├── test_extraction.py
│   ├── test_semantic_node.py
│   ├── test_retrieval.py
│   ├── test_matching.py
│   ├── test_aas_generation.py
│   └── test_dt_validation.py
│
└── README.md
```

---

## 9. 권장 Interface 설계 예시

## 9.1 LLM Adapter

```python
class BaseLLM:
    def generate(self, prompt: str, **kwargs) -> str:
        raise NotImplementedError
```

## 9.2 Embedding Adapter

```python
class BaseEmbeddingModel:
    def embed(self, text: str) -> list[float]:
        raise NotImplementedError
```

## 9.2.1 CV Adapter

```python
class BaseCVModel:
    def classify(self, images: list[str]) -> dict:
        raise NotImplementedError

    def segment(self, images: list[str]) -> list[str]:
        raise NotImplementedError
```

## 9.3 Entity Matcher

```python
class BaseEntityMatcher:
    def match(self, source_entity: dict, target_entity: dict) -> dict:
        raise NotImplementedError
```

## 9.4 AAS Generator

```python
class BaseAASGenerator:
    def generate(self, mapping_plan: dict) -> dict:
        raise NotImplementedError

    def validate(self, aas_json: dict) -> dict:
        raise NotImplementedError
```

## 9.5 3D Model Generator

```python
class BaseModelGenerator:
    def generate_model(self, images: list[str], asset_info: dict) -> dict:
        raise NotImplementedError
```

## 9.6 DT Adapter

```python
class BaseDTAdapter:
    def register_asset(self, aas_json: dict, model_info: dict) -> dict:
        raise NotImplementedError

    def apply_sensor_values(self, asset_id: str, sensor_values: dict) -> dict:
        raise NotImplementedError
```

---

## 10. 정확도 향상 전략

기존 LLM 기반 AAS 자동 생성 연구는 약 62~79% 수준의 effective generation rate를 보였다.

본 프로젝트는 다음 전략으로 정확도 향상을 목표로 한다.

```text
1. LLM 직접 AAS 생성 방지
2. Semantic Node 기반 중간 표현 사용
3. Embedding 기반 Top-N 후보 검색
4. LLM Entity Matching으로 정밀 매핑
5. AAS JSON Schema Validation 수행
6. 사용자 검토 및 수정 피드백 반영
7. 반복적으로 매핑 데이터셋 축적
```

목표 지표:

```text
AAS Property Mapping Accuracy: 80% 이상
AAS JSON Schema Validity: 95% 이상
DT Registration Success Rate: 90% 이상
DT Behavior Validation Success Rate: 90% 이상
```

---

## 11. 평가 지표

## 11.1 AAS 생성 평가

```text
- Property Mapping Accuracy
- Submodel Selection Accuracy
- JSON Schema Validity
- Missing Field Rate
- Human Correction Rate
```

## 11.2 Entity Matching 평가

```text
- Precision
- Recall
- F1-score
- MRR@10
- Hit Rate@10
- Hit Rate@1
```

## 11.3 3D 모델 평가

```text
- Model Generation Success Rate
- Visual Similarity Score
- User-rated Mapping Quality
- File Compatibility
- DT Import Success Rate
```

## 11.4 DT 검증 평가

```text
- Asset Registration Success Rate
- Model Loading Success Rate
- Sensor Input Reflection Success Rate
- Movement / Rotation / State Change Test
```

---

## 12. 구현 우선순위

## Phase 1: AAS 자동 생성 MVP

```text
1. 사용자 입력 기반 자산 정보 수집
2. Semantic Node 생성
3. AAS Property 후보 검색
4. Entity Matching
5. AAS JSON 생성
6. Schema validation
```

## Phase 2: DT 등록 MVP

```text
1. GLB/USD 모델 수동 연결
2. AAS에 3D 모델 참조 정보 추가
3. Web 기반 DT Viewer 구현
4. 자산 정보 표시
```

## Phase 3: 3D 모델 생성

```text
1. 기존 모델이 없는 경우 TripoSR 실행
2. 이미지 기반 3D 모델 생성
3. GLB/OBJ 변환
4. DT Viewer에서 로딩
```

## Phase 4: 동작 검증

```text
1. 임의 센서값 입력 UI 구현
2. 센서값 → 모델 상태 변화 매핑
3. 이동/회전/색상 변화 검증
4. 결과 리포트 생성
```

---

## 13. 최종 시스템 성공 기준

본 시스템이 성공했다고 판단하는 기준은 다음과 같다.

```text
1. 사용자가 입력한 자산 정보가 Semantic Node로 구조화된다.
2. Semantic Node가 적절한 AAS Property에 매핑된다.
3. AAS JSON이 표준 스키마 검증을 통과한다.
4. AAS에 3D 모델 참조 정보가 포함된다.
5. DT Viewer에 자산이 등록된다.
6. 임의 센서값 입력 시 3D 모델이 시각적으로 반응한다.
7. 사용자는 자산이 DT 환경에 정상 등록되었다고 판단할 수 있다.
```

---

## 14. 최종 한 줄 요약

본 프로젝트는 LLM으로 자산 정보를 Semantic Node로 구조화하고, DDMS 기반 Entity Matching을 통해 AAS 표준 필드에 정밀 매핑한 뒤, 생성된 AAS와 3D 모델을 디지털 트윈 환경에 등록하고 임의 센서값 기반 동작으로 통합 여부를 검증하는 시스템이다.
