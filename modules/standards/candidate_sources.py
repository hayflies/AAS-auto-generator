from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterable

from app.models import AASPropertyCandidate
from app.text import normalize_label, slugify, to_id_short


MAPPABLE_ELEMENT_TYPES = {
    "Property",
    "MultiLanguageProperty",
    "Range",
    "File",
    "Blob",
    "ReferenceElement",
    "RelationshipElement",
}


class CandidateSourceRegistry:
    """Loads AAS property candidates from IDTA templates, ECLASS, and IEC CDD."""

    def __init__(
        self,
        template_root: Path,
        eclass_path: Path,
        iec_cdd_path: Path,
    ) -> None:
        self.template_root = template_root
        self.eclass_path = eclass_path
        self.iec_cdd_path = iec_cdd_path

    def load_candidates(self) -> list[AASPropertyCandidate]:
        candidates: list[AASPropertyCandidate] = []
        candidates.extend(SubmodelTemplateRepository(self.template_root).load_candidates())
        candidates.extend(EclassDictionaryRepository(self.eclass_path).load_candidates())
        candidates.extend(IecCddDictionaryRepository(self.iec_cdd_path).load_candidates())
        return self._dedupe(candidates)

    def _dedupe(self, candidates: list[AASPropertyCandidate]) -> list[AASPropertyCandidate]:
        best: dict[tuple[str | None, str, str], AASPropertyCandidate] = {}
        for candidate in candidates:
            key = (
                candidate.semantic_id or candidate.eclass_irdi,
                candidate.submodel,
                candidate.idShort.lower(),
            )
            existing = best.get(key)
            if existing is None or candidate.source_priority > existing.source_priority:
                best[key] = candidate
        return list(best.values())


class SubmodelTemplateRepository:
    """Builds candidates from local IDTA submodel template JSON files."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def load_candidates(self) -> list[AASPropertyCandidate]:
        if not self.root.exists():
            return []

        candidates: list[AASPropertyCandidate] = []
        for path in sorted(self.root.rglob("*.json")):
            data = _load_json(path)
            if not isinstance(data, dict) or not isinstance(data.get("submodels"), list):
                continue
            concepts = _concept_description_index(data)
            family = _template_family_from_path(path)
            for submodel in data.get("submodels", []):
                if not isinstance(submodel, dict):
                    continue
                submodel_id_short = submodel.get("idShort") or family
                template_id = (
                    (submodel.get("administration") or {}).get("templateId")
                    or submodel.get("id")
                    or str(path)
                )
                canonical_submodel = _canonical_submodel(family, submodel_id_short)
                elements = submodel.get("submodelElements", [])
                candidates.extend(
                    self._walk_elements(
                        elements=elements,
                        concepts=concepts,
                        canonical_submodel=canonical_submodel,
                        template_id=template_id,
                        parent_path=[str(submodel_id_short)],
                        source_file=path,
                    )
                )
        return candidates

    def _walk_elements(
        self,
        elements: Any,
        concepts: dict[str, dict[str, Any]],
        canonical_submodel: str,
        template_id: str,
        parent_path: list[str],
        source_file: Path,
    ) -> list[AASPropertyCandidate]:
        candidates: list[AASPropertyCandidate] = []
        for element in _iter_dict_elements(elements):
            id_short = str(element.get("idShort") or "").strip()
            model_type = str(element.get("modelType") or "").strip()
            element_path = parent_path + ([id_short] if id_short else [])

            if id_short and model_type in MAPPABLE_ELEMENT_TYPES:
                semantic_ids = _reference_values(element.get("semanticId"))
                semantic_id = semantic_ids[0] if semantic_ids else None
                supplemental_ids = []
                for supplemental in element.get("supplementalSemanticIds") or []:
                    supplemental_ids.extend(_reference_values(supplemental))

                concept = concepts.get(semantic_id or "", {})
                eclass_irdi = _first_matching([semantic_id] + supplemental_ids, "0173-")
                description = (
                    concept.get("definition")
                    or _text_list(element.get("description"), "en")
                    or _text_list(element.get("displayName"), "en")
                    or normalize_label(id_short)
                )
                value_type = element.get("valueType") or concept.get("dataType")
                unit = element.get("unit") or concept.get("unit")
                aliases = _aliases(
                    id_short,
                    _text_values(element.get("displayName")),
                    [concept.get("preferredName")],
                )
                candidate_id = _candidate_id("SMT", canonical_submodel, "/".join(element_path), semantic_id)
                candidates.append(
                    AASPropertyCandidate(
                        candidate_id=candidate_id,
                        idShort=id_short,
                        description=str(description),
                        submodel=canonical_submodel,
                        semantic_id=semantic_id,
                        preferred_unit=unit,
                        aliases=aliases,
                        eclass_irdi=eclass_irdi,
                        source="submodel_template",
                        path="/".join(element_path),
                        element_type=model_type,
                        value_type=value_type,
                        cardinality=_cardinality(element),
                        definition=concept.get("definition") or str(description),
                        template_id=template_id,
                        allowed_values=list(concept.get("allowedValues") or []),
                        source_priority=1.0,
                    )
                )

            child_containers = []
            if isinstance(element.get("submodelElements"), list):
                child_containers.append(element.get("submodelElements"))
            if isinstance(element.get("value"), list):
                child_containers.append(element.get("value"))
            if isinstance(element.get("statements"), list):
                child_containers.append(element.get("statements"))

            for child_container in child_containers:
                candidates.extend(
                    self._walk_elements(
                        elements=child_container,
                        concepts=concepts,
                        canonical_submodel=canonical_submodel,
                        template_id=template_id,
                        parent_path=element_path,
                        source_file=source_file,
                    )
                )
        return candidates


class EclassDictionaryRepository:
    """Loads ECLASS property records from the local dictionary snapshot."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def load_candidates(self) -> list[AASPropertyCandidate]:
        data = _load_json(self.path)
        candidates: list[AASPropertyCandidate] = []
        for entry in _dictionary_entries(data):
            irdi = str(entry.get("irdi") or "").strip()
            preferred_name = str(entry.get("preferred_name") or entry.get("name") or "").strip()
            if not irdi or not preferred_name:
                continue
            aliases = _aliases(preferred_name, entry.get("aliases") or [])
            id_short = to_id_short(preferred_name)
            candidates.append(
                AASPropertyCandidate(
                    candidate_id=_candidate_id("ECLASS", id_short, irdi),
                    idShort=id_short,
                    description=str(entry.get("definition") or preferred_name),
                    submodel=str(entry.get("submodel_hint") or "TechnicalData"),
                    semantic_id=irdi,
                    preferred_unit=entry.get("unit"),
                    aliases=aliases,
                    eclass_irdi=irdi,
                    source="eclass_dictionary",
                    path=f"ECLASS/{irdi}",
                    element_type="Property",
                    value_type=_aas_value_type(entry.get("datatype")),
                    definition=entry.get("definition"),
                    source_priority=0.75,
                )
            )
        return candidates


class IecCddDictionaryRepository:
    """Loads IEC CDD cache records from a local JSON source."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def load_candidates(self) -> list[AASPropertyCandidate]:
        data = _load_json(self.path)
        candidates: list[AASPropertyCandidate] = []
        for entry in _dictionary_entries(data):
            irdi = str(entry.get("irdi") or "").strip()
            preferred_name = str(entry.get("preferred_name") or entry.get("name") or "").strip()
            if not irdi or not preferred_name:
                continue
            aliases = _aliases(preferred_name, entry.get("aliases") or [])
            id_short = str(entry.get("idShort") or to_id_short(preferred_name))
            candidates.append(
                AASPropertyCandidate(
                    candidate_id=_candidate_id("IEC_CDD", id_short, irdi),
                    idShort=id_short,
                    description=str(entry.get("definition") or preferred_name),
                    submodel=str(entry.get("submodel_hint") or "TechnicalData"),
                    semantic_id=irdi,
                    preferred_unit=entry.get("unit"),
                    aliases=aliases,
                    source="iec_cdd_dictionary",
                    path=f"IEC_CDD/{irdi}",
                    element_type=str(entry.get("element_type") or "Property"),
                    value_type=entry.get("value_type") or _aas_value_type(entry.get("datatype")),
                    definition=entry.get("definition"),
                    source_priority=0.7,
                )
            )
        return candidates


def _load_json(path: Path) -> Any:
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as file:
            return json.load(file)
    except (json.JSONDecodeError, OSError) as exc:
        print(f"[CandidateSources] JSON load failed ({path}): {exc}")
        return {}


def _dictionary_entries(data: Any) -> Iterable[dict[str, Any]]:
    if isinstance(data, dict):
        properties = data.get("properties")
        if isinstance(properties, list):
            for item in properties:
                yield from _dictionary_entries(item)
            return
        if "irdi" in data:
            yield data
        return
    if isinstance(data, list):
        for item in data:
            yield from _dictionary_entries(item)


def _iter_dict_elements(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
    elif isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                yield item


def _concept_description_index(data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    concepts: dict[str, dict[str, Any]] = {}
    for item in data.get("conceptDescriptions", []) or []:
        if not isinstance(item, dict):
            continue
        semantic_id = item.get("id")
        if not semantic_id:
            continue
        content = _first_data_spec_content(item)
        concepts[str(semantic_id)] = {
            "preferredName": _text_list(content.get("preferredName"), "en") or item.get("idShort"),
            "definition": _text_list(content.get("definition"), "en"),
            "unit": content.get("unit"),
            "dataType": content.get("dataType"),
            "allowedValues": _value_list(content),
        }
    return concepts


def _first_data_spec_content(item: dict[str, Any]) -> dict[str, Any]:
    for embedded in item.get("embeddedDataSpecifications") or []:
        if isinstance(embedded, dict):
            content = embedded.get("dataSpecificationContent")
            if isinstance(content, dict):
                return content
    return {}


def _reference_values(ref: Any) -> list[str]:
    values: list[str] = []
    if isinstance(ref, dict):
        for key in ref.get("keys") or []:
            if isinstance(key, dict) and key.get("value"):
                values.append(str(key["value"]))
    return values


def _text_values(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if not isinstance(value, list):
        return []
    texts: list[str] = []
    for item in value:
        if isinstance(item, dict) and item.get("text"):
            texts.append(str(item["text"]))
        elif isinstance(item, str):
            texts.append(item)
    return texts


def _text_list(value: Any, language: str) -> str | None:
    if isinstance(value, str):
        return value
    if not isinstance(value, list):
        return None
    fallback = None
    for item in value:
        if not isinstance(item, dict):
            continue
        text = item.get("text")
        if not text:
            continue
        if item.get("language") == language:
            return str(text)
        fallback = fallback or str(text)
    return fallback


def _aliases(*groups: Any) -> list[str]:
    seen: set[str] = set()
    aliases: list[str] = []
    for group in groups:
        values = group if isinstance(group, list) else [group]
        for value in values:
            if not value:
                continue
            text = str(value).strip()
            for alias in {text, normalize_label(text), text.replace("_", " ")}:
                alias = " ".join(alias.split())
                key = alias.lower()
                if alias and key not in seen:
                    seen.add(key)
                    aliases.append(alias)
    return aliases


def _cardinality(element: dict[str, Any]) -> str | None:
    for qualifier in element.get("qualifiers") or []:
        if not isinstance(qualifier, dict):
            continue
        qtype = str(qualifier.get("type") or "")
        if "Cardinality" in qtype:
            return qualifier.get("value")
    return None


def _value_list(content: dict[str, Any]) -> list[str]:
    value_list = content.get("valueList")
    if not isinstance(value_list, dict):
        return []
    values: list[str] = []
    for pair in value_list.get("valueReferencePairs") or []:
        if isinstance(pair, dict) and pair.get("value"):
            values.append(str(pair["value"]))
    return values


def _first_matching(values: list[str | None], prefix: str) -> str | None:
    for value in values:
        if value and str(value).startswith(prefix):
            return str(value)
    return None


def _template_family_from_path(path: Path) -> str:
    parts = list(path.parts)
    for marker in ("published", "deprecated"):
        if marker in parts:
            index = parts.index(marker)
            if index + 1 < len(parts):
                return to_id_short(parts[index + 1].replace("_", " "))
    return to_id_short(path.parent.name.replace("_", " "))


def _canonical_submodel(family: str, submodel_id_short: str) -> str:
    known = {
        "DigitalNameplate": "DigitalNameplate",
        "TechnicalData": "TechnicalData",
        "ProvisionOf3dModels": "ProvisionOf3DModels",
    }
    if family in known:
        return known[family]
    if submodel_id_short == "Nameplate":
        return "DigitalNameplate"
    return family or submodel_id_short


def _aas_value_type(datatype: Any) -> str | None:
    if not datatype:
        return None
    text = str(datatype).upper()
    if "BOOL" in text:
        return "xs:boolean"
    if "INT" in text or "INTEGER" in text:
        return "xs:int"
    if "REAL" in text or "FLOAT" in text or "MEASURE" in text or "DOUBLE" in text:
        return "xs:double"
    if "DATE" in text:
        return "xs:date"
    return "xs:string"


def _candidate_id(*parts: str | None) -> str:
    text = "_".join(slugify(str(part)) for part in parts if part)
    text = re.sub(r"_+", "_", text).strip("_")
    return text.upper()[:180] or "CANDIDATE"
