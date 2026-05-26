# LLM 및 임베딩 모델

본 시스템은 속성 추출, Semantic Node 생성, entity matching, 후보 검색에 Ollama 기반 로컬 모델을 사용합니다.

---

## LLM: Qwen2.5:7B

**개발사**: Alibaba Cloud  
**출시**: 2024년 9월  
**공식 페이지**: https://qwen2.ai

### 개요

Qwen2.5는 Alibaba Cloud가 공개한 오픈소스 LLM 시리즈로, 18조 토큰으로 사전 학습되었습니다. 7B 파라미터 모델은 동급 크기 대비 추론·분류·구조화 출력에서 높은 성능을 보이며, 특히 JSON 형식 준수율이 우수합니다.

### 주요 사양

| 항목 | 값 |
|---|---|
| 파라미터 | 7B |
| 컨텍스트 길이 | 128K 토큰 |
| 학습 데이터 | 18조 토큰 |
| 지원 언어 | 29개 언어 (한국어 포함) |
| 라이선스 | Apache 2.0 |

### 기존 모델과의 비교

| 항목 | llama3.2:3B | qwen2.5:7B |
|---|---|---|
| 개발사 | Meta | Alibaba Cloud |
| 파라미터 | 3B | 7B |
| 학습 토큰 | 9조 | 18조 |
| 구조화 출력(JSON) | 보통 | 우수 |
| 다국어 지원 | 영어 중심 | 29개 언어 |
| MMLU 벤치마크 | 58.0 | 74.2 |

### 시스템 내 역할

- **속성 추출**: OCR·문서 텍스트에서 키-값 속성을 JSON으로 추출
- **Semantic Node 보강**: 속성의 conceptual_definition, affordance 생성
- **LLM 정밀 매핑**: Top-K 후보 중 최종 AAS Property 선택 및 매핑 근거 생성

### 설치

```bash
ollama pull qwen2.5:7b
```

---

## 임베딩 모델: mxbai-embed-large

**개발사**: mixedbread.ai  
**출시**: 2024년 초  
**공식 페이지**: https://www.mixedbread.ai/blog/mxbai-embed-large-v1

### 개요

mxbai-embed-large는 mixedbread.ai가 공개한 영어 임베딩 모델로, MTEB(Massive Text Embedding Benchmark) 평가에서 오픈소스 모델 상위권을 기록합니다. 검색·분류·매칭 태스크에 특화되어 있으며, 1024차원 벡터로 높은 표현력을 제공합니다.

### 주요 사양

| 항목 | 값 |
|---|---|
| 벡터 차원 | 1024 |
| 모델 크기 | 335M 파라미터 |
| 최대 입력 길이 | 512 토큰 |
| MTEB 점수 | 64.7 |
| 라이선스 | Apache 2.0 |

### 기존 모델과의 비교

| 항목 | nomic-embed-text | mxbai-embed-large |
|---|---|---|
| 개발사 | Nomic AI | mixedbread.ai |
| 벡터 차원 | 768 | 1024 |
| 모델 크기 | 137M | 335M |
| MTEB 점수 | 62.4 | 64.7 |
| 검색·매칭 특화 | 보통 | 우수 |

### MTEB 벤치마크란

MTEB(Massive Text Embedding Benchmark)는 임베딩 모델의 표준 평가 지표입니다. 검색(Retrieval), 분류(Classification), 클러스터링(Clustering), 의미 유사도(STS), 매칭(PairClassification) 등 56개 태스크를 종합 평가합니다.  
공식 리더보드: https://huggingface.co/spaces/mteb/leaderboard

### 시스템 내 역할

ECLASS IRDI가 미등재된 비표준 속성(PayloadCapacity, DegreesOfFreedom, MaxReach 등)에 적용됩니다.

```
SemanticNode (속성명 + 설명)
    ↓ 벡터화
코사인 유사도 계산
    ↓
AAS Property Repository에서 Top-K 후보 반환
```

벡터 차원이 768→1024로 늘어나고 표현력이 높아질수록, 의미가 유사한 속성들 간의 구분이 더 정밀해져 오매핑 가능성이 줄어듭니다.

### 설치

```bash
ollama pull mxbai-embed-large
```

---

## 모델 교체 이력

| 구분 | 이전 | 현재 | 변경 사유 |
|---|---|---|---|
| LLM | llama3.2:3B | qwen2.5:7B | 파라미터 2배 이상, JSON 출력 안정성 향상 |
| 임베딩 | nomic-embed-text (768d) | mxbai-embed-large (1024d) | MTEB 상위권, 검색·매칭 태스크 특화 |
