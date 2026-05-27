from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Any

from app.config import PipelineConfig
from app.models import ModelInfo
from interfaces.base_model_generator import BaseModelGenerator

logger = logging.getLogger(__name__)


class InstantMeshModelManager(BaseModelGenerator):
    # InstantMesh 기반 3D 모델 생성 매니저.

    # 현재는 InstantMesh 연동 구조 및 파이프라인만 구성한 상태이며,
    # 실제 GPU inference 환경(Colab/서버) 연동은 추후 진행 예정.

    def __init__(self, config: PipelineConfig) -> None:
        self.config = config

        # TODO:
        # 실제 배포 환경에서는 config 또는 환경 변수로 분리 예정
        self.instantmesh_script_path = "./InstantMesh/run.py"

        # TODO:
        # 실제 InstantMesh 루트 경로 설정 예정
        self.instantmesh_root_dir = "./InstantMesh"

    def generate_model(
        self,
        images: list[str],
        asset_info: dict[str, Any],
    ) -> ModelInfo:

        # 기존 모델이 존재하면 해당 모델을 반환하고,
        # 없으면 InstantMesh 기반 생성 파이프라인을 수행.


        user_inputs = dict(asset_info.get("user_inputs") or {})

        existing_model_path = (
            asset_info.get("existing_model_path")
            or user_inputs.get("existing_model_path")
        )

        # 1. 기존 모델이 있는 경우
        if existing_model_path:
            path = Path(str(existing_model_path))

            logger.info(
                f"[InstantMeshModelManager] 기존 모델 재사용: {path}"
            )

            return ModelInfo(
                model_path=str(path),
                model_format=path.suffix.lower().lstrip(".") or "unknown",
                generation_method="existing_model_reference",
            )

        # 2. 입력 이미지 검증
        if not images:
            raise ValueError(
                "3D 모델 생성을 위한 입력 이미지가 없습니다."
            )

        input_image_path = images[0]

        # 3. 저장 경로 생성
        asset_id = str(asset_info["asset_id"])

        target_dir = self.config.resolved_generated_models_dir()

        target_dir.mkdir(parents=True, exist_ok=True)

        target_path = target_dir / f"{asset_id}.glb"

        logger.info(
            f"[InstantMeshModelManager] 3D 모델 생성 시작 - Asset ID: {asset_id}"
        )

        # 4. InstantMesh 실행
        try:
            # NOTE:
            # 현재는 InstantMesh 연동 구조만 구현한 상태.
            # 실제 GPU inference 환경에서는
            # subprocess 명령어 및 출력 경로 수정 예정.

            result = subprocess.run(
                [
                    "python",
                    self.instantmesh_script_path,
                    input_image_path,
                    "--output_dir",
                    str(target_dir),
                ],
                cwd=self.instantmesh_root_dir,
                capture_output=True,
                text=True,
                check=True,
            )

            logger.info(
                "[InstantMeshModelManager] InstantMesh 실행 완료"
            )

            logger.debug(result.stdout)


            # 5. 생성 파일 탐색
            generated_file_name = (
                Path(input_image_path).stem + ".glb"
            )

            possible_paths = [
                target_dir / generated_file_name,
                target_dir / "meshes" / generated_file_name,
            ]

            generated_raw_path = None

            for path in possible_paths:
                if path.exists():
                    generated_raw_path = path
                    break

            if generated_raw_path is None:
                raise FileNotFoundError(
                    "InstantMesh 실행은 완료되었지만 "
                    "생성된 GLB 파일을 찾을 수 없습니다."
                )


            # 6. 최종 파일명 정리

            generated_raw_path.rename(target_path)

            logger.info(
                f"[InstantMeshModelManager] GLB 생성 완료: {target_path}"
            )

            return ModelInfo(
                model_path=str(target_path),
                model_format="glb",
                generation_method="instantmesh_ai_generation",
            )

        except subprocess.CalledProcessError as e:
            logger.error(
                f"[InstantMeshModelManager] "
                f"InstantMesh 실행 실패: {e.stderr}"
            )

            raise RuntimeError(
                "InstantMesh 실행 중 오류가 발생했습니다."
            ) from e

        except Exception as e:
            logger.error(
                f"[InstantMeshModelManager] 모델 생성 실패: {str(e)}"
            )

            raise