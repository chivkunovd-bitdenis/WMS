"""Actual start_owned/health/ownership shell functions, external process replies.

No listener, client executable or CUPS is used. The launched external fixture is
only a harmless shell process blocked on a temporary FIFO, released after the
actual startup function returns. Its real builtin kill-0 probe is not rewritten.
"""
import argparse
import errno
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

REPO=Path(__file__).resolve().parents[2]
SOURCE='tools/print-agent/update_macos_direct.sh'
BASE='a04a7b35f1e866c1283bdc46fff2d41eaf68b4d6'
CLASSNAME='test_macos_direct_updater_start_owner_contract.StartupOwnerContract'
RAW=os.environ.get('WMS607_START_OWNER_RAW')


def source_bytes():
    override=os.environ.get('WMS607_START_OWNER_SOURCE_COPY')
    if override:return Path(override).read_bytes()
    local=REPO/SOURCE
    if local.is_file():return local.read_bytes()
    return subprocess.check_output(['git','show','HEAD:'+SOURCE],cwd=REPO)


def files(root):
    return {str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob('*')) if p.is_file()}


@unittest.skipUnless(sys.platform=='darwin','Actual macOS JSON command required; SKIP is not acceptance')
class StartupOwnerContract(unittest.TestCase):
    def execute(self,mode):
        data=source_bytes();source=data.decode()
        functions=source[source.index('port_pid()'):source.index('restart_previous()')]
        json_helper=next(line for line in source.splitlines() if line.startswith('json()'))
        with tempfile.TemporaryDirectory(prefix='wms607-start-owner-') as directory:
            root=Path(directory)
            for name in ('app','work','state/jobs-v2','foreign'):(root/name).mkdir(parents=True)
            (root/'events').touch();os.mkfifo(root/'launcher.release')
            (root/'state/jobs-v2/unknown.json').write_text('{"status":"unknown","receipt":null}')
            (root/'state/jobs-v2/accepted.json').write_text('{"status":"accepted","receipt":"Fixture-42"}')
            (root/'work/transaction').write_text('retained recovery intent')
            # Only the external readiness command is represented by this script.
            binary=root/'app/wms-print'
            binary.write_text('#!/bin/bash\nprintf "readiness\\n" >> "'+str(root/'events')+'"\n[ "$1" = --readiness ]\n')
            binary.chmod(0o755)
            before={'app':files(root/'app'),'state':files(root/'state'),'intent':(root/'work/transaction').read_bytes()}
            driver=root/'actual-startup.sh'
            driver.write_text('''#!/bin/bash
set -euo pipefail
root=$1; mode=$2
app_dir="$root/app"; app_physical="$app_dir"; work="$root/work"; state_dir="$root/state"
# External observations only: the selected executable is not run or modeled.
nohup() {
    printf 'nohup|%s\\n' "$*" >> "$root/events"
    touch "$root/launched"
    read -r release < "$root/launcher.release"
    printf 'launcher-released\\n' >> "$root/events"
}
lsof() {
    printf 'lsof\\n' >> "$root/events"
    if [ ! -f "$root/initial-query" ]; then touch "$root/initial-query"; return 0; fi
    # Synchronize external launch reply; no scheduler/CPU timing assumption.
    while [ ! -f "$root/launched" ]; do /bin/sleep 0.001; done
    if [ "$mode" = warming ] && [ ! -f "$root/ready" ]; then
        printf 'no-owner-yet\\n' >> "$root/events"; return 0
    fi
    printf '42424242\\n'
}
ps() {
    if [ "$mode" = foreign ]; then
        printf 'ps|foreign|42424242\\n' >> "$root/events"
        printf '%s/foreign/wms-print\\n' "$root"
    else
        printf 'ps|owned|42424242\\n' >> "$root/events"
        printf '%s/wms-print\\n' "$app_dir"
    fi
}
curl() {
    printf 'curl|health200\\n' >> "$root/events"
    printf '{"app":"WMS Print Direct","protocolVersion":2}\\n'
}
sleep() {
    printf 'startup-sleep\\n' >> "$root/events"
    if [ "$mode" = warming ]; then touch "$root/ready"; fi
    return 0
}
kill() { printf 'signal|%s\\n' "$*" >> "$root/events"; return 98; }
''' + json_helper+'\n'+functions+'''
result=0
start_owned || result=$?
printf 'startup_returned=%s\\n' "$result"
# Finish only our external launcher fixture, with no signal to any process.
printf 'finished\\n' > "$root/launcher.release"
wait
exit "$result"
''')
            try:
                outcome=subprocess.run(['/bin/bash',str(driver),str(root),mode],capture_output=True,text=True,
                                       env={'PATH':'/usr/bin:/bin:/usr/sbin:/sbin'},timeout=15)
            finally:
                # Also release the external fixture if an unexpected harness timeout
                # killed the driver. No customer/application process is involved.
                try:
                    fd=os.open(root/'launcher.release',os.O_WRONLY|os.O_NONBLOCK)
                    try:os.write(fd,b'finished\n')
                    finally:os.close(fd)
                except OSError as error:
                    if error.errno!=errno.ENXIO:raise
            returned=re.search(r'startup_returned=(\d+)\n',outcome.stdout)
            self.assertIsNotNone(returned,'Actual startup failed to return: '+outcome.stderr)
            self.assertEqual(outcome.returncode,int(returned[1]))
            events=(root/'events').read_text().splitlines()
            after={'app':files(root/'app'),'state':files(root/'state'),'intent':(root/'work/transaction').read_bytes()}
            record={'case':CLASSNAME+'::'+self._testMethodName,'base':BASE,'mode':mode,
                    'source_sha256':hashlib.sha256(data).hexdigest(),'functions_sha256':hashlib.sha256(functions.encode()).hexdigest(),
                    'json_helper_sha256':hashlib.sha256(json_helper.encode()).hexdigest(),
                    'test_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                    'native_exit':outcome.returncode,'stdout':outcome.stdout,'stderr':outcome.stderr,
                    'events':events,'app_unchanged':before['app']==after['app'],'state_unchanged':before['state']==after['state'],
                    'intent_unchanged':before['intent']==after['intent'],'before':{'app':before['app'],'state':before['state']},
                    'health200_available':True,'fixture_launcher_released':events.count('launcher-released')==1}
            if RAW:
                out=Path(RAW);out.mkdir(parents=True,exist_ok=True)
                raw=json.dumps(record,indent=2).replace(str(root),'$CASE')
                (out/(self._testMethodName+'.json')).write_text(raw+'\n')
            self.assertTrue(record['app_unchanged'] and record['state_unchanged'] and record['intent_unchanged'])
            self.assertTrue(record['fixture_launcher_released'])
            self.assertFalse(any(e.startswith('signal|') for e in events),'No TERM/other signal to observed owner')
            return record

    def test_confirmed_foreign_owner_aborts_without_later_startup_wait_or_poll(self):
        actual=self.execute('foreign')
        self.assertNotEqual(actual['native_exit'],0,'Foreign health200 cannot establish owned success')
        first=actual['events'].index('ps|foreign|42424242')
        later=actual['events'][first+1:]
        checks={'no_later_wait_or_poll':not any(e=='lsof' or e=='startup-sleep' or e.startswith('ps|') for e in later),
                'foreign_cause_reported':bool(re.search(r'foreign|another executable|different executable|чуж',actual['stderr'],re.I)),
                'no_foreign_health_or_readiness_acceptance':not any(e.startswith('curl|') or e=='readiness' for e in actual['events'])}
        self.assertTrue(all(checks.values()),json.dumps(checks,sort_keys=True))

    def test_owned_healthy_start_succeeds_with_real_health_validation(self):
        actual=self.execute('owned')
        self.assertEqual(actual['native_exit'],0,actual['stderr'])
        self.assertIn('ps|owned|42424242',actual['events'])
        self.assertIn('curl|health200',actual['events'])
        self.assertIn('readiness',actual['events'])

    def test_no_owner_yet_can_warm_until_owned_ready(self):
        actual=self.execute('warming')
        self.assertEqual(actual['native_exit'],0,actual['stderr'])
        for event in ('no-owner-yet','startup-sleep','ps|owned|42424242','curl|health200','readiness'):
            self.assertIn(event,actual['events'])
        self.assertLess(actual['events'].index('startup-sleep'),actual['events'].index('curl|health200'))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--report',required=True);parser.add_argument('cases',nargs='*');args=parser.parse_args()
    rows={}
    class Result(unittest.TextTestResult):
        def startTest(self,test):super().startTest(test);rows[test._testMethodName]={}
        def addFailure(self,test,error):super().addFailure(test,error);rows[test._testMethodName]['failure']=self._exc_info_to_string(error,test)
        def addError(self,test,error):super().addError(test,error);rows.setdefault(getattr(test,'_testMethodName',str(test)),{})['error']=self._exc_info_to_string(error,test)
        def addSkip(self,test,reason):super().addSkip(test,reason);rows[test._testMethodName]['skipped']=reason
    suite=unittest.defaultTestLoader.loadTestsFromNames(args.cases or ['StartupOwnerContract'],sys.modules[__name__])
    outcome=unittest.TextTestRunner(verbosity=2,resultclass=Result).run(suite)
    xml=ET.Element('testsuite',name='WMS607.startupOwner',tests=str(len(rows)),failures=str(sum('failure' in r for r in rows.values())),
                   errors=str(sum('error' in r for r in rows.values())),skipped=str(sum('skipped' in r for r in rows.values())))
    for name,statuses in rows.items():
        case=ET.SubElement(xml,'testcase',classname=CLASSNAME,name=name)
        for status,message in statuses.items():ET.SubElement(case,status).text=message
    report=Path(args.report);report.parent.mkdir(parents=True,exist_ok=True);ET.ElementTree(xml).write(report,encoding='utf-8',xml_declaration=True)
    return 0 if outcome.wasSuccessful() else 1


if __name__=='__main__':raise SystemExit(main())
