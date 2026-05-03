from __future__ import annotations

from pathlib import Path

from app.models import CVOutput
from interfaces.base_cv import BaseCVModel


class NoOpCVModel(BaseCVModel):
    """CV 의존성 없이 파이프라인을 실행하기 위한 기본 adapter.

    실제 프로젝트에서 YOLO, SAM, Vision Transformer 등을 붙이기 전에도
    Optional CV 단계의 데이터 계약을 확인할 수 있게 해준다.
    """

    # 파일명에 포함된 단어로 장비 유형을 약하게 추론하는 MVP용 힌트다.
    TYPE_HINTS = {
        "robot": "robot_arm",
        "arm": "robot_arm",
        "pump": "pump",
        "motor": "motor",
        "conveyor": "conveyor",
    }

    def classify(self, images: list[str]) -> CVOutput:
        """이미지 파일명에서 자산 유형 힌트를 찾아 낮은 confidence로 반환한다."""
        names = " ".join(Path(image).stem.lower() for image in images)
        for token, asset_type in self.TYPE_HINTS.items():
            if token in names:
                return CVOutput(predicted_type=asset_type, confidence=0.55)
        return CVOutput()

    def segment(self, images: list[str]) -> list[str]:
        """현재는 세그멘테이션을 수행하지 않으므로 빈 목록을 반환한다."""
        return []
