"""WMS-675 exact-scope accounting refresh via installed read-only gateway only."""
import csv
import hashlib
import io
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'tools/support_agent'))

TENANT = 'b80a893b-ab87-42b6-8fd7-6d41502c900f'
SELLER = 'cf6d31c5-944b-4382-af34-636ca9aa8cc3'
SUPPLY = 'b82d1e9a-30d2-4d7b-b52d-9775c3d266e3'
SCOPE = f"o.tenant_id='{TENANT}' AND o.seller_id='{SELLER}' AND o.supply_id='{SUPPLY}' AND o.marketplace='ozon'"
ORDERS = f'SELECT o.id FROM fbs_orders o WHERE {SCOPE}'


def now():
    return datetime.now(timezone.utc).isoformat()


def main():
    from support_agent.config import load_config
    from support_agent.prod_sql import ProdSqlSettings, role_for_tenant, run_query, sanitize_error
    out = HERE / 'accounting-refresh-20261006-attempt1'
    out.mkdir(exist_ok=False)
    cfg = load_config('/Users/deniscivkunov/.wms-support-agent/config.json').prod_db
    settings = ProdSqlSettings(ssh_host=cfg.ssh_host, ssh_user=cfg.ssh_user,
        ssh_key_path=cfg.ssh_key_path, known_hosts=cfg.known_hosts,
        row_limit=200, timeout_sec=30, max_bytes=200000, db_role=role_for_tenant(TENANT))
    queries = {n: (HERE / (n + '.sql')).read_text().strip() for n in (
        'identity', 'orders_positions_reserves', 'ledger', 'unlinked_fbs_movements',
        'balances_vs_all_movements', 'balances_locations')}
    queries['orders_positions_reserves'] = queries['orders_positions_reserves'].replace('p.ozon_sku,', 'p.ozon_sku,p.offer_id,')
    queries['ledger'] = queries['ledger'].replace('l.created_at', 'l.wb_operation_id,l.created_at')
    queries['new_history_attribution'] = (HERE / 'historical_fbs_attribution.sql').read_text().strip().replace("AND m.movement_type='fbs_shipment'", "AND m.movement_type='fbs_shipment' AND m.created_at >= '2026-10-06 06:53:00+00'")
    queries['other_negative_since_audit'] = (HERE / 'negative_other_movements_after_orders.sql').read_text().strip().replace('GROUP BY m.product_id', "AND m.created_at >= '2026-10-06 06:53:00+00' GROUP BY m.product_id")
    queries['billing_entries'] = f"SELECT clock_timestamp() AS db_at,b.id,b.source_id,b.source_type,b.service_code,b.entry_type,b.event_kind,b.quantity,b.amount,b.reversal_of_id,b.occurred_at,b.created_at,(SELECT sum(l.physical_quantity) FROM billing_ledger_lines l WHERE l.tenant_id=b.tenant_id AND l.ledger_entry_id=b.id) AS physical_quantity,(SELECT sum(l.billing_quantity) FROM billing_ledger_lines l WHERE l.tenant_id=b.tenant_id AND l.ledger_entry_id=b.id) AS billing_quantity FROM billing_ledger_entries b WHERE b.tenant_id='{TENANT}' AND b.seller_id='{SELLER}' AND b.source_id IN ({ORDERS}) ORDER BY b.source_id,b.service_code,b.created_at LIMIT 180"
    queries['operation_facts'] = f"SELECT clock_timestamp() AS db_at,f.id,f.document_id,f.source_event_id,f.source_kind,f.operation_code,f.item_quantity,f.idempotency_key,f.created_at FROM operation_facts f WHERE f.tenant_id='{TENANT}' AND f.seller_id='{SELLER}' AND (f.document_id IN ({ORDERS}) OR f.source_event_id IN ({ORDERS})) ORDER BY f.document_id,f.operation_code,f.created_at LIMIT 100"
    queries['supply_operations'] = f"SELECT clock_timestamp() AS db_at,p.id,p.operation_kind,p.idempotency_key,p.local_entity_id,p.state,p.error_code,p.confirmed_at,p.created_at,p.updated_at,(p.request_summary_json::json->'ozon_handoff_progress'->>'carriage_approved') AS carriage_approved FROM fbs_wb_operations p WHERE p.tenant_id='{TENANT}' AND p.seller_id='{SELLER}' AND (p.local_entity_id='{SUPPLY}' OR p.local_entity_id IN ({ORDERS})) ORDER BY p.created_at,p.id LIMIT 100"
    manifest = {'tenant_id':TENANT,'seller_id':SELLER,'supply_id':SUPPLY,'started_at':now(),
                'role': settings.db_role, 'queries':[], 'writes':0, 'external_calls':0,
                'snapshot_consistency':'Separate gateway SELECTs; freshness must be rechecked under WMS-662 locks before mutation.'}
    for name, query in queries.items():
        (out / (name + '.sql')).write_text(query + '\n')
        entry = {'name':name,'started_at':now(),'sql_file':name+'.sql'}
        try:
            result = run_query(settings, query)
            truncated = '# вывод обрезан' in result
            if truncated:
                raise ValueError('truncated_result')
            (out / (name + '.csv')).write_text(result)
            entry.update(status='ok',csv_file=name+'.csv',rows=len(list(csv.DictReader(io.StringIO(result)))),
                         truncated=False,sha256=hashlib.sha256(result.encode()).hexdigest())
        except Exception as exc:
            entry.update(status='failed',error=sanitize_error(str(exc)))
        entry['finished_at'] = now()
        manifest['queries'].append(entry)
        (out / 'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
        print(json.dumps(entry,ensure_ascii=False), flush=True)
    manifest['finished_at'] = now()
    (out / 'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    return 0 if all(q['status']=='ok' for q in manifest['queries']) else 2


if __name__ == '__main__':
    sys.exit(main())
