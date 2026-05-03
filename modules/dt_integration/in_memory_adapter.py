from __future__ import annotations

from typing import Any

from app.config import PipelineConfig
from app.models import DTRegistrationResult
from interfaces.base_dt_adapter import BaseDTAdapter


class InMemoryDTAdapter(BaseDTAdapter):
    """메모리 기반 DT 등록 시뮬레이터.

    실제 Three.js/Unity/Isaac Sim 서버가 없어도 AAS와 3D 모델 참조가 DT 등록
    단계까지 도달하는지 검증할 수 있게 한다.
    """

    def __init__(self, config: PipelineConfig) -> None:
        """등록 결과와 mock sensor 상태를 저장할 메모리 registry를 준비한다."""
        self.config = config
        self.registry: dict[str, dict[str, Any]] = {}

    def register_asset(
        self,
        aas_json: dict[str, Any],
        model_info: dict[str, Any],
    ) -> DTRegistrationResult:
        """AAS JSON과 모델 정보를 메모리 registry에 DT 자산으로 등록한다."""

        shell = aas_json["assetAdministrationShells"][0]
        global_asset_id = shell["assetInformation"]["globalAssetId"]
        asset_id = global_asset_id.rsplit(":", maxsplit=1)[-1]
        dt_asset_id = f"DT_ASSET_{asset_id.upper()}"
        self.registry[dt_asset_id] = {
            "aas_json": aas_json,
            "model_info": model_info,
            "last_sensor_values": {},
        }
        return DTRegistrationResult(
            dt_asset_id=dt_asset_id,
            registration_status="success",
            viewer_url=f"{self.config.dt_viewer_base_url}/{dt_asset_id}",
        )

    def apply_sensor_values(
        self,
        asset_id: str,
        sensor_values: dict[str, Any],
    ) -> dict[str, Any]:
        """mock 센서값을 적용하고 이동/상태/시각 반응 여부를 계산한다."""

        if asset_id not in self.registry:
            return {
                "movement_test": False,
                "state_change_test": False,
                "visual_update_test": False,
                "overall_status": "failed",
                "reason": "Asset is not registered in the DT adapter.",
            }

        self.registry[asset_id]["last_sensor_values"] = dict(sensor_values)
        # 실제 viewer가 없으므로 센서 key 존재 여부로 반응 가능성을 판정한다.
        movement_test = any(key in sensor_values for key in ("rotation_angle", "position", "velocity"))
        state_change_test = any(key in sensor_values for key in ("status", "state", "mode"))
        visual_update_test = any(key in sensor_values for key in ("temperature", "status", "color"))
        overall = movement_test and state_change_test and visual_update_test
        return {
            "movement_test": movement_test,
            "state_change_test": state_change_test,
            "visual_update_test": visual_update_test,
            "overall_status": "passed" if overall else "failed",
        }
