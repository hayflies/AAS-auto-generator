"""LLM 기반 정보 추출기.

interfaces/base_extractor.py의 BaseInformationExtractor를 구현한다.
파이프라인은 ManualInputExtractor 대신 이 클래스를 꽂아 쓸 수 있다.
"""

from __future__ import annotations

from app.models import AssetPackage, CVOutput, ExtractedEntity
from interfaces.base_extractor import BaseInformationExtractor
from interfaces.base_llm import BaseLLM, LLMConnectionError
from modules.llm import OllamaClient
from modules.llm.prompts import build_extraction_prompt


class LLMExtractor(BaseInformationExtractor):
    """LLM을 사용해 AssetPackage에서 ExtractedEntity 목록을 추출한다.

    Args:
        client: BaseLLM 구현체. 기본값은 OllamaClient 인스턴스 생성.
    """

    def __init__(self, client: BaseLLM | None = None):
        self.client = client or OllamaClient()

    def extract(
        self,
        asset_package: AssetPackage,
        cv_output: CVOutput | None = None,
    ) -> list[ExtractedEntity]:
        """AssetPackage에서 속성 목록을 추출한다.

        cv_output은 현재 미사용이나 인터페이스 호환을 위해 받는다.
        """
        input_text = self._build_input_text(asset_package)
        if not input_text.strip():
            return []

        prompt = build_extraction_prompt(input_text)

        # llm 응답이 빈 리스트로 오는 경우를 대비해 최대 3회 재시도
        for attempt in range(3):
            try:
                raw_results = self.client.generate_json_list(prompt, fallback=[])
            except LLMConnectionError as e:
                print(f"[LLMExtractor] LLM 연결 실패: {e}")
                return []

            entities = self._to_extracted_entities(raw_results)
            if entities:
                return entities

        return []

    def _build_input_text(self, asset_package: AssetPackage) -> str:
        """AssetPackage의 필드들을 LLM에 전달할 텍스트 한 덩어리로 만든다."""
        lines = []

        for key in ("asset_name", "manufacturer", "model_name", "asset_type"):
            value = getattr(asset_package, key, None)
            if value:
                lines.append(f"{key}: {value}")

        user_inputs = getattr(asset_package, "user_inputs", {})
        if isinstance(user_inputs, dict):
            for key, value in user_inputs.items():
                if value:
                    lines.append(f"{key}: {value}")

        documents = getattr(asset_package, "documents", [])
        for doc in documents:
            if isinstance(doc, str) and doc.strip():
                lines.append(doc.strip())
            elif isinstance(doc, dict):
                content = doc.get("content", doc.get("text", ""))
                if content:
                    lines.append(str(content))

        return "\n".join(lines)

    def _to_extracted_entities(self, raw_results: list) -> list[ExtractedEntity]:
        """LLM 응답 JSON 배열을 ExtractedEntity dataclass 목록으로 변환한다."""
        entities = []

        for item in raw_results:
            if not isinstance(item, dict):
                continue

            # LLM이 raw_name 또는 name 키를 혼용하는 경우 모두 처리
            raw_name = (item.get("raw_name") or item.get("name") or "").strip()
            raw_value = item.get("raw_value") if "raw_value" in item else item.get("value")
            raw_unit = item.get("raw_unit") if "raw_unit" in item else item.get("unit")
            confidence = item.get("confidence", 0.8)

            if not raw_name or raw_value is None or str(raw_value).strip() == "":
                continue

            if isinstance(raw_unit, str) and raw_unit.lower() in ("null", "none", ""):
                raw_unit = None

            try:
                confidence = float(confidence)
                confidence = max(0.0, min(1.0, confidence))
            except (TypeError, ValueError):
                confidence = 0.8

            entities.append(ExtractedEntity(
                raw_name=raw_name,
                raw_value=str(raw_value).strip(),
                raw_unit=raw_unit,
                source="llm_extraction",
                confidence=confidence,
            ))

        return entities
