# LLM 공통 인프라와 현재 파이프라인 연결

Ollama 기반 로컬 LLM을 사용해 AAS 자동 생성 파이프라인의 문서 정제, 속성 추출, 의미 보강, 매칭, embedding 검색을 지원합니다.
`modules/llm/`에는 공통 클라이언트와 프롬프트만 두고, 계층별 구현체는 프로젝트 구조에 맞춰 각 디렉토리에 배치합니다.

---

## 파이프라인에서의 위치

```
[Input Layer / DocumentProcessor]
        ↓
[OCR/PDF text cleaning]       ← modules/llm/prompts.py
        ↓
[LLMExtractor]                ← modules/extraction
        ↓
[LLMSemanticNodeBuilder]      ← modules/semantic_node
        ↓
[EmbeddingCandidateRetriever] ← modules/retrieval
        ↓
[LLMMatcher 또는 skip_llm 매칭] ← modules/matching
        ↓
[AAS 생성 → DT 등록]        
```

---

## 사용 모델

| 용도 | 모델 |
|---|---|
| Extraction / Semantic Node / Matching | `llama3.2` (Ollama) |
| Embedding | `nomic-embed-text` (Ollama) |

**사전 설치 필요:**
```bash
ollama pull llama3.2
ollama pull nomic-embed-text
```

---

## 파일 구성

| 파일 | 역할 |
|---|---|
| `ollama_client.py` | Ollama REST API 공통 클라이언트 |
| `prompts.py` | LLM 프롬프트 템플릿 모음 |
| `../extraction/llm_extractor.py` | 파이프라인 2단계: 속성 추출 |
| `../semantic_node/llm_semantic_builder.py` | 파이프라인 3단계: 의미 보강 |
| `../retrieval/embedding_retriever.py` | 파이프라인 4단계: 후보 검색 |
| `../matching/llm_matcher.py` | 파이프라인 5단계: 의미 매칭 |

---

## 각 모듈 설명

### `ollama_client.py` — 공통 클라이언트

모든 Ollama 호출의 단일 창구입니다. `interfaces/base_llm.py`의 `BaseLLM`과 `interfaces/base_embedding.py`의 `BaseEmbeddingModel`을 구현하므로, extraction/semantic/matching 계층은 Ollama 구체 타입이 아니라 `BaseLLM` 계약을 통해 사용합니다.

```python
from modules.llm import OllamaClient

client = OllamaClient()
client.generate("안녕")                    # 텍스트 응답
client.generate_json("...")               # dict 응답
client.generate_json_list("...")          # list 응답
client.embed("Rated Voltage V")           # 임베딩 벡터
client.is_available()                     # 서버 상태 확인
```

---

### `prompts.py` — 프롬프트 템플릿

프롬프트를 코드에서 분리해 관리합니다. 수정이 필요할 때 이 파일만 열면 됩니다.

| 함수 | 사용처 |
|---|---|
| `build_extraction_prompt(input_text)` | `llm_extractor.py` |
| `build_text_cleaning_prompt(raw_text)` | `document_processor.py` |
| `build_semantic_node_prompt(name, value, unit)` | `llm_semantic_builder.py` |
| `build_matching_prompt(node, candidate)` | `llm_matcher.py` |
| `build_batch_matching_prompt(node, candidates)` | 현재 직접 호출 없음, batch matching 확장용 |

---

### `llm_extractor.py` — 속성 추출 (2단계)

**인터페이스:** `BaseInformationExtractor`

자산 정보 텍스트를 LLM이 읽고 속성 목록으로 구조화합니다.

```
입력:  AssetPackage (asset_name, manufacturer, documents 등)
출력:  list[ExtractedEntity]

예시 입력 텍스트:
  "asset_name: Robot Arm A, rated_voltage: 24V, weight: 3.5kg"

예시 출력:
  ExtractedEntity(raw_name="Rated Voltage", raw_value="24", raw_unit="V", source="llm_extraction")
  ExtractedEntity(raw_name="Weight",        raw_value="3.5", raw_unit="kg", source="llm_extraction")
```

**특이사항:**
- LLM 응답이 빈 리스트일 경우 최대 3회 재시도
- `raw_name` / `name` 키 모두 처리 (llama3.2 혼용 대응)
- bracket-only 값, 단위만 추출된 값, encoder resolution, 치수+무게단위 오분류, 낮은 confidence 항목을 필터링

---

### `llm_semantic_builder.py` — 의미 보강 (3단계)

**인터페이스:** `BaseSemanticNodeBuilder`

추출된 속성마다 LLM이 개념 정의(conceptual_definition)와 용도(affordance)를 동적으로 생성합니다.
현재 기본 파이프라인에서는 처리 시간을 줄이기 위해 `skip_enrichment=True`를 사용합니다.

```
입력:  list[ExtractedEntity]
출력:  list[SemanticNode]

예시:
  입력: ExtractedEntity(raw_name="Rated Voltage", raw_value="24", raw_unit="V")

  출력: SemanticNode(
    name="Rated Voltage",
    conceptual_definition="Nominal voltage required for operating the asset.",
    affordance="Used to determine electrical compatibility in AAS Nameplate submodel."
  )
```

**기존 대비 개선점:**
- `DefaultSemanticNodeBuilder`: 31개 하드코딩 사전 — 없는 속성은 기본 문장만 반환
- `LLMSemanticNodeBuilder`: 어떤 속성이든 LLM이 동적으로 의미 생성
- ECLASS 사전을 로드해 속성명/alias를 `eclass_irdi`로 보강

---

### `embedding_retriever.py` — 후보 검색 (4단계)

**인터페이스:** `BaseCandidateRetriever`

`nomic-embed-text` 임베딩 벡터의 코사인 유사도로 AAS Property 후보를 검색합니다.

```
입력:  SemanticNode, top_k
출력:  list[AASPropertyCandidate] (유사도 내림차순)

예시:
  쿼리: "Rated Voltage - electrical compatibility - V"
  결과: NominalVoltage (0.924), RatedCurrent (0.752), AssetType (0.624)
```

**기존 대비 개선점:**
- `InMemoryCandidateRetriever`: Jaccard 토큰 겹침 — 의미 유사도 반영 불가
- `EmbeddingCandidateRetriever`: 벡터 코사인 유사도 — 같은 의미 다른 단어도 검색 가능

**동작 방식:**
1. `SemanticNode.eclass_irdi`가 있으면 같은 IRDI 후보를 score 1.0으로 우선 반환
2. IRDI 매칭이 없으면 초기화 시 캐싱한 후보 임베딩과 query embedding의 코사인 유사도 계산
3. 단위 일치와 alias exact/partial match에 boost 적용
4. `nomic-embed-text` 없으면 `llama3.2`로 자동 fallback

---

### `llm_matcher.py` — 의미 매칭 (5단계)

**인터페이스:** `BaseEntityMatcher`

검색 엔진이 가져온 후보 중 LLM이 "이게 같은 의미인가"를 판단합니다.

```
입력:  SemanticNode, AASPropertyCandidate (1:1)
출력:  MatchResult

예시:
  노드:    "Rated Voltage, 24V"
  후보:    "NominalVoltage - Nominal voltage required for operating the asset"
  결과:    MatchResult(match=True, match_score=0.71, reason="same electrical voltage concept")
```

**파이프라인 호출 방식 (pipeline.py 85번 줄):**
```python
node_matches = [self.matcher.match(node, candidate) for candidate in candidates]
```
후보를 하나씩 받아 MatchResult 하나씩 반환하는 구조.

**특이사항:**
- llama3.2는 `match` boolean과 `score`를 모순되게 반환하는 경우가 있어 **score 기준으로 판단**
- `score >= threshold` 이면 match=True (기본 threshold: 0.45)
- 현재 기본 파이프라인은 `skip_llm=True`로 LLM matching 호출을 생략하고 embedding score threshold를 사용

---

## 현재 기본 파이프라인 연결

`app/pipeline.py`의 `create_default_pipeline()`이 현재 LLM/embedding 구현을 기본으로 연결합니다.

```text
LLMExtractor
→ LLMSemanticNodeBuilder(skip_enrichment=True)
→ EmbeddingCandidateRetriever
→ LLMMatcher(skip_llm=True)
```

`app/main.py`에는 `create_llm_pipeline()` import가 남아 있지만 현재 `app/pipeline.py`에는 해당 factory가 정의되어 있지 않습니다. CLI의 `--pipeline llm/yolo/llm-yolo` 경로는 추가 정리가 필요합니다.

---

## 테스트

```bash
# LLM 모듈 단위 테스트
python -m unittest tests/test_llm_client.py tests/test_llm_extractor.py tests/test_llm_matcher.py -v

# 이미지/PDF 경로 통합 실행
python run_from_image.py
```

**테스트 결과 예시:**
```
test_llm_client.py     mock 기반 요청/JSON 파싱/embedding 검증
test_llm_extractor.py  LLM 응답 → ExtractedEntity 변환 검증
test_llm_matcher.py    threshold와 MatchResult 구조 검증

기본 파이프라인 실행:
  semantic_nodes     = 8
  matched_properties = 8
  aas_valid          = True
  dt_status          = success
  dt_validation      = passed
```
