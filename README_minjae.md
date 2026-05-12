# AAS Auto Generator

비정형 자산 정보(명판 이미지, PDF, 자유 텍스트)를 입력받아 LLM과 DDMS 기반 entity matching을 결합하여 AAS(Asset Administration Shell) JSON을 자동 생성하고 디지털 트윈에 등록·검증하는 end-to-end 파이프라인입니다.

## 시스템 개요

핵심 아이디어는 LLM이 최종 AAS JSON을 직접 쓰지 않는 것입니다. LLM은 텍스트 정제, 속성 추출, Semantic Node 보강, 후보 재랭킹, Submodel 배치 판단에만 사용하고, 최종 AAS 구조는 코드 기반 generator가 생성합니다.

### 파이프라인 흐름

```
비정형 입력 (이미지 / PDF / 텍스트)
    ↓
[1] 입력 처리 — EasyOCR / pdfplumber / 텍스트 파싱 → AssetPackage
    ↓
[2] 속성 추출 — Ollama LLM(llama3.2)으로 키-값 속성 추출 + 가비지 필터 5종
    ↓
[3] Semantic Node 생성 — LLM 의미 설명 생성 + ECLASS IRDI 사전 조회
    ↓
[4] DDMS 계층적 매칭
      ① ECLASS IRDI 정확 매칭 (score=1.0, 임베딩 스킵)
      ② 임베딩 코사인 유사도 + alias 부스트 (nomic-embed-text)
      ③ LLM 정밀 매핑 (fallback)
    ↓
[5] AAS 구조 생성 — IDTA 서브모델 템플릿(DigitalNameplate / TechnicalData) 배치
    ↓
[6] 디지털 트윈 등록 및 동작 검증
```

### 가비지 필터 (OCR 노이즈 제거)

| 필터 | 설명 |
|---|---|
| 괄호 단독값 | `[Mbps]`처럼 괄호만으로 구성된 값 제거 |
| 숫자 부재 | 숫자 없는 값(단위만 추출된 경우) 제거 |
| 인코더 해상도 | 단위 없는 Dynamixel 해상도 값(1024·2048·4096·1008·512·256) 제거 |
| 치수-질량 모순 | Width/Height 등 치수 키워드에 g·kg 단위 부여 시 제거 |
| 신뢰도 임계값 | confidence < 0.60 제거 |

### ECLASS IRDI 기반 결정론적 매칭

IDTA 공식 템플릿(Digital Nameplate 3/0, TechnicalData 1/2)에서 수집한 21개 표준 속성 IRDI를 사용합니다. 속성명이 IRDI 사전의 alias와 일치하면 임베딩 계산 없이 score=1.0으로 즉시 매핑됩니다. IRDI가 없는 로봇 특화 속성(DOF, Payload 등)은 임베딩 fallback으로 처리합니다.

## 검증 결과

3종 산업용 로봇 실증 검증:

| 자산 | F1 Score | 서브모델 분류 정확도 |
|---|---|---|
| OMY-Pro | 0.947 | 100% |
| ROBOTIS Hand E1-I | 1.000 | 100% |
| OMX-M6 | 0.889 | 100% |
| **평균** | **0.930** | **100%** |

처리 시간: 수작업 평균 35분 → 자동화 약 114초 (**94.6% 단축**)

## 아키텍처 상세

```text
Input
→ DefaultInputLayer          # 입력 alias 정규화, DocumentProcessor 호출
→ DocumentProcessor          # PDF(pdfplumber) / Image OCR(easyocr)
→ LLMExtractor               # Ollama LLM 속성 추출 + 가비지 필터
→ LLMSemanticNodeBuilder     # ECLASS IRDI 할당 + 의미 설명 생성
→ HybridStandardsCandidateRetriever  # IRDI 매칭 → 임베딩 → lexical
→ LLMMatcher.match_candidates        # 후보 재랭킹
→ TemplateAwareAASMapper     # Submodel 배치 (deterministic / LLM)
→ JsonAASGenerator           # AAS JSON + ConceptDescriptions 생성
→ DT 등록 및 검증
```

## Pipeline Modes

| Mode | 설명 | 외부 의존 |
|---|---|---|
| `default` | 수동 입력, lexical/IRDI 검색, deterministic 매칭 | 없음 |
| `llm` | LLM 추출, 임베딩 검색, LLM 재랭킹·배치 | Ollama |
| `yolo` | default + YOLO CV 명판 탐지 | ultralytics |
| `llm-yolo` | llm + YOLO | Ollama, ultralytics |

## 실행 방법

### 사전 준비

```bash
ollama pull llama3.2
ollama pull nomic-embed-text
pip install fastapi uvicorn pdfplumber easyocr pillow numpy
```

### 웹 UI 실행

```bash
python -m uvicorn api:app --reload
```

브라우저에서 `http://localhost:8000` 접속 → 이미지·PDF 업로드 → **Generate AAS** 클릭

### CLI 실행

```bash
python main.py --input-json data/input/sample_asset.json
python main.py --pipeline llm --input-json data/input/sample_asset.json
```

### 이미지/PDF 직접 실행

```bash
python run_from_image.py
python run_from_image.py --files data/input/nameplate.jpg --name "Robot Arm" --manufacturer "ROBOTIS"
```

## 출력 결과

| 항목 | 경로 |
|---|---|
| 웹 UI 생성 결과 | `data/aas_database.db` |
| AAS JSON | `data/generated_aas/{asset_id}.aas.json` |
| 파이프라인 전체 결과 | `data/output/{asset_id}_pipeline_result.json` |

## 로컬 표준 데이터

| 경로 | 내용 |
|---|---|
| `repositories/submodel_templates/admin_shell_io_submodel_templates/` | IDTA 공식 Submodel Templates 전체 |
| `repositories/eclass_dictionary/eclass_properties.json` | ECLASS IRDI 사전 (21개 속성, 공식 템플릿 기반) |
| `repositories/iec_cdd_dictionary/iec_cdd_properties.json` | IEC CDD 속성 사전 |

## 테스트

```bash
python -m unittest
```
