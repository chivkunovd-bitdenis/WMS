"""Change only the restored explicit selection key, preserving native print keys."""
import json
import os
import subprocess
from pathlib import Path

root = Path.cwd()
evidence = Path(os.environ['WMS652_EVIDENCE'])
evidence.mkdir(parents=True, exist_ok=True)
product = root / 'frontend/src/screens/v2/fbsSequentialPacking.ts'
original = product.read_bytes()
source = original.decode()
before = 'const result = await deps.select(raw, saved.key, saved.preferences, saved.orderId)'
after = 'const result = await deps.select(raw, crypto.randomUUID(), saved.preferences, saved.orderId)'
assert source.count(before) == 1
try:
 product.write_text(source.replace(before, after))
 with (evidence / 'run.log').open('w') as log:
  run = subprocess.run(['node', 'frontend/tests-e2e/wms652-critical/browser.mjs'],
    env={**os.environ, 'WMS652_EVIDENCE': str(evidence)}, stdout=log, stderr=subprocess.STDOUT)
 report = json.loads((evidence / 'result.json').read_text())
 failed = [case for case in report['cases'] if case['status'] == 'FAIL']
 expected = [f'WMS652.realQrFlags[remount-after-lost-ack;{entry}]'
             for entry in ['supply_id=A', 'supply_ids=A', 'supply_ids=A,B']]
 assert run.returncode == 1 and report['status'] == 'FAIL', report
 assert [case['id'] for case in failed] == expected, report
 assert len(report['cases']) == 33 and all(
   case['status'] == 'PASS' for case in report['cases'] if case['id'] not in expected), report
 for case in failed:
  assert 'restored explicit selection must reuse initial idempotency key' in case['failure'], case
  path = evidence / (''.join(c if c.isascii() and (c.isalnum() or c in '_-') else '-' for c in case['id']) + '.json')
  trace = json.loads(path.read_text())
  selections = [r for r in trace['requestLog'] if r['path'].endswith('/scan-auto-print')
                and r['body'] and r['body'].get('order_id') == 'wb-a-order']
  assert len(selections) == 2, selections
  keys = [r['body']['idempotency_key'] for r in selections]
  assert all(isinstance(key, str) and key.strip() for key in keys) and keys[0] != keys[1], keys
  assert [r['body']['barcode'] for r in selections] == ['*DUIkWJJF', '*DUIkWJJF'], selections
  assert [job['idempotencyKey'] for job in trace['printLog']] == [
    'scan-wb-a-order', 'scan-wb-a-order', 'scan-wb-next-order'], trace['printLog']
  assert trace['acceptedPrintKeys'] == ['scan-wb-a-order', 'scan-wb-next-order'], trace
  assert [r['body']['order_id'] for r in trace['requestLog'] if r['path'].endswith('/pack')] == [
    'wb-a-order', 'wb-next-order'], trace
 (evidence / 'mutation-proof.json').write_text(json.dumps({
   'mutation': 'new-key-only-on-restored-explicit-selection', 'sourceSha': report['sha'],
   'failed': failed, 'otherCasesPass': 30, 'nativePrintKeysUnchanged': True,
   'productBytesRestoredInFinally': True,
 }, indent=2, ensure_ascii=False))
 print('three remount selection-key cases: expected RED; other30PASS; native print keys unchanged', flush=True)
finally:
 product.write_bytes(original)
 assert product.read_bytes() == original
