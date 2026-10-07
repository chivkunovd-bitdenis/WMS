"""Independent bounded review probe; actual shell functions, controlled OS process.

No native executable, listener, CUPS, customer Library or network is used.
Filesystem rename/inventory/recovery operations are real, in a temporary directory.
"""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

PRODUCT = '32c3212406eaf57b904c207bfb45d7acfd25a0b0'
PATH = 'tools/print-agent/update_macos_direct.sh'
OUT = Path(__file__).resolve().parent
source = subprocess.check_output(['git', 'show', PRODUCT + ':' + PATH]).decode()
functions = source[source.index('port_pid()'):source.index('# Any interruption after')]
with tempfile.TemporaryDirectory(prefix='wms607-review-rollback-') as directory:
    root = Path(directory)
    for name in ('app', 'work/previous', 'backup/application', 'state'):
        (root / name).mkdir(parents=True)
    (root / 'app/wms-print').write_text('TARGET BYTES')
    for name in ('work/previous', 'backup/application'):
        (root / name / 'wms-print').write_text('PREVIOUS BYTES')
    (root / 'state/current-unknown.json').write_text('{"status":"unknown"}')
    for name in ('transaction', 'backup-path', 'old-running'):
        (root / 'work' / name).write_text('retained recovery intent')
    shell = root / 'probe.sh'
    shell.write_text('''#!/bin/bash
set -euo pipefail
root=$1
app_dir="$root/app"; app_physical="$app_dir"
work="$root/work"; backup="$root/backup"; state_dir="$root/state"
old_running=0; transaction=1
hash() { /usr/bin/shasum -a 256 "$1" | /usr/bin/awk '{print $1}'; }
# Only OS process boundaries are controlled. TERM succeeds but process stays alive.
lsof() { printf '42424242\\n'; }
ps() { printf '%s/wms-print\\n' "$app_dir"; }
kill() { printf '%s\\n' "$*" >> "$root/signals.log"; return 0; }
sleep() { :; }
''' + functions + '''
result=0
rollback || result=$?
printf 'rollback_exit=%s\\ntransaction=%s\\n' "$result" "$transaction"
''')
    result = subprocess.run(['/bin/bash', str(shell), str(root)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    actual = {
        'product_commit': PRODUCT,
        'updater_sha256': hashlib.sha256(source.encode()).hexdigest(),
        'extracted_functions_sha256': hashlib.sha256(functions.encode()).hexdigest(),
        'boundary': 'actual stop_owned/rollback/inventory/clear_transaction; controlled lsof/ps/kill/sleep only',
        'stdout': result.stdout,
        'stderr': result.stderr,
        'application_after': (root / 'app/wms-print').read_text(),
        'recovery_intent_retained': (root / 'work/transaction').exists(),
        'previous_tree_retained': (root / 'work/previous').exists(),
        'failed_target_retained': (root / 'work/failed-target').exists(),
        'current_journal_unchanged': (root / 'state/current-unknown.json').read_text() == '{"status":"unknown"}',
        'TERM_attempts': (root / 'signals.log').read_text().splitlines().count('-TERM 42424242'),
        'controlled_process_remains_alive': True,
    }
    assert 'Owned executable did not stop' in actual['stderr']
    assert actual['TERM_attempts'] == 1
    assert actual['application_after'] == 'PREVIOUS BYTES'
    assert not actual['recovery_intent_retained']
    actual['finding_reproduced'] = True
    actual['required_safety_invariant'] = 'failed owned stop must retain target/recovery intent until safe recovery; cannot replace underneath live process'
    (OUT / 'rollback-result.json').write_text(json.dumps(actual, indent=2) + '\n')
    print(json.dumps(actual, indent=2))
