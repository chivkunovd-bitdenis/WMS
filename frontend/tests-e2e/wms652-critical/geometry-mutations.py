"""C59 product faults: hidden row action, overlapped header, hidden long-data action."""
import json
import os
import subprocess
from pathlib import Path

root = Path.cwd()
evidence = Path(os.environ['WMS652_EVIDENCE'])
workspace = root / 'frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx'
orders = root / 'frontend/src/screens/v2/FfFbsOrdersScreen.tsx'
mutations = [
 ('hide-packing-print-action', workspace,
  'aria-label="Печать ЧЗ и ШК" data-task-id="FBS-10"',
  'aria-label="Печать ЧЗ и ШК" style={{ display: "none" }} data-task-id="FBS-10"',
  ['WMS652.geometry[' + entry + ';1600x1000-long]' for entry in [
    'wb-single', 'wb-group-one', 'wb-group-many', 'ozon-single', 'ozon-group-one', 'ozon-group-many', 'mixed-group-many']]),
 ('overlap-order-seller-header', orders,
  '<TableCell sx={{ minWidth: 125 }}>Селлер</TableCell>',
  '<TableCell sx={{ minWidth: 125, position: "relative", left: -80 }}>Селлер</TableCell>',
  ['WMS652.geometry[orders-expired;1600x1000-long]', 'WMS652.geometry[orders-cancelled;1600x1000-long]']),
 ('hide-selected-action-only-for-long-data', orders,
  'data-testid="fbs-selected-open"',
  'data-testid="fbs-selected-open" style={{ display: selectedOrders.some(o => o.product.name.includes("длинное название товара")) ? "none" : undefined }}',
  ['WMS652.geometry[selection;1600x1000-long]']),
]
results = []
for name, product, before, after, expected in mutations:
 original = product.read_bytes()
 source = original.decode()
 assert source.count(before) == 1, (name, source.count(before))
 target = evidence / name
 target.mkdir(parents=True, exist_ok=True)
 try:
  product.write_text(source.replace(before, after))
  with (target / 'run.log').open('w') as log:
   run = subprocess.run(['node', 'frontend/tests-e2e/wms652-critical/browser.mjs'],
     env={**os.environ, 'WMS652_EVIDENCE': str(target)}, stdout=log, stderr=subprocess.STDOUT)
  report = json.loads((target / 'result.json').read_text())
  failed = [case for case in report['cases'] if case['status'] == 'FAIL']
  assert run.returncode == 1 and report['status'] == 'FAIL', report
  assert [case['id'] for case in failed] == expected, report
  assert len(report['cases']) == 43 and all(
    case['status'] == 'PASS' for case in report['cases'] if case['id'] not in expected), report
  reason = 'order table columns must not overlap' if name.startswith('overlap') else 'visible unobscured bounds'
  assert all(reason in case['failure'] for case in failed), failed
  results.append({'mutation': name, 'sourceSha': report['sha'], 'failed': failed,
                  'otherCasesPass': 43 - len(expected), 'productBytesRestoredInFinally': True})
  print(name + ': expected RED on ' + str(len(expected)) + ' target geometry cases', flush=True)
 finally:
  product.write_bytes(original)
  assert product.read_bytes() == original
(evidence / 'mutations.json').write_text(json.dumps(results, indent=2, ensure_ascii=False))
