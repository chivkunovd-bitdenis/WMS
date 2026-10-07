"""Read only the exact current ledger-linked movements through the tenant gateway."""
import csv
import hashlib
import io
import json
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'tools/support_agent'))
from support_agent.config import load_config
from support_agent.prod_sql import ProdSqlSettings, role_for_tenant, run_query

tenant = 'b80a893b-ab87-42b6-8fd7-6d41502c900f'
rows = list(csv.DictReader((HERE / 'accounting-after-20261007T080200Z/ledger.csv').open()))
ids = sorted({str(uuid.UUID(recipe['movement_id'])) for row in rows
              for recipe in json.loads(row['ozon_positions_json']) if recipe.get('movement_id')})
assert len(rows) == 31 and len(ids) == 26
query = (
    "SELECT clock_timestamp() AS db_at,id,tenant_id,seller_id,product_id,storage_location_id,"
    "warehouse_id,quantity_delta,movement_type,created_at FROM inventory_movements "
    "WHERE tenant_id='" + tenant + "' AND id IN (" + ','.join("'" + x + "'" for x in ids)
    + ') ORDER BY id LIMIT 27'
)
cfg = load_config('/Users/deniscivkunov/.wms-support-agent/config.json').prod_db
settings = ProdSqlSettings(ssh_host=cfg.ssh_host, ssh_user=cfg.ssh_user,
    ssh_key_path=cfg.ssh_key_path, known_hosts=cfg.known_hosts, row_limit=200,
    timeout_sec=30, max_bytes=200000, db_role=role_for_tenant(tenant))
(HERE / 'linked-movements.sql').write_text(query + '\n')
result = run_query(settings, query)
assert '# вывод обрезан' not in result
actual = list(csv.DictReader(io.StringIO(result)))
assert len(actual) == 26 and {x['id'] for x in actual} == set(ids)
(HERE / 'linked-movements.csv').write_text(result)
(HERE / 'linked-movements-read.json').write_text(json.dumps({
    'writes': 0, 'scope': tenant, 'rows': len(actual),
    'query_sha256': hashlib.sha256(query.encode()).hexdigest(),
    'csv_sha256': hashlib.sha256(result.encode()).hexdigest(),
}, indent=2) + '\n')
print('linked_movement_read_complete rows=26 writes=0')
