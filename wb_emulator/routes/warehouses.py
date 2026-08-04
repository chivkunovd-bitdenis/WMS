"""Seller warehouses and offices — shapes from wildberries_client mocks."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

router = APIRouter(tags=["warehouses"])

_DEFAULT_WAREHOUSES: list[dict[str, Any]] = [
    {
        "id": 501001,
        "name": "Emulator Seller Warehouse",
        "officeId": 601001,
        "address": "Emulator Seller WH Address",
        "cargoType": 1,
        "deliveryType": 1,
    },
]

_DEFAULT_OFFICES: list[dict[str, Any]] = [
    {
        "id": 601001,
        "officeId": 601001,
        "name": "Emulator Seller Office",
        "city": "Moscow",
        "address": "Emulator Office Address",
        "longitude": 37.62,
        "latitude": 55.75,
    },
    {
        "id": 601002,
        "officeId": 601002,
        "name": "Emulator PVZ North",
        "city": "Moscow",
        "address": "PVZ North Address",
        "longitude": 37.55,
        "latitude": 55.80,
    },
    {
        "id": 601003,
        "officeId": 601003,
        "name": "Emulator PVZ South",
        "city": "Moscow",
        "address": "PVZ South Address",
        "longitude": 37.70,
        "latitude": 55.70,
    },
]


@router.get("/warehouses")
def list_warehouses() -> list[dict[str, Any]]:
    """GET /api/v3/warehouses — raw list as client expects."""
    return list(_DEFAULT_WAREHOUSES)


@router.get("/offices")
def list_offices() -> list[dict[str, Any]]:
    """GET /api/v3/offices — raw list as client expects."""
    return list(_DEFAULT_OFFICES)
