# AAS Auto Generator Backend

명판 이미지, PDF, 자유 텍스트에서 자산 속성을 추출해 AAS(Asset Administration Shell) JSON으로 생성하는 백엔드입니다. LLM은 추출·의미 보강·표준 후보 재랭킹에만 사용하며, 최종 AAS JSON은 코드 기반 generator가 만듭니다.

## 시스템 구성

```text
FastAPI (`app/api.py`) + 정적 UI
        |
        v
AAS 자동 생성 파이프라인 (`app/pipeline.py`)
  ├─ 입력 처리: DefaultInputLayer / DocumentProcessor
  ├─ Ollama: llama3.2, nomic-embed-text
  ├─ 표준 후보: IDTA Submodel Template, ECLASS, IEC CDD
  ├─ AAS 매핑·생성·검증: TemplateAwareAASMapper / JsonAASGenerator
  └─ 결과 저장: SQLite (`data/aas_database.db`)
```

| 경로 | 역할 |
| --- | --- |
| `app/api.py` | 웹 API와 정적 화면 제공, 생성 결과 저장·조회·삭제 |
| `app/db.py` | 생성 결과 SQLite 저장소 |
| `app/main.py` | JSON·이미지·PDF 입력을 처리하는 단일 CLI 진입점 |
| `app/pipeline.py` | 확정된 AAS 생성 파이프라인 조립과 실행 순서 |
| `modules/input_layer/` | PDF 텍스트 추출과 이미지 OCR 처리 |
| `modules/extraction/`, `modules/semantic_node/` | 속성 추출과 의미 노드 생성 |
| `modules/retrieval/`, `modules/standards/` | IDTA/ECLASS/IEC CDD 후보 검색 |
| `modules/matching/`, `modules/aas_mapping/` | LLM 재랭킹과 Submodel 배치 |
| `modules/aas_generation/` | AAS JSON 및 ConceptDescription 생성 |
| `data/generated_aas/`, `data/output/` | AAS JSON과 전체 실행 결과 |

## 시스템 흐름 로직(파이프라인 로직)

```text
이미지 / PDF / 자유 텍스트 / 수동 입력
  → DefaultInputLayer
  → DocumentProcessor (PDF 텍스트 추출, 이미지 OCR, LLM 텍스트 정제)
  → LLMExtractor (속성명·값·단위 추출)
  → LLMSemanticNodeBuilder + ValueNormalizer
  → HybridStandardsCandidateRetriever
       (IDTA Template · ECLASS · IEC CDD 후보를 top-k로 검색)
  → LLMMatcher (후보군 재랭킹)
  → TemplateAwareAASMapper (Submodel 배치 및 검토 항목 생성)
  → JsonAASGenerator (AAS JSON + ConceptDescription 생성)
  → DefaultMappingValidator
  → InMemoryDTAdapter + DefaultDTValidator
  → SQLite 저장 및 API 응답
```

## 설치

Python 3.9 이상과 [Ollama](https://ollama.com/)가 필요합니다. 프로젝트 루트(`AAS-BackEnd`)에서 다음을 실행합니다.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Ollama 서버를 실행하고, 파이프라인이 사용하는 두 모델을 내려받습니다.

```bash
ollama serve
ollama pull llama3.2
ollama pull nomic-embed-text
```

`ollama serve`는 별도 터미널에서 계속 실행해 두어야 합니다. 이미 Ollama 서비스가 실행 중이면 모델 다운로드 명령만 실행하면 됩니다.

## 프로그램 시작 명령어

### 웹 백엔드

개발 모드:

```bash
python -m uvicorn app.api:app --host 0.0.0.0 --port 8000 --reload
```

일반 실행:

```bash
python -m app.api
```

브라우저에서 `http://localhost:8000`으로 접속합니다.

### CLI 실행

샘플 JSON으로 실행:

```bash
python -m app.main --input-json data/input/sample_asset.json
```

이미지 또는 PDF 파일로 실행:

```bash
python -m app.main --files data/input/테스트사진.jpg --name "Test Asset"
```

`data/input/images/` 안의 모든 이미지·PDF를 처리하려면 다음을 실행합니다.

```bash
python -m app.main --image-dir
```

## 출력

| 산출물 | 경로 |
| --- | --- |
| 생성된 AAS JSON | `data/generated_aas/{asset_id}.aas.json` |
| 전체 파이프라인 결과 | `data/output/{asset_id}_pipeline_result.json` |
| 웹 생성 이력 | `data/aas_database.db` |

## 테스트

외부 모델 없이 fallback 조합을 검증하는 단위 테스트는 다음 명령으로 실행합니다.

```bash
python -m unittest discover -s tests
```
