from __future__ import annotations

from typing import Any

from app.models import AssetPackage, CVOutput, ExtractedEntity
from app.text import normalize_label
from interfaces.base_extractor import BaseInformationExtractor


class ManualInputExtractor(BaseInformationExtractor):
    """사용자 입력 필드에서 구조화된 raw entity를 추출한다.

    OCR, 문서 파서, LLM extractor가 들어오기 전 MVP의 기본 구현이다.
    downstream Semantic Node 계약을 유지한 채 추출 방식을 교체할 수 있다.
    """

    # 이 필드들은 자산 패키지의 메타데이터이거나 다른 단계에서 쓰는 값이라
    # 중복 entity로 만들지 않는다.
    SKIP_FIELDS = {
        "asset_id",
        "images",
        "documents",
        "manual_files",
        "asset_images",
        "existing_model_path",
        "test_sensor_values",
    }

    def extract(
        self,
        asset_package: AssetPackage,
        cv_output: CVOutput | None = None,
    ) -> list[ExtractedEntity]:
        """AssetPackage와 선택 CV 결과를 ExtractedEntity 목록으로 바꾼다."""

        entities: list[ExtractedEntity] = []

        # 자산 식별에 필수적인 기본 필드는 항상 먼저 entity로 만든다.
        base_fields: dict[str, Any] = {
            "asset_name": asset_package.asset_name,
            "asset_type": asset_package.asset_type,
            "manufacturer": asset_package.manufacturer,
            "model_name": asset_package.model_name,
        }
        for key, value in base_fields.items():
            if value not in (None, ""):
                entities.append(self._entity_from_value(key, value, source="manual_input"))

        # user_inputs에 들어온 추가 속성은 AAS 후보 매핑 대상이 된다.
        for key, value in asset_package.user_inputs.items():
            if key in self.SKIP_FIELDS or key in base_fields:
                continue
            if value in (None, ""):
                continue
            entities.append(self._entity_from_value(key, value, source="manual_input"))

        if cv_output and cv_output.predicted_type and asset_package.asset_type == "unknown":
            entities.append(
                ExtractedEntity(
                    raw_name="asset_type",
                    raw_value=cv_output.predicted_type,
                    source="cv_classification",
                    confidence=cv_output.confidence,
                )
            )

        return entities

    def _entity_from_value(self, key: str, value: Any, source: str) -> ExtractedEntity:
        """단순 값 또는 `{value, unit}` 형태 입력을 공통 ExtractedEntity로 변환한다."""

        if isinstance(value, dict):
            raw_value = value.get("value")
            raw_unit = value.get("unit")
            confidence = float(value.get("confidence", 1.0))
            source = str(value.get("source", source))
            source_reference = value.get("source_reference")
        else:
            raw_value = value
            raw_unit = None
            confidence = 1.0
            source_reference = None

        return ExtractedEntity(
            raw_name=normalize_label(key),
            raw_value=raw_value,
            raw_unit=raw_unit,
            source=source,
            confidence=confidence,
            source_reference=source_reference,
        )
