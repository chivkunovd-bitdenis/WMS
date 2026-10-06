"""Addressed all-history attribution; SELECT only, existing tenant role."""
import csv
import hashlib
import io
import json
from datetime import datetime, timezone
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
# Load only common settings before collector's execution section.
base=Path(__file__).with_name('collect_scoped.py').read_text()
namespace={ '__file__':str(Path(__file__).with_name('collect_scoped.py')) }
exec(base[:base.index('def now():')],namespace)
settings,where,products,OUT,TENANT=(namespace[k] for k in ('settings','where','products','OUT','TENANT'))
run_query,sanitize_error=namespace['run_query'],namespace['sanitize_error']
def now(): return datetime.now(timezone.utc).isoformat()
queries={
'historical_fbs_attribution':f"WITH links AS (SELECT l.tenant_id,l.fbs_order_id,l.shipment_movement_id AS movement_id FROM fbs_shipment_reversal_ledger l WHERE l.shipment_movement_id IS NOT NULL UNION SELECT l.tenant_id,l.fbs_order_id,(x.value->>'movement_id')::uuid AS movement_id FROM fbs_shipment_reversal_ledger l CROSS JOIN LATERAL json_array_elements(l.ozon_positions_json::json) x(value) WHERE x.value->>'movement_id' IS NOT NULL AND x.value->>'movement_id' <> '') SELECT clock_timestamp() AS db_at,o.supply_id,s.name,s.status,count(DISTINCT m.id) AS movements,sum(m.quantity_delta) AS delta,count(DISTINCT o.id) AS orders,min(m.created_at) AS first_at,max(m.created_at) AS last_at FROM inventory_movements m JOIN links l ON l.movement_id=m.id AND l.tenant_id=m.tenant_id JOIN fbs_orders o ON o.id=l.fbs_order_id AND o.tenant_id=m.tenant_id LEFT JOIN fbs_supplies s ON s.id=o.supply_id WHERE m.tenant_id='{TENANT}' AND m.product_id IN ({products}) AND m.movement_type='fbs_shipment' GROUP BY o.supply_id,s.name,s.status ORDER BY o.supply_id LIMIT 60",
'balances_vs_all_movements':f"SELECT clock_timestamp() AS db_at,p.id AS product_id,coalesce((SELECT sum(b.quantity) FROM inventory_balances b WHERE b.tenant_id=p.tenant_id AND b.product_id=p.id),0) AS balances_quantity,coalesce((SELECT sum(m.quantity_delta) FROM inventory_movements m WHERE m.tenant_id=p.tenant_id AND m.product_id=p.id),0) AS all_movement_delta,(SELECT min(o.created_at) FROM fbs_orders o JOIN fbs_order_products q ON q.order_id=o.id WHERE {where} AND q.product_id=p.id) AS first_target_order_at FROM products p WHERE p.tenant_id='{TENANT}' AND p.id IN ({products}) ORDER BY p.id LIMIT 20",
'other_negative_movements_all_history':f"SELECT clock_timestamp() AS db_at,m.id,m.product_id,m.seller_id,m.storage_location_id,m.warehouse_id,m.quantity_delta,m.movement_type,m.created_at,m.inventory_count_line_id,m.outbound_shipment_line_id FROM inventory_movements m WHERE m.tenant_id='{TENANT}' AND m.product_id IN ({products}) AND m.quantity_delta<0 AND m.movement_type<>'fbs_shipment' ORDER BY m.created_at,m.id LIMIT 100",
}
manifest={'started_at':now(),'tenant_id':TENANT,'role':settings.db_role,'queries':[]}
for name,query in queries.items():
    (OUT/(name+'.sql')).write_text(query+'\n')
    entry={'name':name,'started_at':now(),'sql_file':name+'.sql'}
    try:
        result=run_query(settings,query)
        (OUT/(name+'.csv')).write_text(result)
        entry.update(status='ok',csv_file=name+'.csv',rows=len(list(csv.DictReader(io.StringIO(result)))),truncated='# вывод обрезан' in result,sha256=hashlib.sha256(result.encode()).hexdigest())
    except Exception as exc: entry.update(status='failed',error=sanitize_error(str(exc)))
    entry['finished_at']=now();manifest['queries'].append(entry)
    print(json.dumps(entry,ensure_ascii=False),flush=True)
manifest['finished_at']=now()
(OUT/'manifest-history.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
