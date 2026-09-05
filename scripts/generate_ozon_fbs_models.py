#!/usr/bin/env python3
"""Generate Pydantic v2 models from the checked-in Ozon FBS OpenAPI document.

The input is deliberately limited to OZON_FBS_OPENAPI.json.  Re-run this script
when the approved Ozon document is replaced; do not edit the generated module by
hand.
"""

from __future__ import annotations

import json
import keyword
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OPENAPI_PATH = ROOT / "tasks/ozon-integration-20260825/OZON_FBS_OPENAPI.json"
OUTPUT_PATH = ROOT / "backend/app/schemas/ozon_fbs_api.py"
REF_PREFIX = "#/components/schemas/"


def _class_name(schema_name: str) -> str:
    parts = re.split(r"[^0-9A-Za-z]+", schema_name)
    return "Ozon" + "".join(part[:1].upper() + part[1:] for part in parts if part)


def _field_name(openapi_name: str) -> str:
    safe_name = re.sub(r"\W", "_", openapi_name)
    if not safe_name or safe_name[0].isdigit():
        safe_name = f"field_{safe_name}"
    return f"{safe_name}_" if keyword.iskeyword(safe_name) else safe_name


def _ref_name(reference: str, names: dict[str, str]) -> str:
    if not reference.startswith(REF_PREFIX):
        raise ValueError(f"Unsupported non-component reference: {reference}")
    schema_name = reference.removeprefix(REF_PREFIX)
    return names[schema_name]


def _type_expression(schema: dict[str, Any], names: dict[str, str]) -> str:
    if "$ref" in schema:
        return _ref_name(schema["$ref"], names)
    if "enum" in schema:
        values = ", ".join(repr(value) for value in schema["enum"])
        return f"Literal[{values}]"

    schema_type = schema.get("type")
    if schema_type == "string":
        return "str"
    if schema_type == "integer":
        return "int"
    if schema_type == "number":
        return "float"
    if schema_type == "boolean":
        return "bool"
    if schema_type in {"array", "array of strings"} or "items" in schema:
        item_schema = schema.get("items", {"type": "string"})
        return f"list[{_type_expression(item_schema, names)}]"
    if schema_type == "object" or "properties" in schema:
        additional = schema.get("additionalProperties")
        if isinstance(additional, dict):
            return f"dict[str, {_type_expression(additional, names)}]"
        return "dict[str, Any]"
    if schema_type is None:
        return "Any"
    raise ValueError(f"Unsupported OpenAPI type: {schema_type!r}")


def _is_real_regex(pattern: object) -> bool:
    """Отличить настоящий шаблон от человеческого описания формата.

    В спеке Ozon поля дат объявлены как `pattern: " YYYY-MM-DDThh:mm:ss.mcsZ"` —
    это подсказка человеку, а не регулярное выражение. Перенесённая в модель
    буквально, она делает поле непроходимым: ни одна настоящая дата ей не
    удовлетворяет, и модель не собирается ни на запросе, ни на разборе ответа.
    Признак такой подсказки — плейсхолдеры YYYY/MM-DD/hh:mm в тексте.
    """
    if not isinstance(pattern, str):
        return False
    if re.search(r"YYYY|MM-DD|hh:mm", pattern):
        return False
    try:
        re.compile(pattern)
    except re.error:
        return False
    return True


def _field_expression(
    openapi_name: str,
    schema: dict[str, Any],
    required: bool,
    names: dict[str, str],
) -> str:
    annotation = _type_expression(schema, names)
    if schema.get("nullable") is True:
        annotation = f"{annotation} | None"

    if required:
        default = "..."
    elif "default" in schema:
        default = repr(schema["default"])
    else:
        default = "_OPTIONAL_FIELD_DEFAULT"
    arguments: list[str] = [default]
    if _field_name(openapi_name) != openapi_name:
        arguments.append(f"alias={openapi_name!r}")
    if "description" in schema:
        arguments.append(f"description={schema['description']!r}")
    if "minimum" in schema:
        arguments.append(f"ge={schema['minimum']!r}")
    if "maximum" in schema:
        arguments.append(f"le={schema['maximum']!r}")
    if "minLength" in schema:
        arguments.append(f"min_length={schema['minLength']!r}")
    if "maxLength" in schema:
        arguments.append(f"max_length={schema['maxLength']!r}")
    if "maxItems" in schema:
        arguments.append(f"max_length={schema['maxItems']!r}")
    if "pattern" in schema and _is_real_regex(schema["pattern"]):
        arguments.append(f"pattern={schema['pattern']!r}")
    if "format" in schema:
        arguments.append(f"json_schema_extra={{'format': {schema['format']!r}}}")
    return f"{_field_name(openapi_name)}: {annotation} = Field({', '.join(arguments)})"


def _enum_member_name(value: Any, index: int, used: set[str]) -> str:
    candidate = re.sub(r"\W", "_", str(value)).upper().strip("_") or "EMPTY"
    if candidate[0].isdigit() or keyword.iskeyword(candidate.lower()):
        candidate = f"VALUE_{candidate}"
    base = candidate
    while candidate in used:
        candidate = f"{base}_{index}"
        index += 1
    used.add(candidate)
    return candidate


def generate() -> str:
    document = json.loads(OPENAPI_PATH.read_text(encoding="utf-8"))
    schemas: dict[str, dict[str, Any]] = document["components"]["schemas"]
    names = {schema_name: _class_name(schema_name) for schema_name in schemas}
    if len(set(names.values())) != len(names):
        raise ValueError("OpenAPI schema names do not map to unique Python names")

    lines = [
        '"""Generated Pydantic v2 models for Ozon Seller API 2.1 FBS operations.',
        "",
        "Source of truth: tasks/ozon-integration-20260825/OZON_FBS_OPENAPI.json.",
        "Run scripts/generate_ozon_fbs_models.py to regenerate this file.",
        '"""',
        "# ruff: noqa: E501, RUF001",
        "",
        "from __future__ import annotations",
        "",
        "from enum import Enum, StrEnum",
        "from typing import Any, cast",
        "",
        "from pydantic import BaseModel, ConfigDict, Field",
        "",
        "_OPTIONAL_FIELD_DEFAULT = cast(Any, None)",
        "",
        "",
        "class OzonFbsModel(BaseModel):",
        '    """Base model preserving OpenAPI\'s default additional-properties behaviour."""',
        "",
        '    model_config = ConfigDict(populate_by_name=True, extra="allow")',
        "",
        "",
    ]

    for schema_name, schema in schemas.items():
        class_name = names[schema_name]
        description = schema.get("description")
        if "enum" in schema:
            lines.append(f"class {class_name}(StrEnum):")
            if description:
                lines.append(f"    {description!r}")
            used: set[str] = set()
            for index, value in enumerate(schema["enum"]):
                member = _enum_member_name(value, index, used)
                lines.append(f"    {member} = {value!r}")
            lines.extend(["", ""])
            continue

        lines.append(f"class {class_name}(OzonFbsModel):")
        lines.append(f"    __openapi_name__ = {schema_name!r}")
        if description:
            lines.append(f"    {description!r}")
        additional = schema.get("additionalProperties")
        if additional is False:
            lines.append('    model_config = ConfigDict(populate_by_name=True, extra="forbid")')
        elif isinstance(additional, dict):
            extra_type = _type_expression(additional, names)
            lines.append(f"    __pydantic_extra__: dict[str, {extra_type}] = Field(init=False)")

        required = set(schema.get("required", []))
        properties: dict[str, dict[str, Any]] = schema.get("properties", {})
        if not properties:
            lines.append("    pass")
        else:
            for property_name, property_schema in properties.items():
                lines.append(
                    "    "
                    + _field_expression(
                        property_name,
                        property_schema,
                        property_name in required,
                        names,
                    )
                )
        lines.extend(["", ""])

    lines.append("MODEL_BY_OPENAPI_NAME: dict[str, type[BaseModel] | type[Enum]] = {")
    for schema_name, class_name in names.items():
        lines.append(f"    {schema_name!r}: {class_name},")
    lines.extend(["}", ""])
    lines.append("for _ozon_model in MODEL_BY_OPENAPI_NAME.values():")
    lines.append("    if isinstance(_ozon_model, type) and issubclass(_ozon_model, BaseModel):")
    lines.append("        _ozon_model.model_rebuild(_types_namespace=globals())")
    lines.append("")
    lines.append("__all__ = [*MODEL_BY_OPENAPI_NAME, 'MODEL_BY_OPENAPI_NAME', 'OzonFbsModel']")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    OUTPUT_PATH.write_text(generate(), encoding="utf-8")


if __name__ == "__main__":
    main()
