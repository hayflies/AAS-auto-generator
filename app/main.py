"""Command-line entry point for JSON, image, and PDF AAS generation."""

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
from app.text import slugify


PROJECT_ROOT = Path(__file__).resolve().parents[1]
IMAGE_INPUT_DIR = PROJECT_ROOT / "data" / "input" / "images"
SUPPORTED_FILE_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif", ".webp", ".pdf"
}


def main() -> None:
    """Run the selected pipeline and save its complete result and AAS JSON."""

    parser = _create_parser()
    args = parser.parse_args()
    payload = _load_cli_payload(args, parser)
    output_dir = Path(args.output_dir).resolve() if args.output_dir else None
    config = PipelineConfig(output_dir=output_dir)
    result = _create_pipeline(args.pipeline, config).run(payload)

    output_path = _write_outputs(result.to_dict(), config)
    print(
        "\n".join(
            [
                f"asset_id={result.asset_package.asset_id}",
                f"semantic_nodes={len(result.semantic_nodes)}",
                f"matched_properties={len(result.matched_properties)}",
                f"mapping_validation={result.mapping_validation.overall_status}",
                f"aas_valid={result.aas_validation['is_valid']}",
                f"dt_status={result.dt_registration.registration_status}",
                f"dt_validation={result.dt_validation.overall_status}",
                f"output={output_path}",
            ]
        )
    )


def _create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the AAS auto-generation pipeline.",
    )
    source = parser.add_mutually_exclusive_group()
    source.add_argument(
        "--input-json",
        help="Path to an input JSON payload. Uses built-in sample data when omitted.",
    )
    source.add_argument(
        "--files",
        nargs="+",
        help="Image/PDF files to process directly.",
    )
    source.add_argument(
        "--image-dir",
        action="store_true",
        help="Process every supported image/PDF in data/input/images/.",
    )
    parser.add_argument(
        "--name",
        help="Asset name hint for --files or --image-dir.",
    )
    parser.add_argument(
        "--manufacturer",
        help="Manufacturer hint for --files or --image-dir.",
    )
    parser.add_argument(
        "--asset-type",
        help="Asset type hint for --files or --image-dir.",
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
            "Pipeline implementation set. Default/LLM modes require Ollama llama3.2 "
            "and nomic-embed-text; YOLO modes also require ultralytics."
        ),
    )
    return parser


def _load_cli_payload(args: argparse.Namespace, parser: argparse.ArgumentParser) -> dict[str, Any]:
    if args.files:
        return _image_payload([Path(path) for path in args.files], args, parser)
    if args.image_dir:
        IMAGE_INPUT_DIR.mkdir(parents=True, exist_ok=True)
        files = [
            path
            for path in sorted(IMAGE_INPUT_DIR.iterdir())
            if path.is_file() and path.suffix.lower() in SUPPORTED_FILE_EXTENSIONS
        ]
        return _image_payload(files, args, parser)
    if args.name or args.manufacturer or args.asset_type:
        parser.error("--name, --manufacturer, --asset-type require --files or --image-dir")
    if not args.input_json:
        return sample_payload()
    with Path(args.input_json).open("r", encoding="utf-8") as file:
        return json.load(file)


def _image_payload(
    files: list[Path],
    args: argparse.Namespace,
    parser: argparse.ArgumentParser,
) -> dict[str, Any]:
    if not files:
        parser.error("처리할 이미지 또는 PDF 파일이 없습니다.")

    resolved_files: list[Path] = []
    for path in files:
        resolved = path.resolve()
        if not resolved.is_file():
            parser.error(f"입력 파일을 찾을 수 없습니다: {path}")
        if resolved.suffix.lower() not in SUPPORTED_FILE_EXTENSIONS:
            parser.error(f"지원하지 않는 입력 형식입니다: {path}")
        resolved_files.append(resolved)

    asset_name = args.name or resolved_files[0].stem.replace("_", " ").title()
    return {
        "manual_files": [str(path) for path in resolved_files],
        "user_inputs": {
            "asset_id": slugify(asset_name),
            "asset_name": asset_name,
            "asset_type": args.asset_type or "unknown",
            **({"manufacturer": args.manufacturer} if args.manufacturer else {}),
        },
    }


def _create_pipeline(mode: str, config: PipelineConfig):
    if mode == "llm":
        return create_llm_pipeline(config)
    if mode == "yolo":
        return create_yolo_pipeline(config)
    if mode == "llm-yolo":
        return create_llm_yolo_pipeline(config)
    return create_default_pipeline(config)


def _write_outputs(result: dict[str, Any], config: PipelineConfig) -> Path:
    output_dir = config.resolved_output_dir()
    aas_dir = config.resolved_generated_aas_dir()
    output_dir.mkdir(parents=True, exist_ok=True)
    aas_dir.mkdir(parents=True, exist_ok=True)

    asset_id = slugify(result["asset_package"]["asset_id"])
    result_path = output_dir / f"{asset_id}_pipeline_result.json"
    aas_path = aas_dir / f"{asset_id}.aas.json"

    result_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    aas_path.write_text(json.dumps(result["aas_json"], indent=2, ensure_ascii=False), encoding="utf-8")
    return result_path


if __name__ == "__main__":
    main()
