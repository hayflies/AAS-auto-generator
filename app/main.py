from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from app.config import PipelineConfig
from app.pipeline import (
    create_default_pipeline,
    create_llm_pipeline,
    create_llm_yolo_pipeline,
    create_yolo_pipeline,
)
from app.sample_data import sample_payload


def main() -> None:
    """CLI에서 파이프라인을 실행하는 진입점.

    입력 JSON을 읽고, 기본 파이프라인을 조립해 실행한 뒤, 팀원이 바로
    확인할 수 있도록 핵심 지표와 결과 파일 경로를 출력한다.
    """

    args = _parse_args()
    payload = _load_payload(args.input_json)
    output_dir = Path(args.output_dir).resolve() if args.output_dir else None
    config = PipelineConfig(output_dir=output_dir)
    pipeline = _create_pipeline(args.pipeline, config)
    result = pipeline.run(payload)

    output_path = _write_outputs(result.to_dict(), config)
    print(
        "\n".join(
            [
                f"asset_id={result.asset_package.asset_id}",
                f"semantic_nodes={len(result.semantic_nodes)}",
                f"matched_properties={len(result.matched_properties)}",
                f"aas_valid={result.aas_validation['is_valid']}",
                f"dt_status={result.dt_registration.registration_status}",
                f"dt_validation={result.dt_validation.overall_status}",
                f"output={output_path}",
            ]
        )
    )


def _parse_args() -> argparse.Namespace:
    """CLI 옵션을 정의한다."""
    parser = argparse.ArgumentParser(
        description="Run the LLM/DDMS-style AAS auto-generation pipeline skeleton.",
    )
    parser.add_argument(
        "--input-json",
        help="Path to an input JSON payload. Uses built-in sample data when omitted.",
    )
    parser.add_argument(
        "--output-dir",
        help="Directory for pipeline result JSON. Defaults to data/output.",
    )
    parser.add_argument(
        "--pipeline",
        choices=("default", "llm", "yolo", "llm-yolo"),
        default="default",
        help=(
            "Pipeline implementation set. 'default' has no external runtime "
            "dependencies; LLM modes require Ollama; YOLO modes require ultralytics."
        ),
    )
    return parser.parse_args()


def _create_pipeline(mode: str, config: PipelineConfig):
    """CLI 옵션에 맞는 파이프라인 구현 조합을 선택한다."""
    if mode == "llm":
        return create_llm_pipeline(config)
    if mode == "yolo":
        return create_yolo_pipeline(config)
    if mode == "llm-yolo":
        return create_llm_yolo_pipeline(config)
    return create_default_pipeline(config)


def _load_payload(input_json: str | None) -> dict[str, Any]:
    """입력 파일이 있으면 JSON을 읽고, 없으면 내장 샘플 데이터를 사용한다."""
    if not input_json:
        return sample_payload()
    with Path(input_json).open("r", encoding="utf-8") as file:
        return json.load(file)


def _write_outputs(result: dict[str, Any], config: PipelineConfig) -> Path:
    """파이프라인 전체 결과와 생성된 AAS JSON을 각각 파일로 저장한다."""
    output_dir = config.resolved_output_dir()
    aas_dir = config.resolved_generated_aas_dir()
    output_dir.mkdir(parents=True, exist_ok=True)
    aas_dir.mkdir(parents=True, exist_ok=True)

    asset_id = result["asset_package"]["asset_id"]
    result_path = output_dir / f"{asset_id}_pipeline_result.json"
    aas_path = aas_dir / f"{asset_id}.aas.json"

    result_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    aas_path.write_text(json.dumps(result["aas_json"], indent=2, ensure_ascii=False), encoding="utf-8")
    return result_path
