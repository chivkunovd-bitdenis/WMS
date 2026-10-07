"""Isolated synthetic CI collector; never part of the ordinary release workflow."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
SPEC = json.loads(Path(__file__).with_name('commands.json').read_text())
EVIDENCE = Path(os.environ['RUNNER_TEMP']) / 'pg-comparison'
EVIDENCE.mkdir(exist_ok=True)

if sys.argv[1] == '--verify':
    rows = [json.loads(p.read_text()) for p in EVIDENCE.glob('*.exit.json')]
    expected = set(SPEC)
    observed = {r['id'] for r in rows if r['id'] in expected}
    print(json.dumps({'expected': sorted(expected), 'observed': sorted(observed),
                      'outcomes': rows}, indent=2))
    assert observed == expected, 'Every ordinary command group must actually execute'
    assert all(r['exit_code'] == 0 for r in rows), 'Native/static refusal remains overall FAIL'
    assert len([r for r in rows if r['id'].startswith('release-pg-')]) == 5
    sys.exit(0)

key = sys.argv[1]
command = SPEC[key]['command']
assert hashlib.sha256(command.encode()).hexdigest() == SPEC[key]['sha256']
assert sys.version_info[:2] == (3, 11)
assert os.environ['GITHUB_ACTIONS'] == 'true' and sys.platform == 'linux'
assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT).decode().strip() == os.environ['GITHUB_SHA']

if command.strip() == 'bash ../scripts/ci/run_release_postgres.sh':
    original = ROOT / 'scripts/ci/run_release_postgres.sh'
    source = original.read_text()
    function = r'''
pg_index=0
pg_failed=0
run_pg_command() {
  pg_index=$((pg_index+1))
  local pg_key="release-pg-$pg_index"
  set +e
  "$@" 2>&1 | tee "$RUNNER_TEMP/pg-comparison/$pg_key.log"
  local pg_code=${PIPESTATUS[0]}
  set -e
  python - "$pg_key" "$pg_code" "$@" <<'PYREPORT'
import json,os,pathlib,sys
p=pathlib.Path(os.environ['RUNNER_TEMP'])/'pg-comparison'
(p/(sys.argv[1]+'.exit.json')).write_text(json.dumps(dict(id=sys.argv[1],exit_code=int(sys.argv[2]),command=sys.argv[3:],sha=os.environ['GITHUB_SHA'],run_id=os.environ['GITHUB_RUN_ID'],run_attempt=os.environ['GITHUB_RUN_ATTEMPT']))+'\n')
PYREPORT
  if [[ "$pg_code" != 0 ]]; then pg_failed=1; fi
  return 0
}
'''
    assert source.count('  pytest -n 0') == 4
    assert source.count('  python ../scripts/ci/run_isolated_pytest.py') == 1
    changed = source.replace('set -euo pipefail\n', 'set -euo pipefail\n' + function, 1)
    changed = changed.replace('  pytest -n 0', '  run_pg_command pytest -n 0')
    changed = changed.replace('  python ../scripts/ci/run_isolated_pytest.py',
                              '  run_pg_command python ../scripts/ci/run_isolated_pytest.py')
    changed += '\n[[ "$pg_index" == 5 ]]\nexit "$pg_failed"\n'
    copy = original.with_name('.wms652_pg_comparison.sh')
    copy.write_text(changed)
    (EVIDENCE / 'ordinary-release-postgres-source.sh').write_text(source)
    (EVIDENCE / 'observed-release-postgres-copy.sh').write_text(changed)
    command = 'bash ../scripts/ci/.wms652_pg_comparison.sh'

started = time.time()
with (EVIDENCE / (key + '.log')).open('wb') as output:
    child = subprocess.Popen(['bash', '-e', '-o', 'pipefail', '-c', command],
                             cwd=ROOT / SPEC[key]['working_directory'], stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT)
    while block := child.stdout.read(8192):
        output.write(block)
        output.flush()
        sys.stdout.buffer.write(block)
        sys.stdout.buffer.flush()
    code = child.wait()
record = {'id': key, 'name': SPEC[key]['name'], 'command': SPEC[key]['command'],
          'working_directory': SPEC[key]['working_directory'],
          'command_sha256': SPEC[key]['sha256'], 'exit_code': code,
          'started_epoch': started, 'completed_epoch': time.time(),
          'sha': os.environ['GITHUB_SHA'], 'run_id': os.environ['GITHUB_RUN_ID'],
          'run_attempt': os.environ['GITHUB_RUN_ATTEMPT']}
(EVIDENCE / (key + '.exit.json')).write_text(json.dumps(record, indent=2) + '\n')
sys.exit(code)
