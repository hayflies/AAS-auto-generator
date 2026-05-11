from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import PipelineConfig
from app.pipeline import create_default_pipeline
from app.sample_data import sample_payload
from modules.evaluation import evaluate_mapping


def main() -> None:
    args = _parse_args()
    config = PipelineConfig()
    payload = _load_json(Path(args.input_json)) if args.input_json else sample_payload()
    gold_payload = _load_json(Path(args.gold_json))
    result = create_default_pipeline(config).run(payload)
    predicted = [
        property_item
        for submodel in result.aas_mapping_plan["submodels"]
        for property_item in submodel.get("properties", [])
        if property_item.get("semantic_node_id")
    ]
    evaluation = evaluate_mapping(predicted, gold_payload.get("items", []))
    print(json.dumps(evaluation.to_dict(), indent=2, ensure_ascii=False))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate semantic-node to AAS-property mapping.")
    parser.add_argument("--input-json", help="Input payload. Defaults to built-in sample.")
    parser.add_argument(
        "--gold-json",
        default="data/evaluation/gold_mapping_sample.json",
        help="Gold mapping JSON.",
    )
    return parser.parse_args()


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


if __name__ == "__main__":
    main()
