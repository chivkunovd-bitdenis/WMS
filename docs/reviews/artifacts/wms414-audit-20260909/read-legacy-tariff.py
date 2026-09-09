import asyncio,json,datetime
from sqlalchemy import text
from app.db.session import SessionLocal,engine
queries={'legacy_tariff_units': "SELECT service_code, unit, count(*) rows FROM billing_tariff_versions WHERE tenant_id='7b98a8aa-c03c-4649-9677-a645be45c622' GROUP BY service_code,unit ORDER BY service_code,unit"}
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
