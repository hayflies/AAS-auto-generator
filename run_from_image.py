"""이미지/PDF만 넣으면 AAS를 자동 생성하는 원클릭 스크립트.

사용법:
    # 1) data/input/images/ 폴더에 스펙 사진 또는 PDF를 넣는다.
    # 2) 아래 명령 실행:
    python run_from_image.py

    # 특정 파일 직접 지정:
    python run_from_image.py --files data/input/images/omy_spec.png

    # 자산 이름/제조사 힌트 추가 (LLM 추출 품질 향상):
    python run_from_image.py --name "OMY" --manufacturer "ROBOTIS"

결과:
    data/generated_aas/{asset_id}.aas.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

IMAGE_DIR = ROOT / "data" / "input" / "images"
SUPPORTED = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif", ".webp", ".pdf"}


def main() -> None:
    args = _parse_args()

    # ── 입력 파일 수집 ──────────────────────────────────────────────────
    if args.files:
        files = [str(Path(f).resolve()) for f in args.files]
    else:
        if not IMAGE_DIR.exists():
            IMAGE_DIR.mkdir(parents=True)
        files = [
            str(p) for p in sorted(IMAGE_DIR.iterdir())
            if p.suffix.lower() in SUPPORTED
        ]

    if not files:
        print(f"[ERROR] 처리할 파일이 없습니다.")
        print(f"  → 이미지나 PDF를 아래 폴더에 넣고 다시 실행하세요:")
        print(f"     {IMAGE_DIR}")
        return

    print("=" * 60)
    print("  AAS 자동 생성 — 이미지/PDF 입력")
    print("=" * 60)
    for f in files:
        print(f"  📄 {Path(f).name}")
    print()

    # ── payload 구성 ─────────────────────────────────────────────────────
    asset_name = args.name or Path(files[0]).stem.replace("_", " ").title()
    asset_id   = asset_name.lower().replace(" ", "_")

    payload = {
        "manual_files": files,
        "user_inputs": {
            "asset_id":     asset_id,
            "asset_name":   asset_name,
            "asset_type":   args.asset_type or "unknown",
            **({"manufacturer": args.manufacturer} if args.manufacturer else {}),
        },
    }

    # ── 파이프라인 실행 ──────────────────────────────────────────────────
    from app.config import PipelineConfig
    from app.pipeline import create_default_pipeline

    config   = PipelineConfig()
    pipeline = create_default_pipeline(config)

    print("  🔄 파이프라인 실행 중...")
    result = pipeline.run(payload)

    # ── 결과 저장 ────────────────────────────────────────────────────────
    from app.text import slugify

    output_dir = config.resolved_output_dir()
    aas_dir    = config.resolved_generated_aas_dir()
    output_dir.mkdir(parents=True, exist_ok=True)
    aas_dir.mkdir(parents=True, exist_ok=True)

    safe_id      = slugify(result.asset_package.asset_id)
    result_path  = output_dir / f"{safe_id}_pipeline_result.json"
    aas_path     = aas_dir    / f"{safe_id}.aas.json"

    result_path.write_text(
        json.dumps(result.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8"
    )
    aas_path.write_text(
        json.dumps(result.aas_json, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # ── 결과 출력 ────────────────────────────────────────────────────────
    print()
    print("=" * 60)
    print("  ✅ 완료!")
    print("=" * 60)
    print(f"  자산 ID         : {result.asset_package.asset_id}")
    print(f"  추출 속성 수    : {len(result.semantic_nodes)}개")
    print(f"  AAS 매칭 속성   : {len(result.matched_properties)}개")
    print(f"  AAS 유효성      : {'✅' if result.aas_validation['is_valid'] else '❌'}")
    print(f"  AAS 파일        : {aas_path}")
    print("=" * 60)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="이미지/PDF → AAS 자동 생성")
    parser.add_argument(
        "--files", nargs="+",
        help="처리할 이미지/PDF 경로 (미지정 시 data/input/images/ 자동 탐색)",
    )
    parser.add_argument("--name",         help="자산 이름 힌트 (예: OMY)")
    parser.add_argument("--manufacturer", help="제조사 힌트 (예: ROBOTIS)")
    parser.add_argument("--asset-type",   help="자산 유형 힌트 (예: robot_arm)")
    return parser.parse_args()


if __name__ == "__main__":
    main()
