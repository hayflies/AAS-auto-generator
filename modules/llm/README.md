# LLM 모듈

Ollama 기반 로컬 LLM을 사용해 AAS 자동 생성 파이프라인의 4개 단계를 구현한 패키지입니다.

---

## 파이프라인에서의 위치

```
[Input Layer]               
        ↓
[LLMExtractor]              ← 이 패키지
        ↓
[LLMSemanticNodeBuilder]    ← 이 패키지
        ↓
[EmbeddingCandidateRetriever] ← 이 패키지
        ↓
[LLMMatcher]                ← 이 패키지
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
| `llm_extractor.py` | 파이프라인 2단계: 속성 추출 |
| `llm_semantic_builder.py` | 파이프라인 3단계: 의미 보강 |
| `embedding_retriever.py` | 파이프라인 4단계: 후보 검색 |
| `llm_matcher.py` | 파이프라인 5단계: 의미 매칭 |

---

## 각 모듈 설명

### `ollama_client.py` — 공통 클라이언트

모든 LLM 호출의 단일 창구입니다. 다른 모듈은 직접 HTTP 요청 없이 이 클라이언트를 통해 Ollama와 통신합니다.

```python
from modules.llm.ollama_client import OllamaClient

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
| `build_semantic_node_prompt(name, value, unit)` | `llm_semantic_builder.py` |
| `build_matching_prompt(node, candidate)` | `llm_matcher.py` |
| `build_batch_matching_prompt(node, candidates)` | `llm_matcher.py` |

---

### `llm_extractor.py` — 속성 추출 (2단계)

**인터페이스:** `BaseInformationExtractor`

자산 정보 텍스트를 LLM이 읽고 속성 목록으로 구조화합니다.

```
입력:  AssetPackage (asset_name, manufacturer, user_inputs, documents 등)
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

---

### `llm_semantic_builder.py` — 의미 보강 (3단계)

**인터페이스:** `BaseSemanticNodeBuilder`

추출된 속성마다 LLM이 개념 정의(conceptual_definition)와 용도(affordance)를 동적으로 생성합니다.

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
1. 초기화 시 `properties.json`의 모든 후보 임베딩을 미리 계산해 캐싱
2. `retrieve()` 호출 시 쿼리 임베딩 생성 후 코사인 유사도 계산
3. `nomic-embed-text` 없으면 `llama3.2`로 자동 fallback

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

---

## 파이프라인 연결 방법

`app/pipeline.py`의 `create_default_pipeline()` 함수에서 교체합니다.

```python
# 현재 (LLM 버전)
from modules.llm.llm_extractor import LLMExtractor
from modules.llm.llm_semantic_builder import LLMSemanticNodeBuilder
from modules.llm.embedding_retriever import EmbeddingCandidateRetriever
from modules.llm.llm_matcher import LLMMatcher

extractor        = LLMExtractor()
semantic_builder = LLMSemanticNodeBuilder()
retriever        = EmbeddingCandidateRetriever(repository_path)
matcher          = LLMMatcher(threshold=config.match_threshold)

# Rule-based로 되돌리려면
from modules.extraction import ManualInputExtractor
from modules.semantic_node import DefaultSemanticNodeBuilder
from modules.retrieval import InMemoryCandidateRetriever
from modules.matching import RuleBasedEntityMatcher
```

---

## 테스트

```bash
# LLM 모듈 단위 테스트 (24개)
python -m unittest tests/test_llm_client.py tests/test_llm_extractor.py tests/test_llm_matcher.py -v

# 전체 파이프라인 통합 테스트
python main.py
```

**테스트 결과 (2026-05-06 기준):**
```
test_llm_client.py     8/8  ✅
test_llm_extractor.py  8/8  ✅
test_llm_matcher.py    8/8  ✅

파이프라인 실행:
  semantic_nodes    = 13
  matched_properties = 3
  aas_valid          = True
  dt_status          = success
  dt_validation      = passed
```
