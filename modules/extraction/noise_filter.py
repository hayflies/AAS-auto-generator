from __future__ import annotations

import re


_BROWSER_TIME = re.compile(r"\b(?:am|pm|오전|오후)\s*\d{1,2}[:.]\d{2}\b", re.IGNORECASE)
_DATE_LIKE = re.compile(r"\b\d{1,4}[./-]\s*\d{1,2}[./-]\s*\d{1,4}\b")
_HTTP_LIKE = re.compile(r"(?:https?://|www\.|\.com\b|\.co\.|\.io\b|\.kr\b)", re.IGNORECASE)
_NUMERIC_ONLY = re.compile(r"^\s*[-+]?\d+(?:[.,]\d+)?\s*$")
_PART_CODE = re.compile(r"^[A-Z]{2,}[-_/]?[A-Z0-9]{2,}(?:[-_/][A-Z0-9]+)*$", re.IGNORECASE)
_PAGE_COUNTER = re.compile(r"\bpage\s+\d+\s+of\s+\d+\b", re.IGNORECASE)

_HEADER_NAMES = {
    "item",
    "item field",
    "qty",
    "quantity",
    "no",
    "number",
    "page",
    "url",
    "https",
    "http",
    "www",
}
_BOM_CONTEXT = {
    "item | qty",
    "package contents",
    "packing list",
    "components",
    "component list",
    "included",
    "accessories",
    "consists of",
}
_TITLE_BLOCK_CONTEXT = {
    "sheet",
    "scale",
    "nonscal",
    "material",
    "drawn",
    "checked",
    "approved",
}
_BOM_NAME_TOKENS = {
    "usb cable",
    "usb hub",
    "hub",
    "cable",
    "smps",
    "adapter",
    "manual",
    "screw",
    "bolt",
    "bracket",
}
_TECHNICAL_NO_UNIT_NAMES = {
    "dof",
    "axis",
    "axes",
    "degree of freedom",
    "serial number",
    "model number",
    "ip rating",
    "protection class",
}


def entity_noise_reason(
    name: str,
    value: object,
    unit: str | None = None,
    source_reference: str | None = None,
) -> str | None:
    """Return a reason when an extracted entity is likely PDF/web noise.

    The rules are conservative: they remove common browser headers, URLs, table
    headers, title blocks, and BOM quantity rows while preserving real technical
    quantities such as voltage, weight, dimensions, speed, and DOF.
    """

    name_text = str(name or "").strip()
    value_text = str(value or "").strip()
    unit_text = str(unit or "").strip()
    reference = str(source_reference or "").strip()

    lower_name = name_text.lower()
    lower_value = value_text.lower()
    lower_unit = unit_text.lower()
    lower_reference = reference.lower()
    combined = " ".join([lower_name, lower_value, lower_unit, lower_reference])

    if not name_text or not value_text:
        return "missing name or value"
    if lower_name in _HEADER_NAMES or lower_value in _HEADER_NAMES:
        return "table/header label"
    if _HTTP_LIKE.search(name_text) or _HTTP_LIKE.search(value_text):
        return "url/header-footer noise"
    if lower_unit == "/" and lower_name in {"http", "https", "url", "www"}:
        return "url split as property"
    if _BROWSER_TIME.search(combined):
        return "browser timestamp/header-footer noise"
    if _PAGE_COUNTER.search(" ".join([lower_name, lower_value, lower_unit])):
        return "browser page counter"
    if lower_unit == "of" and ("sheet" in lower_reference or "page" in lower_reference):
        return "sheet/page counter"
    if "date" in lower_name and any(token in lower_reference for token in _TITLE_BLOCK_CONTEXT):
        return "drawing title block"
    if lower_name == "unnamed property":
        return "unnamed numeric/table artifact"
    if sentence_like_name(name_text) and not technical_name_hint(lower_name):
        return "sentence-like non-property label"
    if _NUMERIC_ONLY.fullmatch(value_text) and bom_quantity_context(
        lower_name,
        lower_value,
        lower_unit,
        lower_reference,
    ):
        return "bom/package quantity row"
    if (
        not lower_unit
        and not technical_name_hint(lower_name)
        and _NUMERIC_ONLY.fullmatch(value_text)
        and looks_like_part_code_name(name_text)
    ):
        return "part code quantity row"
    return None


def sentence_like_name(name: str) -> bool:
    tokens = [token for token in re.split(r"\s+", name.strip()) if token]
    if len(tokens) >= 8:
        return True
    return bool(re.search(r"\b(consists|contains|includes|please|refer|click|manual)\b", name, re.IGNORECASE))


def technical_name_hint(lower_name: str) -> bool:
    technical_tokens = (
        "voltage",
        "current",
        "power",
        "weight",
        "mass",
        "payload",
        "speed",
        "torque",
        "temperature",
        "dimension",
        "width",
        "height",
        "length",
        "depth",
        "reach",
        "repeatability",
        "accuracy",
        "resolution",
        "communication",
        "interface",
        "protocol",
        "frequency",
        "pressure",
        "brake",
        "force",
    )
    return any(token in lower_name for token in technical_tokens)


def bom_quantity_context(
    lower_name: str,
    lower_value: str,
    lower_unit: str,
    lower_reference: str,
) -> bool:
    if lower_unit:
        return False
    if lower_name in _TECHNICAL_NO_UNIT_NAMES:
        return False
    if any(token in lower_reference for token in _BOM_CONTEXT):
        return True
    if any(token in lower_name for token in _BOM_NAME_TOKENS):
        return True
    if lower_value in {"1", "2", "3", "4", "5"} and _PART_CODE.fullmatch(lower_name):
        return True
    return False


def looks_like_part_code_name(name: str) -> bool:
    """Return true for compact part-code labels, not normal technical words."""

    text = name.strip()
    if not _PART_CODE.fullmatch(text):
        return False
    return text.isupper() or any(char.isdigit() for char in text) or any(char in text for char in "-_/")
