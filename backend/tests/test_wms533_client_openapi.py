"""The client Swagger exposes only the three existing integration methods."""

from __future__ import annotations

from urllib.parse import urljoin

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.client_openapi import _references
from app.main import create_app


@pytest.mark.asyncio
@pytest.mark.parametrize("prefix", ["", "/api"])
async def test_client_swagger_routes_and_schema(prefix: str) -> None:
    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app, root_path=prefix),
        base_url="https://wms.example",
    ) as client:
        docs_url = f"{prefix}/docs/client"
        docs = await client.get(docs_url)
        assert docs.status_code == 200
        assert "../openapi-client.json" in docs.text
        schema_url = urljoin(str(docs.url), "../openapi-client.json")
        assert schema_url.endswith(f"{prefix}/openapi-client.json")
        response = await client.get(schema_url)
        assert response.status_code == 200
        schema = response.json()
        assert schema["servers"] == [{"url": "."}]
        assert set(schema["paths"]) == {
            "/auth/login",
            "/reports/client-movements",
            "/reports/client-movements/export.xlsx",
        }
        assert {path: set(methods) for path, methods in schema["paths"].items()} == {
            "/auth/login": {"post"},
            "/reports/client-movements": {"get"},
            "/reports/client-movements/export.xlsx": {"get"},
        }
        login = schema["paths"]["/auth/login"]["post"]
        assert login["requestBody"]["content"]["application/json"]["schema"] == {
            "$ref": "#/components/schemas/LoginBody"
        }
        portal = schema["components"]["schemas"]["LoginBody"]["properties"]["portal"]
        assert "seller" in str(portal) and "fulfillment" in str(portal)
        rows = schema["paths"]["/reports/client-movements"]["get"]
        assert {item["name"] for item in rows["parameters"]} >= {
            "date_from",
            "date_to",
            "sku",
            "barcode",
            "warehouse_id",
            "marketplace",
            "operation",
            "cursor",
            "limit",
        }
        assert rows["security"] == [{"HTTPBearer": []}]
        properties = rows["responses"]["200"]["content"]["application/json"]["schema"]["properties"]
        assert {"rows", "next_cursor", "limit"} <= set(properties)
        assert "kiz" in properties["rows"]["items"]["properties"]
        export = schema["paths"]["/reports/client-movements/export.xlsx"]["get"]
        assert export["security"] == [{"HTTPBearer": []}]
        assert (
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            in export["responses"]["200"]["content"]
        )
        assert schema["components"]["securitySchemes"]["HTTPBearer"]["scheme"] == "bearer"
        refs = _references(schema["paths"]) | _references(schema["components"])
        assert all(
            ref.startswith("#/components/")
            and ref.split("/")[2] in schema["components"]
            and ref.split("/")[3] in schema["components"][ref.split("/")[2]]
            for ref in refs
        )
        assert len(schema["components"]["schemas"]) < 10
        common = await client.get(f"{prefix}/openapi.json")
        assert common.status_code == 200
        assert len(common.json()["paths"]) > len(schema["paths"])
