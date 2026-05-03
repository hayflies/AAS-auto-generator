"""AAS JSON 생성기 인터페이스.

LLM이 최종 AAS JSON을 직접 만들지 않도록, mapping plan을 입력받아 코드로
결정적인 JSON을 생성하고 검증하는 구현체가 이 계약을 따른다.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseAASGenerator(ABC):
    """AAS Mapping Plan을 실제 AAS JSON으로 변환하는 생성기 계약."""

    @abstractmethod
    def generate(self, mapping_plan: dict[str, Any]) -> dict[str, Any]:
        """Submodel 배치 계획을 받아 AAS JSON 구조를 생성한다."""
        raise NotImplementedError

    @abstractmethod
    def validate(self, aas_json: dict[str, Any]) -> dict[str, Any]:
        """생성된 AAS JSON의 필수 구조와 누락 필드를 검증한다."""
        raise NotImplementedError
