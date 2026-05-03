"""Input Layer 인터페이스.

CLI, Web UI, API, 모바일 업로드 등 어떤 입력 채널이든 내부 표준
AssetPackage로 변환하기 위한 계약이다.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.models import AssetPackage


class BaseInputLayer(ABC):
    """외부 payload를 내부 AssetPackage로 정규화하는 계약."""

    @abstractmethod
    def collect(self, payload: dict[str, Any]) -> AssetPackage:
        """사용자 입력 payload를 파이프라인 표준 입력 구조로 변환한다."""
        raise NotImplementedError
