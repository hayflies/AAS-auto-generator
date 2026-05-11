from __future__ import annotations

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
    return f"""You are an industrial asset data extraction expert specializing in robot and equipment specifications.

Extract properties from the text below.

Rules:
- Extract ALL clearly readable properties.
- Separate the numeric value from its unit (e.g. "24 VDC" → raw_value="24", raw_unit="VDC").
- Property names must be in English (translate or normalize if needed).
- If there is no unit, set raw_unit to null.
- Do NOT merge or summarize — extract each property as a separate entry.
- Ignore non-property lines (e.g. table headers like "Item", "Qty", part numbers like "YM070-210-A099-RH").

SKIP a property if ANY of these are true:
- The numeric value is missing or replaced by brackets only (e.g. "[Mbps]", "[N/A]", "[TBD]") → SKIP entirely.
- The value unit clearly contradicts the property name (e.g. a mass unit like "g" or "kg" paired with a dimension name like "Width" or "Length") → SKIP.
- The value appears to be a hardware resolution or encoder count (e.g. integers like 4096, 1024, 2048 paired with no unit for a joint/angle property) → SKIP; these are not angle ranges.
- Multiple conflicting values appear for the same property — pick ONLY the one labeled as the primary/nominal specification. If unclear which is primary, set confidence below 0.60.
- The value is a range expression like "X~Y" or "X to Y" — extract the nominal/maximum value only.

Return ONLY a JSON array. No explanation, no markdown, no extra text.

Example:
[
  {{"raw_name": "Manufacturer", "raw_value": "ROBOTIS", "raw_unit": null, "confidence": 0.99}},
  {{"raw_name": "DOF", "raw_value": "6", "raw_unit": null, "confidence": 0.98}},
  {{"raw_name": "Payload", "raw_value": "3", "raw_unit": "kg", "confidence": 0.97}},
  {{"raw_name": "Reach", "raw_value": "580", "raw_unit": "mm", "confidence": 0.97}},
  {{"raw_name": "Weight", "raw_value": "13.5", "raw_unit": "kg", "confidence": 0.97}},
  {{"raw_name": "Operating Voltage", "raw_value": "24", "raw_unit": "VDC", "confidence": 0.96}},
  {{"raw_name": "Repeatability", "raw_value": "0.05", "raw_unit": "mm", "confidence": 0.95}},
  {{"raw_name": "TCP Speed", "raw_value": "900", "raw_unit": "mm/s", "confidence": 0.95}},
  {{"raw_name": "Host Interface", "raw_value": "Ethernet", "raw_unit": null, "confidence": 0.94}},
  {{"raw_name": "Serial Number", "raw_value": "A1B2C3D4", "raw_unit": null, "confidence": 0.85}}
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
        candidate_id = c.get("candidate_id", f"candidate_{i}")
        id_short = c.get("idShort", candidate_id)
        candidate_desc = c.get("description", "")
        candidate_submodel = c.get("submodel", "")
        candidate_semantic_id = c.get("semantic_id", "")
        candidate_unit = c.get("preferred_unit", "")
        candidate_source = c.get("source", "")
        candidates_text += (
            f"\nCandidate {i}:\n"
            f"  candidate_id: {candidate_id}\n"
            f"  idShort: {id_short}\n"
            f"  Submodel: {candidate_submodel}\n"
            f"  Semantic ID: {candidate_semantic_id}\n"
            f"  Preferred unit: {candidate_unit}\n"
            f"  Source: {candidate_source}\n"
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
- Return the exact candidate_id field shown for each candidate.
- Prefer a Submodel Template or project AAS property candidate over a raw ECLASS/IEC dictionary candidate when both describe the same concept.

Return ONLY a JSON array. No explanation, no markdown, no extra text.

Example:
[
  {{"candidate_id": "AAS_PROP_NOMINAL_VOLTAGE", "match": true, "score": 0.93, "reason": "same voltage concept"}},
  {{"candidate_id": "AAS_PROP_RATED_CURRENT", "match": false, "score": 0.12, "reason": "current is not voltage"}}
]

JSON array:"""


def build_text_cleaning_prompt(raw_text: str) -> str:
    """OCR 또는 PDF에서 추출한 원본 텍스트를 정제하는 프롬프트를 생성한다.

    노이즈(오탈자, 줄 깨짐, 불필요한 기호)를 제거하고
    산업 자산 속성 텍스트만 남기도록 LLM에 지시한다.

    Args:
        raw_text: OCR 결과 또는 PDF에서 추출한 원본 텍스트.

    Returns:
        LLM에 전달할 완성된 프롬프트 문자열.

    Example:
        prompt = build_text_cleaning_prompt("R4ted V0ltage: 24V\\nW3ight 3.5 kg")
        response = client.generate(prompt)
        # "Rated Voltage: 24V\\nWeight: 3.5 kg"
    """
    return f"""You are an industrial asset data extraction expert.

The following text was extracted from a nameplate image or PDF document using OCR.
It may contain noise, typos, garbled characters, or formatting artifacts.

Your task:
1. Fix obvious OCR errors (e.g. "R4ted" → "Rated", "V0ltage" → "Voltage")
2. Keep only lines that describe asset properties (name: value, unit)
3. Remove headers, footers, watermarks, and irrelevant text
4. Preserve the original key-value structure
5. Output clean plain text only — no JSON, no markdown, no explanation

Raw text:
{raw_text}

Cleaned text:"""


def build_submodel_template_selection_prompt(
    asset: dict,
    property_item: dict,
    options: list[dict],
) -> str:
    """MatchedProperty를 어떤 Submodel Template/Submodel에 둘지 판단하는 프롬프트."""
    option_lines = []
    for index, option in enumerate(options, start=1):
        option_lines.append(
            "\n".join(
                [
                    f"Option {index}:",
                    f"  submodel: {option.get('submodel', '')}",
                    f"  description: {option.get('description', '')}",
                    f"  evidence: {option.get('evidence', '')}",
                ]
            )
        )
    options_text = "\n\n".join(option_lines)

    return f"""You are an AAS (Asset Administration Shell) submodel template placement expert.

Choose the best Submodel for the property below.

[Asset]
name: {asset.get("asset_name", "")}
type: {asset.get("asset_type", "")}
manufacturer: {asset.get("manufacturer", "")}

[Property]
idShort: {property_item.get("idShort", "")}
value: {property_item.get("value", "")}
unit: {property_item.get("unit", "")}
definition: {property_item.get("definition", "")}
semanticId: {property_item.get("semanticId", "")}
eclassIrdi: {property_item.get("eclassIrdi", "")}
currentSubmodel: {property_item.get("currentSubmodel", "")}
source: {property_item.get("source", "")}
path: {property_item.get("path", "")}

[Allowed Submodel Options]
{options_text}

Rules:
- Select exactly one submodel from the allowed options.
- DigitalNameplate is for identity, manufacturer, model, serial, product designation, certificates, and static nameplate information.
- TechnicalData is for technical specifications, ratings, dimensions, performance, electrical/mechanical limits, and ECLASS/IEC CDD technical properties.
- ProvisionOf3DModels is only for 3D model files or geometry references.
- OperationalData is for runtime state, sensor values, status, and time-varying telemetry.
- Prefer the option whose evidence says the semanticId or idShort exists in a loaded template.
- If the currentSubmodel is wrong, correct it.
- If confidence is below 0.70, set review_required=true.

Return ONLY this JSON object:
{{"selected_submodel": "...", "confidence": 0.0, "review_required": true, "reason": "short reason"}}

JSON:"""


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
