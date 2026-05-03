from __future__ import annotations

from pathlib import Path
from typing import Any

from app.config import PipelineConfig
from app.models import ModelInfo
from interfaces.base_model_generator import BaseModelGenerator


class DefaultModelManager(BaseModelGenerator):
    """기존 3D 모델 참조 또는 생성 예정 경로를 준비하는 기본 manager.

    현재는 실제 TripoSR/Blender 실행 없이 model_info 계약만 보장한다.
    3D 생성기가 붙으면 이 클래스 또는 동일 interface 구현체를 교체하면 된다.
    """

    def __init__(self, config: PipelineConfig) -> None:
        """생성 모델 기본 저장 경로를 알기 위해 PipelineConfig를 보관한다."""
        self.config = config

    def generate_model(
        self,
        images: list[str],
        asset_info: dict[str, Any],
    ) -> ModelInfo:
        """기존 모델 경로가 있으면 참조하고, 없으면 생성 예정 GLB 경로를 만든다."""

        user_inputs = dict(asset_info.get("user_inputs") or {})
        existing_model_path = asset_info.get("existing_model_path") or user_inputs.get("existing_model_path")

        # 사용자가 이미 GLB/USD/OBJ 등을 제공한 경우 AAS에는 해당 파일 참조만 남긴다.
        if existing_model_path:
            path = Path(str(existing_model_path))
            return ModelInfo(
                model_path=str(path),
                model_format=path.suffix.lower().lstrip(".") or "unknown",
                generation_method="existing_model_reference",
            )

        # 모델이 없을 때는 추후 3D 생성 adapter가 채울 목표 경로를 기록한다.
        asset_id = str(asset_info["asset_id"])
        target_path = self.config.resolved_generated_models_dir() / f"{asset_id}.glb"
        return ModelInfo(
            model_path=str(target_path),
            model_format="glb",
            generation_method="pending_3d_generation_adapter",
        )
