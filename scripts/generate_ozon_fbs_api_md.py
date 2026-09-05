#!/usr/bin/env python3
"""Generate the checked-in Ozon FBS API reference from the official OpenAPI JSON.

The generator intentionally does not contain an API model of its own: every field,
type, enum, description and response is read from OZON_FBS_OPENAPI.json.  This keeps
the Markdown reviewable and makes a stale hand-edited reference fail ``--check``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "tasks/ozon-integration-20260825/OZON_FBS_OPENAPI.json"
DEFAULT_OUTPUT = ROOT / "tasks/ozon-integration-20260825/OZON_FBS_API.md"
SOURCE_URL = "https://docs.ozon.ru/api/seller/swagger.json"
SNAPSHOT_DATE = "25.08.2026"
HTTP_METHODS = {"get", "post", "put", "patch", "delete", "head", "options", "trace"}


def markdown(value: Any) -> str:
    """Keep OpenAPI text literal while making it safe in a Markdown table cell."""
    if value is None:
        return ""
    return str(value).replace("\\", "\\\\").replace("|", "\\|").replace("\n", "<br>")


def code(value: Any) -> str:
    return f"`{markdown(value)}`"


def anchor(name: str) -> str:
    # GitHub's generated anchor is deterministic for the ASCII schema headings here.
    return "schema-" + re.sub(r"[^a-z0-9-]+", "-", name.lower()).strip("-")


def ref_name(ref: str) -> str:
    prefix = "#/components/schemas/"
    if ref.startswith(prefix):
        return ref[len(prefix) :]
    return ref


def ref_link(ref: str) -> str:
    name = ref_name(ref)
    if ref.startswith("#/components/schemas/"):
        return f"[{code(name)}](#{anchor(name)})"
    return code(ref)


def bool_text(value: Any) -> str:
    if value is None:
        return "не указано"
    return "да" if value else "нет"


def json_value(value: Any) -> str:
    return code(json.dumps(value, ensure_ascii=False, separators=(",", ":")))


def constraint_text(schema: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in ("format", "pattern", "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum",
                "multipleOf", "minLength", "maxLength", "minItems", "maxItems", "uniqueItems",
                "minProperties", "maxProperties", "default", "example", "readOnly", "writeOnly",
                "deprecated"):
        if key in schema:
            parts.append(f"{key}={json_value(schema[key])}")
    if "enum" in schema:
        parts.append("enum=" + ", ".join(json_value(item) for item in schema["enum"]))
    if "const" in schema:
        parts.append("const=" + json_value(schema["const"]))
    if "additionalProperties" in schema:
        additional = schema["additionalProperties"]
        if isinstance(additional, dict):
            parts.append("additionalProperties=" + schema_type(additional))
        else:
            parts.append("additionalProperties=" + bool_text(additional))
    return "; ".join(parts) or "—"


def schema_type(schema: dict[str, Any]) -> str:
    if "$ref" in schema:
        result = ref_link(schema["$ref"])
    elif "type" in schema:
        kind = schema["type"]
        if kind == "array":
            items = schema.get("items", {})
            result = f"array&lt;{schema_type(items) if isinstance(items, dict) else 'unspecified'}&gt;"
        else:
            result = code(kind)
    elif "oneOf" in schema:
        result = "oneOf(" + ", ".join(schema_type(item) for item in schema["oneOf"]) + ")"
    elif "anyOf" in schema:
        result = "anyOf(" + ", ".join(schema_type(item) for item in schema["anyOf"]) + ")"
    elif "allOf" in schema:
        result = "allOf(" + ", ".join(schema_type(item) for item in schema["allOf"]) + ")"
    elif "not" in schema:
        result = "not(" + schema_type(schema["not"]) + ")"
    else:
        result = "unspecified"
    if schema.get("nullable") is True:
        result += "; nullable"
    return result


def composition(schema: dict[str, Any]) -> list[str]:
    parts: list[str] = []
    for key in ("allOf", "oneOf", "anyOf"):
        if key in schema:
            parts.append(f"{key}: " + ", ".join(schema_type(item) for item in schema[key]))
    if "not" in schema:
        parts.append("not: " + schema_type(schema["not"]))
    return parts


def dereference_parameter(document: dict[str, Any], parameter: dict[str, Any]) -> dict[str, Any]:
    if "$ref" not in parameter:
        return parameter
    prefix = "#/components/parameters/"
    ref = parameter["$ref"]
    if not ref.startswith(prefix):
        return parameter
    parameters = document.get("components", {}).get("parameters", {})
    name = ref[len(prefix) :]
    if name not in parameters:
        # The supplied official JSON has header references but no
        # components.parameters section. Preserve that fact rather than inventing
        # a type or requiredness for the credentials.
        return {
            "in": "header",
            "name": name,
            "required": None,
            "schema": {},
            "description": f"Исходная ссылка {ref} не разрешается: components.parameters отсутствует в снимке.",
        }
    result = dict(parameters[name])
    result["$source_ref"] = ref
    return result


def media_schema_lines(content: dict[str, Any] | None) -> list[str]:
    if not content:
        return ["без тела"]
    lines: list[str] = []
    for media_type in sorted(content):
        media = content[media_type]
        schema = media.get("schema")
        line = f"{code(media_type)}: {schema_type(schema) if isinstance(schema, dict) else 'schema не задана'}"
        if media.get("description"):
            line += f" — {markdown(media['description'])}"
        lines.append(line)
    return lines


def render_operation(document: dict[str, Any], path: str, method: str, operation: dict[str, Any]) -> list[str]:
    operation_id = operation.get("operationId", "(не задан)")
    lines = [f"### {operation_id}", "", f"- HTTP: `{method.upper()} {path}`", f"- operationId: {code(operation_id)}"]
    if operation.get("summary"):
        lines.append(f"- Summary: {markdown(operation['summary'])}")
    if operation.get("description"):
        lines.append(f"- Description: {markdown(operation['description'])}")
    if operation.get("tags"):
        lines.append("- Tags: " + ", ".join(code(tag) for tag in operation["tags"]))
    lines.extend(["", "#### Параметры", "", "| Где | Имя | Обязательный | Тип | Nullable | Описание |", "| --- | --- | --- | --- | --- | --- |"])
    params = [dereference_parameter(document, parameter) for parameter in operation.get("parameters", [])]
    if params:
        for parameter in params:
            schema = parameter.get("schema", {})
            lines.append(
                "| " + " | ".join(
                    [
                        markdown(parameter.get("in", "")),
                        code(parameter.get("name", "")),
                        bool_text(parameter.get("required", False)),
                        schema_type(schema) if isinstance(schema, dict) else "unspecified",
                        bool_text(isinstance(schema, dict) and schema.get("nullable") is True),
                        markdown(parameter.get("description", "—")),
                    ]
                ) + " |"
            )
    else:
        lines.append("| — | — | — | — | — | — |")
    request = operation.get("requestBody")
    lines.extend(["", "#### Request body", ""])
    if request:
        lines.append(f"Обязательный: **{bool_text(request.get('required', False))}**.")
        if request.get("description"):
            lines.append(markdown(request["description"]))
        for item in media_schema_lines(request.get("content")):
            lines.append(f"- {item}")
    else:
        lines.append("Тело запроса отсутствует.")
    lines.extend(["", "#### Responses", "", "| Status | Описание | Content / schema |", "| --- | --- | --- |"])
    for status, response in operation.get("responses", {}).items():
        if "$ref" in response:
            response = {"description": response["$ref"]}
        body = "<br>".join(media_schema_lines(response.get("content")))
        lines.append(f"| {code(status)} | {markdown(response.get('description', '—'))} | {body} |")
    lines.append("")
    return lines


def render_schema(name: str, schema: dict[str, Any]) -> list[str]:
    lines = [f"### {name}", "", f"<a id=\"{anchor(name)}\"></a>"]
    if schema.get("description"):
        lines.extend(["", markdown(schema["description"])])
    lines.extend(["", f"- Тип: {schema_type(schema)}", f"- Nullable: **{bool_text(schema.get('nullable') is True)}**", f"- Ограничения: {constraint_text(schema)}"])
    composed = composition(schema)
    if composed:
        lines.append("- Композиция: " + "; ".join(composed))
    properties = schema.get("properties", {})
    lines.extend(["", "#### Поля", "", "| Поле | Required | Тип / вложенная ссылка | Nullable | Ограничения и enum | Description |", "| --- | --- | --- | --- | --- | --- |"])
    if properties:
        required = set(schema.get("required", []))
        for property_name, property_schema in properties.items():
            lines.append(
                "| " + " | ".join(
                    [
                        code(property_name),
                        bool_text(property_name in required),
                        schema_type(property_schema),
                        bool_text(property_schema.get("nullable") is True),
                        constraint_text(property_schema),
                        markdown(property_schema.get("description", "—")),
                    ]
                ) + " |"
            )
    else:
        lines.append("| — | — | — | — | — | — |")
    lines.append("")
    return lines


def reachable_schemas(document: dict[str, Any]) -> set[str]:
    """Return local schemas referenced by operations and recursively by schemas."""
    schemas = document["components"]["schemas"]
    found: set[str] = set()

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            ref = value.get("$ref")
            if isinstance(ref, str) and ref.startswith("#/components/schemas/"):
                name = ref_name(ref)
                if name not in found:
                    found.add(name)
                    visit(schemas[name])
            for key, nested in value.items():
                if key != "$ref":
                    visit(nested)
        elif isinstance(value, list):
            for nested in value:
                visit(nested)

    for item in document["paths"].values():
        for method, operation in item.items():
            if method.lower() in HTTP_METHODS:
                visit(operation)
    return found


def validate(document: dict[str, Any]) -> None:
    if document.get("openapi") != "3.0.0":
        raise ValueError("expected OpenAPI 3.0.0")
    info = document.get("info", {})
    if info.get("title") != "Документация Ozon Seller API" or str(info.get("version")) != "2.1":
        raise ValueError("unexpected Ozon Seller API title or version")
    operations = [
        operation
        for item in document.get("paths", {}).values()
        for method, operation in item.items()
        if method.lower() in HTTP_METHODS
    ]
    schemas = document.get("components", {}).get("schemas", {})
    # Сторож против незаметного дрейфа утверждённого документа. Числа выросли
    # 03.09.2026, когда в документ добавили отмену отправления: `/v2/posting/fbs/cancel`
    # и `/v1/posting/fbs/cancel-reason` с их схемами. Оба скопированы дословно из
    # официальной спецификации Ozon (docs.ozon.ru/api/seller/swagger.json).
    if len(operations) != 26:
        raise ValueError(f"expected 26 operations, got {len(operations)}")
    if len(schemas) != 165:
        raise ValueError(f"expected 165 component schemas, got {len(schemas)}")
    unreferenced = set(schemas) - reachable_schemas(document)
    if unreferenced:
        raise ValueError("schemas are not transitively reachable: " + ", ".join(sorted(unreferenced)))


def render(document: dict[str, Any], input_bytes: bytes) -> str:
    operations: list[tuple[str, str, dict[str, Any]]] = []
    for path, item in document["paths"].items():
        for method, operation in item.items():
            if method.lower() in HTTP_METHODS:
                operations.append((path, method, operation))
    operations.sort(key=lambda item: (item[0], item[1]))
    schemas = document["components"]["schemas"]
    checksum = hashlib.sha256(input_bytes).hexdigest()
    unresolved_header_operations = [
        operation.get("operationId", "(не задан)")
        for _, _, operation in operations
        if not operation.get("parameters")
    ]
    lines = [
        "# Ozon FBS API — точная выписка OpenAPI",
        "",
        f"Источник: [{SOURCE_URL}]({SOURCE_URL}) (локальный снимок `OZON_FBS_OPENAPI.json`).",
        f"Дата снимка: **{SNAPSHOT_DATE}**.",
        f"OpenAPI: `{document['openapi']}`; title: {code(document['info']['title'])}; version: `{document['info']['version']}`.",
        f"SHA-256 входного JSON: `{checksum}`.",
        "",
        "Этот файл генерируется командой `python3 scripts/generate_ozon_fbs_api_md.py`. "
        "Проверка соответствия JSON: `python3 scripts/generate_ozon_fbs_api_md.py --check`.",
        "",
        "## Состав",
        "",
        f"- Методов: **{len(operations)}**.",
        f"- Транзитивно достижимых схем: **{len(reachable_schemas(document))}** из **{len(schemas)}** компонентов.",
        "- В снимке `Client-Id` и `Api-Key` перечислены ссылками в параметрах 21 метода. "
        "Их определения (`components.parameters`) в самом JSON отсутствуют, поэтому тип и requiredness не добавлены от себя.",
        "- В трёх методах параметры вовсе не перечислены в источнике: "
        + ", ".join(code(operation_id) for operation_id in unresolved_header_operations) + ".",
        "- `Required: нет` означает необязательное поле. `Nullable: нет` означает, что `nullable: true` в исходной схеме отсутствует.",
        "",
        "## Методы",
        "",
    ]
    for path, method, operation in operations:
        lines.extend(render_operation(document, path, method, operation))
    lines.extend(["## Справочник схем", ""])
    for name in sorted(schemas):
        lines.extend(render_schema(name, schemas[name]))
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true", help="fail if the checked-in Markdown differs")
    args = parser.parse_args()
    input_bytes = args.input.read_bytes()
    document = json.loads(input_bytes)
    validate(document)
    rendered = render(document, input_bytes)
    if args.check:
        if not args.output.exists() or args.output.read_text() != rendered:
            print(f"{args.output} is stale; run {Path(__file__).name}", file=sys.stderr)
            return 1
        print(f"OK: {args.output} matches {args.input} (26 operations, 165 schemas)")
        return 0
    args.output.write_text(rendered)
    print(f"wrote {args.output} (26 operations, 165 schemas)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
