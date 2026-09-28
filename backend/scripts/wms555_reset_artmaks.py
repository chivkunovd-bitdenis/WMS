"""Approved one-off reset; stdout is a private before/after backup, never Git."""

import asyncio
import json
import sys
import uuid
from typing import Any

from sqlalchemy import text

from app.db.session import SessionLocal

REQ = "f140d4ca-cf60-402e-90cd-7fa9d8815f9d"
TENANT = "82b36645-8662-497f-9631-a0743994632c"
WAREHOUSE = "5740eda2-b353-4c98-9755-0f2df4e862bc"
SORTING = "9f3fbb36-2996-43bb-a2b8-4e7fe4ba9977"


async def main() -> None:
    async with SessionLocal() as s:
        await s.execute(text("SET LOCAL lock_timeout='5s'"))
        await s.execute(text("SET LOCAL statement_timeout='20s'"))
        params = {"req": REQ, "tenant": TENANT, "warehouse": WAREHOUSE, "sorting": SORTING}

        async def rows(sql: str) -> list[dict[str, Any]]:
            return [dict(row) for row in (await s.execute(text(sql), params)).mappings()]

        request = await rows("SELECT * FROM inbound_intake_requests WHERE id=:req FOR UPDATE")
        assert len(request) == 1 and str(request[0]["tenant_id"]) == TENANT
        assert str(request[0]["warehouse_id"]) == WAREHOUSE and request[0]["status"] == "sorting"
        await rows(
            "SELECT p.id FROM products p JOIN inbound_intake_lines l ON l.product_id=p.id "
            "WHERE l.request_id=:req ORDER BY p.id FOR UPDATE OF p"
        )
        lines = await rows(
            "SELECT * FROM inbound_intake_lines WHERE request_id=:req ORDER BY id FOR UPDATE"
        )
        boxes = await rows(
            "SELECT * FROM inbound_intake_boxes WHERE request_id=:req ORDER BY id FOR UPDATE"
        )
        balances = await rows(
            "SELECT b.* FROM inventory_balances b "
            "JOIN inbound_intake_lines l ON l.product_id=b.product_id "
            "WHERE l.request_id=:req AND b.tenant_id=:tenant ORDER BY b.id FOR UPDATE OF b"
        )
        receipts = await rows(
            "SELECT * FROM inbound_intake_distribution_lines WHERE request_id=:req "
            "ORDER BY id FOR UPDATE"
        )
        contents = await rows(
            "SELECT l.* FROM inbound_intake_box_lines l "
            "JOIN inbound_intake_boxes b ON b.id=l.box_id "
            "WHERE b.request_id=:req FOR UPDATE OF l"
        )
        assert len(lines) == 321 and sum(x["actual_qty"] for x in lines) == 4139
        assert sum(x["posted_qty"] for x in lines) == 59 and all(
            x["defective_qty"] == 0 for x in lines
        )
        assert len(receipts) == 59 and sum(x["quantity"] for x in receipts) == 59
        assert len(boxes) == 60 and not contents
        assert all(
            str(x["storage_location_id"]) == SORTING and x["pallet_id"] is None for x in boxes
        )
        positive = [b for b in balances if b["quantity"] > 0]
        assert all(
            str(b["storage_location_id"]) == SORTING
            and b["quantity_unpacked"] == b["quantity"]
            and b["quantity_packed"] == 0
            for b in positive
        )
        for line in lines:
            assert (
                sum(b["quantity"] for b in positive if b["product_id"] == line["product_id"])
                == line["actual_qty"]
            )
        boxed = [b for b in positive if b["container_id"] is not None]
        assert sum(b["quantity"] for b in boxed) == 2
        assert all(
            b["container_kind"] == "box" and b["container_id"] in {x["id"] for x in boxes}
            for b in boxed
        )
        print(
            json.dumps(
                {
                    "before": {
                        "request": request,
                        "lines": lines,
                        "boxes": boxes,
                        "balances": balances,
                        "receipts": receipts,
                        "contents": contents,
                    }
                },
                default=str,
            ),
            flush=True,
        )
        for source in boxed:
            target = next(
                b
                for b in balances
                if b["product_id"] == source["product_id"]
                and str(b["storage_location_id"]) == SORTING
                and b["container_id"] is None
            )
            line = next(x for x in lines if x["product_id"] == source["product_id"])
            move = dict(
                params,
                product=source["product_id"],
                source=source["id"],
                target=target["id"],
                box=source["container_id"],
                qty=source["quantity"],
                line=line["id"],
                group=uuid.uuid4(),
            )
            await s.execute(
                text("""INSERT INTO inventory_movements
                (id,tenant_id,product_id,seller_id,storage_location_id,warehouse_id,quantity_delta,movement_type,transfer_group_id,container_kind,container_id,inbound_intake_line_id,reporting_dimensions_legacy)
                SELECT gen_random_uuid(),p.tenant_id,p.id,p.seller_id,CAST(:sorting AS uuid),
                    CAST(:warehouse AS uuid),-CAST(:qty AS integer),'container_reattach',
                    CAST(:group AS uuid),'box',CAST(:box AS uuid),CAST(:line AS uuid),false
                    FROM products p WHERE p.id=:product
                UNION ALL
                SELECT gen_random_uuid(),p.tenant_id,p.id,p.seller_id,CAST(:sorting AS uuid),
                    CAST(:warehouse AS uuid),CAST(:qty AS integer),'container_reattach',
                    CAST(:group AS uuid),NULL,NULL,CAST(:line AS uuid),false
                    FROM products p WHERE p.id=:product"""),
                move,
            )
            await s.execute(
                text(
                    "UPDATE inventory_balances SET quantity=quantity+:qty,"
                    "quantity_unpacked=quantity_unpacked+:qty,updated_at=now() WHERE id=:target"
                ),
                move,
            )
            await s.execute(
                text(
                    "UPDATE inventory_balances SET quantity=0,quantity_unpacked=0,"
                    "quantity_packed=0,updated_at=now() WHERE id=:source"
                ),
                move,
            )
        await s.execute(
            text("UPDATE inbound_intake_lines SET posted_qty=0 WHERE request_id=:req"), params
        )
        # Retain map events and movement history. Old scan IDs remain blocked by
        # their map-event receipt instead of becoming new physical scans.
        await s.execute(
            text("DELETE FROM inbound_intake_distribution_lines WHERE request_id=:req"), params
        )
        after = await rows(
            "SELECT b.* FROM inventory_balances b "
            "JOIN inbound_intake_lines l ON l.product_id=b.product_id "
            "WHERE l.request_id=:req AND b.tenant_id=:tenant AND b.quantity>0"
        )
        assert len(after) == 321 and all(
            b["container_id"] is None and str(b["storage_location_id"]) == SORTING for b in after
        )
        for line in lines:
            assert (
                sum(b["quantity"] for b in after if b["product_id"] == line["product_id"])
                == line["actual_qty"]
            )
        apply = "--apply" in sys.argv
        if apply:
            await s.commit()
        else:
            await s.rollback()
        print(
            json.dumps(
                {
                    "committed": apply,
                    "request": REQ,
                    "accepted": 4139,
                    "loose": sum(b["quantity"] for b in after),
                    "empty_boxes": 60,
                    "posted": 0,
                    "after": after,
                },
                default=str,
            ),
            flush=True,
        )


asyncio.run(main())
