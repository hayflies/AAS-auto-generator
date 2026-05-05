# AAS Auto Generator

`description.md`의 설계를 기반으로 한 **LLM 기반 AAS 자동 생성 + 디지털 트윈 등록 파이프라인 뼈대**입니다.

현재 구현은 외부 LLM, OCR, Embedding DB, 3D 생성기, DT Viewer 없이도 샘플 입력이 끝까지 흐르도록 만든 MVP 골격입니다. 각 핵심 기능은 `interfaces/`의 abstract class를 통해 교체할 수 있습니다.

## 전체 흐름

```text
Input Layer
→ Optional CV Module
→ Information Extraction Layer
→ Semantic Node Builder
→ Candidate Retrieval Engine
→ Entity Matching Engine
→ AAS Mapping Engine
→ 3D Model Manager
→ AAS Generator
→ DT Integration Layer
→ DT Validation Layer
```

## 실행

```bash
python main.py
```

샘플이 아닌 JSON을 넣으려면:

```bash
python main.py --input-json data/input/sample_asset.json
```

선택형 구현체를 명시적으로 켤 수도 있습니다.

```bash
python main.py --pipeline llm
python main.py --pipeline yolo
python main.py --pipeline llm-yolo
```

`default` 파이프라인은 외부 런타임 의존성 없이 동작합니다. `llm` 계열은 Ollama 서버와 모델이 필요하고, `yolo` 계열은 `ultralytics`와 YOLO weight 파일이 필요합니다.

결과 파일은 기본적으로 다음 위치에 생성됩니다.

```text
data/output/{asset_id}_pipeline_result.json
data/generated_aas/{asset_id}.aas.json
```

## 테스트

```bash
python -m unittest
```

## 교체 지점

- `interfaces/base_extractor.py`: OCR, 문서 파서, LLM 추출기
- `interfaces/base_semantic_builder.py`: Semantic Node enricher
- `interfaces/base_retriever.py`: Embedding/Vector DB 기반 후보 검색기
- `interfaces/base_matcher.py`: LLM matcher, cross-encoder, classifier
- `interfaces/base_aas_generator.py`: AAS JSON/AASX 생성기
- `interfaces/base_model_generator.py`: 기존 모델 로더, TripoSR, Blender, Meshy
- `interfaces/base_dt_adapter.py`: Three.js, Unity, Isaac Sim, Omniverse 연동

## 현재 기본 구현

- 수동 입력 기반 entity 추출
- 로컬 JSON repository 기반 후보 검색
- rule-based entity matching
- NoOp CV adapter
- 코드 기반 AAS JSON 생성 및 구조 검증
- 기존 3D 모델 경로 참조 또는 생성 예정 경로 기록
- in-memory DT 등록 및 mock sensor validation
