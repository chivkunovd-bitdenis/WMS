#!/usr/bin/env python3
"""WMS-686: демо-данные для FBO-отгрузки с подбором из коробов приёмки INB.

Скрипт работает только через HTTP API (httpx), поэтому подходит и к локальному
стенду (SQLite + uvicorn), и к стенду staging с тем же кодом. Данные полностью
фиктивные: токен WB — заглушка, настоящих ключей нет.

Что создаётся (одна новая организация ФФ на запуск):
- склад с адресным хранением, ячейки «А-1-1» и «А-1-2» (кириллическая «А»);
- селлер WB (фиктивный токен «Поставки» — нужен только, чтобы открылся
  справочник складов WB);
- товары: «Футболка 48» (ЧЗ, ШК 4600000000017), «Футболка 50» (ЧЗ, 4600000000024),
  «Носки» (без ЧЗ, 4600000000031);
- пул КИЗ через обычный импорт кодов: 20 для «Футболки 48», 4 для «Футболки 50»;
- одна приёмка на три короба INB: короб 1 — 6 «Футболка 48» + 2 «Носки»,
  короб 2 — 5 «Футболка 48», короб 3 — 8 «Футболка 50». Приёмка проведена до
  статуса «сортировка», затем короба 1 и 2 целиком поставлены в «А-1-1»;
  «Футболки 50» лежат в «А-1-2» россыпью (по умолчанию) или коробом INB
  (флаг --tee50-in-box);
- утверждённая отгрузка FBO на WB с планом: Футболка 48 — 6, Футболка 50 — 4,
  Носки — 2.

Скрипт ничего не списывает и не подбирает: отгрузка остаётся в состоянии
«до подбора». КИЗ нигде не привязаны к единицам (так и должно быть в исходном
состоянии: привязка происходит при подборе/упаковке).

Запуск на локальном стенде (регистрация нового ФФ разрешена только на localhost):
    python scripts/demo/wms686_demo_seed.py --base-url http://127.0.0.1:18086 \\
        --out-dir /path/to/stand

Запуск на любом другом адресе: нужен готовый токен администратора ФФ
(--token), регистрация там не выполняется. Организация уже есть, поэтому
повторный запуск упрётся в занятые коды — берите свободный --suffix.

Склад WB берётся из справочника /operations/wb-mp-warehouses. Без мока WB этот
справочник ходит во внешний API; тогда укажите --wb-warehouse-id вручную.

Пример для проверки после запуска (id печатается в конце):
    GET /operations/marketplace-unload-requests/<id>/pick-options
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import date, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

# Тестовые данные ЛОКАЛЬНОГО стенда (не боевые). Используются только для
# регистрации/входа на localhost; для остальных адресов нужен --token.
LOCAL_ADMIN_EMAIL = "wms686.demo@example.com"  # с --suffix: wms686.demo-<суффикс>@example.com
LOCAL_ADMIN_PASSWORD = "Wms686Demo2026!"
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "[::1]"}

GS = "\x1d"

BASE_PATH = "/operations/marketplace-unload-requests"
INBOUND_PATH = "/operations/inbound-intake-requests"

LOC_1 = "А-1-1"  # кириллическая «А», как в постановке WMS-686
LOC_2 = "А-1-2"

# (ключ, название, ШК WB, нужен ЧЗ)
PRODUCTS: tuple[tuple[str, str, str, bool], ...] = (
    ("t48", "Футболка 48", "4600000000017", True),
    ("t50", "Футболка 50", "4600000000024", True),
    ("socks", "Носки", "4600000000031", False),
)
POOL_SIZE = {"t48": 20, "t50": 4}
SHIPMENT_PLAN = {"t48": 6, "t50": 4, "socks": 2}


class SeedError(RuntimeError):
    pass


class Api:
    """Тонкая обёртка над httpx: любой не-2xx превращается в понятную ошибку."""

    def __init__(self, base_url: str) -> None:
        self.client = httpx.Client(base_url=base_url.rstrip("/"), timeout=120.0)
        self.headers: dict[str, str] = {}

    def call(
        self, method: str, path: str, *, ok: tuple[int, ...] = (200, 201, 204), **kwargs: Any
    ) -> Any:
        resp = self.client.request(method, path, headers=self.headers, **kwargs)
        if resp.status_code not in ok:
            raise SeedError(f"{method} {path} -> {resp.status_code}: {resp.text[:600]}")
        if resp.status_code == 204 or not resp.content:
            return None
        return resp.json()

    def get(self, path: str, **kw: Any) -> Any:
        return self.call("GET", path, **kw)

    def post(self, path: str, **kw: Any) -> Any:
        return self.call("POST", path, **kw)

    def patch(self, path: str, **kw: Any) -> Any:
        return self.call("PATCH", path, **kw)

    def put(self, path: str, **kw: Any) -> Any:
        return self.call("PUT", path, **kw)


def authenticate(api: Api, base_url: str, args: argparse.Namespace) -> str:
    if args.token:
        api.headers = {"Authorization": f"Bearer {args.token}"}
        return str(args.token)
    host = urlparse(base_url).hostname or ""
    if host not in LOCAL_HOSTS:
        raise SeedError(
            "регистрация нового ФФ разрешена только на localhost; "
            "для другого адреса передайте --token администратора ФФ"
        )
    suffix = args.suffix
    email = LOCAL_ADMIN_EMAIL.replace("@", f"-{suffix}@") if suffix else LOCAL_ADMIN_EMAIL
    reg = api.client.post(
        "/auth/register",
        json={
            "organization_name": f"WMS-686 демо ФФ{(' ' + suffix) if suffix else ''}",
            "slug": f"wms686-demo{('-' + suffix) if suffix else ''}",
            "admin_email": email,
            "password": LOCAL_ADMIN_PASSWORD,
        },
    )
    if reg.status_code in (200, 201):
        token = str(reg.json()["access_token"])
    elif reg.status_code == 409:
        login = api.client.post(
            "/auth/login",
            json={"email": email, "password": LOCAL_ADMIN_PASSWORD},
        )
        if login.status_code != 200:
            raise SeedError(f"организация уже есть, вход не удался: {login.status_code}")
        token = str(login.json()["access_token"])
    else:
        raise SeedError(f"регистрация не удалась: {reg.status_code} {reg.text[:400]}")
    api.headers = {"Authorization": f"Bearer {token}"}
    return token


def make_kiz(ean13: str, serial: str, *, with_tail: bool) -> str:
    """КИЗ: 01 + GTIN-14 (0 + EAN-13) + 21 + серийный номер [+ GS + 93 + хвост]."""
    code = f"010{ean13}21{serial}"
    if with_tail:
        code += f"{GS}93{serial[-4:]}"
    return code


def import_pool(
    api: Api, *, seller_id: str, product_id: str, sku: str, title: str, codes: list[str]
) -> int:
    body = "cis,sku_code\n" + "\n".join(f"{code},{sku}" for code in codes)
    result = api.post(
        "/operations/marking-codes/import",
        data={
            "seller_id": seller_id,
            "pools_json": json.dumps([{"title": title, "product_ids": [product_id]}]),
        },
        files=[("files", ("codes.csv", body.encode(), "text/csv"))],
    )
    accepted = int(result["accepted_count"])
    if accepted != len(codes):
        raise SeedError(f"импорт КИЗ принял {accepted} из {len(codes)}: {result}")
    return accepted


def place_box(api: Api, warehouse_id: str, request_id: str, box_id: str, cell_id: str) -> None:
    """Поставить короб приёмки в ячейку так же, как это делает экран «Сортировка»."""
    api.post(
        f"/warehouses/{warehouse_id}/sorting-objects/place",
        json={
            "kind": "box",
            "id": box_id,
            "cell_id": cell_id,
            "inbound_request_id": request_id,
            "operation_id": str(uuid.uuid4()),
        },
    )


def find_product_balance_id(
    api: Api, warehouse_id: str, cell_id: str, product_id: str, box_id: str
) -> str:
    """id остатка товара внутри короба на ячейке — по карте склада (как видит экран)."""
    cells = api.get(f"/warehouses/{warehouse_id}/map")["cells"]
    cell = next((row for row in cells if row["id"] == cell_id), None)
    if cell is None:
        raise SeedError(f"ячейка {cell_id} не найдена на карте склада")

    def walk(nodes: list[dict[str, Any]], inside_box: bool) -> str | None:
        for node in nodes:
            in_box = inside_box or (node.get("kind") == "box" and node.get("id") == box_id)
            if node.get("kind") == "product" and node.get("product_id") == product_id and in_box:
                return str(node["id"])
            found = walk(node.get("children") or [], in_box)
            if found:
                return found
        return None

    balance_id = walk(cell.get("children") or [], False)
    if balance_id is None:
        raise SeedError(f"в коробе {box_id} на ячейке {cell_id} нет товара {product_id}")
    return balance_id


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--base-url", default="http://127.0.0.1:18086")
    parser.add_argument("--token", help="токен администратора ФФ (для не-localhost обязателен)")
    parser.add_argument("--suffix", default="", help="суффикс кодов, чтобы запускать повторно")
    parser.add_argument("--out-dir", default=".", help="куда писать kiz-codes.txt и demo-ids.json")
    parser.add_argument(
        "--wb-warehouse-id", type=int, help="склад WB; по умолчанию первый из справочника"
    )
    parser.add_argument("--with-tail", action="store_true", help="добавить к КИЗ хвост GS+93")
    parser.add_argument(
        "--tee50-in-box",
        action="store_true",
        help="«Футболки 50» поставить в «А-1-2» коробом INB (по умолчанию — россыпью)",
    )
    args = parser.parse_args()
    suffix = args.suffix
    sfx = f"-{suffix}" if suffix else ""

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    api = Api(args.base_url)
    token = authenticate(api, args.base_url, args)

    # --- склад и ячейки ---------------------------------------------------
    api.patch("/tenant/settings", json={"address_storage_enabled": True})
    wh = api.post("/warehouses", json={"name": f"Склад WMS-686{sfx}", "code": f"wms686{sfx}"})
    wid = str(wh["id"])
    cells: dict[str, dict[str, str]] = {}
    for code in (LOC_1, LOC_2):
        loc = api.post(f"/warehouses/{wid}/locations", json={"code": code})
        cells[code] = {"id": str(loc["id"]), "barcode": str(loc["barcode"])}

    # --- селлер WB (фиктивный токен) и склад WB ----------------------------
    seller = api.post("/sellers", json={"name": f"Демо WB селлер{sfx}"})
    sid = str(seller["id"])
    api.patch(
        f"/integrations/wildberries/sellers/{sid}/tokens",
        json={"supplies_api_token": "demo-fake-wb-supplies-token"},
    )
    if args.wb_warehouse_id is not None:
        wb_wid = int(args.wb_warehouse_id)
    else:
        rows = api.get("/operations/wb-mp-warehouses")
        if not rows:
            raise SeedError("справочник складов WB пуст: передайте --wb-warehouse-id")
        wb_wid = int(rows[0]["wb_warehouse_id"])

    # --- товары и пул КИЗ ---------------------------------------------------
    products: dict[str, dict[str, str]] = {}
    for key, name, barcode, honest in PRODUCTS:
        sku = f"W686-{key.upper()}{sfx}"
        created = api.post(
            "/products",
            json={
                "name": name,
                "sku_code": sku,
                "length_mm": 300,
                "width_mm": 200,
                "height_mm": 20,
                "seller_id": sid,
                "wb_barcode": barcode,
                "requires_honest_sign": honest,
            },
        )
        pid = str(created["id"])
        api.patch(
            f"/products/{pid}/packaging-instructions",
            json={"packaging_instructions": "Демо WMS-686: упаковка по ШК товара."},
        )
        products[key] = {"id": pid, "sku": sku, "name": name, "barcode": barcode}

    kiz_codes: dict[str, list[str]] = {}
    for key, count in POOL_SIZE.items():
        info = products[key]
        prefix = key.upper()
        codes = [
            make_kiz(info["barcode"], f"{prefix}{index:010d}"[:13], with_tail=args.with_tail)
            for index in range(1, count + 1)
        ]
        import_pool(
            api,
            seller_id=sid,
            product_id=info["id"],
            sku=info["sku"],
            title=f"WMS-686 пул {info['name']}",
            codes=codes,
        )
        kiz_codes[key] = codes

    # --- приёмка на три короба INB ----------------------------------------
    request = api.post(INBOUND_PATH, json={"warehouse_id": wid})
    rid = str(request["id"])
    expected = {"t48": 11, "t50": 8, "socks": 2}
    for key, qty in expected.items():
        api.post(
            f"{INBOUND_PATH}/{rid}/lines",
            json={"product_id": products[key]["id"], "expected_qty": qty},
        )
    api.patch(f"{INBOUND_PATH}/{rid}", json={"planned_box_count": 3})
    api.post(f"{INBOUND_PATH}/{rid}/submit")
    api.post(f"{INBOUND_PATH}/{rid}/begin-receiving")

    box_plan: list[dict[str, int]] = [
        {"t48": 6, "socks": 2},  # короб 1
        {"t48": 5},  # короб 2
        {"t50": 8},  # короб 3
    ]
    boxes: list[dict[str, Any]] = []
    for number, contents in enumerate(box_plan, start=1):
        box = api.post(f"{INBOUND_PATH}/{rid}/boxes")
        box_id = str(box["id"])
        for key, qty in contents.items():
            api.put(
                f"{INBOUND_PATH}/{rid}/boxes/{box_id}/lines/{products[key]['id']}",
                json={"quantity": qty},
            )
        api.post(f"{INBOUND_PATH}/{rid}/boxes/{box_id}/close")
        boxes.append(
            {
                "number": number,
                "id": box_id,
                "barcode": str(box["internal_barcode"]),
                "contents": contents,
            }
        )
    api.post(f"{INBOUND_PATH}/{rid}/verify")  # приёмка → «сортировка»

    # --- размещение: короба 1 и 2 целиком в «А-1-1», «Футболки 50» в «А-1-2» ---
    # Штатный путь экрана «Сортировка» (/warehouses/{id}/sorting-objects/place):
    # он двигает остаток и одновременно записывает место самого короба. Ручка
    # приёмки .../boxes/{id}/putaway переносит только остаток, и место короба
    # остаётся «Сортировка» — подбор FBO тогда отвечает 409 invalid_container_reference.
    for index in (0, 1):
        place_box(api, wid, rid, str(boxes[index]["id"]), cells[LOC_1]["id"])
        boxes[index]["location"] = LOC_1
    place_box(api, wid, rid, str(boxes[2]["id"]), cells[LOC_2]["id"])
    if args.tee50_in_box:
        boxes[2]["location"] = LOC_2
    else:
        # Выкладка из короба: товар остаётся в ячейке, но уже без тары.
        balance_id = find_product_balance_id(
            api, wid, cells[LOC_2]["id"], products["t50"]["id"], str(boxes[2]["id"])
        )
        api.post(
            f"/warehouses/{wid}/map/move",
            json={
                "kind": "product",
                "id": balance_id,
                "to_kind": "cell",
                "to_id": cells[LOC_2]["id"],
                "qty": 8,
            },
        )
        boxes[2]["location"] = f"{LOC_2} (россыпью, короб пуст)"
    inbound = api.get(f"{INBOUND_PATH}/{rid}")

    # --- утверждённая отгрузка FBO на WB -----------------------------------
    shipment = api.post(
        BASE_PATH, json={"warehouse_id": wid, "seller_id": sid, "wb_mp_warehouse_id": wb_wid}
    )
    mid = str(shipment["id"])
    for key, qty in SHIPMENT_PLAN.items():
        api.post(
            f"{BASE_PATH}/{mid}/lines", json={"product_id": products[key]["id"], "quantity": qty}
        )
    api.patch(
        f"{BASE_PATH}/{mid}",
        json={"planned_shipment_date": (date.today() + timedelta(days=3)).isoformat()},
    )
    submitted = api.post(f"{BASE_PATH}/{mid}/submit")
    if submitted["status"] != "confirmed":
        raise SeedError(f"отгрузка не утверждена: {submitted['status']}")
    options = api.get(f"{BASE_PATH}/{mid}/pick-options")

    # --- файлы для ведущего ---------------------------------------------------
    lines_out = ["КИЗ демо WMS-686 (фиктивные, формат 01+GTIN-14+21+серийный)", ""]
    for key in ("t48", "t50"):
        lines_out.append(
            f"== {products[key]['name']} (ШК {products[key]['barcode']}), "
            f"{len(kiz_codes[key])} шт =="
        )
        lines_out.extend(code.replace(GS, "<GS>") for code in kiz_codes[key])
        lines_out.append("")
    (out_dir / "kiz-codes.txt").write_text("\n".join(lines_out), encoding="utf-8")

    summary = {
        "base_url": args.base_url,
        "token": token,
        "warehouse_id": wid,
        "cells": cells,
        "seller_id": sid,
        "wb_warehouse_id": wb_wid,
        "products": products,
        "inbound_request_id": rid,
        "inbound_document_number": inbound.get("document_number"),
        "inbound_status": inbound.get("status"),
        "inbound_boxes": boxes,
        "shipment_id": mid,
        "shipment_document_number": submitted.get("document_number"),
        "shipment_status": submitted["status"],
        "pick_options": options,
    }
    (out_dir / "demo-ids.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # --- отчёт -----------------------------------------------------------------
    print("=== WMS-686: демо-данные FBO готовы ===")
    print(f"Склад: {wh['name']} ({wid})")
    for code, cell in cells.items():
        print(f"Ячейка {code}: id={cell['id']} ШК={cell['barcode']}")
    print(f"Селлер: {seller['name']} ({sid}), склад WB {wb_wid}")
    for key, info in products.items():
        print(f"Товар {info['name']}: id={info['id']} sku={info['sku']} ШК={info['barcode']}")
    print(f"Приёмка: {inbound.get('document_number')} ({rid}), статус {inbound.get('status')}")
    for box in boxes:
        print(
            f"Короб INB {box['number']}: ШК {box['barcode']} -> {box['location']} "
            f"{box['contents']}"
        )
    print(f"Отгрузка FBO: {submitted.get('document_number')} id={mid} статус {submitted['status']}")
    print(f"  экран отгрузки: /app/ff/mp-shipments?open_mp={mid}")
    print(f"  экран подбора:  /app/ff/unload-pick/{mid}")
    print(f"КИЗ: {out_dir / 'kiz-codes.txt'}")
    print(f"ID и токен: {out_dir / 'demo-ids.json'}")
    print()
    print("pick-options (место -> источники):")
    for product in options:
        name = next(
            (p["name"] for p in products.values() if p["id"] == product["product_id"]), "?"
        )
        print(f"  {name}: план {product.get('planned_qty')}")
        for location in product["locations"]:
            for source in location["sources"]:
                print(
                    f"    {location['location_code']}: {source['source_label']} "
                    f"— {source['quantity']} шт"
                )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SeedError as exc:
        print(f"ОШИБКА: {exc}", file=sys.stderr)
        sys.exit(1)
