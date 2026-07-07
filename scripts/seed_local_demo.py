#!/usr/bin/env python3
"""Seed local dev DB with demo FF data for manual CZ / packaging testing."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import httpx

API = "http://127.0.0.1:18080"
ADMIN_EMAIL = "demo.ff@example.com"
ADMIN_PASSWORD = "DemoWms2026!"
SELLER_EMAIL = "seller.demo@example.com"
SELLER_PASSWORD = "DemoWms2026!"
ORG_NAME = "Демо ФФ (локально)"
SLUG = "demo-ff-local"

ROOT = Path(__file__).resolve().parents[1]
LEGgings_PDF = ROOT / "output/pdf/cz-leggings-preview/compare-seller-vs-generated.pdf"


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def poll_job(client: httpx.Client, token: str, job_id: str) -> None:
    for _ in range(60):
        res = client.get(f"/operations/background-jobs/{job_id}", headers=auth_headers(token))
        res.raise_for_status()
        status = res.json().get("status")
        if status == "done":
            return
        if status == "failed":
            raise RuntimeError(f"background job failed: {res.json()}")
        time.sleep(0.4)
    raise TimeoutError(f"background job {job_id} timed out")


def register_or_login(client: httpx.Client) -> str:
    reg = client.post(
        "/auth/register",
        json={
            "organization_name": ORG_NAME,
            "slug": SLUG,
            "admin_email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD,
        },
    )
    if reg.status_code == 200:
        return str(reg.json()["access_token"])
    if reg.status_code != 409:
        reg.raise_for_status()
    login = client.post(
        "/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    login.raise_for_status()
    return str(login.json()["access_token"])


def begin_inbound_receiving(client: httpx.Client, token: str, inbound_id: str) -> None:
    base = f"/operations/inbound-intake-requests/{inbound_id}"
    body = client.get(base, headers=auth_headers(token)).json()
    if body.get("status") != "submitted":
        return
    line_id = body["lines"][0]["id"]
    client.patch(
        f"{base}/lines/{line_id}/actual",
        headers=auth_headers(token),
        json={"actual_qty": 0},
    ).raise_for_status()


def create_box_and_scan(
    client: httpx.Client,
    token: str,
    inbound_id: str,
    barcode: str,
    qty: int,
) -> None:
    base = f"/operations/inbound-intake-requests/{inbound_id}"
    box = client.post(f"{base}/boxes", headers=auth_headers(token))
    box.raise_for_status()
    box_id = box.json()["id"]
    for _ in range(qty):
        client.post(
            f"{base}/boxes/{box_id}/scan",
            headers=auth_headers(token),
            json={"barcode": barcode},
        ).raise_for_status()
    client.post(f"{base}/boxes/{box_id}/close", headers=auth_headers(token)).raise_for_status()


def post_inbound_lines(
    client: httpx.Client,
    token: str,
    inbound_id: str,
    scans: list[tuple[str, int]],
) -> None:
    base = f"/operations/inbound-intake-requests/{inbound_id}"
    begin_inbound_receiving(client, token, inbound_id)
    for barcode, qty in scans:
        if qty > 0:
            create_box_and_scan(client, token, inbound_id, barcode, qty)
    client.post(f"{base}/verify", headers=auth_headers(token)).raise_for_status()
    client.post(f"{base}/post", headers=auth_headers(token)).raise_for_status()


def main() -> int:
    client = httpx.Client(base_url=API, timeout=120.0)
    token = register_or_login(client)
    h = auth_headers(token)

    client.patch(
        "/tenant/settings",
        headers=h,
        json={"separate_marking_print_enabled": True},
    ).raise_for_status()

    wh = client.post("/warehouses", headers=h, json={"name": "Склад демо", "code": "wh-demo"}).json()
    wh_id = wh["id"]
    loc = client.post(
        f"/warehouses/{wh_id}/locations",
        headers=h,
        json={"code": "A-01"},
    ).json()
    loc_id = loc["id"]

    seller = client.post(
        "/sellers",
        headers=h,
        json={"name": "Бренд Леггинсы", "email": "brand@example.com"},
    ).json()
    seller_id = seller["id"]

    client.patch(
        f"/integrations/wildberries/sellers/{seller_id}/tokens",
        headers=h,
        json={"content_api_token": "demo-content", "supplies_api_token": "demo-supplies"},
    ).raise_for_status()

    job = client.post(
        "/operations/background-jobs",
        headers=h,
        json={"job_type": "wildberries_cards_sync", "seller_id": seller_id},
    ).json()
    poll_job(client, token, job["id"])

    client.post(
        "/auth/seller-accounts",
        headers=h,
        json={"seller_id": seller_id, "email": SELLER_EMAIL, "password": SELLER_PASSWORD},
    ).raise_for_status()

    sku_cz = "LEG-DEMO-CZ"
    sku_plain = "TSH-DEMO-NO-CZ"
    scan_barcode = "E2E-MOCK-BARCODE"

    prod_cz = client.post(
        "/products",
        headers=h,
        json={
            "name": "Спортивные леггинсы (ЧЗ)",
            "sku_code": sku_cz,
            "length_mm": 200,
            "width_mm": 150,
            "height_mm": 30,
            "seller_id": seller_id,
        },
    ).json()
    prod_cz_id = prod_cz["id"]

    prod_plain = client.post(
        "/products",
        headers=h,
        json={
            "name": "Футболка без ЧЗ",
            "sku_code": sku_plain,
            "length_mm": 250,
            "width_mm": 200,
            "height_mm": 20,
            "seller_id": seller_id,
        },
    ).json()
    prod_plain_id = prod_plain["id"]

    for product_id in (prod_cz_id, prod_plain_id):
        link = client.post(
            f"/integrations/wildberries/sellers/{seller_id}/link-product",
            headers=h,
            json={"product_id": product_id, "nm_id": 424242},
        )
        if link.status_code == 409 and product_id != prod_cz_id:
            continue
        link.raise_for_status()

    client.patch(
        f"/products/{prod_cz_id}/packaging-instructions",
        headers=h,
        json={
            "requires_honest_sign": True,
            "packaging_instructions": "2 ЧЗ на единицу + ШК ВБ. Печать из вкладки Упаковка.",
        },
    ).raise_for_status()

    client.patch(
        f"/products/{prod_plain_id}/packaging-instructions",
        headers=h,
        json={
            "requires_honest_sign": False,
            "packaging_instructions": "Только ШК ВБ.",
        },
    ).raise_for_status()

    # ЧЗ: PDF с клиентскими этикетками (если файл есть), иначе CSV fallback.
    pdf_path = LEGgings_PDF
    if pdf_path.is_file():
        imp = client.post(
            "/operations/marking-codes/import",
            headers=h,
            files={
                "files": ("leggings-labels.pdf", pdf_path.read_bytes(), "application/pdf"),
            },
            data={
                "seller_id": seller_id,
                "pools_json": json.dumps(
                    [{"title": "Леггинсы PDF", "product_ids": [prod_cz_id]}],
                ),
            },
        )
        if not imp.is_success:
            print(f"WARN: PDF import failed ({imp.status_code}): {imp.text}", file=sys.stderr)
    else:
        print(f"WARN: PDF not found at {pdf_path}, importing CSV codes", file=sys.stderr)

    gtin = "02900446283341"
    cis_rows = [
        f"01{gtin}21{'M' * 19}{str(i).zfill(4)},{sku_cz}" for i in range(5)
    ]
    client.post(
        "/operations/marking-codes/import",
        headers=h,
        files={"files": ("codes.csv", "\n".join(["cis,sku_code", *cis_rows]), "text/csv")},
        data={
            "seller_id": seller_id,
            "pools_json": json.dumps(
                [{"title": "Леггинсы CSV", "product_ids": [prod_cz_id]}],
            ),
        },
    ).raise_for_status()

    plan_qty_cz = 3
    plan_qty_plain = 2

    # Приёмка 1 — уже проведена (остаток на складе).
    in1 = client.post(
        "/operations/inbound-intake-requests",
        headers=h,
        json={"warehouse_id": wh_id},
    ).json()
    in1_id = in1["id"]
    client.post(
        f"/operations/inbound-intake-requests/{in1_id}/lines",
        headers=h,
        json={
            "product_id": prod_cz_id,
            "expected_qty": plan_qty_cz,
            "storage_location_id": loc_id,
        },
    ).raise_for_status()
    client.post(
        f"/operations/inbound-intake-requests/{in1_id}/lines",
        headers=h,
        json={
            "product_id": prod_plain_id,
            "expected_qty": plan_qty_plain,
            "storage_location_id": loc_id,
        },
    ).raise_for_status()
    client.post(f"/operations/inbound-intake-requests/{in1_id}/submit", headers=h).raise_for_status()
    post_inbound_lines(
        client,
        token,
        in1_id,
        [(scan_barcode, plan_qty_cz), (sku_plain, plan_qty_plain)],
    )

    # Приёмка 2 — в очереди (submitted), для теста экрана приёмки.
    in2 = client.post(
        "/operations/inbound-intake-requests",
        headers=h,
        json={"warehouse_id": wh_id},
    ).json()
    in2_id = in2["id"]
    client.post(
        f"/operations/inbound-intake-requests/{in2_id}/lines",
        headers=h,
        json={
            "product_id": prod_cz_id,
            "expected_qty": 2,
            "storage_location_id": loc_id,
        },
    ).raise_for_status()
    client.post(f"/operations/inbound-intake-requests/{in2_id}/submit", headers=h).raise_for_status()

    wb_whs = client.get("/operations/wb-mp-warehouses", headers=h).json()
    wb_wid = int(wb_whs[0]["wb_warehouse_id"])

    mu = client.post(
        "/operations/marketplace-unload-requests",
        headers=h,
        json={
            "warehouse_id": wh_id,
            "seller_id": seller_id,
            "wb_mp_warehouse_id": wb_wid,
        },
    ).json()
    mu_id = mu["id"]
    client.post(
        f"/operations/marketplace-unload-requests/{mu_id}/lines",
        headers=h,
        json={"product_id": prod_cz_id, "quantity": plan_qty_cz},
    ).raise_for_status()
    client.post(
        f"/operations/marketplace-unload-requests/{mu_id}/lines",
        headers=h,
        json={"product_id": prod_plain_id, "quantity": 1},
    ).raise_for_status()
    client.post(
        f"/operations/marketplace-unload-requests/{mu_id}/confirm",
        headers=h,
        json={"planned_shipment_date": "2026-07-15"},
    ).raise_for_status()

    codes = client.get(
        f"/operations/marking-codes/products/{prod_cz_id}/codes",
        headers=h,
    ).json()
    artifact_count = sum(1 for row in codes if row.get("has_label_artifact"))

    print("=== Локальный демо-сид готов ===")
    print(f"Фронт: http://127.0.0.1:5173/")
    print(f"API:   {API}")
    print()
    print("FF портал (админ):")
    print(f"  Email:    {ADMIN_EMAIL}")
    print(f"  Пароль:   {ADMIN_PASSWORD}")
    print()
    print("Кабинет селлера:")
    print(f"  URL:      http://127.0.0.1:5173/seller/")
    print(f"  Email:    {SELLER_EMAIL}")
    print(f"  Пароль:   {SELLER_PASSWORD}")
    print()
    print("Настройки:")
    print("  separate_marking_print_enabled = true")
    print()
    print("Данные:")
    print(f"  Склад: {wh['name']} ({wh_id})")
    print(f"  Селлер: Бренд Леггинсы ({seller_id})")
    print(f"  Товар с ЧЗ: {sku_cz} ({prod_cz_id}) — КМ в пуле: {len(codes)}, с artifact: {artifact_count}")
    print(f"  Товар без ЧЗ: {sku_plain} ({prod_plain_id})")
    print(f"  Приёмка проведена: {in1_id}")
    print(f"  Приёмка в очереди: {in2_id}")
    print(f"  Отгрузка МП (упаковка): {mu_id}")
    print()
    print("Куда идти:")
    print("  Отгрузки МП → открыть отгрузку → вкладка «Упаковка» → печать строки")
    print("  Честный знак → товар «Спортивные леггинсы» → список КМ")
    print("  Приёмка → вторая заявка в очереди")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
