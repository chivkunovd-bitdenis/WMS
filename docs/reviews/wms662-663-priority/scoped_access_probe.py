"""Single bounded gateway probe; never submits a shipment or edits credentials."""
from dataclasses import asdict
import json

from support_agent.config import load_config
from support_agent.prod_sql import ProdSqlSettings, run_query, role_for_tenant, sanitize_error
from support_agent.seller_directory import SellerDirectory

TENANT = "b80a893b-ab87-42b6-8fd7-6d41502c900f"
c = load_config("/Users/deniscivkunov/.wms-support-agent/config.json").prod_db
settings = ProdSqlSettings(
    ssh_host=c.ssh_host, ssh_user=c.ssh_user, ssh_key_path=c.ssh_key_path,
    known_hosts=c.known_hosts, row_limit=60, timeout_sec=30,
    db_role=role_for_tenant(TENANT),
)
directory = SellerDirectory(settings)
try:
    directory.ensure_tenant(TENANT)
except Exception as exc:
    print(json.dumps({"ensure_tenant": "failed", "tenant_id": TENANT,
                      "error": sanitize_error(str(exc))}, ensure_ascii=False))
else:
    print(json.dumps({"ensure_tenant": "ok", "tenant_id": TENANT}))
    try:
        print(run_query(settings, f"""
            SELECT id,tenant_id,seller_id,warehouse_id,marketplace,
                   external_supply_id,wb_supply_id,name,source,status,
                   delivered_at,created_at,updated_at
            FROM fbs_supplies
            WHERE tenant_id = '{TENANT}'
              AND (id = '9f479e17-1723-49a1-a836-97eeff3d4ea2'
                   OR created_at >= '2026-10-01')
            ORDER BY created_at DESC LIMIT 60
        """))
    except Exception as exc:
        print(json.dumps({"bounded_read": "failed",
                          "error": sanitize_error(str(exc))}, ensure_ascii=False))

for name in ("Full Human", "FullHuman"):
    try:
        print(json.dumps({"find_tenants": name,
                          "matches": [asdict(row) for row in directory.find_tenants(name)]},
                         ensure_ascii=False))
    except Exception as exc:
        print(json.dumps({"find_tenants": name, "error": sanitize_error(str(exc))},
                         ensure_ascii=False))
