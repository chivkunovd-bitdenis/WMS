import asyncio,json,datetime
from sqlalchemy import text
from app.db.session import SessionLocal,engine
queries={'H': "WITH movement_by_line AS (\n  SELECT m.inbound_intake_line_id AS line_id,\n         count(*) AS movement_rows,\n         sum(m.quantity_delta) AS movement_qty\n  FROM inventory_movements m\n  WHERE m.tenant_id='7b98a8aa-c03c-4649-9677-a645be45c622'\n    AND m.movement_type='inbound_intake'\n    AND m.inbound_intake_line_id IS NOT NULL\n  GROUP BY m.inbound_intake_line_id\n), linked_lines AS (\n  SELECT r.id AS request_id,l.id AS line_id,r.status,\n         coalesce(l.actual_qty,0) AS actual_qty,\n         l.posted_qty,\n         m.movement_rows,m.movement_qty\n  FROM inbound_intake_lines l\n  JOIN inbound_intake_requests r ON r.id=l.request_id\n  JOIN movement_by_line m ON m.line_id=l.id\n  WHERE r.tenant_id='7b98a8aa-c03c-4649-9677-a645be45c622'\n)\nSELECT count(DISTINCT request_id) AS documents,\n       count(*) AS linked_lines,\n       sum(movement_rows) AS movement_rows,\n       sum(actual_qty) AS actual_qty,\n       sum(posted_qty) AS posted_qty,\n       sum(movement_qty) AS movement_qty,\n       count(*) FILTER (WHERE actual_qty=0 AND movement_qty>0)\n         AS positive_movement_zero_actual_lines,\n       count(*) FILTER (WHERE actual_qty<>movement_qty)\n         AS actual_movement_mismatch_lines\nFROM linked_lines"}
async def main():
 for key,query in queries.items():
  async with SessionLocal() as session:
   try:
    await session.execute(text("SET TRANSACTION READ ONLY"))
    await session.execute(text("SET LOCAL statement_timeout = '10s'"))
    await session.execute(text("SET LOCAL lock_timeout = '1s'"))
    data=(await session.execute(text(query))).mappings().all()
    print(json.dumps({"section":key,"checked_at_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),"rows":[dict(x) for x in data]},default=str),flush=True)
   except Exception as e:
    print(json.dumps({"section":key,"error_type":type(e).__name__,"detail":str(e).split("[SQL:")[0]},default=str),flush=True)
   finally: await session.rollback()
 await engine.dispose()
asyncio.run(main())
