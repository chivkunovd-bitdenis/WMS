"""Purposeful extended real-screen mutations. No permanent product changes."""
import json
import os
import subprocess
from pathlib import Path

root = Path.cwd()
evidence = Path(os.environ['WMS652_EVIDENCE'])
sequential = root / 'frontend/src/screens/v2/fbsSequentialPacking.ts'
group = root / 'frontend/src/screens/v2/FbsSupplyGroupCreateDialog.tsx'
mutations = [
 ('swap-canonical-cis', sequential,
  'cis: claim.kiz, codeId: claim.code_id,',
  'cis: claim.kiz.includes("SERIAL-A") ? "010460000000000221SERIAL-B\\u001d91EFGH\\u001d92signed-B" : "010460000000000121SERIAL-A\\u001d91ABCD\\u001d92signed-A", codeId: claim.code_id,'),
 ('repeat-successful-group-on-second-submit', group,
  '        pendingGroups,\n        results,',
  '        compatibleGroups,\n        new Map(),'),
 ('double-pack-quantity', sequential,
  'quantity: 1, order_id: result.order_id, idempotency_key: packingScanPackKey(result),',
  'quantity: 2, order_id: result.order_id, idempotency_key: packingScanPackKey(result),'),
 ('new-print-intent-on-retry', sequential,
  'return dispatchPreparedQrInKiosk({ imageDataUrl, idempotencyKey, widthMm: size.widthMm, heightMm: size.heightMm })',
  'return dispatchPreparedQrInKiosk({ imageDataUrl, idempotencyKey: idempotencyKey + ":" + crypto.randomUUID(), widthMm: size.widthMm, heightMm: size.heightMm })'),
 ('allocate-pool-for-explicit-sticker', sequential,
  'print_chz: orderId ? false : snapshot.printChz,',
  'print_chz: snapshot.printChz,'),
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
  failed = [one for one in report['cases'] if one['status'] == 'FAIL']
  if name == 'swap-canonical-cis':
   assert len([one for one in failed if 'reprint' in one['id'] or one['id'].startswith('WMS652.realQr[')]) == 9, report
   assert all('native cop' in one['failure'] for one in failed), report
  if name == 'double-pack-quantity':
   assert len([one for one in failed if one['id'].startswith('WMS652.realQrFlags[')]) == 27, report
  if name == 'new-print-intent-on-retry':
   assert len([one for one in failed if any(kind in one['id'] for kind in ['held-receipt','lost-accepted-ack','remount-after-lost-ack'])]) == 9, report
  if name == 'allocate-pool-for-explicit-sticker':
   assert len([one for one in failed if 'qr+pool;' in one['id']]) == 3, report
  if name == 'repeat-successful-group-on-second-submit':
   requests = json.loads((target / 'last-requests.json').read_text())['requestLog']
   posts = [one for one in requests if one['path'] == '/operations/fbs-supplies/from-orders']
   assert len(posts) == 6, posts
   assert len([one for one in posts if one['body']['order_ids'] == ['order-a']]) == 2, posts
   assert '6 !== 4' in report['failure'], report
  results.append({'mutation':name,'exit':run.returncode,'failed':failed,'failure':report.get('failure')})
  print(name + ': expected RED', flush=True)
 finally:
  file.write_bytes(original)
  assert file.read_bytes() == original
(evidence / 'mutations.json').write_text(json.dumps(results, indent=2, ensure_ascii=False))
