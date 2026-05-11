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
from interfaces.base_semantic_builder import BaseSemanticNodeBuilder
from modules.llm.ollama_client import OllamaClient, OllamaConnectionError
from modules.llm.prompts import build_semantic_node_prompt

# ECLASS 사전 기본 경로
_ECLASS_DICT_PATH = (
    Path(__file__).parents[2]
    / "repositories"
    / "eclass_dictionary"
    / "eclass_properties.json"
)


class LLMSemanticNodeBuilder(BaseSemanticNodeBuilder):
    """Ollama LLM을 사용해 ExtractedEntity를 SemanticNode로 변환한다.

    각 속성마다 LLM에 conceptual_definition과 affordance 생성을 요청한다.
    Ollama 연결 실패 시 기본 문장으로 fallback한다.
    초기화 시 ECLASS 사전을 로드해 속성명 → IRDI 역인덱스를 구성한다.

    Args:
        client: OllamaClient 인스턴스. 기본값은 새 인스턴스 생성.
        skip_enrichment: True이면 LLM enrichment를 생략한다.
        eclass_dict_path: ECLASS 사전 JSON 파일 경로. 기본값은 repositories/eclass_dictionary.
    """

    def __init__(
        self,
        client: OllamaClient | None = None,
        skip_enrichment: bool = False,
        eclass_dict_path: Path | None = None,
    ):
        self.client = client or OllamaClient()
        self.skip_enrichment = skip_enrichment
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
        for entry in data.get("properties", []):
            irdi = entry.get("irdi", "").strip()
            if not irdi:
                continue
            lookup[entry.get("preferred_name", "").lower()] = irdi
            for alias in entry.get("aliases", []):
                lookup[alias.lower()] = irdi
        return lookup

    def build(self, entities: list[ExtractedEntity]) -> list[SemanticNode]:
        """raw entity 목록에 LLM이 생성한 의미 설명과 ECLASS IRDI를 추가한다."""
        nodes: list[SemanticNode] = []
        for index, entity in enumerate(entities, start=1):
            if self.skip_enrichment:
                definition = f"Asset attribute describing {entity.raw_name}."
                affordance = f"Used as structured metadata for {entity.raw_name}."
            else:
                definition, affordance = self._enrich(entity)

            # ECLASS 사전 조회 — 이름 기반 alias 매칭 (대소문자 무관)
            eclass_irdi = self._eclass_lookup.get(entity.raw_name.lower())
            if eclass_irdi:
                print(f"[LLMSemanticNodeBuilder] IRDI 매칭: {entity.raw_name} → {eclass_irdi}")

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
                eclass_irdi=eclass_irdi,
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
