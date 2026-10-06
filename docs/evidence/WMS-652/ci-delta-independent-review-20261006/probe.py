"""Bounded independent review: inspect saved evidence, do not rerun browsers."""
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
UI = ROOT.parent / 'wms652-critical-fbs-contracts'
EVIDENCE = 'docs/evidence/WMS-652/critical-fbs-contracts-20261006/'
SOURCE = '1c045a4f2d6c1bb34eeed2f5e79f6e53be2a8a9d'
SAVED = 'd6e39bb4fdf97a046f2c34a7b4d4e00345daa835'


def show(sha, path):
    return subprocess.check_output(['git', 'show', sha + ':' + path], cwd=ROOT)


ids = json.loads(show(SOURCE, 'frontend/tests-e2e/wms652-critical/cases.json'))
print('case-list-type', type(ids).__name__)
if isinstance(ids, dict):
    ids = ids['cases']
ids = [item['id'] if isinstance(item, dict) else item for item in ids]
report = json.loads(show(SAVED, EVIDENCE + 'geometry-final-green/result.json'))
assert report['sha'] == SOURCE
assert report['status'] == 'PASS'
assert [case['id'] for case in report['cases']] == ids
assert len(ids) == len(set(ids)) == 43
assert all(case['status'] == 'PASS' for case in report['cases'])
mutants = json.loads(show(SAVED, EVIDENCE + 'geometry-mutants/mutations.json'))
failures = {}
for mutation in mutants:
    name = mutation['mutation']
    negative = json.loads(show(SAVED, EVIDENCE + 'geometry-mutants/' + name + '/result.json'))
    assert negative['sha'] == '695a429cd08b4a0b3675cb2d4af0d3f33eeaf9f5'
    assert negative['status'] == 'FAIL'
    assert [case['id'] for case in negative['cases']] == ids
    failed = [case for case in negative['cases'] if case['status'] == 'FAIL']
    assert failed == mutation['failed']
    assert len(failed) + mutation['otherCasesPass'] == 43
    assert all(case['status'] == 'PASS' for case in negative['cases'] if case not in failed)
    failures[name] = len(failed)
assert sorted(failures.values()) == [1, 2, 7]
for path in ['geometry.mjs', 'geometry-mutations.py', 'cases.json']:
    full = 'frontend/tests-e2e/wms652-critical/' + path
    assert show(SOURCE, full) == show('695a429cd', full)
collection = [line.strip() for line in (Path(__file__).parent / 'full-collection.log').read_text().splitlines()
              if line.startswith('tests/') and '::' in line]
from scripts.ci.backend_shards import partition
left, right = [partition(collection, index) for index in (0, 1)]
assert len(collection) == len(set(collection)) == 4625
assert set(left).isdisjoint(right) and set(left) | set(right) == set(collection)
summary = dict(reviewedSha=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
               freshCollection=len(collection), shardCounts=[len(left), len(right)],
               geometrySource=SOURCE, savedEvidence=SAVED, geometryPass=43, exactMutantFailures=failures)
print(json.dumps(summary, indent=2))
