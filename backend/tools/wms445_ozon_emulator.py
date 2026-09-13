"""Local, persistent Ozon wire fixture for WMS-445. No upstream transport.

Run with WMS445_OZON_STATE=<local json> uvicorn tools.wms445_ozon_emulator:app
--host 127.0.0.1 --port 19093. Uses only synthetic Client-Id 445a/445b.
Unknown routes and unknown postings fail; mutations are recorded for replay checks.
"""

from __future__ import annotations

import base64
import io
import json
import os
from pathlib import Path
from typing import Any, cast

import fitz
import qrcode  # type: ignore[import-untyped]
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response

app = FastAPI(title="WMS445 synthetic Ozon")
STATE_PATH = Path(os.environ.get("WMS445_OZON_STATE", "wms445-ozon-state.json"))


def read_state() -> dict[str, Any]:
    if STATE_PATH.exists():
        return cast(dict[str, Any], json.loads(STATE_PATH.read_text()))
    return {"postings": {}, "carriages": {}, "label_tasks": {}, "calls": [], "faults": {}}


def save_state(state: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = STATE_PATH.with_suffix(".writing")
    temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2))
    temporary.replace(STATE_PATH)


def label_pdf(names: list[str]) -> bytes:
    document = fitz.open()
    for name in names:
        page = document.new_page(width=283, height=425)
        page.insert_text((20, 40), "OZON - TEST WMS445", fontsize=16)
        page.insert_text((20, 65), name, fontsize=11)
        buffer = io.BytesIO()
        qrcode.make(name).save(buffer, format="PNG")
        page.insert_image(fitz.Rect(30, 85, 230, 285), stream=buffer.getvalue())
    content = document.tobytes()
    document.close()
    return bytes(content)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "fixture": "WMS445"}


@app.get("/__admin/state")
async def state_snapshot() -> dict[str, Any]:
    return read_state()  # Never stores incoming credential headers.


@app.post("/__admin/seed")
async def seed(request: Request) -> dict[str, int]:
    state = read_state()
    body = await request.json()
    count = 0
    for posting in body["postings"]:
        number = posting["posting_number"]
        if not number.startswith("445-"):
            raise HTTPException(400, "Only WMS445 posting numbers are accepted")
        if number not in state["postings"]:
            state["postings"][number] = posting
            count += 1
    save_state(state)
    return {"created": count, "total": len(state["postings"])}


@app.post("/__admin/faults")
async def set_fault(request: Request) -> dict[str, Any]:
    body = await request.json()
    if body.get("timing") not in {"before", "after"}:
        raise HTTPException(400, "timing is before or after")
    state = read_state()
    state["faults"][body["path"]] = {"timing": body["timing"], "remaining": 1}
    save_state(state)
    return {"configured": True}


@app.get("/labels/{task_id}.pdf")
async def download_label(task_id: str) -> Response:
    state = read_state()
    names = state["label_tasks"].get(task_id)
    if names is None:
        raise HTTPException(404, "Unknown label task")
    return Response(label_pdf(names), media_type="application/pdf")


def dispatch(path: str, body: dict[str, Any], state: dict[str, Any], client: str) -> Any:
    postings = state["postings"]
    number = body.get("posting_number")
    posting = postings.get(number) if isinstance(number, str) else None
    if (
        isinstance(number, str)
        and number
        and (posting is None or posting["fixture_client"] != client)
    ):
        raise HTTPException(404, "Unknown synthetic posting")
    if path == "/v1/seller/info":
        return {"result": {"name": f"WMS445 {client}"}}
    if path == "/v2/warehouse/list":
        return {
            "result": {
                "warehouses": [
                    {"warehouse_id": 1020005029603630, "name": "WMS445 Ozon", "is_enabled": True}
                ],
                "has_next": False,
            }
        }
    if path in {"/v4/posting/fbs/unfulfilled/list", "/v3/posting/fbs/list"}:
        rows = json.loads(
            json.dumps([p for p in postings.values() if p["fixture_client"] == client])
        )
        if path == "/v4/posting/fbs/unfulfilled/list":
            for row in rows:
                for product in row["products"]:
                    product["price"] = {"amount": product["price"], "currency_code": "RUB"}
        return {"result": {"postings": rows, "has_next": False}}
    if path == "/v3/posting/fbs/get":
        return {"result": posting}
    if path == "/v1/posting/fbs/restrictions":
        return {"result": {"posting_number": number}}
    if path == "/v4/posting/fbs/ship":
        if posting is None or posting["status"] != "awaiting_packaging":
            raise HTTPException(409, "Posting already shipped or unavailable")
        requested: dict[int, int] = {}
        for package in body.get("packages", []):
            for product in package.get("products", []):
                sku = int(product["product_id"])
                requested[sku] = requested.get(sku, 0) + int(product["quantity"])
        expected = {int(p["sku"]): int(p["quantity"]) for p in posting["products"]}
        if requested != expected:
            raise HTTPException(400, "Posting composition differs from seeded units")
        posting["status"] = "awaiting_deliver"
        posting["substatus"] = "posting_not_in_carriage"
        return {"result": [number]}
    if path == "/v2/posting/fbs/package-label/create":
        names = body.get("posting_number", body.get("posting_numbers", []))
        if isinstance(names, str):
            names = [names]
        if not names or any(n not in postings for n in names):
            raise HTTPException(404, "Unknown label postings")
        task_id = str(445000 + len(state["label_tasks"]) + 1)
        state["label_tasks"][task_id] = names
        return {"result": {"tasks": [{"task_id": int(task_id), "task_type": "big_label"}]}}
    if path == "/v1/posting/fbs/package-label/get":
        task_id = str(body["task_id"])
        if task_id not in state["label_tasks"]:
            raise HTTPException(404, "Unknown label task")
        return {
            "result": {
                "status": "completed",
                "file_url": f"http://127.0.0.1:19093/labels/{task_id}.pdf",
            }
        }
    if path == "/v2/posting/fbs/package-label":
        names = body.get("posting_number", body.get("posting_numbers", []))
        return {
            "file_content": base64.b64encode(label_pdf(names)).decode(),
            "file_name": "labels.pdf",
            "content_type": "application/pdf",
        }
    if path == "/v1/carriage/create":
        carriage_id = str(445000 + len(state["carriages"]) + 1)
        state["carriages"][carriage_id] = {
            "carriage_id": int(carriage_id),
            "status": "new",
            "posting_numbers": [
                p["posting_number"]
                for p in postings.values()
                if p["fixture_client"] == client and p["status"] == "awaiting_deliver"
            ],
            "fixture_client": client,
        }
        return {"carriage_id": int(carriage_id)}
    if path in {"/v1/carriage/set-postings", "/v1/carriage/approve", "/v1/carriage/get"}:
        carriage = state["carriages"].get(str(body["carriage_id"]))
        if carriage is None or carriage["fixture_client"] != client:
            raise HTTPException(404, "Unknown carriage")
        if path.endswith("set-postings"):
            names = body["posting_numbers"]
            if any(n not in postings or postings[n]["fixture_client"] != client for n in names):
                raise HTTPException(404, "Unknown carriage postings")
            carriage["posting_numbers"] = names
            return {"result": [{"posting_number": n, "result": True} for n in names]}
        if path.endswith("approve"):
            if carriage["status"] != "new":
                raise HTTPException(409, "Already approved")
            carriage["status"] = "formed"
            for name in carriage["posting_numbers"]:
                postings[name]["substatus"] = "posting_in_carriage"
            return {}
        return carriage
    if path == "/v2/posting/fbs/act/get-barcode/text":
        return {"result": f"OZON-ACT-{body.get('id') or body.get('carriage_id')}"}
    if path in {"/v2/posting/fbs/act/get-pdf", "/v2/posting/fbs/act/get-barcode"}:
        return {
            "file_content": base64.b64encode(label_pdf([f"ACT-{body.get('id')}"])).decode(),
            "file_name": "act.pdf",
            "content_type": "application/pdf",
        }
    if path == "/v2/products/stocks":
        return {
            "result": [
                {"product_id": s.get("product_id"), "updated": True, "errors": []}
                for s in body.get("stocks", [])
            ]
        }
    raise HTTPException(501, f"Fixture route not implemented: {path}")


@app.post("/{path:path}")
async def ozon(path: str, request: Request) -> Any:
    client = request.headers.get("client-id", "")
    if client not in {"445a", "445b"} or request.headers.get("api-key") != "wms445-synthetic":
        raise HTTPException(401, "Use synthetic fixture credentials")
    body = await request.json()
    path = "/" + path
    state = read_state()
    fault = state["faults"].get(path, {})
    if fault.get("timing") == "before" and fault.get("remaining", 0):
        fault["remaining"] = 0
        save_state(state)
        raise HTTPException(503, "WMS445 injected failure before mutation")
    result = dispatch(path, body, state, client)
    state["calls"].append({"path": path, "client": client, "body": body})
    save_state(state)
    if fault.get("timing") == "after" and fault.get("remaining", 0):
        fault["remaining"] = 0
        save_state(state)
        raise HTTPException(503, "WMS445 injected response loss after mutation")
    return result
