#!/usr/bin/env python3
"""One-off read-only export of unused WB labels for the photographed ArtMaks SKUs."""
import base64
import io
import json
import shlex
import subprocess
from collections import Counter
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from PIL import Image
import zxingcpp
from pypdf import PdfReader
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Table, TableStyle, Paragraph
from reportlab.lib.styles import ParagraphStyle

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "output/pdf/artmaks-unused-20261001"
REMOTE_CODE = "import asyncio,json,uuid,httpx\nfrom datetime import datetime,timezone\nfrom app.services.wildberries_credentials_service import get_decrypted_marketplace_token\nfrom app.services.wildberries_fbs_client import marketplace_request,fetch_marketplace_order_stickers_typed,_parse_orders_meta_response\nfrom sqlalchemy import text\nfrom app.db.session import SessionLocal\nasync def main():\n async with SessionLocal() as s:\n  await s.execute(text(\"SET TRANSACTION READ ONLY\"))\n  sql=\"\"\"SELECT o.id,o.wb_order_id,o.wb_article,o.wb_barcode,p.sku_code,p.wb_size,p.wb_barcode AS product_barcode,su.wb_supply_id,o.status,o.pick_status,o.pack_status,o.sticker_code,o.sticker_barcode,\n  (SELECT count(*) FROM fbs_order_markings m WHERE m.order_id=o.id) AS marking_count,\n  (SELECT count(*) FROM document_event e WHERE e.tenant_id=o.tenant_id AND e.document_id=o.supply_id AND e.payload_json->>'kind'='wms514_scan_auto_print' AND e.payload_json->>'order_id'=o.id::text) AS scan_count\n  FROM fbs_orders o JOIN fbs_supplies su ON su.id=o.supply_id JOIN products p ON p.id=o.product_id\n  WHERE o.tenant_id='82b36645-8662-497f-9631-a0743994632c' AND o.seller_id='68dd641b-c5cc-4e0a-8057-015eca180d0e'\n  AND su.wb_supply_id IN ('WB-GI-285910955','WB-GI-285911018')\n  AND (o.wb_barcode IN ('2039751847730','2039751847747','04650263657358','04650263670142','04650263695978','04640379271968') OR p.wb_barcode IN ('2039751847730','2039751847747','4743348608885','4743348608915','9742492744314','2009989381795'))\n  ORDER BY su.wb_supply_id,p.sku_code,o.wb_order_id\"\"\"\n  r=(await s.execute(text(sql))).mappings().all()\n  all_rows=[dict(x) for x in r]\n  free=[x for x in all_rows if x[\"marking_count\"]==0 and x[\"scan_count\"]==0 and x[\"pick_status\"]==\"pending\" and x[\"pack_status\"]==\"pending\" and x[\"status\"] in (\"new\",\"in_supply\",\"assembling\",\"packed\")]\n  assert free,\"No eligible orders\"\n  ids=[x[\"wb_order_id\"] for x in free]\n  token=await get_decrypted_marketplace_token(s,uuid.UUID(\"82b36645-8662-497f-9631-a0743994632c\"),uuid.UUID(\"68dd641b-c5cc-4e0a-8057-015eca180d0e\"))\n  assert token,\"WB credential unavailable\"\n  async with httpx.AsyncClient(timeout=60) as client:\n   meta_resp=await marketplace_request(client,\"POST\",\"https://marketplace-api.wildberries.ru/api/marketplace/v3/orders/meta\",api_token=token,json_body={\"orders\":ids})\n   assert meta_resp.status_code==200,(\"Metadata HTTP\",meta_resp.status_code)\n   meta={x.order_id:x.meta for x in _parse_orders_meta_response(meta_resp.json())}\n   assert set(meta)==set(ids),\"WB metadata incomplete\"\n   for oid in ids:\n    sg=(meta[oid] or {}).get(\"sgtin\")\n    value=sg.get(\"value\") if isinstance(sg,dict) else sg\n    assert not value,(\"WB KIZ already linked\",oid)\n   stickers=await fetch_marketplace_order_stickers_typed(client,api_token=token,order_ids=ids,marketplace_api_base=\"https://marketplace-api.wildberries.ru\",width=58,height=40)\n   byid={x[\"orderId\"]:x for x in stickers}\n   assert len(stickers)==len(ids) and set(byid)==set(ids),\"Sticker set mismatch\"\n   for row in free:\n    sticker=byid[row[\"wb_order_id\"]]\n    assert sticker[\"barcode\"]==row[\"sticker_barcode\"],(\"Barcode mismatch\",row[\"wb_order_id\"])\n    assert (str(sticker[\"partA\"])+\" \"+str(sticker[\"partB\"]).zfill(4))==row[\"sticker_code\"],(\"Visible QR number mismatch\",row[\"wb_order_id\"])\n    row[\"sticker_file\"]=sticker[\"file\"]\n  recheck=[dict(x) for x in (await s.execute(text(sql))).mappings().all()]\n  eligible_now={x[\"wb_order_id\"] for x in recheck if x[\"marking_count\"]==0 and x[\"scan_count\"]==0 and x[\"pick_status\"]==\"pending\" and x[\"pack_status\"]==\"pending\" and x[\"status\"] in (\"new\",\"in_supply\",\"assembling\",\"packed\")}\n  assert set(ids)==eligible_now,\"Order availability changed during export; stop\"\n  print(json.dumps({\"checked_at\":datetime.now(timezone.utc).isoformat(),\"rows\":free,\"all_rows\":all_rows,\"source\":\"WMS read-only snapshot + live WB order metadata and original PNG stickers\",\"database_mutations\":False},default=str,ensure_ascii=False))\n  await s.rollback()\nasyncio.run(main())"
SSH_COMMAND = "cd /opt/wms && docker compose -p wms_prod -f docker-compose.prod.yml -f docker-compose.wms-host-8088.yml exec -T api python -c " + shlex.quote(REMOTE_CODE)

def fetch():
    result = subprocess.run(["ssh", "-o", "BatchMode=yes", "root@194.87.96.144", SSH_COMMAND], capture_output=True, text=True, timeout=150)
    if result.returncode:
        raise RuntimeError("Read-only export failed: " + result.stderr[-1800:])
    return json.loads(result.stdout)

def render(data):
    OUT.mkdir(parents=True, exist_ok=True)
    pdfmetrics.registerFont(TTFont("Arial", "/System/Library/Fonts/Supplemental/Arial.ttf"))
    pdfmetrics.registerFont(TTFont("ArialBold", "/System/Library/Fonts/Supplemental/Arial Bold.ttf"))
    rows = data["rows"]
    labels_path = OUT / "WB-unused-QR-58x40.pdf"
    picking_path = OUT / "Picking-list-A4.pdf"
    label_pdf = canvas.Canvas(str(labels_path), pagesize=(58*mm, 40*mm))
    label_pdf.setTitle("Артмакс - свободные QR WB - 58 x 40 мм")
    for page, row in enumerate(rows, 1):
        raw = base64.b64decode(row.pop("sticker_file"), validate=True)
        picture = Image.open(io.BytesIO(raw))
        assert picture.format == "PNG"
        decoded = {x.text for x in zxingcpp.read_barcodes(picture)}
        assert row["sticker_barcode"] in decoded, ("Original WB QR unreadable or incorrect", page, decoded)
        row["pdf_page"] = page
        row["original_qr_decoded"] = True
        label_pdf.drawImage(ImageReader(picture), 0, 0, width=58*mm, height=40*mm)
        label_pdf.showPage()
    label_pdf.save()
    when = datetime.fromisoformat(data["checked_at"]).astimezone(ZoneInfo("Europe/Moscow")).strftime("%d.%m.%Y %H:%M МСК")
    c = canvas.Canvas(str(picking_path), pagesize=A4)
    c.setTitle("Артмакс - лист подбора свободных QR WB")
    width, height = A4
    supplies = list(dict.fromkeys(x["wb_supply_id"] for x in rows))
    body = ParagraphStyle("body", fontName="Arial", fontSize=8.7, leading=11)
    head = ParagraphStyle("head", fontName="ArialBold", fontSize=8, leading=10, textColor=colors.white)
    for sheet, supply in enumerate(supplies, 1):
        subset = [r for r in rows if r["wb_supply_id"] == supply]
        c.setFont("ArialBold", 20)
        c.drawString(14*mm, height-19*mm, "ЛИСТ ПОДБОРА")
        c.setFont("Arial", 10)
        c.drawString(14*mm, height-27*mm, 'Артмакс / ООО "фабрика" / Wildberries FBS')
        c.setFont("ArialBold", 12)
        c.drawString(14*mm, height-38*mm, supply)
        c.setFont("Arial", 9)
        c.drawString(14*mm, height-45*mm, f"Свободных QR: {len(subset)}. Проверено: {when}.")
        c.drawString(14*mm, height-51*mm, "Стр. QR = номер страницы в файле этикеток 58 x 40 мм.")
        table_data = [[Paragraph(v, head) for v in ["Стр.<br/>QR", "Артикул", "Раз-<br/>мер", "ШК товара", "Номер QR WB", "Отм."]]]
        for row in subset:
            table_data.append([
                str(row["pdf_page"]),
                Paragraph(row["wb_article"], body),
                row["wb_size"],
                row["product_barcode"] or row["wb_barcode"],
                row["sticker_code"],
                "",
            ])
        table = Table(table_data, colWidths=[13*mm, 49*mm, 13*mm, 43*mm, 48*mm, 16*mm], rowHeights=[10*mm]+[10.5*mm]*len(subset))
        table.setStyle(TableStyle([
            ("BACKGROUND",(0,0),(-1,0),colors.HexColor("#233247")),
            ("FONTNAME",(0,1),(-1,-1),"Arial"),
            ("FONTSIZE",(0,1),(-1,-1),9),
            ("VALIGN",(0,0),(-1,-1),"MIDDLE"),
            ("LEFTPADDING",(0,0),(-1,-1),6),
            ("RIGHTPADDING",(0,0),(-1,-1),5),
            ("ALIGN",(0,1),(0,-1),"CENTER"),
            ("ALIGN",(2,1),(2,-1),"CENTER"),
            ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,colors.HexColor("#F3F5F8")]),
            ("LINEBELOW",(0,0),(-1,-1),.35,colors.HexColor("#CDD3DA")),
        ]))
        tw, th = table.wrap(182*mm, 220*mm)
        bottom = height-57*mm-th
        table.drawOn(c, 14*mm, bottom)
        note_y = bottom - 9*mm
        if sheet == 1:
            c.setFont("ArialBold", 9)
            c.drawString(14*mm, note_y, "88900-007, размер 54, этикетка ЧЗ №651: свободных QR нет.")
            c.setFont("Arial", 8.5)
            c.drawString(14*mm, note_y-5*mm, "ШК товара 2009989381795. Занятые QR в печать не включены.")
        c.setFont("Arial", 8)
        c.drawString(14*mm, 23*mm, "Список содержит все свободные заказы по артикулам и размерам с 10 фотографий.")
        c.drawString(14*mm, 18*mm, "Не закрепляет QR за конкретными КИЗ. Базу и статусы поставок выгрузка не меняет.")
        c.drawString(14*mm, 13*mm, "Свободно на время проверки; создание PDF не резервирует заказы.")
        c.drawRightString(width-14*mm, 8*mm, f"{sheet} / {len(supplies)}")
        c.showPage()
    c.save()
    assert len(PdfReader(labels_path).pages) == len(rows)
    assert len(PdfReader(picking_path).pages) == len(supplies)
    for row in rows:
        assert all(row[x] == 0 for x in ["marking_count", "scan_count"])
        assert row["pick_status"] == row["pack_status"] == "pending"
    assert len({r["wb_order_id"] for r in rows}) == len(rows)
    assert len({r["sticker_barcode"] for r in rows}) == len(rows)
    (OUT / "verification.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"checked_at":data["checked_at"],"label_pages":len(rows),"picking_pages":len(supplies),"supplies":dict(Counter(r["wb_supply_id"] for r in rows)),"output":str(OUT)}, ensure_ascii=False))

if __name__ == "__main__":
    render(fetch())
