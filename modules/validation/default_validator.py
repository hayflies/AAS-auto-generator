from __future__ import annotations

from typing import Any

from app.models import DTRegistrationResult, ValidationResult
from interfaces.base_dt_adapter import BaseDTAdapter
from interfaces.base_validator import BaseDTValidator


class DefaultDTValidator(BaseDTValidator):
    """DT adapter에 mock sensor 값을 넣어 동작 검증을 수행한다.

    현재는 수동/임의 센서값 기반 검증만 담당하며, 추후 MQTT/REST/WebSocket
    입력 adapter와 연결해도 이 계층의 출력 계약은 유지된다.
    """

    def __init__(self, dt_adapter: BaseDTAdapter) -> None:
        """검증 과정에서 사용할 DT adapter를 주입받는다."""
        self.dt_adapter = dt_adapter

    def validate(
        self,
        registration: DTRegistrationResult,
        sensor_values: dict[str, Any],
    ) -> ValidationResult:
        """DT adapter의 센서 적용 결과를 표준 ValidationResult로 감싼다."""
        result = self.dt_adapter.apply_sensor_values(
            registration.dt_asset_id,
            sensor_values,
        )
        return ValidationResult(
            movement_test=bool(result.get("movement_test")),
            state_change_test=bool(result.get("state_change_test")),
            visual_update_test=bool(result.get("visual_update_test")),
            overall_status=str(result.get("overall_status", "failed")),
        )
