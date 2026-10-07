"""Actual CLI repeat with default app/manifest, frozen external OS fixtures."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[4]
spec = importlib.util.spec_from_file_location('updater_contract', ROOT / 'tools/print-agent/test_macos_direct_updater_contract.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
cls = module.UpdaterContract
cls.setUpClass()
case = cls('test_uc6_repeat_concurrent_and_interrupted_update_recover')
case.setUp()
try:
    entry = module.ENTRY.read_bytes()
    archive = case.root / 'arm64.zip'
    with zipfile.ZipFile(archive, 'a') as z:
        info = zipfile.ZipInfo('wms-print/update_macos_direct.sh')
        info.external_attr = 0o100755 << 16
        z.writestr(info, entry)
    case.manifest['artifacts']['arm64']['sha256'] = hashlib.sha256(archive.read_bytes()).hexdigest()
    (case.root / 'manifest.json').write_text(json.dumps(case.manifest))
    first = case.run_update()
    assert first.returncode == 0, first.stderr
    case.assert_target()
    case.assert_archived()
    assert (case.app / 'updater-manifest.json').read_bytes() == (case.root / 'manifest.json').read_bytes()
    before = module.snapshot(case.backups)
    command_count = len(case.commands())
    # Replace only absolute OS tool boundaries, exactly as the frozen contract.
    text = entry.decode()
    names = ('curl','uname','sysctl','file','lipo','lsof','ps','kill','df','ditto','cp','tar','rsync','mkdir','mv','sudo','spctl','xattr','defaults','lpadmin','brew','pip','pip3','pkill','killall','lp','lpr','lpstat','cancel','open','codesign')
    for name in names:
        text = re.sub(r'/(?:usr/bin|usr/sbin|bin|sbin)/' + name + r'\b', str(case.bin / name), text)
    installed = case.app / 'update_macos_direct.sh'
    installed.write_text(text)
    env = {'PATH': str(case.bin)+':/usr/bin:/bin:/usr/sbin:/sbin', 'TMPDIR': str(case.root), 'WMS607_FX_ROOT': str(case.root), 'WMS607_FX_BIN': str(case.bin)}
    wrapper = 'function kill(){ "$WMS607_FX_BIN/kill" "$@"; }; export -f kill; exec /bin/bash "$@"'
    repeat = subprocess.run(['/bin/bash','-c',wrapper,'fixture',str(installed),'--state-dir',str(case.state),'--backup-dir',str(case.backups)],env=env,capture_output=True,text=True,timeout=15)
    assert repeat.returncode == 0, repeat.stderr
    assert module.snapshot(case.backups) == before
    commands = case.commands()[command_count:]
    assert not any(c[0] == 'kill' and '-0' not in c for c in commands), commands
    assert not any(c[0] in ('lp','lpr','cancel') for c in commands), commands
    record = {'pass':True,'entry_sha256':hashlib.sha256(entry).hexdigest(),'first':{'exit':first.returncode,'stdout':first.stdout,'stderr':first.stderr},'repeat':{'exit':repeat.returncode,'stdout':repeat.stdout,'stderr':repeat.stderr},'defaults_checked':['app-dir','manifest'],'state_and_backup':'explicit temporary boundaries; HOME unchanged','archives_unchanged':True,'stop_or_print_on_repeat':False,'process_alias':'/var and /private/var resolve to same selected executable','commands':commands}
    encoded = json.dumps(record,indent=2).replace(str(case.root.resolve()),'$CASE').replace(str(case.root),'$CASE')
    Path(__file__).with_name('default-repeat.json').write_text(encoded+'\n')
    print(encoded)
finally:
    case.tmp.cleanup()
    cls.tearDownClass()
