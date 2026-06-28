"""BACKEND-01 / T-A6: deprecated marking endpoints must stay visible in OpenAPI."""

from __future__ import annotations

from app.main import create_app

_DEPRECATED_POST_PATHS = (
    "/operations/marking-codes/scan-print",
    "/operations/marking-codes/verify-pair",
)


def test_deprecated_marking_endpoints_in_openapi() -> None:
    schema = create_app().openapi()
    paths = schema["paths"]

    for path in _DEPRECATED_POST_PATHS:
        post = paths[path]["post"]
        assert post.get("deprecated") is True, path
        assert "Deprecated" in post.get("summary", ""), path

    print_all = paths["/operations/marking-codes/packaging-tasks/{task_id}/print-all"]["post"]
    assert print_all.get("deprecated") is True
    assert "Deprecated" in print_all.get("summary", "")
