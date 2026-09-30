"""Small public OpenAPI view of the existing client report routes."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

_PATHS = {
    "/auth/login": "post",
    "/reports/client-movements": "get",
    "/reports/client-movements/export.xlsx": "get",
}
_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _references(value: Any) -> set[str]:
    if isinstance(value, dict):
        found = {value["$ref"]} if isinstance(value.get("$ref"), str) else set()
        for child in value.values():
            found.update(_references(child))
        return found
    if isinstance(value, list):
        found = set()
        for child in value:
            found.update(_references(child))
        return found
    return set()


def _client_page_schema() -> dict[str, Any]:
    string = {"type": "string"}
    nullable_string = {"type": ["string", "null"]}
    row = {
        "type": "object",
        "required": [
            "id",
            "movement_id",
            "occurred_at",
            "operation",
            "warehouse_id",
            "product_id",
            "sku",
            "product_name",
            "shk",
            "size",
            "marketplace",
            "document",
            "quantity_delta",
            "kiz",
        ],
        "properties": {
            "id": string,
            "movement_id": {"type": "string", "format": "uuid"},
            "occurred_at": {"type": "string", "format": "date-time"},
            "operation": {
                "type": "string",
                "enum": [
                    "inbound_intake",
                    "return",
                    "fbs_shipment",
                    "marketplace_unload",
                    "inventory_count",
                ],
                "description": (
                    "Только приёмка, возврат, отгрузка FBS/FBO или инвентаризация. "
                    "Резервы и отмены FBS не включаются."
                ),
            },
            "warehouse_id": {"type": "string", "format": "uuid"},
            "product_id": {"type": "string", "format": "uuid"},
            "sku": string,
            "product_name": string,
            "shk": nullable_string,
            "size": nullable_string,
            "marketplace": {"type": ["string", "null"], "enum": ["wb", "ozon", None]},
            "document": {
                "anyOf": [
                    {
                        "type": "object",
                        "required": ["id", "type", "number"],
                        "properties": {
                            "id": string,
                            "type": string,
                            "number": string,
                            "status": {
                                "type": "string",
                                "description": (
                                    "Текущий статус связанной заявки FBO marketplace_unload."
                                ),
                            },
                            "shipped_at": {
                                "type": ["string", "null"],
                                "format": "date-time",
                                "description": (
                                    "Время завершённой отгрузки FBO; незавершённые заявки "
                                    "не попадают в отчёт."
                                ),
                            },
                        },
                    },
                    {"type": "null"},
                ],
            },
            "quantity_delta": {"type": "integer"},
            "kiz": nullable_string,
        },
    }
    return {
        "type": "object",
        "required": ["rows", "next_cursor", "limit"],
        "properties": {
            "rows": {"type": "array", "items": row},
            "next_cursor": nullable_string,
            "limit": {"type": "integer", "minimum": 1, "maximum": 1000},
        },
    }


def client_openapi(source: dict[str, Any]) -> dict[str, Any]:
    """Copy selected operations and only their transitively referenced components."""
    paths = {
        path: {method: deepcopy(source["paths"][path][method])} for path, method in _PATHS.items()
    }
    login = paths["/auth/login"]["post"]
    for path in ("/reports/client-movements", "/reports/client-movements/export.xlsx"):
        operation = paths[path]["get"]
        operation["parameters"] = [
            parameter for parameter in operation.get("parameters", [])
            if parameter["name"] != "warehouse_id"
        ]
    login["summary"] = "Вход и получение токена"
    login["description"] = (
        "Existing login for seller or fulfillment portal. Set body.portal to "
        "seller or fulfillment, then use access_token as HTTP Bearer."
    )
    login["requestBody"]["content"]["application/json"]["example"] = {
        "email": "seller@example.com",
        "password": "<password>",
        "portal": "seller",
    }
    movement = paths["/reports/client-movements"]["get"]
    movement["summary"] = "Отчёт движений JSON"
    movement["description"] = (
        "Оприходования и списания за период [date_from, date_to). Укажите sku или shk, но не оба: "
        "вместе они дают HTTP 422. Без них возвращается весь доступный отчёт за период. "
        "Пройдите страницы с next_cursor до null. FBS: одна штука в строке; "
        "operation в ответе — тип движения; подтверждённая возвратная приёмка имеет return. "
        "FBO включается только после завершения отгрузки; occurred_at равен "
        "document.shipped_at и используется для периода и курсора."
    )
    movement["responses"]["200"]["content"] = {
        "application/json": {
            "schema": _client_page_schema(),
            "example": {
                "rows": [
                    {
                        "id": "4cd4e360-4130-4141-b5e3-a3f50dbc1464:0",
                        "movement_id": "4cd4e360-4130-4141-b5e3-a3f50dbc1464",
                        "occurred_at": "2026-09-12T12:00:00+00:00",
                        "operation": "fbs_shipment",
                        "warehouse_id": "00000000-0000-0000-0000-000000000001",
                        "product_id": "00000000-0000-0000-0000-000000000002",
                        "sku": "0007",
                        "product_name": "Товар",
                        "shk": "0000123456789",
                        "size": "42",
                        "marketplace": "ozon",
                        "document": {
                            "id": "00000000-0000-0000-0000-000000000003",
                            "type": "fbs_order",
                            "number": "OZ-702",
                        },
                        "quantity_delta": -1,
                        "kiz": "0101234567890121\u001dSERIAL",
                    }
                ],
                "next_cursor": None,
                "limit": 200,
            },
        }
    }
    export = paths["/reports/client-movements/export.xlsx"]["get"]
    export["summary"] = "Отчёт движений Excel"
    export["description"] = (
        "Все подходящие строки на листах WB, Ozon и Общие. Укажите sku или shk, "
        "но не оба; без них выгружается весь доступный отчёт за период. "
        "В файле русские названия колонок и только оприходования и списания."
    )
    export["responses"]["200"]["content"] = {
        _XLSX: {"schema": {"type": "string", "format": "binary"}}
    }
    result: dict[str, Any] = {
        "openapi": source["openapi"],
        "info": {"title": "WMS Client Reports API", "version": "1.0.0"},
        # Relative to /openapi-client.json: same API origin directly and behind /api.
        "servers": [{"url": "."}],
        "paths": paths,
    }
    source_components = source.get("components", {})
    components: dict[str, dict[str, Any]] = {}
    pending = list(_references(paths))
    for methods in paths.values():
        for operation in methods.values():
            for requirement in operation.get("security", []):
                pending.extend(f"#/components/securitySchemes/{name}" for name in requirement)
    while pending:
        reference = pending.pop()
        parts = reference.split("/")
        if len(parts) != 4 or parts[:2] != ["#", "components"]:
            continue
        _, _, section, name = parts
        kept = components.setdefault(section, {})
        if name in kept:
            continue
        definition = deepcopy(source_components[section][name])
        kept[name] = definition
        pending.extend(_references(definition))
    login_body = components.get("schemas", {}).get("LoginBody")
    if login_body is not None:
        login_body["properties"]["portal"]["description"] = (
            "Choose seller for the seller cabinet or fulfillment for fulfillment staff."
        )
    result["components"] = components
    return result
