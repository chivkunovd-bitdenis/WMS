from __future__ import annotations

import json
from enum import Enum
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from typing import Any, cast, get_args

from pydantic import BaseModel

from app.schemas.ozon_fbs_api import MODEL_BY_OPENAPI_NAME

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
OPENAPI_PATH = REPOSITORY_ROOT / "tasks/ozon-integration-20260825/OZON_FBS_OPENAPI.json"
GENERATED_MODELS_PATH = REPOSITORY_ROOT / "backend/app/schemas/ozon_fbs_api.py"
GENERATOR_PATH = REPOSITORY_ROOT / "scripts/generate_ozon_fbs_models.py"


def _openapi_schemas() -> dict[str, dict[str, Any]]:
    document = json.loads(OPENAPI_PATH.read_text(encoding="utf-8"))
    return cast(dict[str, dict[str, Any]], document["components"]["schemas"])


def _generated_source() -> str:
    spec = spec_from_file_location("generate_ozon_fbs_models", GENERATOR_PATH)
    assert spec is not None
    assert spec.loader is not None
    generator = module_from_spec(spec)
    spec.loader.exec_module(generator)
    return cast(str, generator.generate())


def _annotation_contains(annotation: Any, expected: type[object]) -> bool:
    if annotation is expected:
        return True
    return any(_annotation_contains(argument, expected) for argument in get_args(annotation))


def _referenced_model(schema: dict[str, Any]) -> type[object] | None:
    reference = schema.get("$ref")
    if reference is None:
        return None
    schema_name = reference.removeprefix("#/components/schemas/")
    return MODEL_BY_OPENAPI_NAME[schema_name]


def _rendered_value(rendered: dict[str, Any], key: str) -> Any:
    if key in rendered:
        return rendered[key]
    for branch in rendered.get("anyOf", []):
        if key in branch:
            return branch[key]
    return None


def test_generated_module_is_current_with_checked_in_openapi() -> None:
    assert GENERATED_MODELS_PATH.read_text(encoding="utf-8") == _generated_source()


def test_all_openapi_components_have_exact_model_fields_and_requiredness() -> None:
    schemas = _openapi_schemas()
    assert set(MODEL_BY_OPENAPI_NAME) == set(schemas)

    for schema_name, openapi_schema in schemas.items():
        model = MODEL_BY_OPENAPI_NAME[schema_name]
        if "enum" in openapi_schema:
            assert isinstance(model, type)
            assert issubclass(model, Enum)
            assert {member.value for member in model} == set(openapi_schema["enum"])
            continue

        assert isinstance(model, type)
        assert issubclass(model, BaseModel)
        properties: dict[str, dict[str, Any]] = openapi_schema.get("properties", {})
        fields_by_alias = {
            field.alias or field_name: field for field_name, field in model.model_fields.items()
        }
        assert set(fields_by_alias) == set(properties), schema_name

        required = set(openapi_schema.get("required", []))
        actual_required = {alias for alias, field in fields_by_alias.items() if field.is_required()}
        assert actual_required == required

        expected_extra = (
            "forbid" if openapi_schema.get("additionalProperties") is False else "allow"
        )
        assert model.model_config.get("extra") == expected_extra

        rendered_properties = model.model_json_schema(by_alias=True).get("properties", {})
        for field_name, field_schema in properties.items():
            field = fields_by_alias[field_name]
            if field_name not in required:
                assert field.default == field_schema.get("default", None)

            rendered = rendered_properties[field_name]
            for source_key, rendered_key in (
                ("description", "description"),
                ("format", "format"),
                ("minimum", "minimum"),
                ("maximum", "maximum"),
                ("minLength", "minLength"),
                ("maxLength", "maxLength"),
                ("maxItems", "maxItems"),
                ("pattern", "pattern"),
            ):
                if source_key in field_schema:
                    assert _rendered_value(rendered, rendered_key) == field_schema[source_key]

            referenced = _referenced_model(field_schema)
            if referenced is None and "items" in field_schema:
                referenced = _referenced_model(field_schema["items"])
            if referenced is not None:
                assert _annotation_contains(field.annotation, referenced)
