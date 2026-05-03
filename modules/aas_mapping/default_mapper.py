from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.models import AssetPackage, MatchedProperty, ModelInfo
from interfaces.base_mapper import BaseAASMapper


class DefaultAASMapper(BaseAASMapper):
    """MatchedProperty를 AAS Submodel 구조에 배치하는 기본 mapper.

    이 계층은 AAS JSON을 직접 만들지 않는다. 어떤 Submodel에 어떤 Property가
    들어갈지 계획만 세우고, 최종 JSON 생성은 AAS Generator가 담당한다.
    """

    def __init__(self, template_path: Path) -> None:
        """Submodel 기본 템플릿을 로드한다."""
        self.template_path = template_path
        self.submodel_ids = self._load_submodel_ids(template_path)

    def map(
        self,
        asset_package: AssetPackage,
        matched_properties: list[MatchedProperty],
        model_info: ModelInfo,
    ) -> dict[str, Any]:
        """매칭 결과와 3D 모델 정보를 AAS Mapping Plan으로 변환한다."""

        # 템플릿에 정의된 기본 Submodel은 property가 없어도 결과에 포함한다.
        submodels = {
            submodel_id: {"idShort": submodel_id, "properties": []}
            for submodel_id in self.submodel_ids
        }

        # Entity Matching에서 선택된 property들을 후보가 지정한 submodel에 배치한다.
        for item in matched_properties:
            submodel = submodels.setdefault(
                item.submodel,
                {"idShort": item.submodel, "properties": []},
            )
            submodel["properties"].append(
                {
                    "semantic_node_id": item.semantic_node_id,
                    "aas_property_id": item.aas_property_id,
                    "idShort": item.idShort,
                    "value": item.value,
                    "unit": item.unit,
                    "match_score": item.match_score,
                    "semanticId": item.semantic_id,
                }
            )

        # 3D 모델은 AAS 내부에 저장하지 않고 참조 정보만 property로 기록한다.
        submodels.setdefault(
            "ProvisionOf3DModels",
            {"idShort": "ProvisionOf3DModels", "properties": []},
        )
        submodels["ProvisionOf3DModels"]["properties"].extend(
            [
                {
                    "semantic_node_id": None,
                    "aas_property_id": "AAS_PROP_MODEL_PATH",
                    "idShort": "ModelFile",
                    "value": model_info.model_path,
                    "unit": None,
                    "match_score": 1.0,
                    "semanticId": "https://admin-shell.io/idta/3d/ModelFile/1/0",
                },
                {
                    "semantic_node_id": None,
                    "aas_property_id": "AAS_PROP_MODEL_FORMAT",
                    "idShort": "ModelFormat",
                    "value": model_info.model_format,
                    "unit": None,
                    "match_score": 1.0,
                    "semanticId": "https://admin-shell.io/idta/3d/ModelFormat/1/0",
                },
                {
                    "semantic_node_id": None,
                    "aas_property_id": "AAS_PROP_MODEL_GENERATION_METHOD",
                    "idShort": "GenerationMethod",
                    "value": model_info.generation_method,
                    "unit": None,
                    "match_score": 1.0,
                    "semanticId": "https://example.org/aas/3d/GenerationMethod",
                },
            ]
        )

        return {
            "asset": asset_package.to_dict(),
            "submodels": list(submodels.values()),
            "model_info": model_info.to_dict(),
        }

    def _load_submodel_ids(self, template_path: Path) -> list[str]:
        """Submodel template JSON에서 idShort 목록만 추출한다."""
        with template_path.open("r", encoding="utf-8") as file:
            data = json.load(file)
        return [item["idShort"] for item in data.get("submodels", [])]
