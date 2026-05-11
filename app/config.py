from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PipelineConfig:
    """파이프라인 전체에서 공유하는 실행 설정.

    각 모듈이 직접 경로나 상수를 하드코딩하지 않도록, 출력 위치와 매칭
    임계값 같은 공통 설정을 이 객체 하나로 전달한다.
    """

    project_root: Path = Path(__file__).resolve().parents[1]
    top_k_candidates: int = 5
    match_threshold: float = 0.45
    human_review_threshold: float = 0.78
    output_dir: Path | None = None
    generated_aas_dir: Path | None = None
    generated_models_dir: Path | None = None
    dt_viewer_base_url: str = "http://localhost:3000/assets"

    def resolved_output_dir(self) -> Path:
        """전체 파이프라인 결과 JSON을 저장할 디렉터리를 반환한다."""
        return self.output_dir or self.project_root / "data" / "output"

    def resolved_generated_aas_dir(self) -> Path:
        """생성된 AAS JSON 파일을 저장할 디렉터리를 반환한다."""
        return self.generated_aas_dir or self.project_root / "data" / "generated_aas"

    def resolved_generated_models_dir(self) -> Path:
        """생성 또는 참조된 3D 모델 파일의 기본 디렉터리를 반환한다."""
        return self.generated_models_dir or self.project_root / "data" / "generated_models"
