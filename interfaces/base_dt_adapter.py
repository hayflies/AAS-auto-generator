"""디지털 트윈 플랫폼 연동 인터페이스.

Three.js, Unity, Isaac Sim, Omniverse 같은 실제 DT 환경은 이 adapter 계약을
구현해 파이프라인에 연결한다.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.models import DTRegistrationResult


class BaseDTAdapter(ABC):
    """AAS와 3D 모델을 DT 환경에 등록하고 센서값을 적용하는 계약."""

    @abstractmethod
    def register_asset(
        self,
        aas_json: dict[str, Any],
        model_info: dict[str, Any],
    ) -> DTRegistrationResult:
        """AAS JSON과 모델 참조 정보를 DT 자산으로 등록한다."""
        raise NotImplementedError

    @abstractmethod
    def apply_sensor_values(
        self,
        asset_id: str,
        sensor_values: dict[str, Any],
    ) -> dict[str, Any]:
        """임의 센서값을 등록된 DT 자산에 적용하고 반응 결과를 반환한다."""
        raise NotImplementedError
