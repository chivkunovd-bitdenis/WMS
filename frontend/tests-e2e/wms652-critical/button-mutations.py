"""Visibility and actual second-submit regressions through real mouse input."""
import json
import os
import subprocess
from pathlib import Path

root = Path.cwd()
evidence = Path(os.environ['WMS652_EVIDENCE'])
mutations = [
 ('hide-create-button', root / 'frontend/src/screens/v2/FbsSupplyCreateDialog.tsx',
  'data-testid="fbs-create-submit"', 'data-testid="fbs-create-submit" style={{ display: "none" }}'),
 ('duplicate-groups-after-real-mouse-retry', root / 'frontend/src/screens/v2/FbsSupplyGroupCreateDialog.tsx',
  '        pendingGroups,\n        results,', '        compatibleGroups,\n        new Map(),'),
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
  if name == 'hide-create-button':
   assert report['currentCase'] == 'WMS652.selection[single-create]', report
   assert 'visible unobscured bounds' in report['failure'], report
   assert 'fbs-create-submit' in report['failure'], report
   requests = json.loads((target / 'last-requests.json').read_text())['requestLog']
   assert not [one for one in requests if one['path'] == '/operations/fbs-supplies/from-orders'], requests
  else:
   requests = json.loads((target / 'last-requests.json').read_text())['requestLog']
   posts = [one for one in requests if one['path'] == '/operations/fbs-supplies/from-orders']
   assert len(posts) == 6 and '6 !== 4' in report['failure'], (posts, report)
  results.append({'mutation': name, 'exit': run.returncode, 'cases': report['cases'], 'failure': report['failure']})
  print(name + ': expected RED', flush=True)
 finally:
  file.write_bytes(original)
  assert file.read_bytes() == original
(evidence / 'mutations.json').write_text(json.dumps(results, indent=2, ensure_ascii=False))
