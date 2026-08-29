"""FBSFLOW-130: FBS operator OpenAPI contract gate."""

from __future__ import annotations

import json
from pathlib import Path

from app.main import create_app

REPO_ROOT = Path(__file__).resolve().parents[2]
EXPORT_PATH = REPO_ROOT / "tasks" / "fbs-operator-flow" / "openapi" / "fbs-operations.openapi.json"

REQUIRED_FBS_PATHS = (
    "/operations/fbs-orders/worklist",
    "/operations/fbs-supplies/preflight",
    "/operations/fbs-supplies/from-orders",
    "/operations/fbs-supplies/{supply_id}/workspace",
    "/operations/fbs-supplies/{supply_id}/pick/set",
    "/operations/fbs-supplies/{supply_id}/pick/scan",
    "/operations/fbs-supplies/{supply_id}/pick/scan-location",
    "/operations/fbs-supplies/{supply_id}/pick/scan-product",
    "/operations/fbs-supplies/{supply_id}/print-assets",
    "/operations/fbs-print-assets/{asset_id}/content",
    "/operations/fbs-supplies/{supply_id}/cargo-places",
    "/operations/fbs-supplies/{supply_id}/delivery-preflight",
    "/operations/fbs-supplies/{supply_id}/deliver",
)

DEPRECATED_PATHS = (
    "/operations/fbs-supplies/{supply_id}/trbx/{trbx_id}/orders",
    "/operations/fbs-supplies/{supply_id}/stickers",
    "/operations/fbs-supplies/{supply_id}/trbx/stickers",
)

REMOVED_FBS_PATHS = (
    "/operations/fbs-orders/{order_id}/metadata/scan",
    "/operations/fbs-orders/{order_id}/markings/{kind}",
)


def test_fbs_openapi_generation_includes_contract_paths() -> None:
    schema = create_app().openapi()
    paths = schema["paths"]
    for path in REQUIRED_FBS_PATHS:
        assert path in paths, f"missing FBS contract path: {path}"


def test_removed_fbs_marking_paths_are_absent() -> None:
    paths = create_app().openapi()["paths"]
    for path in REMOVED_FBS_PATHS:
        assert path not in paths, f"removed FBS marking path is still exposed: {path}"


def test_deprecated_print_compatibility_marked_in_openapi() -> None:
    schema = create_app().openapi()
    bind = schema["paths"]["/operations/fbs-supplies/{supply_id}/trbx/{trbx_id}/orders"]["post"]
    stickers = schema["paths"]["/operations/fbs-supplies/{supply_id}/stickers"]["post"]
    trbx_stickers = schema["paths"]["/operations/fbs-supplies/{supply_id}/trbx/stickers"][
        "post"
    ]
    barcode = schema["paths"]["/operations/fbs-supplies/{supply_id}/barcode"]["get"]
    assert bind.get("deprecated") is True
    assert stickers.get("deprecated") is True
    assert trbx_stickers.get("deprecated") is True
    assert barcode.get("deprecated") is True


def test_exported_fbs_openapi_file_matches_live_schema() -> None:
    assert EXPORT_PATH.is_file(), "run backend/scripts/export_fbs_openapi.py first"
    exported = json.loads(EXPORT_PATH.read_text(encoding="utf-8"))
    live = create_app().openapi()
    live_paths = {
        path: ops
        for path, ops in live["paths"].items()
        if path.startswith("/operations/fbs-")
    }
    assert exported["paths"] == live_paths
    for path in DEPRECATED_PATHS:
        assert exported["paths"][path]["post"].get("deprecated") is True
    assert exported["paths"]["/operations/fbs-supplies/{supply_id}/barcode"]["get"].get(
        "deprecated"
    ) is True
