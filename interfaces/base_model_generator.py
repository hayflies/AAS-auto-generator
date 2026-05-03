"""3D Model Manager 인터페이스.

기존 GLB/USD/OBJ 모델을 참조하거나, TripoSR/Blender 같은 생성기를 붙여
DT 환경에서 사용할 모델 정보를 준비한다.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.models import ModelInfo


class BaseModelGenerator(ABC):
    """3D 모델 참조 또는 생성 결과를 ModelInfo로 반환하는 계약."""

    @abstractmethod
    def generate_model(
        self,
        images: list[str],
        asset_info: dict[str, Any],
    ) -> ModelInfo:
        """이미지와 자산 메타데이터를 이용해 DT용 모델 정보를 만든다."""
        raise NotImplementedError
