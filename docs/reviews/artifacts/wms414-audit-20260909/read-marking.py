import asyncio,json,datetime
from sqlalchemy import text
from app.db.session import SessionLocal,engine
queries={'marking_shape': 'SELECT\n    status,\n    source,\n    (printed_at IS NOT NULL) AS has_printed_at,\n    (product_id IS NOT NULL) AS has_product_id,\n    COUNT(*) AS code_count\nFROM marking_codes\nGROUP BY\n    status,\n    source,\n    (printed_at IS NOT NULL),\n    (product_id IS NOT NULL)\nORDER BY status, source, has_printed_at, has_product_id', 'reserved_age': "SELECT\n    CASE\n        WHEN reserved_at IS NULL THEN 'reserved_at_null'\n        WHEN reserved_at >= CURRENT_TIMESTAMP - INTERVAL '15 minutes' THEN 'under_15m'\n        WHEN reserved_at >= CURRENT_TIMESTAMP - INTERVAL '1 hour' THEN '15m_to_1h'\n        WHEN reserved_at >= CURRENT_TIMESTAMP - INTERVAL '24 hours' THEN '1h_to_24h'\n        WHEN reserved_at >= CURRENT_TIMESTAMP - INTERVAL '7 days' THEN '1d_to_7d'\n        ELSE 'over_7d'\n    END AS reserved_age,\n    (reserved_by_user_id IS NOT NULL) AS has_reserving_user,\n    COUNT(*) AS code_count\nFROM marking_codes\nWHERE status = 'reserved'\nGROUP BY reserved_age, (reserved_by_user_id IS NOT NULL)\nORDER BY reserved_age, has_reserving_user", 'printed_product_invariant': "SELECT\n    status,\n    COUNT(*) FILTER (WHERE printed_at IS NOT NULL AND product_id IS NULL) AS printed_without_product,\n    COUNT(*) FILTER (WHERE printed_at IS NULL AND product_id IS NOT NULL) AS product_without_print_time,\n    COUNT(*) AS total_in_status\nFROM marking_codes\nWHERE status IN ('printed', 'applied', 'introduced', 'shipped', 'transferred')\nGROUP BY status\nORDER BY status", 'recovery_shape': "SELECT\n    status,\n    char_length(cis_code) AS stored_length,\n    (right(cis_code, 1) = chr(29)) AS ends_with_group_separator,\n    (label_artifact_pdf IS NOT NULL) AS has_own_pdf_artifact,\n    COUNT(*) AS code_count\nFROM marking_codes\nWHERE source = 'pool'\n  AND import_batch_id IS NOT NULL\nGROUP BY\n    status,\n    char_length(cis_code),\n    (right(cis_code, 1) = chr(29)),\n    (label_artifact_pdf IS NOT NULL)\nORDER BY status, stored_length, ends_with_group_separator, has_own_pdf_artifact"}
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
