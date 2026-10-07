"""WMS-607 P1: actual shell rollback/stop functions; only OS process replies fake.

No server/port/executable, printer or customer directory is used. The complete
committed function block is executed unchanged; inventory/rename/delete are real.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

REPO = Path(__file__).resolve().parents[2]
SOURCE = 'tools/print-agent/update_macos_direct.sh'
BASE = '6232cf29765f1b25466e96919ee7840bf5874c62'
CLASSNAME = 'test_macos_direct_updater_stop_contract.RollbackStopContract'
RAW = os.environ.get('WMS607_STOP_RAW')


def source_bytes():
    copy = os.environ.get('WMS607_STOP_SOURCE_COPY')
    if copy:
        return Path(copy).read_bytes()
    path = REPO / SOURCE
    if path.is_file():
        return path.read_bytes()
    return subprocess.check_output(['git', 'show', 'HEAD:' + SOURCE], cwd=REPO)


def inventory(root):
    if not root.exists():
        return None
    result = {}
    for path in [root, *sorted(root.rglob('*'))]:
        name = str(path.relative_to(root))
        mode = stat.S_IMODE(path.lstat().st_mode)
        if path.is_symlink():
            result[name] = ['link', mode, os.readlink(path)]
        elif path.is_file():
            result[name] = ['file', mode, hashlib.sha256(path.read_bytes()).hexdigest()]
        else:
            result[name] = ['directory', mode]
    return result


@unittest.skipUnless(sys.platform == 'darwin', 'Actual macOS stat/inventory required; SKIP is not acceptance')
class RollbackStopContract(unittest.TestCase):
    def execute(self, mode):
        data = source_bytes()
        text = data.decode()
        functions = text[text.index('port_pid()'):text.index('# Any interruption after')]
        hash_function = next(line for line in text.splitlines() if line.startswith('hash()'))
        with tempfile.TemporaryDirectory(prefix='wms607-stop-contract-') as directory:
            root = Path(directory)
            for name in ('app', 'work/previous', 'backup/application', 'state/jobs-v2', 'state/labels'):
                (root / name).mkdir(parents=True)
            for name, payload in [('app', 'TARGET BYTES'), ('work/previous', 'PREVIOUS BYTES'), ('backup/application', 'PREVIOUS BYTES')]:
                (root / name / 'wms-print').write_text(payload)
                (root / name / 'wms-print').chmod(0o755)
                (root / name / 'build.json').write_text(json.dumps({'runtime': 'direct', 'source_commit': 'a'*40 if name == 'app' else 'b'*40}))
                (root / name / 'mode-file').write_text('private fixture file')
                (root / name / 'mode-file').chmod(0o600)
                (root / name / 'link').symlink_to('mode-file')
            # Synthetic current receipt/unknown bytes. No old snapshot is restored.
            for key, status, receipt in [('accepted-key', 'accepted', 'Fixture-42'), ('unknown-key', 'unknown', None)]:
                (root / 'state/jobs-v2' / (key+'.json')).write_text(json.dumps({'idempotencyKey': key, 'status': status, 'receipt': receipt}))
            (root / 'state/direct-jobs.json').write_text('{"legacy-accepted":{"receipt":"Fixture-41"}}')
            (root / 'state/labels/retained.png').write_bytes(b'fixture retained payload')
            for name, value in [('transaction', 'replace\n'), ('backup-path', str(root/'backup')+'\n'), ('old-running', '0\n')]:
                (root / 'work' / name).write_text(value)
            (root / 'alive').touch()
            before = {name: inventory(root/name) for name in ('app', 'work/previous', 'backup', 'state')}
            intent = {name: (root/'work'/name).read_bytes() for name in ('transaction', 'backup-path', 'old-running')}
            shell = root/'actual-functions.sh'
            shell.write_text('''#!/bin/bash
set -euo pipefail
root=$1; mode=$2
app_dir="$root/app"; app_physical="$app_dir"
work="$root/work"; backup="$root/backup"; state_dir="$root/state"
transaction=1; old_running=0
# Only process observations/signals and waiting are external controlled boundaries.
lsof() { [ ! -f "$root/alive" ] || printf '42424242\\n'; }
ps() {
    [ -f "$root/alive" ] || return 1
    if [ "$mode" = foreign ]; then printf '%s/foreign/wms-print\\n' "$root"
    else printf '%s/wms-print\\n' "$app_dir"; fi
}
kill() {
    printf '%s\\n' "$*" >> "$root/signals.log"
    if [ "$1" = -0 ]; then [ -f "$root/alive" ]; return $?; fi
    [ "$1" = -TERM ] && [ "$2" = 42424242 ] || return 98
    case "$mode" in
        stops) rm -f "$root/alive";;
        term_error) printf 'kill: 42424242: Operation not permitted\\n' >&2; return 1;;
        survives) return 0;;
        *) return 98;;
    esac
}
sleep() { :; }
''' + hash_function + '\n' + functions + '''
result=0
rollback || result=$?
printf 'rollback_returned=%s\\ntransaction=%s\\n' "$result" "$transaction"
exit "$result"
''')
            outcome = subprocess.run(['/bin/bash', str(shell), str(root), mode], capture_output=True, text=True, timeout=10,
                                     env={'PATH': '/usr/bin:/bin:/usr/sbin:/sbin'})
            returned = re.search(r'rollback_returned=(\d+)\ntransaction=(\d+)\n', outcome.stdout)
            self.assertIsNotNone(returned, 'Actual rollback did not return: '+outcome.stderr)
            self.assertEqual(outcome.returncode, int(returned[1]))
            signals = (root/'signals.log').read_text().splitlines() if (root/'signals.log').exists() else []
            after = {name: inventory(root/name) for name in before}
            record = {'case': CLASSNAME+'::'+self._testMethodName, 'mode': mode, 'base': BASE,
                      'source_sha256': hashlib.sha256(data).hexdigest(), 'functions_sha256': hashlib.sha256(functions.encode()).hexdigest(),
                      'test_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                      'native_exit': outcome.returncode, 'stdout': outcome.stdout, 'stderr': outcome.stderr,
                      'transaction': int(returned[2]), 'before': before, 'after': after,
                      'intent_unchanged': all((root/'work'/name).exists() and (root/'work'/name).read_bytes() == value for name,value in intent.items()),
                      'intent_absent': all(not (root/'work'/name).exists() for name in intent),
                      'process_alive': (root/'alive').exists(), 'signals': signals,
                      'failed_target_exists': (root/'work/failed-target').exists()}
            if RAW:
                out = Path(RAW); out.mkdir(parents=True, exist_ok=True)
                (out/(self._testMethodName+'.json')).write_text(json.dumps(record, indent=2)+'\n')
            return record

    def assert_owned_stop_failure(self, mode):
        actual = self.execute(mode)
        self.assertNotEqual(actual['native_exit'], 0)
        self.assertTrue(actual['process_alive'])
        self.assertEqual(actual['signals'].count('-TERM 42424242'), 1)
        checks = {name+'_unchanged': actual['after'][name] == actual['before'][name] for name in actual['before']}
        checks.update(intent_unchanged=actual['intent_unchanged'], transaction_retained=actual['transaction']==1,
                      no_target_rename=not actual['failed_target_exists'],
                      truthful_owned_stop_failure=bool(re.search(r'owned.*(?:stop|term)|(?:stop|term).*owned', actual['stderr'], re.I)),
                      not_misreported_foreign='foreign' not in actual['stderr'].lower())
        self.assertTrue(all(checks.values()), json.dumps(checks, sort_keys=True))

    def test_owned_TERM_success_survivor_retains_target_and_recovery(self):
        self.assert_owned_stop_failure('survives')

    def test_owned_TERM_error_retains_target_and_recovery(self):
        self.assert_owned_stop_failure('term_error')

    def test_successful_owned_stop_restores_previous_and_preserves_journal(self):
        actual = self.execute('stops')
        self.assertEqual(actual['native_exit'], 0, actual['stderr'])
        self.assertFalse(actual['process_alive'])
        self.assertEqual(actual['signals'].count('-TERM 42424242'), 1)
        self.assertEqual(actual['after']['app'], actual['before']['work/previous'])
        self.assertIsNone(actual['after']['work/previous'])
        self.assertEqual(actual['after']['backup'], actual['before']['backup'])
        self.assertEqual(actual['after']['state'], actual['before']['state'])
        self.assertEqual(actual['transaction'], 0)
        self.assertTrue(actual['intent_absent'])
        self.assertFalse(actual['failed_target_exists'])

    def test_foreign_owner_not_signaled_existing_application_recovery_preserved(self):
        actual = self.execute('foreign')
        self.assertNotEqual(actual['native_exit'], 0)
        self.assertTrue(actual['process_alive'])
        self.assertEqual(actual['signals'], [])
        self.assertEqual(actual['after']['app'], actual['before']['work/previous'])
        self.assertEqual(actual['after']['state'], actual['before']['state'])
        self.assertEqual(actual['after']['backup'], actual['before']['backup'])
        self.assertEqual(actual['transaction'], 0)
        self.assertTrue(actual['intent_absent'])
        self.assertIn('foreign', actual['stderr'].lower())
        self.assertFalse(actual['failed_target_exists'])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--report', required=True)
    parser.add_argument('cases', nargs='*')
    args = parser.parse_args()
    rows = {}
    class Result(unittest.TextTestResult):
        def startTest(self, test):
            super().startTest(test); rows[test._testMethodName] = {}
        def addFailure(self, test, error):
            super().addFailure(test,error); rows[test._testMethodName]['failure'] = self._exc_info_to_string(error,test)
        def addError(self, test, error):
            super().addError(test,error); rows.setdefault(getattr(test,'_testMethodName',str(test)),{})['error'] = self._exc_info_to_string(error,test)
        def addSkip(self, test, reason):
            super().addSkip(test,reason); rows[test._testMethodName]['skipped'] = reason
    suite = unittest.defaultTestLoader.loadTestsFromNames(args.cases or ['RollbackStopContract'], sys.modules[__name__])
    outcome = unittest.TextTestRunner(verbosity=2,resultclass=Result).run(suite)
    xml = ET.Element('testsuite', name='WMS607.updaterRollbackStop', tests=str(len(rows)),
                     failures=str(sum('failure' in x for x in rows.values())), errors=str(sum('error' in x for x in rows.values())),
                     skipped=str(sum('skipped' in x for x in rows.values())))
    for name, statuses in rows.items():
        case = ET.SubElement(xml,'testcase',classname=CLASSNAME,name=name)
        for status, text in statuses.items():
            ET.SubElement(case,status).text = text
    report = Path(args.report); report.parent.mkdir(parents=True,exist_ok=True)
    ET.ElementTree(xml).write(report,encoding='utf-8',xml_declaration=True)
    return 0 if outcome.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
