from __future__ import annotations

import json
import re
import sys
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path
from typing import Any


DATASET = "gart-labor/eclassCorpus"
CONFIG = "default"
SPLIT = "train"
SOURCE_URL = "https://huggingface.co/datasets/gart-labor/eclassCorpus"
ROWS_URL = "https://datasets-server.huggingface.co/rows"
OUTPUT_PATH = Path("repositories/eclass_dictionary/eclass_properties.json")
PAGE_SIZE = 100


CURATED_ALIASES = {
    "Manufacturer name": [
        "manufacturer",
        "manufacturer name",
        "maker",
        "supplier",
        "name of manufacturer",
        "manufacturer_name",
        "manufacturername",
        "제조사",
        "제조업체",
        "제조자",
    ],
    "Manufacturer product designation": [
        "manufacturer product designation",
        "product designation",
        "model name",
        "model",
        "product name",
        "type designation",
        "manufacturer_product_designation",
        "manufacturerproductdesignation",
        "제품명",
        "모델명",
    ],
    "Serial number": [
        "serial number",
        "serial",
        "s/n",
        "sn",
        "serial no",
        "serial_number",
        "serialnumber",
        "시리얼 번호",
        "시리얼번호",
    ],
    "Nominal voltage": [
        "nominal voltage",
        "rated voltage",
        "operating voltage",
        "supply voltage",
        "input voltage",
        "voltage",
        "vdc",
        "정격 전압",
        "공급 전압",
        "동작 전압",
    ],
    "Manufacturer product family": [
        "manufacturer product family",
        "product family",
        "product series",
        "product group",
        "manufacturer_product_family",
        "manufacturerproductfamily",
        "제품 패밀리",
        "제품 계열",
    ],
    "Product type": [
        "product type",
        "manufacturer product type",
        "type",
        "product category",
        "product_type",
        "producttype",
        "제품 유형",
        "제품 타입",
    ],
    "Date of manufacture": [
        "date of manufacture",
        "manufacture date",
        "production date",
        "manufacturing date",
        "dateofmanufacture",
        "제조일",
        "제조 날짜",
    ],
    "GTIN": [
        "gtin",
        "global trade item number",
        "article number",
        "product article number",
    ],
    "Weight": [
        "weight",
        "mass",
        "net weight",
        "gross weight",
        "total weight",
        "무게",
        "중량",
    ],
}

COMPATIBILITY_PROPERTIES = [
    {
        "irdi": "0173-1#02-AAS804#002",
        "preferred_name": "Weight",
        "definition": "Total weight or mass of the asset.",
        "datatype": "REAL_MEASURE",
        "unit": "kg",
        "source_did": None,
        "metalabel": None,
        "submodel_hint": "TechnicalData",
    }
]


def main() -> None:
    rows = _fetch_all_rows()
    properties = [_row_to_property(row) for row in rows]
    properties = _with_compatibility_properties(properties)
    payload = {
        "version": "Hugging Face gart-labor/eclassCorpus default/train",
        "source": SOURCE_URL,
        "source_doi": "10.57967/hf/0410",
        "retrieved_at": date.today().isoformat(),
        "dataset": DATASET,
        "config": CONFIG,
        "split": SPLIT,
        "row_count": len(rows),
        "property_count": len(properties),
        "notes": (
            "Rebuilt from Hugging Face dataset rows. Aliases are generated from "
            "preferred names and a small project compatibility alias table."
        ),
        "properties": properties,
    }
    OUTPUT_PATH.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {len(properties)} properties to {OUTPUT_PATH}")


def _fetch_all_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    total: int | None = None
    offset = 0
    while total is None or offset < total:
        page = _fetch_page(offset)
        total = int(page["num_rows_total"])
        for item in page.get("rows", []):
            row = item.get("row")
            if isinstance(row, dict):
                rows.append(row)
        offset += PAGE_SIZE
    return rows


def _fetch_page(offset: int) -> dict[str, Any]:
    query = urllib.parse.urlencode(
        {
            "dataset": DATASET,
            "config": CONFIG,
            "split": SPLIT,
            "offset": offset,
            "length": PAGE_SIZE,
        }
    )
    request = urllib.request.Request(f"{ROWS_URL}?{query}", method="GET")
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def _row_to_property(row: dict[str, Any]) -> dict[str, Any]:
    name = str(row.get("name") or "").strip()
    definition = str(row.get("query") or "").strip()
    datatype = _clean_optional(row.get("datatype"))
    unit = _clean_optional(row.get("unit"))
    return {
        "irdi": str(row.get("IRDI") or "").strip(),
        "preferred_name": name,
        "aliases": _aliases(name),
        "definition": definition,
        "datatype": datatype,
        "unit": unit,
        "submodel_hint": _submodel_hint(name, definition),
        "source_did": row.get("did"),
        "metalabel": row.get("metalabel"),
    }


def _with_compatibility_properties(properties: list[dict[str, Any]]) -> list[dict[str, Any]]:
    existing_irdis = {item["irdi"] for item in properties}
    merged = list(properties)
    for item in COMPATIBILITY_PROPERTIES:
        if item["irdi"] in existing_irdis:
            continue
        merged.append(
            {
                "irdi": item["irdi"],
                "preferred_name": item["preferred_name"],
                "aliases": _aliases(item["preferred_name"]),
                "definition": item["definition"],
                "datatype": item["datatype"],
                "unit": item["unit"],
                "submodel_hint": item["submodel_hint"],
                "source_did": item["source_did"],
                "metalabel": item["metalabel"],
                "source": "project_compatibility",
            }
        )
    return merged


def _aliases(name: str) -> list[str]:
    variants = []
    variants.append(name)
    variants.append(name.lower())
    variants.append(_to_id_short(name))
    variants.append(_to_snake_case(name))
    variants.append(re.sub(r"[^A-Za-z0-9]+", "", name).lower())
    variants.extend(CURATED_ALIASES.get(name, []))

    seen: set[str] = set()
    result: list[str] = []
    for item in variants:
        alias = " ".join(str(item).strip().split())
        key = alias.lower()
        if alias and key not in seen:
            seen.add(key)
            result.append(alias)
    return result


def _to_id_short(value: str) -> str:
    words = re.findall(r"[A-Za-z0-9]+", value)
    return "".join(word[:1].upper() + word[1:] for word in words)


def _to_snake_case(value: str) -> str:
    words = re.findall(r"[A-Za-z0-9]+", value.lower())
    return "_".join(words)


def _clean_optional(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _submodel_hint(name: str, definition: str) -> str:
    text = name.lower()
    identity_terms = [
        "manufacturer",
        "supplier",
        "vendor",
        "serial",
        "gtin",
        "article number",
        "product designation",
        "product family",
        "product type",
        "date of manufacture",
        "uri of the product",
        "country of origin",
        "certificate",
        "conformity",
    ]
    if any(term in text for term in identity_terms):
        return "DigitalNameplate"
    operational_text = f"{name} {definition}".lower()
    if any(term in operational_text for term in ["status", "runtime", "operating state", "sensor"]):
        return "OperationalData"
    return "TechnicalData"


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"failed to rebuild ECLASS dictionary: {exc}", file=sys.stderr)
        raise
