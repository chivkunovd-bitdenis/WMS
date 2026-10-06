"""WMS-675: bounded SELECT evidence only; no access provisioning or marketplace mutation."""
import csv
import hashlib
import io
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'tools/support_agent'))
from support_agent.config import load_config
from support_agent.prod_sql import ProdSqlSettings, role_for_tenant, run_query, sanitize_error

OUT = Path(__file__).resolve().parent
TENANT = 'b80a893b-ab87-42b6-8fd7-6d41502c900f'
SUPPLY = 'b82d1e9a-30d2-4d7b-b52d-9775c3d266e3'
SELLER = 'cf6d31c5-944b-4382-af34-636ca9aa8cc3'
where = f"o.tenant_id='{TENANT}' AND o.supply_id='{SUPPLY}' AND o.seller_id='{SELLER}' AND o.marketplace='ozon'"
products = f"SELECT DISTINCT p.product_id FROM fbs_order_products p JOIN fbs_orders o ON o.id=p.order_id WHERE {where}"
config = load_config('/Users/deniscivkunov/.wms-support-agent/config.json').prod_db
settings = ProdSqlSettings(ssh_host=config.ssh_host, ssh_user=config.ssh_user,
    ssh_key_path=config.ssh_key_path, known_hosts=config.known_hosts,
    row_limit=100, timeout_sec=30, max_bytes=100000, db_role=role_for_tenant(TENANT))
QUERIES = {
'identity': f"SELECT clock_timestamp() AS db_at,current_user,current_setting('transaction_read_only') AS read_only,current_setting('row_security') AS rls,s.id,s.tenant_id,s.seller_id,s.warehouse_id,s.status,s.external_supply_id,s.wb_supply_id,s.created_at,s.updated_at FROM fbs_supplies s WHERE s.tenant_id='{TENANT}' AND s.id='{SUPPLY}' LIMIT 1",
'orders_positions_reserves': f"SELECT clock_timestamp() AS db_at,o.id,o.external_order_id,o.wb_order_id,o.status,o.wb_status,o.supplier_status,o.created_at,o.created_at_wb,o.updated_at,o.last_wb_sync_at,p.id AS position_id,p.product_id,p.ozon_sku,p.quantity,p.reserved_quantity,coalesce((SELECT sum(r.quantity) FROM fbs_order_reservations r WHERE r.fbs_order_id=o.id AND r.tenant_id=o.tenant_id),0) AS legacy_reserved,coalesce((SELECT sum(r.quantity) FROM fbs_order_product_reservations r WHERE r.order_product_id=p.id AND r.tenant_id=o.tenant_id),0) AS position_reserved FROM fbs_orders o JOIN fbs_order_products p ON p.order_id=o.id WHERE {where} ORDER BY o.external_order_id LIMIT 80",
'ledger': f"SELECT clock_timestamp() AS db_at,o.external_order_id,l.id,l.fbs_order_id,l.product_id,l.storage_location_id,l.source_warehouse_id,l.source_mode,l.quantity,l.shortage_quantity,l.negative_quantity,l.ozon_positions_json,l.shipment_movement_id,l.written_off_at,l.reversed_at,l.reversal_movement_id,l.created_at FROM fbs_orders o JOIN fbs_shipment_reversal_ledger l ON l.fbs_order_id=o.id AND l.tenant_id=o.tenant_id WHERE {where} ORDER BY o.external_order_id LIMIT 80",
'balances_locations': f"SELECT clock_timestamp() AS db_at,b.id,b.product_id,b.storage_location_id,s.warehouse_id,s.code,s.deleted_at,b.container_kind,b.container_id,b.quantity,b.quantity_unpacked,b.quantity_packed,b.updated_at FROM inventory_balances b JOIN storage_locations s ON s.id=b.storage_location_id WHERE b.tenant_id='{TENANT}' AND b.product_id IN ({products}) ORDER BY b.product_id,b.storage_location_id,b.id LIMIT 100",
'movements_types_all_history': f"SELECT clock_timestamp() AS db_at,m.product_id,m.movement_type,count(*) AS rows,sum(m.quantity_delta) AS delta,min(m.created_at) AS first_at,max(m.created_at) AS last_at,count(*) FILTER (WHERE m.quantity_delta<0) AS negative_rows FROM inventory_movements m WHERE m.tenant_id='{TENANT}' AND m.product_id IN ({products}) GROUP BY m.product_id,m.movement_type ORDER BY m.product_id,m.movement_type LIMIT 100",
'fbs_movements_all_history_links': f"SELECT clock_timestamp() AS db_at,m.product_id,count(*) AS rows,sum(m.quantity_delta) AS delta,min(m.created_at) AS first_at,max(m.created_at) AS last_at,count(*) FILTER(WHERE EXISTS(SELECT 1 FROM fbs_shipment_reversal_ledger l WHERE l.tenant_id=m.tenant_id AND (l.shipment_movement_id=m.id OR l.reversal_movement_id=m.id))) AS scalar_linked,count(*) FILTER(WHERE EXISTS(SELECT 1 FROM fbs_shipment_reversal_ledger l CROSS JOIN LATERAL json_array_elements(l.ozon_positions_json::json) x(value) WHERE l.tenant_id=m.tenant_id AND (x.value->>'movement_id'=m.id::text OR x.value->>'reversal_movement_id'=m.id::text))) AS recipe_linked,count(*) FILTER(WHERE NOT EXISTS(SELECT 1 FROM fbs_shipment_reversal_ledger l WHERE l.tenant_id=m.tenant_id AND (l.shipment_movement_id=m.id OR l.reversal_movement_id=m.id)) AND NOT EXISTS(SELECT 1 FROM fbs_shipment_reversal_ledger l CROSS JOIN LATERAL json_array_elements(l.ozon_positions_json::json) x(value) WHERE l.tenant_id=m.tenant_id AND (x.value->>'movement_id'=m.id::text OR x.value->>'reversal_movement_id'=m.id::text))) AS unlinked FROM inventory_movements m WHERE m.tenant_id='{TENANT}' AND m.product_id IN ({products}) AND m.movement_type='fbs_shipment' GROUP BY m.product_id ORDER BY m.product_id LIMIT 20",
'unlinked_fbs_movements': f"SELECT clock_timestamp() AS db_at,m.id,m.product_id,m.seller_id,m.storage_location_id,m.warehouse_id,m.quantity_delta,m.movement_type,m.created_at,m.outbound_shipment_line_id,m.transfer_group_id FROM inventory_movements m WHERE m.tenant_id='{TENANT}' AND m.product_id IN ({products}) AND m.movement_type='fbs_shipment' AND NOT EXISTS(SELECT 1 FROM fbs_shipment_reversal_ledger l WHERE l.tenant_id=m.tenant_id AND (l.shipment_movement_id=m.id OR l.reversal_movement_id=m.id)) AND NOT EXISTS(SELECT 1 FROM fbs_shipment_reversal_ledger l CROSS JOIN LATERAL json_array_elements(l.ozon_positions_json::json) x(value) WHERE l.tenant_id=m.tenant_id AND (x.value->>'movement_id'=m.id::text OR x.value->>'reversal_movement_id'=m.id::text)) ORDER BY m.created_at,m.id LIMIT 100",
'negative_other_movements_after_orders': f"SELECT clock_timestamp() AS db_at,m.product_id,m.movement_type,m.storage_location_id,m.warehouse_id,count(*) AS rows,sum(m.quantity_delta) AS delta,min(m.created_at) AS first_at,max(m.created_at) AS last_at,count(m.outbound_shipment_line_id) AS outbound_line_refs,count(m.inventory_count_line_id) AS inventory_count_refs,count(m.transfer_group_id) AS transfer_refs FROM inventory_movements m WHERE m.tenant_id='{TENANT}' AND m.product_id IN ({products}) AND m.quantity_delta<0 AND m.movement_type<>'fbs_shipment' AND m.created_at >= (SELECT min(o.created_at) FROM fbs_orders o WHERE {where}) GROUP BY m.product_id,m.movement_type,m.storage_location_id,m.warehouse_id ORDER BY m.product_id,m.movement_type LIMIT 100",
'position_picks': f"SELECT clock_timestamp() AS db_at,o.external_order_id,k.id,k.product_id,k.source_storage_location_id,k.sorting_storage_location_id,k.picked_at,k.undone_at FROM fbs_orders o JOIN fbs_order_products p ON p.order_id=o.id JOIN fbs_order_product_picks k ON k.order_product_id=p.id WHERE {where} ORDER BY o.external_order_id,k.id LIMIT 100",
}
def now(): return datetime.now(timezone.utc).isoformat()
manifest = {'started_at': now(), 'tenant_id':TENANT,'seller_id':SELLER,'supply_id':SUPPLY,'role':settings.db_role,'max_rows':100,'timeout_sec':30,'queries':[]}
manifest_path = OUT / ('manifest-'+sys.argv[1]+'.json' if len(sys.argv)>1 else 'manifest.json')
for name, query in QUERIES.items():
    if len(sys.argv)>1 and name != sys.argv[1]: continue
    entry = {'name':name,'started_at':now(),'sql_file':name+'.sql'}
    (OUT / (name+'.sql')).write_text(query+'\n')
    try:
        result = run_query(settings,query)
        (OUT/(name+'.csv')).write_text(result)
        entry.update(status='ok',csv_file=name+'.csv',rows=len(list(csv.DictReader(io.StringIO(result)))),truncated='# вывод обрезан' in result,sha256=hashlib.sha256(result.encode()).hexdigest())
    except Exception as exc:
        entry.update(status='failed',error=sanitize_error(str(exc)))
    entry['finished_at']=now()
    manifest['queries'].append(entry)
    manifest_path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(entry,ensure_ascii=False),flush=True)
manifest['finished_at']=now()
manifest_path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
if len(sys.argv)>1: sys.exit(0)
# Exact-name local Telegram evidence. No bot polling or outgoing calls.
db=sqlite3.connect('file:/Users/deniscivkunov/.wms-support-agent/state.db?mode=ro',uri=True)
db.row_factory=sqlite3.Row
needles=['%FullHuman%','%Full Human%','%Фул Хьюман%','%Фулхьюман%','%Фуллхьюман%']
clauses=' OR '.join(['text LIKE ? OR caption LIKE ?']*len(needles))
params=tuple(v for n in needles for v in (n,n))
identity={'observed_at':now(),'source':'local Telegram state.db, SQLite mode=ro','needles':needles,
 'binding_bambook':[dict(r) for r in db.execute('SELECT chat_id,seller_id,seller_name,tenant_id,tenant_name,bound_by,chat_title,level FROM chat_bindings WHERE chat_id=?',(-5515853898,))],
 'fullhuman_messages':[dict(r) for r in db.execute('SELECT id,source,chat_id,msg_id,author_id,ts,kind,text,caption,reply_to FROM messages WHERE '+clauses+' ORDER BY ts DESC LIMIT 30',params)],
 'fullhuman_revisions':[dict(r) for r in db.execute('SELECT message_id,revision,author_id,edited_at,text,caption FROM message_revisions WHERE '+clauses+' ORDER BY edited_at DESC LIMIT 30',params)],
 'fullhuman_bindings':[dict(r) for r in db.execute('SELECT chat_id,seller_id,seller_name,tenant_id,tenant_name,bound_by,chat_title,level FROM chat_bindings WHERE '+' OR '.join(['chat_title LIKE ? OR tenant_name LIKE ? OR seller_name LIKE ?']*len(needles))+' LIMIT 30',tuple(v for n in needles for v in (n,n,n)))]}
(OUT/'telegram_identity.json').write_text(json.dumps(identity,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'telegram_at':identity['observed_at'],'fullhuman_message_matches':len(identity['fullhuman_messages']),'revision_matches':len(identity['fullhuman_revisions']),'binding_matches':len(identity['fullhuman_bindings'])}))
