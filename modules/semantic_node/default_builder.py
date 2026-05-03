from __future__ import annotations

from typing import Any

from app.models import ExtractedEntity, SemanticNode
from interfaces.base_semantic_builder import BaseSemanticNodeBuilder


class DefaultSemanticNodeBuilder(BaseSemanticNodeBuilder):
    """결정적 규칙으로 ExtractedEntity를 Semantic Node로 변환한다.

    실제 LLM/ontology enricher가 붙기 전에도 Semantic Node 형식과 downstream
    매핑 과정을 검증할 수 있도록 만든 기본 구현이다.
    """

    # MVP에서는 대표 필드의 개념 정의를 사전으로 제공한다.
    # 추후에는 LLM, ECLASS, IEC CDD, 사내 ontology로 보강할 수 있다.
    DEFINITIONS = {
        "asset name": "Human-readable name assigned to the asset.",
        "asset type": "Functional class or category of the asset.",
        "manufacturer": "Organization that manufactured or supplied the asset.",
        "model name": "Manufacturer-specific model or product designation.",
        "rated voltage": "Nominal voltage required for operating the asset.",
        "nominal voltage": "Nominal voltage required for operating the asset.",
        "rated current": "Nominal electrical current required by the asset.",
        "serial number": "Unique serial identifier assigned by the manufacturer.",
        "weight": "Mass or weight of the asset.",
        "temperature": "Observed or allowed temperature value associated with the asset.",
        "rotation angle": "Angular position or rotation command applied to the asset.",
        "status": "Operational state reported for the asset.",
    }

    # 각 속성이 DT 등록/검증에서 어떤 의미로 쓰이는지 설명한다.
    AFFORDANCES = {
        "asset name": "Used to identify the asset in AAS and DT views.",
        "asset type": "Used to select suitable submodels and DT behavior.",
        "manufacturer": "Used for Digital Nameplate registration and traceability.",
        "model name": "Used for Digital Nameplate registration and catalog matching.",
        "rated voltage": "Used to determine electrical compatibility.",
        "nominal voltage": "Used to determine electrical compatibility.",
        "rated current": "Used to determine electrical load requirements.",
        "serial number": "Used for unique asset tracking.",
        "weight": "Used for installation, transport, and simulation metadata.",
        "temperature": "Used to verify state and visual updates in the DT layer.",
        "rotation angle": "Used to verify movement behavior in the DT layer.",
        "status": "Used to verify state changes in the DT layer.",
    }

    def build(self, entities: list[ExtractedEntity]) -> list[SemanticNode]:
        """raw entity 목록에 의미 설명과 value type을 추가한다."""

        nodes: list[SemanticNode] = []
        for index, entity in enumerate(entities, start=1):
            key = entity.raw_name.lower()
            nodes.append(
                SemanticNode(
                    semantic_node_id=f"SN_{index:03d}",
                    name=entity.raw_name,
                    value=entity.raw_value,
                    unit=entity.raw_unit,
                    value_type=self._infer_value_type(entity.raw_value),
                    conceptual_definition=self.DEFINITIONS.get(
                        key,
                        f"Asset attribute describing {entity.raw_name}.",
                    ),
                    affordance=self.AFFORDANCES.get(
                        key,
                        f"Used as structured metadata for {entity.raw_name}.",
                    ),
                    source_description=f"Extracted from {entity.source}.",
                    source_reference=entity.source_reference,
                    confidence=entity.confidence,
                )
            )
        return nodes

    def _infer_value_type(self, value: Any) -> str:
        """AAS Property 생성에 필요한 단순 value type을 추론한다."""
        if isinstance(value, bool):
            return "boolean"
        if isinstance(value, int) and not isinstance(value, bool):
            return "integer"
        if isinstance(value, float):
            return "float"
        if isinstance(value, str):
            try:
                int(value)
                return "integer"
            except ValueError:
                pass
            try:
                float(value)
                return "float"
            except ValueError:
                return "string"
        return "string"
