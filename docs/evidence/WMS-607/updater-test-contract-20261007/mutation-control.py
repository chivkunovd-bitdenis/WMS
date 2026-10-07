"""Only temporary COPY mutations of actual existing product; no updater model.
Both existing preservation controls must fail by assertions, with zero errors.
"""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3]
runner=HERE/'run-contract.py'
summary=[]
with tempfile.TemporaryDirectory(prefix='wms607-updater-copy-') as temporary:
    for path,old,new,envname,case in [
        ('tools/print-agent/build_console.py','"runtime": "direct"','"runtime": "paired"','WMS607_UPDATER_BUILD_COPY','UpdaterContract.test_preservation_actual_direct_build_metadata'),
        ('tools/print-agent/wms_print_direct_macos.swift','if let old=jobs[key] {','if let old=jobs[key], old.status == "failed_before_submit" {','WMS607_UPDATER_SWIFT_COPY','UpdaterContract.test_preservation_actual_public_and_current_journal_replay')]:
        data=subprocess.check_output(['git','show','HEAD:'+path],cwd=ROOT).decode();assert data.count(old)==1
        mutant=Path(temporary)/Path(path).name;mutant.write_text(data.replace(old,new))
        name='metadata' if 'build_console' in path else 'journal'
        env={'PATH':'/usr/bin:/bin:/usr/sbin:/sbin',envname:str(mutant),'WMS607_UPDATER_EVIDENCE_DIR':str(HERE/('mutant-'+name))}
        r=subprocess.run([sys.executable,'-B',str(runner),'--report',str(HERE/('mutation-'+name+'.xml')),case],cwd=ROOT,env=env,capture_output=True,text=True,timeout=60)
        log=r.stdout+r.stderr;(HERE/('mutation-'+name+'.log')).write_text(log)
        rejected=r.returncode==1 and 'FAILED (failures=1)' in log and 'ERROR:' not in log
        summary.append({'source_path':path,'source_sha256':hashlib.sha256(data.encode()).hexdigest(),'mutant_sha256':hashlib.sha256(mutant.read_bytes()).hexdigest(),'replacement':[old,new],
                        'case':case,'native_exit':r.returncode,'meaningful_assertion_FAIL':rejected,'tracked_source_unchanged':subprocess.check_output(['git','show','HEAD:'+path],cwd=ROOT).decode()==data})
(HERE/'mutation-result.json').write_text(json.dumps(summary,indent=2)+'\n')
if not all(r['meaningful_assertion_FAIL'] and r['tracked_source_unchanged'] for r in summary):raise SystemExit(1)
print('Two actual-source COPY preservation mutations rejected by assertions; no product file changed.')
