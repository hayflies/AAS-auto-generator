# AAS Auto Generator

이미지·PDF → AAS(Asset Administration Shell) JSON 자동 생성 파이프라인

---

## 실행 방법

### 사전 준비

```bash
# 1. Ollama 설치 (https://ollama.ai)
ollama pull llama3.2
ollama pull nomic-embed-text

# 2. Python 패키지 설치
pip install -r requirements.txt
```

### 웹 UI 실행 (권장)

```bash
python -m uvicorn api:app --reload
```

브라우저에서 `http://localhost:8000` 접속  
→ 이미지·PDF 업로드 → Asset Name 입력 → **Generate AAS** 클릭

### CLI 직접 실행

```bash
# 이미지 파일로 바로 실행
python run_from_image.py

# 샘플 데이터로 파이프라인 테스트
python main.py
```

### 테스트

```bash
python -m unittest
```

---

## 결과물 위치

| 항목 | 경로 |
|---|---|
| 웹 UI 생성 결과 | SQLite DB (`data/aas_database.db`) |
| CLI 실행 결과 | `data/generated_aas/{asset_id}.aas.json` |
| 파이프라인 전체 결과 | `data/output/{asset_id}_pipeline_result.json` |

---

## 전체 흐름

```
이미지 / PDF 업로드
  → OCR (easyocr)
  → LLM 속성 추출 (llama3.2)
  → Semantic Node 변환
  → 임베딩 후보 검색 (nomic-embed-text)
  → 의미 매칭
  → AAS 매핑 (DigitalNameplate / TechnicalData)
  → AAS JSON 생성
```

---

## 모듈 구조

```
app/            파이프라인 오케스트레이터, 설정, 모델
interfaces/     추상 인터페이스 (교체 지점)
modules/
  extraction/   LLM 속성 추출기
  retrieval/    임베딩 기반 후보 검색기
  matching/     LLM / 규칙 기반 매처
  semantic_node/ Semantic Node 빌더
  aas_mapping/  서브모델 분류 + AAS 매핑
  aas_generation/ AAS JSON 생성기
  llm/          Ollama 클라이언트, 프롬프트 템플릿
repositories/   AAS Property DB (properties.json)
static/         웹 UI (index.html)
api.py          FastAPI 백엔드
db.py           SQLite 헬퍼
```
