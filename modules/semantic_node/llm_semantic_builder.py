"""LLM 기반 Semantic Node Builder.

interfaces/base_semantic_builder.py의 BaseSemanticNodeBuilder를 구현한다.
파이프라인은 DefaultSemanticNodeBuilder 대신 이 클래스를 꽂아 쓸 수 있다.

DefaultSemanticNodeBuilder는 31개 하드코딩 사전에 없는 속성은 기본 문장만 반환한다.
이 구현은 어떤 속성이든 LLM이 동적으로 개념 정의와 용도를 생성한다.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.models import ExtractedEntity, SemanticNode
from interfaces.base_llm import BaseLLM, LLMConnectionError, LLMResponseFormatError
from interfaces.base_semantic_builder import BaseSemanticNodeBuilder
from modules.llm.ollama_client import OllamaClient
from modules.llm.prompts import build_batch_semantic_node_prompt, build_semantic_node_prompt

# ECLASS 사전 기본 경로
_ECLASS_DICT_PATH = (
    Path(__file__).parents[2]
    / "repositories"
    / "eclass_dictionary"
    / "eclass_properties.json"
)


class LLMSemanticNodeBuilder(BaseSemanticNodeBuilder):
    """LLM을 사용해 ExtractedEntity를 SemanticNode로 변환한다.

    각 속성마다 LLM에 conceptual_definition과 affordance 생성을 요청한다.
    fail_fast=False이면 LLM 연결 실패 시 기본 문장으로 fallback한다.
    초기화 시 ECLASS 사전을 로드해 속성명 → IRDI 역인덱스를 구성한다.

    Args:
        client: BaseLLM 인스턴스. 기본값은 새 OllamaClient 인스턴스.
        skip_enrichment: True이면 LLM enrichment를 생략한다.
        fail_fast: True이면 LLM enrichment 실패 시 기본 문장 fallback 대신 예외를 전파한다.
        eclass_dict_path: ECLASS 사전 JSON 파일 경로. 기본값은 repositories/eclass_dictionary.
    """

    def __init__(
        self,
        client: BaseLLM | None = None,
        skip_enrichment: bool = False,
        fail_fast: bool = False,
        eclass_dict_path: Path | None = None,
        semantic_batch_size: int = 1,
    ):
        self.client = client or OllamaClient()
        self.skip_enrichment = skip_enrichment
        self.fail_fast = fail_fast
        self.semantic_batch_size = max(1, semantic_batch_size)
        self.last_llm_call_count = 0
        self._eclass_lookup: dict[str, str] = self._load_eclass_dict(
            eclass_dict_path or _ECLASS_DICT_PATH
        )
        if self._eclass_lookup:
            print(f"[LLMSemanticNodeBuilder] ECLASS 사전 로드 완료: {len(self._eclass_lookup)}개 alias")

    @staticmethod
    def _load_eclass_dict(path: Path) -> dict[str, str]:
        """ECLASS 사전에서 alias → IRDI 역인덱스를 빌드한다.

        파일이 없으면 빈 dict를 반환해 파이프라인이 계속 동작하도록 한다.
        """
        if not path.exists():
            return {}
        try:
            with path.open(encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            print(f"[LLMSemanticNodeBuilder] ECLASS 사전 로드 실패: {e}")
            return {}

        lookup: dict[str, str] = {}
        entries = LLMSemanticNodeBuilder._dictionary_entries(data)
        for entry in entries:
            irdi = str(entry.get("irdi") or "").strip()
            if not irdi:
                continue
            preferred_name = entry.get("preferred_name", "")
            if preferred_name:
                lookup[preferred_name.lower()] = irdi
            for alias in entry.get("aliases", []):
                lookup[alias.lower()] = irdi
        return lookup

    @staticmethod
    def _dictionary_entries(data: Any) -> list[dict[str, Any]]:
        """Support both project JSON shapes: {"properties": [...]} and loose lists."""
        entries: list[dict[str, Any]] = []
        if isinstance(data, dict):
            properties = data.get("properties")
            if isinstance(properties, list):
                return LLMSemanticNodeBuilder._dictionary_entries(properties)
            if "irdi" in data:
                return [data]
            return []
        if isinstance(data, list):
            for item in data:
                entries.extend(LLMSemanticNodeBuilder._dictionary_entries(item))
        return entries

    def build(self, entities: list[ExtractedEntity]) -> list[SemanticNode]:
        """raw entity 목록에 LLM이 생성한 의미 설명과 ECLASS IRDI를 추가한다."""
        self.last_llm_call_count = 0
        if not self.skip_enrichment and self.semantic_batch_size > 1:
            return self._build_batch(entities, self.semantic_batch_size)

        nodes: list[SemanticNode] = []
        for index, entity in enumerate(entities, start=1):
            if self.skip_enrichment:
                definition = f"Asset attribute describing {entity.raw_name}."
                affordance = f"Used as structured metadata for {entity.raw_name}."
            else:
                definition, affordance = self._enrich(entity)

            nodes.append(self._node_from_entity(index, entity, definition, affordance))
        return nodes

    def build_batch(
        self,
        entities: list[ExtractedEntity],
        batch_size: int | None = None,
    ) -> list[SemanticNode]:
        """여러 entity를 batch prompt로 묶어 SemanticNode 목록을 생성한다."""
        self.last_llm_call_count = 0
        if self.skip_enrichment:
            return self.build(entities)
        return self._build_batch(entities, batch_size or self.semantic_batch_size)

    def _build_batch(
        self,
        entities: list[ExtractedEntity],
        batch_size: int,
    ) -> list[SemanticNode]:
        nodes: list[SemanticNode] = []
        next_node_index = 1
        for chunk in self._chunks(entities, max(1, batch_size)):
            enrichments = self._enrich_batch(chunk)
            for local_index, entity in enumerate(chunk, start=1):
                definition, affordance = enrichments.get(
                    local_index,
                    self._fallback_enrichment(entity),
                )
                nodes.append(
                    self._node_from_entity(
                        next_node_index,
                        entity,
                        definition,
                        affordance,
                    )
                )
                next_node_index += 1
        return nodes

    def _enrich(self, entity: ExtractedEntity) -> tuple[str, str]:
        """LLM으로 conceptual_definition과 affordance를 생성한다.

        fail_fast=False이면 LLM 호출 실패 시 기본 문장으로 fallback한다.
        """
        prompt = build_semantic_node_prompt(
            name=entity.raw_name,
            value=str(entity.raw_value),
            unit=entity.raw_unit,
        )
        try:
            self.last_llm_call_count += 1
            response = self.client.generate_json(prompt, fallback={})
        except LLMConnectionError as e:
            if self.fail_fast:
                raise
            print(f"[LLMSemanticNodeBuilder] LLM 연결 실패: {e}")
            response = {}

        definition = str(response.get("conceptual_definition") or "").strip()
        affordance = str(response.get("affordance") or "").strip()

        if self.fail_fast and (not definition or not affordance):
            raise LLMResponseFormatError(
                "LLM semantic enrichment response must include conceptual_definition and affordance."
            )

        if not definition:
            definition = f"Asset attribute describing {entity.raw_name}."
        if not affordance:
            affordance = f"Used as structured metadata for {entity.raw_name}."

        return definition, affordance

    def _enrich_batch(
        self,
        entities: list[ExtractedEntity],
    ) -> dict[int, tuple[str, str]]:
        prompt = build_batch_semantic_node_prompt(
            [entity.to_dict() for entity in entities]
        )
        try:
            self.last_llm_call_count += 1
            response = self.client.generate_json_list(prompt, fallback=[])
        except LLMConnectionError as e:
            if self.fail_fast:
                raise
            print(f"[LLMSemanticNodeBuilder] LLM batch 연결 실패: {e}")
            response = []

        enrichments: dict[int, tuple[str, str]] = {}
        for item in response:
            if not isinstance(item, dict):
                continue
            try:
                input_index = int(item.get("input_index"))
            except (TypeError, ValueError):
                continue
            if input_index < 1 or input_index > len(entities):
                continue
            definition = str(item.get("conceptual_definition") or "").strip()
            affordance = str(item.get("affordance") or "").strip()
            if definition and affordance:
                enrichments[input_index] = (definition, affordance)

        if self.fail_fast and len(enrichments) != len(entities):
            raise LLMResponseFormatError(
                "LLM batch semantic enrichment response must include one complete item per entity."
            )
        if not self.fail_fast and len(enrichments) != len(entities):
            missing_count = len(entities) - len(enrichments)
            print(
                "[LLMSemanticNodeBuilder] "
                f"{missing_count} semantic enrichment item(s) omitted; using fallback definitions."
            )
        return enrichments

    def _node_from_entity(
        self,
        index: int,
        entity: ExtractedEntity,
        definition: str,
        affordance: str,
    ) -> SemanticNode:
        eclass_irdi = self._eclass_lookup.get(entity.raw_name.lower())
        if eclass_irdi:
            print(f"[LLMSemanticNodeBuilder] IRDI 매칭: {entity.raw_name} → {eclass_irdi}")

        return SemanticNode(
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
            eclass_irdi=eclass_irdi,
        )

    @staticmethod
    def _fallback_enrichment(entity: ExtractedEntity) -> tuple[str, str]:
        return (
            f"Asset attribute describing {entity.raw_name}.",
            f"Used as structured metadata for {entity.raw_name}.",
        )

    @staticmethod
    def _chunks(
        entities: list[ExtractedEntity],
        batch_size: int,
    ) -> list[list[ExtractedEntity]]:
        return [
            entities[index:index + batch_size]
            for index in range(0, len(entities), batch_size)
        ]

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
