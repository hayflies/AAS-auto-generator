"""LLM 기반 Semantic Node Builder.

interfaces/base_semantic_builder.py의 BaseSemanticNodeBuilder를 구현한다.
파이프라인은 DefaultSemanticNodeBuilder 대신 이 클래스를 꽂아 쓸 수 있다.

DefaultSemanticNodeBuilder는 31개 하드코딩 사전에 없는 속성은 기본 문장만 반환한다.
이 구현은 어떤 속성이든 LLM이 동적으로 개념 정의와 용도를 생성한다.
"""

from __future__ import annotations

from typing import Any

from app.models import ExtractedEntity, SemanticNode
from interfaces.base_semantic_builder import BaseSemanticNodeBuilder
from modules.llm.ollama_client import OllamaClient, OllamaConnectionError
from modules.llm.prompts import build_semantic_node_prompt


class LLMSemanticNodeBuilder(BaseSemanticNodeBuilder):
    """Ollama LLM을 사용해 ExtractedEntity를 SemanticNode로 변환한다.

    각 속성마다 LLM에 conceptual_definition과 affordance 생성을 요청한다.
    Ollama 연결 실패 시 기본 문장으로 fallback한다.

    Args:
        client: OllamaClient 인스턴스. 기본값은 새 인스턴스 생성.
    """

    def __init__(self, client: OllamaClient | None = None):
        self.client = client or OllamaClient()

    def build(self, entities: list[ExtractedEntity]) -> list[SemanticNode]:
        """raw entity 목록에 LLM이 생성한 의미 설명을 추가한다."""
        nodes: list[SemanticNode] = []
        for index, entity in enumerate(entities, start=1):
            definition, affordance = self._enrich(entity)
            nodes.append(SemanticNode(
                semantic_node_id=f"SN_{index:03d}",
                name=entity.raw_name,
                value=entity.raw_value,
                unit=entity.raw_unit,
                value_type=self._infer_value_type(entity.raw_value),
                conceptual_definition=definition,
                affordance=affordance,
                source_description=f"Extracted from {entity.source}.",
                source_reference=entity.source_reference,
                confidence=entity.confidence,
            ))
        return nodes

    def _enrich(self, entity: ExtractedEntity) -> tuple[str, str]:
        """LLM으로 conceptual_definition과 affordance를 생성한다.

        LLM 호출 실패 시 기본 문장으로 fallback한다.
        """
        prompt = build_semantic_node_prompt(
            name=entity.raw_name,
            value=str(entity.raw_value),
            unit=entity.raw_unit,
        )
        try:
            response = self.client.generate_json(prompt, fallback={})
        except OllamaConnectionError as e:
            print(f"[LLMSemanticNodeBuilder] Ollama 연결 실패: {e}")
            response = {}

        definition = str(response.get("conceptual_definition") or "").strip()
        affordance = str(response.get("affordance") or "").strip()

        if not definition:
            definition = f"Asset attribute describing {entity.raw_name}."
        if not affordance:
            affordance = f"Used as structured metadata for {entity.raw_name}."

        return definition, affordance

    def _infer_value_type(self, value: Any) -> str:
        """AAS Property 생성에 필요한 value type을 추론한다."""
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
