from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from app.models import AssetPackage, MatchedProperty, ModelInfo
from interfaces.base_llm import BaseLLM, LLMConnectionError
from interfaces.base_mapper import BaseAASMapper
from modules.llm.prompts import build_submodel_template_selection_prompt
from modules.standards import SubmodelTemplateRepository


class TemplateAwareAASMapper(BaseAASMapper):
    """Places matched properties into submodels and validates them against templates."""

    def __init__(
        self,
        default_submodels_path: Path,
        template_root: Path,
        min_score: float = 0.55,
        review_threshold: float = 0.78,
        llm_client: BaseLLM | None = None,
        use_llm_template_selection: bool = False,
        llm_selection_threshold: float = 0.70,
    ) -> None:
        self.default_submodels_path = default_submodels_path
        self.template_root = template_root
        self.min_score = min_score
        self.review_threshold = review_threshold
        self.llm_client = llm_client
        self.use_llm_template_selection = use_llm_template_selection and llm_client is not None
        self.llm_selection_threshold = llm_selection_threshold
        self.submodel_descriptions = self._load_submodel_descriptions(default_submodels_path)
        self.submodel_ids = list(self.submodel_descriptions)
        self._template_candidates = SubmodelTemplateRepository(template_root).load_candidates()
        self._valid_by_semantic = {
            (candidate.submodel, candidate.semantic_id)
            for candidate in self._template_candidates
            if candidate.semantic_id
        }
        self._valid_by_id_short = {
            (candidate.submodel, candidate.idShort.lower())
            for candidate in self._template_candidates
        }
        self._template_matches_by_key = self._index_template_matches()

    def map(
        self,
        asset_package: AssetPackage,
        matched_properties: list[MatchedProperty],
        model_info: ModelInfo,
    ) -> dict[str, Any]:
        submodels: dict[str, dict[str, Any]] = {
            submodel_id: {"idShort": submodel_id, "properties": []}
            for submodel_id in self.submodel_ids
        }
        diagnostics: list[dict[str, Any]] = []
        review_queue: list[dict[str, Any]] = []

        for item in matched_properties:
            if item.match_score < self.min_score:
                diagnostics.append(self._diagnostic(item, "rejected_low_confidence"))
                review_queue.append(self._review_item(item, "low_confidence"))
                continue

            placement = self._select_submodel(asset_package, item)
            item.submodel = placement["submodel"]

            status, reason, review_required = self._validation_status(item)
            reason = self._merge_reasons(reason, placement["reason"])
            review_required = review_required or item.match_score < self.review_threshold
            review_required = review_required or placement["review_required"]

            target_submodel = item.submodel or "TechnicalData"
            submodel = submodels.setdefault(
                target_submodel,
                {"idShort": target_submodel, "properties": []},
            )

            entry = self._property_entry(
                item=item,
                status=status,
                reason=reason,
                review_required=review_required,
                placement=placement,
            )
            self._upsert_property(submodel["properties"], entry)

            diagnostics.append(self._diagnostic(item, status, reason))
            if review_required:
                review_queue.append(self._review_item(item, reason))

        self._append_model_references(submodels, model_info)

        return {
            "asset": asset_package.to_dict(),
            "submodels": list(submodels.values()),
            "model_info": model_info.to_dict(),
            "diagnostics": diagnostics,
            "reviewQueue": review_queue,
        }

    def _validation_status(self, item: MatchedProperty) -> tuple[str, str, bool]:
        semantic_key = (item.submodel, item.semantic_id)
        id_short_key = (item.submodel, item.idShort.lower())

        if item.source == "submodel_template":
            return "template_validated", "candidate is defined by a loaded submodel template", False
        if item.semantic_id and semantic_key in self._valid_by_semantic:
            return "template_validated", "semanticId exists in a loaded submodel template", False
        if id_short_key in self._valid_by_id_short:
            return "template_validated", "idShort exists in a loaded submodel template", False
        if item.submodel == "TechnicalData" and item.source in {
            "eclass_dictionary",
            "iec_cdd_dictionary",
            "project_repository",
        }:
            return "template_extension", "TechnicalData accepts arbitrary technical property areas", False
        return "needs_review", "no matching element was found in loaded templates", True

    def _property_entry(
        self,
        item: MatchedProperty,
        status: str,
        reason: str,
        review_required: bool,
        placement: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "semantic_node_id": item.semantic_node_id,
            "aas_property_id": item.aas_property_id,
            "idShort": item.idShort,
            "value": item.value,
            "unit": item.unit,
            "match_score": item.match_score,
            "semanticId": item.semantic_id,
            "eclassIrdi": item.eclass_irdi,
            "source": item.source,
            "path": item.path,
            "elementType": item.element_type or self._infer_element_type(item),
            "valueType": item.value_type,
            "cardinality": item.cardinality,
            "definition": item.definition,
            "templateId": item.template_id,
            "mappingStatus": status,
            "reviewRequired": review_required,
            "reason": reason,
            "placement": placement,
        }

    def _select_submodel(
        self,
        asset_package: AssetPackage,
        item: MatchedProperty,
    ) -> dict[str, Any]:
        options = self._submodel_options(item)
        fallback = self._deterministic_placement(item, options)
        if not self.use_llm_template_selection:
            return fallback

        prompt = build_submodel_template_selection_prompt(
            asset_package.to_dict(),
            self._placement_property_payload(item),
            options,
        )
        try:
            response = self.llm_client.generate_json(prompt, fallback={})  # type: ignore[union-attr]
        except LLMConnectionError as exc:
            return {
                **fallback,
                "review_required": True,
                "source": "deterministic_fallback",
                "reason": f"{fallback['reason']}; LLM placement unavailable: {exc}",
            }

        selected = str(response.get("selected_submodel") or "").strip()
        confidence = self._score(response.get("confidence"))
        allowed = {option["submodel"] for option in options}
        if selected not in allowed:
            return {
                **fallback,
                "review_required": True,
                "source": "deterministic_fallback",
                "reason": f"{fallback['reason']}; LLM selected invalid submodel: {selected}",
            }

        return {
            "submodel": selected,
            "confidence": confidence,
            "review_required": bool(response.get("review_required")) or confidence < self.llm_selection_threshold,
            "source": "llm_template_selector",
            "reason": str(response.get("reason") or "LLM selected the submodel placement."),
            "options": options,
        }

    def _deterministic_placement(
        self,
        item: MatchedProperty,
        options: list[dict[str, Any]],
    ) -> dict[str, Any]:
        ranked = sorted(options, key=lambda option: option["score"], reverse=True)
        selected = ranked[0] if ranked else {"submodel": item.submodel or "TechnicalData", "score": 0.5}
        return {
            "submodel": selected["submodel"],
            "confidence": selected["score"],
            "review_required": selected["score"] < self.llm_selection_threshold,
            "source": "deterministic_template_selector",
            "reason": selected.get("evidence") or "selected by template/idShort evidence",
            "options": options,
        }

    def _submodel_options(self, item: MatchedProperty) -> list[dict[str, Any]]:
        scores: dict[str, dict[str, Any]] = {}

        def add(submodel: str, score: float, evidence: str) -> None:
            if not submodel:
                return
            current = scores.get(submodel)
            description = self.submodel_descriptions.get(submodel, "")
            if current is None or score > current["score"]:
                scores[submodel] = {
                    "submodel": submodel,
                    "description": description,
                    "score": score,
                    "evidence": evidence,
                }

        for submodel, description in self.submodel_descriptions.items():
            add(submodel, 0.20, f"default available submodel: {description}")

        if item.submodel:
            current_score = 0.90 if item.submodel in self.submodel_descriptions else 0.55
            add(item.submodel, current_score, "current property candidate submodel")

        for candidate in self._template_matches(item):
            evidence = []
            if item.semantic_id and candidate.semantic_id == item.semantic_id:
                evidence.append("semanticId exists in template")
            if item.eclass_irdi and candidate.eclass_irdi == item.eclass_irdi:
                evidence.append("ECLASS IRDI exists in template")
            if candidate.idShort.lower() == item.idShort.lower():
                evidence.append("idShort exists in template")
            base_score = 0.65
            if item.semantic_id and candidate.semantic_id == item.semantic_id:
                base_score = max(base_score, 0.92)
            if item.eclass_irdi and candidate.eclass_irdi == item.eclass_irdi:
                base_score = max(base_score, 0.88)
            if candidate.idShort.lower() == item.idShort.lower():
                base_score = max(base_score, 0.80)
            if candidate.submodel not in self.submodel_descriptions:
                base_score = min(base_score, 0.72)
            add(candidate.submodel, base_score, "; ".join(evidence) or "similar template element")

        self._add_rule_based_option(item, add)
        return sorted(scores.values(), key=lambda option: option["score"], reverse=True)[:8]

    def _template_matches(self, item: MatchedProperty):
        keys = [
            ("semantic", item.semantic_id or ""),
            ("eclass", item.eclass_irdi or ""),
            ("idShort", item.idShort.lower()),
        ]
        seen: set[str] = set()
        for key in keys:
            for candidate in self._template_matches_by_key.get(key, []):
                unique = f"{candidate.submodel}:{candidate.idShort}:{candidate.semantic_id}"
                if unique in seen:
                    continue
                seen.add(unique)
                yield candidate

    def _add_rule_based_option(self, item: MatchedProperty, add) -> None:
        identity_text = " ".join(
            str(part or "").lower()
            for part in [item.idShort, item.path, item.semantic_id, item.eclass_irdi]
        )
        technical_text = " ".join(
            str(part or "").lower()
            for part in [item.idShort, item.definition, item.path, item.semantic_id, item.eclass_irdi]
        )
        if any(token in identity_text for token in ["manufacturer", "serial", "nameplate", "designation", "certificate"]):
            add("DigitalNameplate", 0.96, "identity/nameplate keyword heuristic")
        if any(token in technical_text for token in ["voltage", "current", "weight", "mass", "payload", "speed", "dimension"]):
            add("TechnicalData", 0.97, "technical specification keyword heuristic")
        if any(token in technical_text for token in ["model file", "geometry", "3d", "glb", "gltf", "step"]):
            add("ProvisionOf3DModels", 0.96, "3D model reference keyword heuristic")
        if any(token in technical_text for token in ["status", "temperature", "runtime", "sensor", "telemetry"]):
            add("OperationalData", 0.96, "operational/runtime keyword heuristic")

    def _placement_property_payload(self, item: MatchedProperty) -> dict[str, Any]:
        payload = asdict(item)
        payload["semanticId"] = item.semantic_id
        payload["eclassIrdi"] = item.eclass_irdi
        payload["currentSubmodel"] = item.submodel
        return payload

    def _index_template_matches(self) -> dict[tuple[str, str], list]:
        index: dict[tuple[str, str], list] = {}
        for candidate in self._template_candidates:
            keys = [
                ("semantic", candidate.semantic_id or ""),
                ("eclass", candidate.eclass_irdi or ""),
                ("idShort", candidate.idShort.lower()),
            ]
            for key in keys:
                if key[1]:
                    index.setdefault(key, []).append(candidate)
        return index

    def _infer_element_type(self, item: MatchedProperty) -> str:
        if item.value_type == "range":
            return "Range"
        if isinstance(item.value, str) and item.value.startswith(("http://", "https://")):
            return "Property"
        return "Property"

    def _upsert_property(self, properties: list[dict[str, Any]], entry: dict[str, Any]) -> None:
        existing = next(
            (
                item
                for item in properties
                if item.get("idShort") == entry["idShort"]
                or (
                    item.get("semantic_node_id") is not None
                    and item.get("semantic_node_id") == entry["semantic_node_id"]
                )
            ),
            None,
        )
        if existing is None:
            properties.append(entry)
        elif entry["match_score"] > existing.get("match_score", 0):
            properties.remove(existing)
            properties.append(entry)

    def _append_model_references(
        self,
        submodels: dict[str, dict[str, Any]],
        model_info: ModelInfo,
    ) -> None:
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
                    "source": "pipeline",
                    "elementType": "File",
                    "valueType": None,
                    "mappingStatus": "pipeline_generated",
                    "reviewRequired": False,
                },
                {
                    "semantic_node_id": None,
                    "aas_property_id": "AAS_PROP_MODEL_FORMAT",
                    "idShort": "ModelFormat",
                    "value": model_info.model_format,
                    "unit": None,
                    "match_score": 1.0,
                    "semanticId": "https://admin-shell.io/idta/3d/ModelFormat/1/0",
                    "source": "pipeline",
                    "elementType": "Property",
                    "valueType": "xs:string",
                    "mappingStatus": "pipeline_generated",
                    "reviewRequired": False,
                },
                {
                    "semantic_node_id": None,
                    "aas_property_id": "AAS_PROP_MODEL_GENERATION_METHOD",
                    "idShort": "GenerationMethod",
                    "value": model_info.generation_method,
                    "unit": None,
                    "match_score": 1.0,
                    "semanticId": "https://example.org/aas/3d/GenerationMethod",
                    "source": "pipeline",
                    "elementType": "Property",
                    "valueType": "xs:string",
                    "mappingStatus": "pipeline_generated",
                    "reviewRequired": False,
                },
            ]
        )

    def _diagnostic(
        self,
        item: MatchedProperty,
        status: str,
        reason: str | None = None,
    ) -> dict[str, Any]:
        return {
            "semantic_node_id": item.semantic_node_id,
            "idShort": item.idShort,
            "submodel": item.submodel,
            "score": item.match_score,
            "status": status,
            "reason": reason,
            "source": item.source,
            "semanticId": item.semantic_id,
            "eclassIrdi": item.eclass_irdi,
        }

    def _review_item(self, item: MatchedProperty, reason: str | None) -> dict[str, Any]:
        return {
            "semantic_node_id": item.semantic_node_id,
            "name": item.idShort,
            "submodel": item.submodel,
            "semanticId": item.semantic_id,
            "score": item.match_score,
            "reason": reason,
        }

    def _load_submodel_ids(self, template_path: Path) -> list[str]:
        with template_path.open("r", encoding="utf-8") as file:
            data = json.load(file)
        return [item["idShort"] for item in data.get("submodels", [])]

    def _load_submodel_descriptions(self, template_path: Path) -> dict[str, str]:
        with template_path.open("r", encoding="utf-8") as file:
            data = json.load(file)
        return {
            item["idShort"]: str(item.get("description") or "")
            for item in data.get("submodels", [])
        }

    def _merge_reasons(self, validation_reason: str, placement_reason: str) -> str:
        if placement_reason and placement_reason not in validation_reason:
            return f"{validation_reason}; placement: {placement_reason}"
        return validation_reason

    def _score(self, value: object) -> float:
        try:
            score = float(value or 0.0)
        except (TypeError, ValueError):
            return 0.0
        return max(0.0, min(1.0, score))
