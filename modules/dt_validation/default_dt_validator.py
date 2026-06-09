"""기본 DT 동작 검증기 — InMemoryDTAdapter의 apply_sensor_values를 활용한다."""

from __future__ import annotations

from typing import Any

from app.models import DTRegistrationResult, ValidationResult
from interfaces.base_validator import BaseDTValidator


class DefaultDTValidator(BaseDTValidator):
    """InMemoryDTAdapter를 통해 mock 센서값으로 DT 동작을 검증한다."""

    def __init__(self, dt_adapter: Any) -> None:
        self.dt_adapter = dt_adapter

    def validate(
        self,
        registration: DTRegistrationResult,
        sensor_values: dict[str, Any],
    ) -> ValidationResult:
        result = self.dt_adapter.apply_sensor_values(
            registration.dt_asset_id, sensor_values
        )
        return ValidationResult(
            movement_test=bool(result.get("movement_test", False)),
            state_change_test=bool(result.get("state_change_test", False)),
            visual_update_test=bool(result.get("visual_update_test", False)),
            overall_status=result.get("overall_status", "failed"),
        )
