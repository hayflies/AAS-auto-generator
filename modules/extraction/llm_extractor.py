"""LLM 기반 정보 추출기.

interfaces/base_extractor.py의 BaseInformationExtractor를 구현한다.
파이프라인은 ManualInputExtractor 대신 이 클래스를 꽂아 쓸 수 있다.
"""

from __future__ import annotations

import re

from app.models import AssetPackage, CVOutput, ExtractedEntity
from interfaces.base_extractor import BaseInformationExtractor
from interfaces.base_llm import BaseLLM, LLMConnectionError
from modules.llm import OllamaClient
from modules.llm.prompts import build_extraction_prompt

# 값이 브래킷만으로 이루어진 경우: [Mbps], [N/A], [TBD] 등
_BRACKET_ONLY = re.compile(r"^\s*\[.*\]\s*$")

# 숫자가 전혀 없고 알파벳·특수문자만 있는 값 (단위 텍스트만 읽힌 경우)
_NO_DIGIT = re.compile(r"^[^\d]+$")

# Dynamixel 엔코더 분해능으로 흔히 나타나는 정수값들 (각도 아님)
_ENCODER_RESOLUTION = {1024, 2048, 4096, 1008, 512, 256}

# 치수(길이) 속성 키워드 — 무게 단위(g/kg)와 함께 나타나면 FP로 판정
_DIMENSION_KEYWORDS = {"width", "height", "depth", "length", "size", "dimension"}
_MASS_UNIT_PATTERN  = re.compile(r"\b(g|kg|gram|kilogram)\b", re.IGNORECASE)

# 낮은 신뢰도 임계값
_MIN_CONFIDENCE = 0.60


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

            value_str = str(raw_value).strip()
            unit_str  = str(raw_unit).strip() if raw_unit else ""

            # ── 쓰레기 값 필터 ────────────────────────────────────────────
            skip_reason = self._garbage_reason(raw_name, value_str, unit_str)
            if skip_reason:
                print(f"[LLMExtractor] 필터 제거 ({raw_name}={value_str}): {skip_reason}")
                continue
            # ─────────────────────────────────────────────────────────────

            if isinstance(raw_unit, str) and raw_unit.lower() in ("null", "none", ""):
                raw_unit = None

            try:
                confidence = float(confidence)
                confidence = max(0.0, min(1.0, confidence))
            except (TypeError, ValueError):
                confidence = 0.8

            # 신뢰도 낮은 항목 제거
            if confidence < _MIN_CONFIDENCE:
                print(f"[LLMExtractor] 낮은 신뢰도 제거 ({raw_name}, confidence={confidence:.2f})")
                continue

            entities.append(ExtractedEntity(
                raw_name=raw_name,
                raw_value=value_str,
                raw_unit=raw_unit,
                source="llm_extraction",
                confidence=confidence,
            ))

        return entities

    @staticmethod
    def _garbage_reason(name: str, value: str, unit: str) -> str | None:
        """값이 신뢰할 수 없는 경우 이유 문자열을 반환한다. 정상이면 None."""

        # 1. 브래킷만 있는 값: [Mbps], [N/A] 등
        if _BRACKET_ONLY.match(value):
            return "bracket-only value"

        # 2. 숫자가 전혀 없는 단순 텍스트 (단위만 읽힌 경우)
        #    단, "Ethernet", "USB" 같은 인터페이스 이름은 정상이므로
        #    unit 필드에도 같은 값이 있을 때만 필터링
        if _NO_DIGIT.match(value) and unit and value.lower() == unit.lower():
            return "value equals unit (unit-only extraction)"

        # 3. Dynamixel 엔코더 분해능 정수 — 각도 아님
        try:
            int_val = int(float(value))
            if int_val in _ENCODER_RESOLUTION and not unit:
                return f"likely encoder resolution ({int_val}), not a physical quantity"
        except (ValueError, TypeError):
            pass

        # 4. 치수 속성에 무게 단위가 붙은 경우 (FP 방지)
        name_lower = name.lower()
        if any(kw in name_lower for kw in _DIMENSION_KEYWORDS):
            if _MASS_UNIT_PATTERN.search(value) or _MASS_UNIT_PATTERN.search(unit):
                return "mass unit on a dimension property"

        return None
