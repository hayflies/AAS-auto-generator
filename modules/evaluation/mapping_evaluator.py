from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any


@dataclass
class MappingEvaluationResult:
    total: int
    correct: int
    missing: int
    incorrect: int
    precision: float
    recall: float
    accuracy: float
    details: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def evaluate_mapping(
    predicted: list[dict[str, Any]],
    gold: list[dict[str, Any]],
) -> MappingEvaluationResult:
    """Compare predicted mappings with a small gold mapping set."""

    predicted_by_node = {
        str(item.get("semantic_node_id")): item
        for item in predicted
        if item.get("semantic_node_id")
    }
    details: list[dict[str, Any]] = []
    correct = 0
    missing = 0
    incorrect = 0

    for expected in gold:
        node_id = str(expected.get("semantic_node_id"))
        actual = predicted_by_node.get(node_id)
        if actual is None:
            missing += 1
            details.append({"semantic_node_id": node_id, "status": "missing"})
            continue

        expected_id_short = expected.get("idShort")
        expected_semantic_id = expected.get("semanticId")
        id_short_ok = not expected_id_short or actual.get("idShort") == expected_id_short
        semantic_ok = not expected_semantic_id or actual.get("semanticId") == expected_semantic_id

        if id_short_ok and semantic_ok:
            correct += 1
            status = "correct"
        else:
            incorrect += 1
            status = "incorrect"

        details.append(
            {
                "semantic_node_id": node_id,
                "status": status,
                "expected": expected,
                "actual": actual,
            }
        )

    total_predictions = len(predicted_by_node)
    total_gold = len(gold)
    precision = correct / total_predictions if total_predictions else 0.0
    recall = correct / total_gold if total_gold else 0.0
    accuracy = correct / total_gold if total_gold else 0.0

    return MappingEvaluationResult(
        total=total_gold,
        correct=correct,
        missing=missing,
        incorrect=incorrect,
        precision=precision,
        recall=recall,
        accuracy=accuracy,
        details=details,
    )
