from __future__ import annotations

from typing import Any


def sample_payload() -> dict[str, Any]:
    """개발/테스트용 샘플 입력.

    외부 OCR, LLM, 3D 생성기 없이도 전체 파이프라인이 끝까지 동작하는지
    확인하기 위해 Robot Arm 예시 데이터를 제공한다.
    """

    return {
        "asset_images": ["data/input/robot_arm_front.jpg", "data/input/robot_arm_nameplate.jpg"],
        "manual_files": ["data/input/robot_arm_datasheet.pdf"],
        "user_inputs": {
            "asset_id": "robot_arm_a",
            "asset_name": "Robot Arm A",
            "manufacturer": "ROBOTIS",
            "model_name": "example_model",
            "asset_type": "robot_arm",
            "rated_voltage": {"value": 24, "unit": "V"},
            "rated_current": {"value": 3.5, "unit": "A"},
            "serial_number": "RA-2026-0001",
            "weight": {"value": 12.4, "unit": "kg"},
            "existing_model_path": "data/generated_models/robot_arm_a.glb",
            "test_sensor_values": {
                "rotation_angle": 30,
                "temperature": 80,
                "status": "running",
            },
        },
    }
