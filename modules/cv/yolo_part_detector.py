"""YOLOv8 기반 로봇 부품 탐지 CV 모듈.

학습된 YOLOv8 모델을 사용해 입력 이미지에서 로봇 부품
(base, joint, link, gripper, nameplate)을 탐지하고,
부품별로 크롭한 이미지를 저장한다.

학습 데이터: 본인 촬영 5장 (Roboflow에서 라벨링, augmentation 적용)
학습 환경: Google Colab Tesla T4 GPU
학습 결과: mAP50 0.659 (base/gripper 0.99, link 0.60)
"""
from __future__ import annotations

import os
from pathlib import Path

from app.models import CVOutput
from interfaces.base_cv import BaseCVModel


# 로봇 부품 클래스 → 자산 유형 매핑
# (joint/link/gripper 등이 탐지되면 robot_arm일 가능성이 높음)
ROBOT_ARM_PARTS = {"base", "joint", "link", "gripper"}


class YOLOPartDetector(BaseCVModel):
    """YOLOv8 사전 학습 모델 기반 부품 탐지기."""

    def __init__(
        self,
        model_path: str | None = None,
        conf_threshold: float = 0.25,
        output_dir: str = "data/output/cv_crops",
    ) -> None:
        """
        Args:
            model_path: best.pt 경로. None이면 modules/cv/models/robot_parts_best.pt 사용.
            conf_threshold: 탐지 신뢰도 최소 기준값 (0~1).
            output_dir: 부품별 크롭 이미지 저장 경로.
        """
        if model_path is None:
            module_dir = Path(__file__).resolve().parent
            model_path = str(module_dir / "models" / "robot_parts_best.pt")

        if not Path(model_path).exists():
            raise FileNotFoundError(
                f"YOLO 모델 파일을 찾을 수 없습니다: {model_path}"
            )

        # ultralytics는 lazy import (초기 import 비용 절감 + 미설치 환경 지원)
        try:
            from ultralytics import YOLO
        except ImportError as exc:
            raise RuntimeError(
                "YOLOPartDetector를 사용하려면 ultralytics 패키지가 필요합니다. "
                "기본 파이프라인은 NoOpCVModel을 사용하므로 이 의존성이 필요 없습니다."
            ) from exc

        self._model = YOLO(model_path)
        self._conf_threshold = conf_threshold
        self._output_dir = output_dir
        os.makedirs(self._output_dir, exist_ok=True)

    def classify(self, images: list[str]) -> CVOutput:
        """이미지에서 부품을 탐지하고, 탐지된 부품으로 자산 유형을 추론한다.

        부품(base/joint/link/gripper) 중 하나라도 탐지되면 'robot_arm'으로 간주.
        """
        if not images:
            return CVOutput(predicted_type=None, confidence=0.0)

        existing_images = [image for image in images if Path(image).exists()]
        if not existing_images:
            return CVOutput(predicted_type=None, confidence=0.0)

        # 첫 번째 존재 이미지로 분류 (대표값)
        results = self._model.predict(
            source=existing_images[0],
            conf=self._conf_threshold,
            verbose=False,
        )

        if not results:
            return CVOutput(predicted_type=None, confidence=0.0)

        result = results[0]
        if result.boxes is None or len(result.boxes) == 0:
            return CVOutput(predicted_type=None, confidence=0.0)

        # 탐지된 클래스 이름 수집
        class_names = [result.names[int(cls)] for cls in result.boxes.cls]
        confidences = [float(c) for c in result.boxes.conf]

        # 로봇팔 부품이 하나라도 있으면 robot_arm
        robot_parts_detected = [
            (name, conf)
            for name, conf in zip(class_names, confidences)
            if name in ROBOT_ARM_PARTS
        ]

        if robot_parts_detected:
            avg_conf = sum(c for _, c in robot_parts_detected) / len(robot_parts_detected)
            return CVOutput(predicted_type="robot_arm", confidence=avg_conf)

        return CVOutput(predicted_type=None, confidence=0.0)

    def segment(self, images: list[str]) -> list[str]:
        """이미지에서 부품을 탐지하고, 부품별 크롭 이미지를 저장 후 경로를 반환한다.

        파일명 컨벤션: {원본파일명}_{클래스명}_{인덱스}_{신뢰도}.jpg
        예: robot_a_joint_0_92.jpg, robot_a_joint_1_88.jpg, robot_a_nameplate_0_95.jpg

        후속 단계(OCR, LLM)에서 파일명으로 어떤 부품인지 식별 가능.
        """
        from PIL import Image as PILImage

        cropped_paths: list[str] = []

        for image_path in images:
            if not Path(image_path).exists():
                continue

            results = self._model.predict(
                source=image_path,
                conf=self._conf_threshold,
                verbose=False,
            )

            if not results or results[0].boxes is None:
                continue

            result = results[0]
            stem = Path(image_path).stem  # 확장자 제외한 파일명

            # 원본 이미지 로드 (크롭용)
            original = PILImage.open(image_path)

            # 클래스별 인덱스 카운터 (joint가 여러 개일 수 있음)
            class_counters: dict[str, int] = {}

            for box, cls_idx, conf in zip(
                result.boxes.xyxy, result.boxes.cls, result.boxes.conf
            ):
                cls_name = result.names[int(cls_idx)]
                conf_val = int(float(conf) * 100)

                # 클래스별 인덱스 증가
                idx = class_counters.get(cls_name, 0)
                class_counters[cls_name] = idx + 1

                # 박스 좌표 (xyxy 형식)
                x1, y1, x2, y2 = [int(v) for v in box.tolist()]

                # 크롭 + 저장
                cropped = original.crop((x1, y1, x2, y2))
                output_filename = f"{stem}_{cls_name}_{idx}_{conf_val}.jpg"
                output_path = os.path.join(self._output_dir, output_filename)
                cropped.save(output_path)
                cropped_paths.append(output_path)

        return cropped_paths
