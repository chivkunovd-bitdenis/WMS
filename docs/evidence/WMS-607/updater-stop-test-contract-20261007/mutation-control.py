"""Temporary actual shell COPY controls; no tracked updater edit or replacement model."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
SOURCE = 'tools/print-agent/update_macos_direct.sh'
TEST = 'tools/print-agent/test_macos_direct_updater_stop_contract.py'
original = subprocess.check_output(['git','show','HEAD:'+SOURCE],cwd=REPO)
controls = [
    ('clear-intent', [('    clear_transaction\n','    : # COPY: omit successful recovery finalization\n')],
     'RollbackStopContract.test_successful_owned_stop_restores_previous_and_preserves_journal'),
    ('foreign-ownership', [('    process_matches "$pid" || return 2\n','    : # COPY: ignore owner identity\n'),
                           ('    # Recheck immediately before TERM. No blanket process-name kill or forced kill.\n    process_matches "$pid" || return 1\n','    : # COPY: ignore pre-TERM ownership recheck\n')],
     'RollbackStopContract.test_foreign_owner_not_signaled_existing_application_recovery_preserved'),
]
records = []
with tempfile.TemporaryDirectory(prefix='wms607-stop-copy-') as directory:
    for name, edits, case in controls:
        mutated = original.decode()
        for before, after in edits:
            assert mutated.count(before)==1
            mutated=mutated.replace(before,after)
        copy=Path(directory)/(name+'.sh');copy.write_text(mutated)
        env={'PATH':'/usr/bin:/bin:/usr/sbin:/sbin','WMS607_STOP_SOURCE_COPY':str(copy),'WMS607_STOP_RAW':str(HERE/('mutation-'+name))}
        outcome=subprocess.run([sys.executable,'-B',str(REPO/TEST),'--report',str(HERE/('mutation-'+name+'.xml')),case],
                               cwd=REPO,env=env,capture_output=True,text=True,timeout=15)
        (HERE/('mutation-'+name+'.log')).write_text(outcome.stdout+outcome.stderr)
        xml=ET.parse(HERE/('mutation-'+name+'.xml')).getroot()
        expected=(xml.attrib['tests'],xml.attrib['failures'],xml.attrib['errors'],xml.attrib['skipped'])==('1','1','0','0')
        assert expected and outcome.returncode==1
        records.append({'name':name,'case':case,'source_sha256':hashlib.sha256(original).hexdigest(),
                        'copy_sha256':hashlib.sha256(mutated.encode()).hexdigest(),'edits':edits,'native_exit':outcome.returncode,
                        'assertion_FAIL':True,'ERROR':0,'SKIP':0})
assert subprocess.check_output(['git','show','HEAD:'+SOURCE],cwd=REPO)==original
(HERE/'mutation-result.json').write_text(json.dumps({'tracked_source_unchanged':True,'temporary_copies_removed':True,'controls':records},indent=2)+'\n')
print('Both preservation COPY controls: 1 targeted assertion FAIL, 0 ERROR/SKIP each; actual source unchanged.')
