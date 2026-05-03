"""AAS Mapping Engine 인터페이스.

매칭된 property들을 DigitalNameplate, TechnicalData, ProvisionOf3DModels 같은
Submodel 구조에 배치하는 계층의 계약이다.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.models import AssetPackage, MatchedProperty, ModelInfo


class BaseAASMapper(ABC):
    """MatchedProperty 목록을 AAS Mapping Plan으로 변환하는 계약."""

    @abstractmethod
    def map(
        self,
        asset_package: AssetPackage,
        matched_properties: list[MatchedProperty],
        model_info: ModelInfo,
    ) -> dict[str, Any]:
        """자산 정보, 매핑 결과, 모델 정보를 합쳐 generator 입력 계획을 만든다."""
        raise NotImplementedError
