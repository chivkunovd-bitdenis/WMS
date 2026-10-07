"""Purposeful temporary actual-source COPY failures of both preservation cases."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

HERE=Path(__file__).resolve().parent;REPO=HERE.parents[3]
SOURCE='tools/print-agent/update_macos_direct.sh'
TEST='tools/print-agent/test_macos_direct_updater_start_owner_contract.py'
original=subprocess.check_output(['git','show','HEAD:'+SOURCE],cwd=REPO)
controls=[
 ('healthy-rejected','        if health_ok "${1:-target}"; then return 0; fi\n',
  '        if health_ok "${1:-target}"; then return 1; fi # COPY: reject actual healthy result\n',
  'StartupOwnerContract.test_owned_healthy_start_succeeds_with_real_health_validation'),
 ('warming-rejected','        sleep 0.05\n    done\n    printf \'%s\\n\' \'Start/readiness failed.',
  '        return 1 # COPY: refuse no-owner warmup\n    done\n    printf \'%s\\n\' \'Start/readiness failed.',
  'StartupOwnerContract.test_no_owner_yet_can_warm_until_owned_ready'),
]
records=[]
with tempfile.TemporaryDirectory(prefix='wms607-start-owner-copy-') as directory:
 for name,before,after,case in controls:
  assert original.decode().count(before)==1
  changed=original.decode().replace(before,after)
  copy=Path(directory)/(name+'.sh');copy.write_text(changed)
  env={'PATH':'/usr/bin:/bin:/usr/sbin:/sbin','WMS607_START_OWNER_SOURCE_COPY':str(copy),'WMS607_START_OWNER_RAW':str(HERE/('mutation-'+name))}
  result=subprocess.run([sys.executable,'-B',str(REPO/TEST),'--report',str(HERE/('mutation-'+name+'.xml')),case],cwd=REPO,
                        env=env,capture_output=True,text=True,timeout=20)
  (HERE/('mutation-'+name+'.log')).write_text(result.stdout+result.stderr)
  xml=ET.parse(HERE/('mutation-'+name+'.xml')).getroot()
  assert result.returncode==1 and (xml.attrib['tests'],xml.attrib['failures'],xml.attrib['errors'],xml.attrib['skipped'])==('1','1','0','0')
  records.append({'case':case,'name':name,'source_sha256':hashlib.sha256(original).hexdigest(),
                  'copy_sha256':hashlib.sha256(changed.encode()).hexdigest(),'replacement':[before,after],
                  'native_test_exit':result.returncode,'meaningful_assertion_FAIL':True,'ERROR':0,'SKIP':0})
assert subprocess.check_output(['git','show','HEAD:'+SOURCE],cwd=REPO)==original
(HERE/'mutation-result.json').write_text(json.dumps({'controls':records,'copies_removed':True,'tracked_source_unchanged':True},indent=2)+'\n')
print('Both real-source preservation COPY mutations: 1 assertion FAIL / 0 ERROR / 0 SKIP each.')
