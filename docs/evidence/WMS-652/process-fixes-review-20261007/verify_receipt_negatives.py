"""Reject missing/nonpass new mandatory receipts using real report inputs.

Mutations below are synthetic negative fixtures, never saved as release proof.
"""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
TARGET = '65049df62d2bac87932fc5349f6326caec43dea5'
sys.path.insert(0, str(ROOT))
from scripts.ci import process_contracts as pc

assert (ROOT / 'scripts/ci/process_contracts.py').read_bytes() == subprocess.check_output(['git', 'show', TARGET + ':scripts/ci/process_contracts.py'], cwd=ROOT)
policy = json.loads(subprocess.check_output(['git', 'show', TARGET + ':guards/PROCESS_CONTRACTS.json'], cwd=ROOT))
inputs = {
    'ci-shards': ROOT / 'docs/evidence/WMS-652/process-fixes-20261007/ci-shards-process-final.xml',
    'docgate-687': HERE / 'docgate-687.xml',
    'pg-654': ROOT / 'docs/evidence/WMS-654/combined-postgres-20261007.xml',
    'print-672-c5a': ROOT / 'docs/evidence/WMS-652/closure-20261007/wms672-c5a.json',
}
results = []
with tempfile.TemporaryDirectory(prefix='wms652-new-receipt-negative-') as temporary:
    root = Path(temporary)
    for name, source in inputs.items():
        suite = copy.deepcopy(policy['suites'][name])
        suite['report'] = source.name
        required = {'version': 1, 'files': {}, 'suites': {name: suite}}
        path = root / source.name
        original = source.read_bytes()
        path.write_bytes(original)
        assert len(pc.verify_reports(required, root)[name]) == len(suite['cases'])
        path.unlink()
        try:
            pc.verify_reports(required, root)
            raise AssertionError('Missing receipt accepted')
        except ValueError as exc:
            results.append({'suite': name, 'mutation': 'missing receipt', 'rejected': True, 'reason': str(exc)})
        for mutation in ['missing-required-case', 'same-count-wrong-name', 'required-skip', 'required-failure']:
            if suite['format'] == 'junit':
                tree = ET.fromstring(original)
                selected = next(c for c in tree.iter('testcase') if (
                    ('test_protected_original_stays_registered' in c.get('name', '')) if name == 'ci-shards' else True))
                if mutation == 'missing-required-case':
                    next(p for p in tree.iter() if selected in list(p)).remove(selected)
                elif mutation == 'same-count-wrong-name':
                    selected.set('name', 'unrelated-case')
                else:
                    ET.SubElement(selected, 'skipped' if mutation == 'required-skip' else 'failure')
                changed = ET.tostring(tree)
            else:
                data = json.loads(original)
                owner = next(s for s in data['testResults'] if any(c['fullName'].startswith('C5a 33 labels:') for c in s['assertionResults']))
                selected = next(c for c in owner['assertionResults'] if c['fullName'].startswith('C5a 33 labels:'))
                if mutation == 'missing-required-case':
                    owner['assertionResults'].remove(selected)
                elif mutation == 'same-count-wrong-name':
                    selected['fullName'] = 'unrelated-case'
                else:
                    selected['status'] = 'pending' if mutation == 'required-skip' else 'failed'
                changed = json.dumps(data).encode()
            path.write_bytes(changed)
            try:
                pc.verify_reports(required, root)
                raise AssertionError('Bad required receipt accepted: ' + mutation)
            except ValueError as exc:
                results.append({'suite': name, 'mutation': mutation, 'rejected': True, 'reason': str(exc)})
        path.unlink()
(HERE / 'receipt-negatives.json').write_text(json.dumps({'reviewed_sha': TARGET, 'negative_fixtures_not_release_proof': True, 'probes': results}, ensure_ascii=False, indent=2) + '\n')
print('20/20 missing/nonpass/same-count new receipt probes rejected')
