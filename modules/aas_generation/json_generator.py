from __future__ import annotations

from typing import Any

from app.text import to_id_short
from interfaces.base_aas_generator import BaseAASGenerator


class JsonAASGenerator(BaseAASGenerator):
    """코드 기반 AAS JSON 생성기.

    LLM은 추출/보강/매칭까지만 돕고, 최종 AAS JSON은 이 클래스가 deterministic
    하게 생성한다. description.md의 "LLM 직접 AAS 생성 방지" 원칙을 지키는
    핵심 계층이다.
    """

    def generate(self, mapping_plan: dict[str, Any]) -> dict[str, Any]:
        """Mapping Plan을 AAS JSON 최상위 구조로 변환한다."""

        asset = mapping_plan["asset"]
        asset_id = asset["asset_id"]
        aas_id = f"urn:aas:{asset_id}"
        global_asset_id = f"urn:asset:{asset_id}"
        submodels = [self._submodel(asset_id, item) for item in mapping_plan["submodels"]]

        return {
            "assetAdministrationShells": [
                {
                    "modelType": "AssetAdministrationShell",
                    "id": aas_id,
                    "idShort": to_id_short(asset.get("asset_name", asset_id)),
                    "assetInformation": {
                        "assetKind": "Instance",
                        "globalAssetId": global_asset_id,
                    },
                    "submodels": [
                        {
                            "type": "ModelReference",
                            "keys": [
                                {
                                    "type": "Submodel",
                                    "value": submodel["id"],
                                }
                            ],
                        }
                        for submodel in submodels
                    ],
                }
            ],
            "submodels": submodels,
            "conceptDescriptions": self._concept_descriptions(mapping_plan),
        }

    def validate(self, aas_json: dict[str, Any]) -> dict[str, Any]:
        """생성된 AAS JSON에 필수 필드가 있는지 가볍게 검증한다.

        실제 운영 단계에서는 AAS 공식 JSON Schema validator나 BaSyx/AASX
        도구로 교체할 수 있다.
        """

        errors: list[str] = []
        shells = aas_json.get("assetAdministrationShells")
        submodels = aas_json.get("submodels")

        if not isinstance(shells, list) or not shells:
            errors.append("assetAdministrationShells must contain at least one shell.")
        if not isinstance(submodels, list) or not submodels:
            errors.append("submodels must contain at least one submodel.")

        for index, shell in enumerate(shells or []):
            self._require(shell, ["id", "idShort", "assetInformation", "submodels"], errors, f"shell[{index}]")
        for index, submodel in enumerate(submodels or []):
            self._require(submodel, ["id", "idShort", "submodelElements"], errors, f"submodel[{index}]")
            for element_index, element in enumerate(submodel.get("submodelElements", [])):
                self._require(
                    element,
                    ["modelType", "idShort", "valueType", "value"],
                    errors,
                    f"submodel[{index}].element[{element_index}]",
                )

        return {"is_valid": not errors, "errors": errors}

    def _submodel(self, asset_id: str, item: dict[str, Any]) -> dict[str, Any]:
        """Mapping Plan의 Submodel 항목을 AAS Submodel JSON으로 만든다."""
        submodel_id_short = item["idShort"]
        return {
            "modelType": "Submodel",
            "id": f"urn:aas:{asset_id}:submodel:{submodel_id_short}",
            "idShort": submodel_id_short,
            "submodelElements": [
                self._property_element(property_item)
                for property_item in item.get("properties", [])
            ],
        }

    def _property_element(self, item: dict[str, Any]) -> dict[str, Any]:
        """Mapping Plan의 property 항목을 AAS Property element로 변환한다."""
        element: dict[str, Any] = {
            "modelType": "Property",
            "idShort": item["idShort"],
            "valueType": self._value_type(item.get("value")),
            "value": str(item.get("value", "")),
        }
        if item.get("semanticId"):
            element["semanticId"] = {
                "type": "ExternalReference",
                "keys": [
                    {
                        "type": "GlobalReference",
                        "value": item["semanticId"],
                    }
                ],
            }
        if item.get("unit"):
            element["qualifiers"] = [
                {
                    "type": "unit",
                    "valueType": "xs:string",
                    "value": item["unit"],
                }
            ]
        return element

    def _concept_descriptions(self, mapping_plan: dict[str, Any]) -> list[dict[str, Any]]:
        """semanticId가 있는 property에 대해 ConceptDescription 목록을 만든다."""
        seen: set[str] = set()
        descriptions: list[dict[str, Any]] = []
        for submodel in mapping_plan["submodels"]:
            for item in submodel.get("properties", []):
                semantic_id = item.get("semanticId")
                if not semantic_id or semantic_id in seen:
                    continue
                seen.add(semantic_id)
                descriptions.append(
                    {
                        "modelType": "ConceptDescription",
                        "id": semantic_id,
                        "idShort": item["idShort"],
                    }
                )
        return descriptions

    def _require(
        self,
        payload: dict[str, Any],
        keys: list[str],
        errors: list[str],
        location: str,
    ) -> None:
        """검증 대상 payload에 필요한 key가 모두 있는지 확인한다."""
        for key in keys:
            if key not in payload:
                errors.append(f"{location} is missing required field: {key}")

    def _value_type(self, value: Any) -> str:
        """Python 값 타입을 AAS Property valueType 문자열로 매핑한다."""
        if isinstance(value, bool):
            return "xs:boolean"
        if isinstance(value, int) and not isinstance(value, bool):
            return "xs:int"
        if isinstance(value, float):
            return "xs:double"
        return "xs:string"
