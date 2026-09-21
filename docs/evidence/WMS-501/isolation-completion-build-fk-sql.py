import re
from pathlib import Path
out=Path(__file__).parent
checks=[]
for row in (out/'isolation-completion-production-metadata.txt').read_text().splitlines():
    bits=row.split('|')
    if len(bits)!=5: continue
    schema,c,col,p,pcol=bits
    assert all(re.fullmatch(r'[a-z0-9_]+', x) for x in bits)
    checks.append((f'{c}.{col}->{p}.{pcol}',f'"{c}" c JOIN "{p}" p ON p."{pcol}"=c."{col}"','c.tenant_id','p.tenant_id'))
nested=[('inbound_intake_lines','request_id','inbound_intake_requests','product_id','products'),
('inbound_intake_lines','request_id','inbound_intake_requests','storage_location_id','storage_locations'),
('outbound_shipment_lines','request_id','outbound_shipment_requests','product_id','products'),
('outbound_shipment_lines','request_id','outbound_shipment_requests','storage_location_id','storage_locations'),
('marketplace_unload_lines','request_id','marketplace_unload_requests','product_id','products'),
('packaging_task_lines','task_id','packaging_tasks','product_id','products'),
('packaging_task_lines','task_id','packaging_tasks','storage_location_id','storage_locations'),
('inventory_count_lines','count_id','inventory_counts','product_id','products'),
('inventory_count_lines','count_id','inventory_counts','storage_location_id','storage_locations'),
('discrepancy_act_lines','act_id','discrepancy_acts','product_id','products'),
('inbound_intake_box_lines','box_id','inbound_intake_boxes','product_id','products'),
('inbound_intake_cargo_place_lines','cargo_place_id','inbound_intake_cargo_places','product_id','products')]
for c,owner_fk,owner,target_fk,target in nested:
    checks.append((f'{c}: {owner}->{target}',f'"{c}" c JOIN "{owner}" r ON r.id=c."{owner_fk}" JOIN "{target}" p ON p.id=c."{target_fk}"','r.tenant_id','p.tenant_id'))
lines=['-- WMS-501 authorized production audit: aggregate counts only; no changes.',
       '-- Each check is bounded separately and a timeout is retained as incomplete, not retried.']
for label,source,left,right in checks:
    lines += ['BEGIN READ ONLY;',"SET LOCAL statement_timeout = '5s';","SET LOCAL lock_timeout = '1s';",
        f"SELECT '{label}' AS relation, count(*) AS linked_rows, count(*) FILTER (WHERE {left} IS DISTINCT FROM {right}) AS tenant_mismatches FROM {source};",'COMMIT;']
(out/'isolation-completion-production-fk.sql').write_text('\n'.join(lines)+'\n')
print('Bounded aggregate relationship checks:',len(checks))
