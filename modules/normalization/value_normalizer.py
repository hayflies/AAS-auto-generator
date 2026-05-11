from __future__ import annotations

import re
from dataclasses import replace
from typing import Any

from app.models import SemanticNode


_VALUE_WITH_UNIT = re.compile(
    r"^\s*(?P<value>[-+]?\d+(?:[.,]\d+)?(?:\s*(?:~|to|-)\s*[-+]?\d+(?:[.,]\d+)?)?)\s*(?P<unit>[A-Za-z/%°µ]+(?:/[A-Za-z]+)?)?\s*$",
    re.IGNORECASE,
)


class ValueNormalizer:
    """Normalizes extracted SemanticNode values before candidate matching."""

    UNIT_ALIASES = {
        "vdc": "V",
        "vac": "V",
        "volt": "V",
        "volts": "V",
        "a": "A",
        "amp": "A",
        "amps": "A",
        "ampere": "A",
        "amperes": "A",
        "ma": "mA",
        "hz": "Hz",
        "khz": "kHz",
        "kg": "kg",
        "g": "g",
        "gram": "g",
        "grams": "g",
        "mm": "mm",
        "cm": "cm",
        "m": "m",
        "mm/s": "mm/s",
        "rpm": "1/min",
        "r/min": "1/min",
        "min-1": "1/min",
        "c": "degC",
        "°c": "degC",
        "degc": "degC",
        "degreecelsius": "degC",
    }

    def normalize_nodes(self, nodes: list[SemanticNode]) -> list[SemanticNode]:
        return [self.normalize_node(node) for node in nodes]

    def normalize_node(self, node: SemanticNode) -> SemanticNode:
        value = node.value
        unit = node.unit

        if isinstance(value, str):
            value = value.strip()
            match = _VALUE_WITH_UNIT.match(value)
            if match:
                value = self._normalize_scalar(match.group("value"))
                embedded_unit = match.group("unit")
                if not unit and embedded_unit:
                    unit = embedded_unit
            else:
                value = self._normalize_scalar(value)

        normalized_unit = self.normalize_unit(unit)
        value_type = self.infer_value_type(value)
        return replace(node, value=value, unit=normalized_unit, value_type=value_type)

    def normalize_unit(self, unit: str | None) -> str | None:
        if unit is None:
            return None
        text = str(unit).strip()
        if not text:
            return None
        key = text.lower().replace(" ", "")
        return self.UNIT_ALIASES.get(key, text)

    def infer_value_type(self, value: Any) -> str:
        if isinstance(value, bool):
            return "boolean"
        if isinstance(value, int) and not isinstance(value, bool):
            return "integer"
        if isinstance(value, float):
            return "float"
        if isinstance(value, str):
            if self._is_range(value):
                return "range"
            try:
                int(value)
                return "integer"
            except ValueError:
                pass
            try:
                float(value)
                return "float"
            except ValueError:
                return "string"
        return "string"

    def _normalize_scalar(self, value: str) -> Any:
        text = value.replace(",", ".").strip()
        if self._is_range(text):
            return text
        try:
            integer = int(text)
            return integer
        except ValueError:
            pass
        try:
            return float(text)
        except ValueError:
            return value.strip()

    def _is_range(self, value: str) -> bool:
        return bool(re.search(r"\d\s*(~|to|-)\s*\d", value, re.IGNORECASE))
