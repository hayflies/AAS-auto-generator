"""DT Validation Layer 인터페이스.

등록된 DT 자산이 임의 센서값에 대해 이동/상태/시각 변화로 반응하는지
확인하는 계층의 계약이다.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.models import DTRegistrationResult, ValidationResult


class BaseDTValidator(ABC):
    """DT 등록 결과와 센서값을 이용해 동작 검증을 수행하는 계약."""

    @abstractmethod
    def validate(
        self,
        registration: DTRegistrationResult,
        sensor_values: dict[str, Any],
    ) -> ValidationResult:
        """센서값 반영 결과를 ValidationResult로 반환한다."""
        raise NotImplementedError
