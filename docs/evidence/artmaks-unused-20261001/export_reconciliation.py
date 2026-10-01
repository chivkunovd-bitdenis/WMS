"""A4 reconciliation sheet for 14 occupied WB order labels, read-only."""
import json
import shlex
import subprocess
from datetime import datetime
from pathlib import Path
from xml.sax.saxutils import escape
from zoneinfo import ZoneInfo

from pypdf import PdfReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Flowable, Paragraph, Table, TableStyle
from reportlab.graphics.shapes import Drawing
from reportlab.graphics.barcode.qr import QrCodeWidget

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "output/pdf/artmaks-unused-20261001"
REMOTE_CODE = "import asyncio,json,uuid,httpx\nfrom datetime import datetime,timezone\nfrom sqlalchemy import text\nfrom app.db.session import SessionLocal\nfrom app.services.wildberries_credentials_service import get_decrypted_marketplace_token\nfrom app.services.wildberries_fbs_client import fetch_marketplace_order_stickers_typed\nasync def main():\n async with SessionLocal() as s:\n  await s.execute(text(\"SET TRANSACTION READ ONLY\"))\n  q=\"\"\"SELECT o.id,o.wb_order_id,p.sku_code,p.wb_size,o.wb_article,o.wb_barcode,su.wb_supply_id,o.sticker_code,o.sticker_barcode,o.pick_status,o.pack_status,o.sticker_status,m.value AS kiz,m.meta_status\n  FROM fbs_orders o JOIN products p ON p.id=o.product_id JOIN fbs_supplies su ON su.id=o.supply_id JOIN fbs_order_markings m ON m.order_id=o.id\n  WHERE o.tenant_id='82b36645-8662-497f-9631-a0743994632c' AND o.seller_id='68dd641b-c5cc-4e0a-8057-015eca180d0e'\n  AND su.wb_supply_id IN ('WB-GI-285910955','WB-GI-285911018') AND p.sku_code IN ('88900-007/54','38900-001/48')\n  ORDER BY CASE WHEN p.sku_code='88900-007/54' THEN 0 ELSE 1 END,o.wb_order_id\"\"\"\n  rows=[dict(x) for x in (await s.execute(text(q))).mappings()]\n  assert len(rows)==14 and len(set(r[\"wb_order_id\"] for r in rows))==14\n  assert all(r[\"pack_status\"]==\"packed\" for r in rows),\"Current occupancy changed\"\n  token=await get_decrypted_marketplace_token(s,uuid.UUID(\"82b36645-8662-497f-9631-a0743994632c\"),uuid.UUID(\"68dd641b-c5cc-4e0a-8057-015eca180d0e\"))\n  async with httpx.AsyncClient(timeout=45) as c:\n   stickers=await fetch_marketplace_order_stickers_typed(c,api_token=token,order_ids=[r[\"wb_order_id\"] for r in rows],marketplace_api_base=\"https://marketplace-api.wildberries.ru\")\n   stickers={x[\"orderId\"]:x for x in stickers}\n   assert set(stickers)==set(r[\"wb_order_id\"] for r in rows)\n   for row in rows:\n    st=stickers[row[\"wb_order_id\"]]\n    assert st[\"barcode\"]==row[\"sticker_barcode\"]\n    assert str(st[\"partA\"])+\" \"+str(st[\"partB\"]).zfill(4)==row[\"sticker_code\"]\n    raw=row.pop(\"kiz\")\n    assert raw.startswith(\"01\") and raw[16:18]==\"21\"\n    row[\"kiz_gtin\"]=raw[2:16]\n    row[\"kiz_serial\"]=raw[18:].split(chr(29),1)[0]\n    row[\"wb_sticker_verified\"]=True\n  print(json.dumps({\"checked_at\":datetime.now(timezone.utc).isoformat(),\"rows\":rows,\"read_only\":True},ensure_ascii=False,default=str))\n  await s.rollback()\nasyncio.run(main())"
META = {
    "88900-007/54": ("Синее платье", "2009989381795", "5CRkDE8*j6pWG", "651"),
    "38900-001/48": ("Юбка-шорты", "4680163564715", "5pdyoyDSGtTmF", ""),
}

class Marker(Flowable):
    def __init__(self):
        super().__init__()
        self.width = 39*mm
        self.height = 14*mm
    def draw(self):
        self.canv.setStrokeColor(colors.HexColor("#697586"))
        self.canv.rect(0, 8*mm, 4*mm, 4*mm, fill=0)
        self.canv.setFont("Arial", 8)
        self.canv.drawString(6*mm, 9*mm, "Найден на товаре")
        self.canv.line(0, 2*mm, 38*mm, 2*mm)

def qr(value):
    widget = QrCodeWidget(value, barLevel="M", barBorder=4)
    x1,y1,x2,y2 = widget.getBounds()
    size = 17.5*mm
    drawing = Drawing(size,size,transform=[size/(x2-x1),0,0,size/(y2-y1),0,0])
    drawing.add(widget)
    return drawing

def main():
    command = "cd /opt/wms && docker compose -p wms_prod -f docker-compose.prod.yml -f docker-compose.wms-host-8088.yml exec -T api python -c " + shlex.quote(REMOTE_CODE)
    result = subprocess.run(["ssh","-o","BatchMode=yes","root@194.87.96.144",command],capture_output=True,text=True,timeout=120)
    if result.returncode:
        raise RuntimeError(result.stderr[-1500:])
    data = json.loads(result.stdout)
    rows = data["rows"]
    OUT.mkdir(parents=True,exist_ok=True)
    pdfmetrics.registerFont(TTFont("Arial","/System/Library/Fonts/Supplemental/Arial.ttf"))
    pdfmetrics.registerFont(TTFont("ArialBold","/System/Library/Fonts/Supplemental/Arial Bold.ttf"))
    when = datetime.fromisoformat(data["checked_at"]).astimezone(ZoneInfo("Europe/Moscow")).strftime("%d.%m.%Y %H:%M МСК")
    target = OUT / "Picking-reconciliation-14-existing-QR-A4.pdf"
    c = canvas.Canvas(str(target),pagesize=A4)
    c.setTitle("Лист подбора и сверки - 14 существующих QR WB")
    width,height = A4
    normal = ParagraphStyle("normal",fontName="Arial",fontSize=9,leading=12)
    header = ParagraphStyle("header",fontName="ArialBold",fontSize=8,leading=10,textColor=colors.white)
    number = 0
    for page,(sku,(name,barcode,photo_serial,label_no)) in enumerate(META.items(),1):
        subset = [row for row in rows if row["sku_code"]==sku]
        assert len(subset)==(4 if page==1 else 10)
        assert len({r["kiz_gtin"] for r in subset})==1
        assert len({r["wb_supply_id"] for r in subset})==1
        c.setFont("ArialBold",19)
        c.drawString(14*mm,height-17*mm,"ЛИСТ ПОДБОРА / СВЕРКИ QR")
        c.setFont("ArialBold",12)
        orders_label = "заказа" if len(subset) == 4 else "заказов"
        c.drawString(14*mm,height-26*mm,f"{name}  {sku}  |  {len(subset)} {orders_label}")
        c.setFont("Arial",9)
        c.drawString(14*mm,height-33*mm,f'ООО "фабрика"  |  {subset[0]["wb_supply_id"]}  |  {when}')
        c.drawString(14*mm,height-39*mm,f'ШК на упаковке: {barcode}  |  GTIN ЧЗ: {subset[0]["kiz_gtin"]}')
        c.setFillColor(colors.HexColor("#943700"))
        c.setFont("ArialBold",9)
        c.drawString(14*mm,height-46*mm,"ПО УЧЁТУ ЗАНЯТЫ. Лист для сверки, не комплект новых наклеек.")
        c.setFillColor(colors.black)
        c.setFont("Arial",8)
        c.drawString(14*mm,height-51*mm,"КИЗ в таблице: серийная часть после (21). Отметьте QR, найденные на собранных вещах.")
        table_rows = [[Paragraph(t,header) for t in ["№","QR WB","Номер QR / заказ WB","Текущий КИЗ<br/>(серийная часть)","Отметка / где найден"]]]
        for row in subset:
            number += 1
            row["sheet_page"] = page
            row["sheet_row"] = number
            table_rows.append([
                str(number),qr(row["sticker_barcode"]),
                Paragraph(f'<font name="ArialBold" size="11">{row["sticker_code"]}</font><br/><font size="8">Заказ {row["wb_order_id"]}</font>',normal),
                Paragraph(escape(row["kiz_serial"]),normal),Marker(),
            ])
        table = Table(table_rows,colWidths=[10*mm,25*mm,43*mm,59*mm,45*mm],rowHeights=[10*mm]+[20*mm]*len(subset))
        table.setStyle(TableStyle([
            ("BACKGROUND",(0,0),(-1,0),colors.HexColor("#233247")),
            ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,colors.HexColor("#F4F6F8")]),
            ("FONTNAME",(0,1),(-1,-1),"Arial"),("FONTSIZE",(0,1),(-1,-1),9),
            ("VALIGN",(0,0),(-1,-1),"MIDDLE"),("ALIGN",(0,1),(1,-1),"CENTER"),
            ("LEFTPADDING",(0,0),(-1,-1),5),("RIGHTPADDING",(0,0),(-1,-1),5),
            ("TOPPADDING",(0,1),(-1,-1),0),("BOTTOMPADDING",(0,1),(-1,-1),0),
            ("LINEBELOW",(0,0),(-1,-1),.3,colors.HexColor("#C7CDD6")),
        ]))
        _,th = table.wrap(182*mm,220*mm)
        table.drawOn(c,14*mm,height-56*mm-th)
        c.setFont("ArialBold",8)
        photo = f"КИЗ отложенной вещи{' №'+label_no if label_no else ''}: {photo_serial}"
        c.drawString(14*mm,23*mm,photo)
        c.setFont("Arial",8)
        c.drawString(14*mm,18*mm,"Этот КИЗ не совпадает с текущими привязками в таблице. Привязки не изменены.")
        c.drawString(14*mm,13*mm,"У всех QR зарегистрирован запуск печати; выход бумаги и наклеивание не подтверждены.")
        c.drawRightString(width-14*mm,8*mm,f"{page} / 2")
        c.showPage()
    c.save()
    assert number==14 and len(PdfReader(target).pages)==2
    content="\n".join(page.extract_text() for page in PdfReader(target).pages)
    for row in rows:
        assert row["sticker_code"] in content and row["kiz_serial"] in content
    (OUT/"reconciliation-14-verification.json").write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"output":str(target),"pages":2,"qr_count":number,"checked_at":data["checked_at"]},ensure_ascii=False))

if __name__=="__main__":
    main()
