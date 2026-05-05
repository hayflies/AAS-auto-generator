"""LLM 프롬프트 템플릿 모음.

이 모듈은 Extraction, Matching, Semantic Node 단계에서 사용하는 프롬프트 템플릿을 관리한다.
프롬프트를 코드에서 분리해서 수정이 필요할 때 이 파일만 열면 된다.

사용처:
    - llm_extractor.py: build_extraction_prompt
    - llm_matcher.py: build_matching_prompt, build_batch_matching_prompt
    - llm_semantic_builder.py: build_semantic_node_prompt
"""


def build_extraction_prompt(input_text: str) -> str:
    """자산 텍스트에서 속성을 추출하는 프롬프트를 생성한다.

    LLM이 텍스트에서 속성명, 값, 단위를 추출해서
    JSON 배열 형식으로 반환하도록 지시한다.

    Args:
        input_text: 자산 정보가 담긴 원본 텍스트.
                    명판 OCR 결과, 사양서 텍스트, 사용자 입력 등.

    Returns:
        LLM에 전달할 완성된 프롬프트 문자열.

    Example:
        prompt = build_extraction_prompt("정격전압 24V, 무게 3.5kg")
        response = client.generate_json_list(prompt)
        # [{"raw_name": "Rated Voltage", "raw_value": "24", "raw_unit": "V"}, ...]
    """
    return f"""You are an industrial asset data extraction expert.

Extract all properties from the text below.
Each property must have a name, value, and unit.
If there is no unit, set unit to null.
Property names must be written in English.

Return ONLY a JSON array. No explanation, no markdown, no extra text.

Example:
[
  {{"raw_name": "Rated Voltage", "raw_value": "24", "raw_unit": "V", "confidence": 0.95}},
  {{"raw_name": "Weight", "raw_value": "3.5", "raw_unit": "kg", "confidence": 0.90}},
  {{"raw_name": "Serial Number", "raw_value": "SN-001", "raw_unit": null, "confidence": 0.85}}
]

Text to extract from:
{input_text}

JSON array:"""


def build_matching_prompt(semantic_node: dict, candidate: dict) -> str:
    """Semantic Node와 AAS Property 후보의 의미 일치 여부를 판단하는 프롬프트를 생성한다.

    LLM이 두 속성이 같은 의미인지 판단해서
    match 여부와 score를 JSON으로 반환하도록 지시한다.

    Args:
        semantic_node: 추출된 자산 속성 정보.
                       name, value, unit, conceptual_definition 등을 포함.
        candidate: AAS Property 후보 정보.
                   idShort, description, submodel 등을 포함.

    Returns:
        LLM에 전달할 완성된 프롬프트 문자열.

    Example:
        prompt = build_matching_prompt(
            {"name": "Rated Voltage", "value": "24", "unit": "V"},
            {"idShort": "NominalVoltage", "description": "Nominal voltage of the asset"}
        )
        response = client.generate_json(prompt)
        # {"match": true, "score": 0.94, "reason": "same electrical voltage concept"}
    """
    node_name = semantic_node.get("name", "")
    node_value = semantic_node.get("value", "")
    node_unit = semantic_node.get("unit", "")
    node_definition = semantic_node.get("conceptual_definition", "")

    candidate_id = candidate.get("idShort", candidate.get("candidate_id", ""))
    candidate_desc = candidate.get("description", "")
    candidate_submodel = candidate.get("submodel", "")

    return f"""You are an AAS (Asset Administration Shell) standard expert.

Determine whether the following two properties represent the same concept.

[My Property]
Name: {node_name}
Value: {node_value}
Unit: {node_unit}
Definition: {node_definition}

[AAS Candidate Property]
idShort: {candidate_id}
Description: {candidate_desc}
Submodel: {candidate_submodel}

Rules:
- match is true if both properties represent the same or equivalent physical concept, even if terminology differs (e.g. "rated voltage" and "nominal voltage" are the same concept).
- In industrial/AAS context, prefer matching: similar unit + similar physical meaning = match.
- score is a float between 0.0 and 1.0 representing semantic similarity.
- reason must be a short English sentence explaining your decision.

Return ONLY a JSON object. No explanation, no markdown, no extra text.

Example:
{{"match": true, "score": 0.92, "reason": "both represent the same electrical voltage concept"}}

JSON:"""


def build_batch_matching_prompt(semantic_node: dict, candidates: list) -> str:
    """Semantic Node와 여러 후보를 한 번에 비교하는 프롬프트를 생성한다.

    후보가 많을 때 하나씩 호출하는 대신 한 번에 처리해서
    Ollama 호출 횟수를 줄인다.

    Args:
        semantic_node: 추출된 자산 속성 정보.
        candidates: AAS Property 후보 목록.

    Returns:
        LLM에 전달할 완성된 프롬프트 문자열.

    Example:
        prompt = build_batch_matching_prompt(
            {"name": "Rated Voltage", "value": "24", "unit": "V"},
            [
                {"idShort": "NominalVoltage", "description": "..."},
                {"idShort": "RatedCurrent",   "description": "..."},
            ]
        )
        response = client.generate_json_list(prompt)
        # [
        #   {"candidate_id": "NominalVoltage", "match": true,  "score": 0.94},
        #   {"candidate_id": "RatedCurrent",   "match": false, "score": 0.12},
        # ]
    """
    node_name = semantic_node.get("name", "")
    node_value = semantic_node.get("value", "")
    node_unit = semantic_node.get("unit", "")
    node_definition = semantic_node.get("conceptual_definition", "")

    candidates_text = ""
    for i, c in enumerate(candidates, start=1):
        candidate_id = c.get("idShort", c.get("candidate_id", f"candidate_{i}"))
        candidate_desc = c.get("description", "")
        candidates_text += (
            f"\nCandidate {i}:\n"
            f"  idShort: {candidate_id}\n"
            f"  Description: {candidate_desc}\n"
        )

    return f"""You are an AAS (Asset Administration Shell) standard expert.

Determine whether each candidate property matches the given property.

[My Property]
Name: {node_name}
Value: {node_value}
Unit: {node_unit}
Definition: {node_definition}

[Candidates]
{candidates_text}

Rules:
- match is true if the candidate represents the same or equivalent concept as My Property, even if terminology differs.
- In industrial/AAS context, similar unit + similar physical meaning = match.
- score is a float between 0.0 and 1.0.
- Use the exact idShort value as candidate_id.

Return ONLY a JSON array. No explanation, no markdown, no extra text.

Example:
[
  {{"candidate_id": "NominalVoltage", "match": true, "score": 0.93}},
  {{"candidate_id": "RatedCurrent", "match": false, "score": 0.12}}
]

JSON array:"""


def build_semantic_node_prompt(name: str, value: str, unit: str | None) -> str:
    """산업 자산 속성의 개념 정의와 용도를 생성하는 프롬프트를 만든다.

    Args:
        name: 속성 이름 (예: "Rated Voltage")
        value: 속성 값 (예: "24")
        unit: 단위 (예: "V", 없으면 None)

    Returns:
        LLM에 전달할 완성된 프롬프트 문자열.

    Example:
        prompt = build_semantic_node_prompt("Rated Voltage", "24", "V")
        response = client.generate_json(prompt)
        # {"conceptual_definition": "...", "affordance": "..."}
    """
    unit_text = f", unit: {unit}" if unit else ""
    return f"""You are an industrial asset ontology expert specializing in AAS (Asset Administration Shell).

Given an asset property, provide its conceptual definition and how it is used in digital twin systems.

Property:
  name: {name}
  value: {value}{unit_text}

Rules:
- conceptual_definition: one sentence explaining what this property physically means.
- affordance: one sentence explaining how this property is used in AAS or digital twin systems.
- Keep both fields concise (under 20 words each).

Return ONLY a JSON object. No explanation, no markdown, no extra text.

Example:
{{"conceptual_definition": "Nominal voltage required for operating the asset.", "affordance": "Used to determine electrical compatibility in AAS Nameplate submodel."}}

JSON:"""
