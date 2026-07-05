"""BACKEND-01 / T-A6: deprecated marking endpoints must stay visible in OpenAPI."""

from __future__ import annotations

from app.main import create_app


def test_deprecated_marking_endpoints_in_openapi() -> None:
    schema = create_app().openapi()
    paths = schema["paths"]

    scan_print = paths["/operations/marking-codes/scan-print"]["post"]
    assert scan_print.get("deprecated") is True
    assert "Removed" in scan_print.get("summary", "")

    verify_pair = paths["/operations/marking-codes/verify-pair"]["post"]
    assert verify_pair.get("deprecated") is True
    assert "Deprecated" in verify_pair.get("summary", "")

    print_all = paths["/operations/marking-codes/packaging-tasks/{task_id}/print-all"]["post"]
    assert print_all.get("deprecated") is True
    assert "Removed" in print_all.get("summary", "")
