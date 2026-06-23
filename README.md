# ⚙️ AAS Auto Generator Backend

> 명판 이미지, PDF, 자유 텍스트와 사용자 입력을 분석하여  
> **AAS(Asset Administration Shell) JSON 초안**을 생성하는 백엔드 시스템입니다.

LLM은 자산 정보 추출, 의미 보강, 표준 후보 재랭킹에 활용하며, 최종 AAS JSON은 **코드 기반 Generator**가 생성합니다. 이를 통해 생성 결과의 일관성과 AAS 표준 구조 준수 가능성을 높였습니다.

---

## ✨ 주요 기능

- 🖼️ 명판 이미지 OCR 및 자산 속성 추출
- 📄 사용자 매뉴얼 PDF 텍스트 분석
- ✍️ 자유 텍스트 및 수동 입력 처리
- 🧠 LLM 기반 속성 추출과 의미 보강
- 🔎 IDTA, ECLASS, IEC CDD 기반 표준 후보 검색
- 🧩 표준 Submodel 자동 배치
- 🏗️ 코드 기반 AAS JSON 및 ConceptDescription 생성
- ✅ 생성 결과 검증 및 검토 필요 항목 표시
- 💾 SQLite 기반 생성 이력 저장·조회·삭제
- 🌐 FastAPI 기반 웹 API 및 정적 UI 제공

---

## 🏛️ 시스템 구성

```text
FastAPI (`app/api.py`) + 정적 UI
        │
        ▼
AAS 자동 생성 파이프라인 (`app/pipeline.py`)
  ├─ 입력 처리
  │   └─ DefaultInputLayer / DocumentProcessor
  ├─ AI 모델
  │   └─ Ollama: llama3.2 / nomic-embed-text
  ├─ 표준 후보 검색
  │   └─ IDTA Submodel Template / ECLASS / IEC CDD
  ├─ AAS 매핑·생성·검증
  │   └─ TemplateAwareAASMapper / JsonAASGenerator
  └─ 결과 저장
      └─ SQLite (`data/aas_database.db`)
```

---

## 📁 주요 디렉터리 및 파일

| 경로 | 역할 |
| --- | --- |
| `app/api.py` | 웹 API와 정적 화면 제공, 생성 결과 저장·조회·삭제 |
| `app/db.py` | 생성 결과를 관리하는 SQLite 저장소 |
| `app/main.py` | JSON, 이미지, PDF 입력을 처리하는 CLI 진입점 |
| `app/pipeline.py` | AAS 생성 파이프라인 조립 및 실행 순서 관리 |
| `modules/input_layer/` | PDF 텍스트 추출 및 이미지 OCR 처리 |
| `modules/extraction/` | 문서와 사용자 입력에서 자산 속성 추출 |
| `modules/semantic_node/` | 추출 결과를 의미 노드로 변환하고 값 정규화 |
| `modules/retrieval/` | 표준 후보 검색 및 검색 결과 구성 |
| `modules/standards/` | IDTA, ECLASS, IEC CDD 표준 데이터 처리 |
| `modules/matching/` | LLM 기반 표준 후보 재랭킹 |
| `modules/aas_mapping/` | 속성의 Submodel 배치 및 검토 항목 생성 |
| `modules/aas_generation/` | AAS JSON과 ConceptDescription 생성 |
| `data/generated_aas/` | 최종 생성된 AAS JSON 저장 |
| `data/output/` | 전체 파이프라인 실행 결과 저장 |

---

## 🔄 AAS 생성 파이프라인

```text
이미지 / PDF / 자유 텍스트 / 수동 입력
        │
        ▼
DefaultInputLayer
        │
        ▼
DocumentProcessor
PDF 텍스트 추출 · 이미지 OCR · LLM 텍스트 정제
        │
        ▼
LLMExtractor
속성명 · 값 · 단위 추출
        │
        ▼
LLMSemanticNodeBuilder + ValueNormalizer
의미 노드 생성 · 값과 단위 정규화
        │
        ▼
HybridStandardsCandidateRetriever
IDTA Template · ECLASS · IEC CDD 후보 Top-K 검색
        │
        ▼
LLMMatcher
표준 후보 재랭킹
        │
        ▼
TemplateAwareAASMapper
Submodel 배치 · 검토 필요 항목 생성
        │
        ▼
JsonAASGenerator
AAS JSON · ConceptDescription 생성
        │
        ▼
DefaultMappingValidator
매핑 결과 검증
        │
        ▼
InMemoryDTAdapter + DefaultDTValidator
디지털 트윈 구조 변환 및 최종 검증
        │
        ▼
SQLite 저장 · API 응답
```

---

## 🛠️ 실행 환경

### 필수 환경

- Python 3.9 이상
- Ollama
- pip

> 아래 명령어는 프로젝트 루트인 `AAS-BackEnd` 디렉터리에서 실행합니다.

---

## 📦 설치 방법

### 1. 가상환경 생성 및 활성화

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 2. Python 패키지 설치

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### 3. Ollama 모델 설치

별도 터미널에서 Ollama 서버를 실행합니다.

```bash
ollama serve
```

파이프라인에서 사용하는 모델을 내려받습니다.

```bash
ollama pull llama3.2
ollama pull nomic-embed-text
```

> `ollama serve`는 백엔드 실행 중 계속 켜져 있어야 합니다.  
> 이미 Ollama 서비스가 실행 중이라면 모델 다운로드 명령만 실행하면 됩니다.

---

## 🚀 프로그램 실행

### 🌐 웹 백엔드 실행

#### 개발 모드

코드 변경 사항을 자동으로 반영합니다.

```bash
python -m uvicorn app.api:app --host 0.0.0.0 --port 8000 --reload
```

#### 일반 실행

```bash
python -m app.api
```

실행 후 브라우저에서 아래 주소로 접속합니다.

```text
http://localhost:8000
```

---

## 💻 CLI 실행

### 샘플 JSON 입력

```bash
python -m app.main --input-json data/input/sample_asset.json
```

### 이미지 또는 PDF 입력

```bash
python -m app.main --files data/input/테스트사진.jpg --name "Test Asset"
```

여러 파일을 함께 입력할 수도 있습니다.

```bash
python -m app.main \
  --files data/input/nameplate.jpg data/input/manual.pdf \
  --name "Industrial Asset"
```

### 입력 디렉터리 일괄 처리

`data/input/images/` 내부의 이미지와 PDF를 모두 처리합니다.

```bash
python -m app.main --image-dir
```

---

## 📤 출력 결과

| 산출물 | 저장 경로 |
| --- | --- |
| 생성된 AAS JSON | `data/generated_aas/{asset_id}.aas.json` |
| 전체 파이프라인 결과 | `data/output/{asset_id}_pipeline_result.json` |
| 웹 생성 이력 및 메타데이터 | `data/aas_database.db` |

### 출력 예시

```text
data/
├─ generated_aas/
│  └─ motor-001.aas.json
├─ output/
│  └─ motor-001_pipeline_result.json
└─ aas_database.db
```

---

## 🧪 테스트

외부 모델 없이 fallback 조합을 검증하는 단위 테스트를 실행합니다.

```bash
python -m unittest discover -s tests
```

---

## 🧠 LLM의 역할

본 시스템에서 LLM은 최종 AAS JSON을 직접 작성하지 않습니다.

| 단계 | LLM 사용 여부 | 처리 방식 |
| --- | :---: | --- |
| 문서 텍스트 정제 | ✅ | OCR 및 문서 노이즈 정제 |
| 자산 속성 추출 | ✅ | 속성명, 값, 단위 추출 |
| 의미 정보 보강 | ✅ | 추출 속성의 의미적 문맥 보완 |
| 표준 후보 재랭킹 | ✅ | 검색 후보 중 적합한 항목 선정 |
| Submodel 배치 | 혼합 | 템플릿과 규칙 기반 매핑 중심 |
| 최종 AAS JSON 생성 | ❌ | 코드 기반 Generator 사용 |
| 결과 검증 | ❌ | Validator와 스키마 기반 검증 |

이 구조는 LLM의 유연한 의미 분석 능력을 활용하면서도, 최종 산출물의 구조적 일관성과 재현성을 확보하기 위한 설계입니다.

---

## 📌 핵심 요약

```text
비정형 자산 정보 입력
        ↓
LLM 기반 정보 추출 및 표준 후보 탐색
        ↓
템플릿·규칙 기반 AAS 매핑
        ↓
코드 기반 AAS JSON 생성 및 검증
        ↓
SQLite 저장 및 웹 API 제공
```

> **비정형 산업 자산 정보를 최소한의 사용자 개입으로 표준화된 AAS JSON 초안으로 변환합니다.**
