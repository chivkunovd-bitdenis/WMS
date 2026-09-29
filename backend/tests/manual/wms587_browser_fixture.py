"""Create disposable WMS-587 browser data through the local test API only.

Run with the local backend on 127.0.0.1:8187 and its isolated SQLite database.
"""

from __future__ import annotations

import io
import time
from pathlib import Path

import httpx
from openpyxl import Workbook

BASE_URL = "http://127.0.0.1:8187"
TEST_PASSWORD = "password123"
OUTPUT_DIR = Path(__file__).resolve().parent / "wms587_generated"
HEADERS = ("Товар", "Артикул", "ШК", "Размер", "Количество (штук)")


def _xlsx(rows: list[tuple[str | int, ...]]) -> bytes:
    book = Workbook()
    sheet = book.active
    assert sheet is not None
    sheet.append(HEADERS)
    for row in rows:
        sheet.append(row)
    output = io.BytesIO()
    book.save(output)
    return output.getvalue()


def _ok(response: httpx.Response) -> dict[str, object]:
    if response.is_error:
        raise RuntimeError(f"Local fixture API returned {response.status_code}: {response.text}")
    value = response.json()
    assert isinstance(value, dict)
    return value


def main() -> None:
    suffix = str(time.time_ns())
    with httpx.Client(base_url=BASE_URL, timeout=30) as client:
        account = _ok(
            client.post(
                "/auth/register",
                json={
                    "organization_name": "WMS 587 browser fixture",
                    "slug": f"w587-{suffix}",
                    "admin_email": f"wms587-admin-{suffix}@example.com",
                    "password": TEST_PASSWORD,
                },
            )
        )
        admin_headers = {"Authorization": f"Bearer {account['access_token']}"}
        warehouse = _ok(
            client.post(
                "/warehouses",
                headers=admin_headers,
                json={"name": "Тестовый склад WMS-587", "code": f"wms587-{suffix}"},
            )
        )
        seller = _ok(
            client.post(
                "/sellers",
                headers=admin_headers,
                json={"name": "Тестовый селлер WMS-587"},
            )
        )
        for article, barcode, size in (
            ("TEST-587-36", "00058736", "36"),
            ("TEST-587-38", "00058738", "38"),
        ):
            _ok(
                client.post(
                    "/products",
                    headers=admin_headers,
                    json={
                        "name": "Тестовый товар",
                        "sku_code": article,
                        "wb_barcode": barcode,
                        "wb_size": size,
                        "seller_id": seller["id"],
                        "length_mm": 1,
                        "width_mm": 1,
                        "height_mm": 1,
                    },
                )
            )
        email = f"wms587-seller-{suffix}@example.com"
        _ok(
            client.post(
                "/auth/seller-accounts",
                headers=admin_headers,
                json={"seller_id": seller["id"], "email": email, "password": TEST_PASSWORD},
            )
        )
        seller_login = _ok(
            client.post(
                "/auth/login",
                json={"email": email, "password": TEST_PASSWORD},
            )
        )
        seller_headers = {"Authorization": f"Bearer {seller_login['access_token']}"}
        request = _ok(
            client.post(
                "/operations/inbound-intake-requests",
                headers=seller_headers,
                json={"warehouse_id": warehouse["id"], "operation_type": "inbound"},
            )
        )

    OUTPUT_DIR.mkdir(exist_ok=True)
    valid_path = OUTPUT_DIR / "valid.xlsx"
    invalid_path = OUTPUT_DIR / "unknown-sku.xlsx"
    valid_path.write_bytes(
        _xlsx(
            [
                ("Тестовый товар", "TEST-587-36", "00058736", "36", 3),
                ("Тестовый товар", "TEST-587-38", "00058738", "38", 5),
            ]
        )
    )
    invalid_path.write_bytes(
        _xlsx(
            [
                ("Тестовый товар", "TEST-587-36", "00058736", "36", 8),
                ("Неизвестный товар", "MISSING-587", "00059999", "99", 1),
            ]
        )
    )
    print(f"UI: http://127.0.0.1:5187/seller/inbound/{request['id']}")
    print(f"Email: {email}")
    print(f"Password: {TEST_PASSWORD} (local disposable fixture only)")
    print(f"Valid XLSX: {valid_path}")
    print(f"Unknown SKU XLSX: {invalid_path}")
    print(f"Request ID: {request['id']}")


if __name__ == "__main__":
    main()
