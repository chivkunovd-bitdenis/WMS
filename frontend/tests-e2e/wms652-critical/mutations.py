"""Purposeful product mutations in this isolated checkout; always restore bytes.

Invoke from repository root while the isolated Vite test server is running.
All HTTP/printer boundaries remain intercepted by browser.mjs.
"""
import json
import os
import subprocess
from pathlib import Path

root = Path.cwd()
evidence = Path(os.environ['WMS652_EVIDENCE'])
bar = root / 'frontend/src/screens/v2/FbsPackingScanBar.tsx'
sequential = root / 'frontend/src/screens/v2/fbsSequentialPacking.ts'
create = root / 'frontend/src/screens/v2/FbsSupplyCreateDialog.tsx'
group = root / 'frontend/src/screens/v2/FbsSupplyGroupCreateDialog.tsx'
screen = root / 'frontend/src/screens/v2/FfFbsOrdersScreen.tsx'
qr = 'await deps.print(current.result, await current.image, current.labelSizeId, intent.scanId)'
mutations = [
 ('disconnect-input', bar,
  "void routePackingScan(controllers, raw, 'сборке', serialQueue)", 'void Promise.resolve()'),
 ('skip-qr-print', sequential, qr, 'void current.image'),
 ('duplicate-qr-print', sequential, qr,
  qr + '\n        await deps.print(current.result, await current.image, current.labelSizeId, intent.scanId + ":UNWANTED_DUPLICATE")'),
 ('wrong-next-order', sequential,
  'pending = startPending(raw, result, attempt, explicit, needsKiz, bound)',
  'pending = startPending(raw, result, attempt, explicit, needsKiz, bound)\n      if (raw === "*DUIkNEXT") pending.result.order_id = "wb-a-order"'),
 ('wrong-selected-create-ids', create,
  '        order_ids: orderIds,', '        order_ids: [],'),
 ('repeat-successful-group', group,
  "const pendingGroups = compatibleGroups.filter((group) => results.get(group.key)?.status !== 'created')",
  'const pendingGroups = compatibleGroups'),
 ('wrong-selected-add-ids', screen,
  '        order_ids: selectedOrderIds,', '        order_ids: [],'),
]
results = []
for name, file, before, after in mutations:
 original = file.read_bytes()
 source = original.decode()
 assert source.count(before) == 1, (name, source.count(before))
 target = evidence / name
 target.mkdir(parents=True, exist_ok=True)
 try:
  file.write_text(source.replace(before, after))
  with (target / 'run.log').open('w') as log:
   run = subprocess.run(['node', 'frontend/tests-e2e/wms652-critical/browser.mjs'],
     env={**os.environ, 'WMS652_EVIDENCE': str(target)}, stdout=log, stderr=subprocess.STDOUT)
  report = json.loads((target / 'result.json').read_text())
  assert run.returncode != 0 and report['status'] == 'FAIL', (name, report)
  if name in {'disconnect-input', 'skip-qr-print', 'duplicate-qr-print', 'wrong-next-order'}:
   failed = [one for one in report['cases'] if one['id'].startswith('WMS652.realQr') and one['status'] == 'FAIL']
   assert len(failed) == 3, (name, report)
  results.append({'mutation': name, 'exit': run.returncode, 'cases': report['cases'], 'failure': report.get('failure')})
  print(name + ': expected RED', flush=True)
 finally:
  file.write_bytes(original)
  assert file.read_bytes() == original
(evidence / 'mutations.json').write_text(json.dumps(results, indent=2, ensure_ascii=False))
