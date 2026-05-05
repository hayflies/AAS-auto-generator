"""Optional CV Module 구현체 패키지."""

from modules.cv.noop_cv import NoOpCVModel
from modules.cv.yolo_part_detector import YOLOPartDetector

__all__ = ["NoOpCVModel", "YOLOPartDetector"]
