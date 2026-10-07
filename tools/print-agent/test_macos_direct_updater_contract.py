"""WMS-607 updater black-box contract: actual installer, isolated files/OS boundaries.

The Direct updater does not exist at the frozen base. Missing entry is an explicit
assertion (unimplemented integration), never claimed as behavioural RED. Future
implementation executes as bash CLI, not a test-written updater/model. Metadata,
ZIP/files/archives are real; hardware/download/process/security are external fakes.
No host HOME/Library/default printer, actual client process or physical print.
"""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tarfile
import stat
import subprocess
import sys
import tempfile
import types
import unittest
import uuid
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parent
BASE = '756b45a4d46b9e9a33657549e2c2addb6bae89c1'
INSTALLED = '9a33b651c309796707053e1056c7f80dff7194d5'
TARGET = 'dc652472d75812dbebc68ef4353a718b0f629cbe'
ENTRY = Path(os.environ.get('WMS607_UPDATER_ENTRY', ROOT / 'update_macos_direct.sh'))
EVIDENCE = os.environ.get('WMS607_UPDATER_EVIDENCE_DIR')
PNG = 'iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAAFklEQVR4nGP8//8/AwMDEwMDAwMDAwAkBgMB/DXemwAAAABJRU5ErkJggg=='


def source(path, ref=None):
    if ref is None and (ROOT.parents[1]/path).is_file():
        return (ROOT.parents[1]/path).read_bytes()
    return subprocess.check_output(['git', 'show', (ref or 'HEAD') + ':' + path], cwd=ROOT)


def snapshot(root):
    result = {}
    for p in sorted(root.rglob('*')):
        rel = str(p.relative_to(root))
        if p.is_symlink():
            result[rel] = ['link', os.readlink(p)]
        elif p.is_file():
            result[rel] = ['file', stat.S_IMODE(p.stat().st_mode), hashlib.sha256(p.read_bytes()).hexdigest()]
    return result


BINARY = r'''#!PYTHON
import json,os,sys
from pathlib import Path
r=Path(os.environ['WMS607_FX_ROOT']);fx=json.loads((r/'system.json').read_text())
with (r/'commands.jsonl').open('a') as f:f.write(json.dumps(['binary',str(Path(__file__).absolute())]+sys.argv[1:])+'\n')
if '--self-test' in sys.argv:sys.exit(1 if fx.get('selftest_fail') else 0)
meta=json.loads((Path(__file__).parent/'build.json').read_text())
if (fx.get('start_fail') or fx.get('permission_denied')) and meta['source_commit']==fx.get('failure_source','dc652472d75812dbebc68ef4353a718b0f629cbe'):
    if fx.get('start_fail'):(r/'state/late-unknown.json').write_text('{"status":"unknown","receipt":"late-fixture"}')
    print('Permission required: Privacy & Security; Allow this executable' if fx.get('permission_denied') else 'fixture start failed',file=sys.stderr);sys.exit(1)
fx['running']=True;fx['process_path']=str(Path(__file__).absolute()) if not (fx.get('wrong_running_path') and meta['source_commit']=='dc652472d75812dbebc68ef4353a718b0f629cbe') else str(r/'foreign/wms-print')
(r/'system.json').write_text(json.dumps(fx))
'''

# External command fixtures retain actual argument shape. No installer decision is
# implemented here: selection/checks/archive/replacement/rollback must be product.
COMMANDS = r'''#!PYTHON
import hashlib,json,os,shutil,signal,stat,subprocess,sys,zipfile
from pathlib import Path
r=Path(os.environ['WMS607_FX_ROOT']);fx=json.loads((r/'system.json').read_text());name=Path(sys.argv[0]).name;a=sys.argv[1:]
with (r/'commands.jsonl').open('a') as f:f.write(json.dumps([name]+a)+'\n')
if name=='uname': print(fx.get('os','Darwin') if '-s' in a else fx.get('machine','arm64'));sys.exit()
if name=='sysctl':print(fx.get('hardware_arm64',1) if any('hw.optional.arm64' in s for s in a) else fx.get('translated',0));sys.exit()
if name=='curl':
    if fx.get('download_fail') and not any('127.0.0.1' in x for x in a):sys.exit(22)
    url=next((x for x in a if x.startswith(('https://','http://'))),'')
    if '127.0.0.1' in url:
        if not fx.get('running'):sys.exit(7)
        print(json.dumps({'app':'WMS Print Direct','protocolVersion':2}));sys.exit()
    package=r/('arm64.zip' if 'arm64' in url else 'x86_64.zip')
    flag=next((i for i,x in enumerate(a) if x in ('-o','--output')),-1)
    if flag>=0:shutil.copyfile(package,a[flag+1])
    else:sys.stdout.buffer.write(package.read_bytes())
    sys.exit()
if name in ('file','lipo'):
    path=Path(a[-1]);meta=json.loads((path.parent/'build.json').read_text());arch=meta.get('fixture_binary_arch',meta['architecture'])
    print(arch if name=='lipo' else 'Mach-O 64-bit executable '+arch);sys.exit()
if name=='lsof':
    if fx.get('running'):print('42424242' if any('-t' in x for x in a) else 'COMMAND PID USER FD TYPE DEVICE SIZE/OFF NODE NAME\nwms-print 42424242 fixture 3u IPv4 0 0 TCP 127.0.0.1:17843 (LISTEN)')
    sys.exit(0 if fx.get('running') else 1)
if name=='ps':
    if not fx.get('running'):sys.exit(1)
    print(fx.get('process_path','') if any('command' in x or 'comm' in x or 'args' in x for x in a) else '42424242');sys.exit()
if name=='kill':
    if '-0' in a:sys.exit(0 if fx.get('running') else 1)
    fx['running']=False;(r/'system.json').write_text(json.dumps(fx));sys.exit()
if name=='df':print('Filesystem 512-blocks Used Available Capacity Mounted on\nfixture 100000 1000 '+('0' if fx.get('no_space') else '99000')+' 1% /fixture');sys.exit()
if name=='ditto':
    if '-xk' in a:
        z=zipfile.ZipFile(a[-2]);out=Path(a[-1]);out.mkdir(parents=True,exist_ok=True)
        for info in z.infolist():
            p=out/info.filename;p.parent.mkdir(parents=True,exist_ok=True);mode=info.external_attr>>16
            if stat.S_ISLNK(mode):p.symlink_to(z.read(info).decode())
            elif not info.is_dir():p.write_bytes(z.read(info));p.chmod(stat.S_IMODE(mode) or 0o644)
        sys.exit()
    if fx.get('archive_fail'):sys.exit(1)
    if '-c' in a and '-k' in a:
        source=Path(a[-2])
        with zipfile.ZipFile(a[-1],'w') as z:
            for p in source.rglob('*'):
                if p.is_dir():continue
                i=zipfile.ZipInfo(source.name+'/'+str(p.relative_to(source)));i.external_attr=p.lstat().st_mode<<16
                z.writestr(i,os.readlink(p).encode() if p.is_symlink() else p.read_bytes())
        sys.exit()
    shutil.copytree(a[-2],a[-1],symlinks=True,dirs_exist_ok=True);sys.exit()
if name in ('cp','tar','rsync','mkdir'):
    if fx.get('archive_fail') and any(str(r/'backups') in x for x in a):sys.exit(1)
    actual={'cp':'/bin/cp','tar':'/usr/bin/tar','rsync':'/usr/bin/rsync','mkdir':'/bin/mkdir'}[name]
    sys.exit(subprocess.call([actual]+a))
if name=='mv':
    if fx.get('interrupt') and not (r/'interrupted').exists():
        (r/'interrupted').touch();os.kill(os.getppid(),signal.SIGKILL);sys.exit(1)
    if fx.get('replace_fail') and not (r/'replace-failed').exists() and a[-1]==str(r/'app'):
        (r/'replace-failed').touch();sys.exit(1)
    sys.exit(subprocess.call(['/bin/mv']+a))
if name=='spctl' and '--assess' in a:sys.exit(1 if fx.get('permission_denied') else 0)
if name=='xattr' and not any('r' in x for x in a if x.startswith('-')):sys.exit()
if name=='defaults' and 'read' in a:sys.exit()
if name in ('sudo','spctl','xattr','defaults','lpadmin','brew','pip','pip3','pkill','killall'):
    print('forbidden or denied external fixture command',file=sys.stderr);sys.exit(1)
if name=='lpstat':print('system default destination: Fixture_Label_Printer');sys.exit()
if name in ('lp','lpr','cancel'):print('No print or cancel authorized',file=sys.stderr);sys.exit(98)
if name=='open':
    executable=next((x for x in a if x.endswith('/wms-print')),None)
    if executable:sys.exit(subprocess.call([executable]))
    sys.exit()
if name=='codesign':sys.exit(0 if '--verify' in a else 1)
sys.exit(97)
'''


@unittest.skipUnless(sys.platform == "darwin", "Requires actual macOS Swift journal boundary; SKIP is not acceptance")
class UpdaterContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.native_tmp = tempfile.TemporaryDirectory(prefix='wms607-updater-native-')
        cls.native_root = Path(cls.native_tmp.name)
        candidate_override = os.environ.get('WMS607_UPDATER_SWIFT_COPY')
        candidate = Path(candidate_override).read_bytes() if candidate_override else source('tools/print-agent/wms_print_direct_macos.swift')
        cls.source_hash = hashlib.sha256(candidate).hexdigest()
        cls.native = cls.compile_native(candidate.decode(), 'current')
        cls.legacy = cls.compile_native(source('tools/print-agent/wms_print_direct_macos.swift', INSTALLED).decode(), 'legacy', legacy=True)

    @classmethod
    def compile_native(cls, text, name, legacy=False):
        prefix = text.split('private struct HTTPRequest {')[0]
        body = 'let body:[String:Any] = ["idempotencyKey":key,"imageDataUrl":"data:image/png;base64,'+PNG+'","widthMm":58.0,"heightMm":40.0]\n'
        if legacy:
            driver = '''private let p=try Printer(directory:dir,submit:{_,_,_,_ in calls+=1;return "Fixture-41"},queue:{"Fixture"})
do {print(try p.printJob(body))} catch {print("ERROR:"+String(describing:error))}
'''
        else:
            prefix += '\n@_cdecl("wms_cups_observe")\nfunc updaterObserve(_ q:UnsafePointer<CChar>,_ r:UnsafePointer<CChar>,_ t:UnsafePointer<CChar>)->Int32 { fatalError("No CUPS observation authorized") }\n'
            driver = '''private let p=try Printer(directory:dir,autoWork:false,submit:{_,_ in calls+=1;if key=="current-unknown" {throw PrintError.message("External outcome unknown")};return "Fixture-42"},queue:{"Fixture"})
_ = try p.printJob(body)
if CommandLine.arguments[3]=="seed" {p.process(key)}
print(String(data:try JSONSerialization.data(withJSONObject:try p.detail(key)!),encoding:.utf8)!)
'''
        code = prefix + '\nlet dir=URL(fileURLWithPath:CommandLine.arguments[1]);let key=CommandLine.arguments[2];var calls=0\n' + body + driver + '\nprint("SUBMISSIONS:\\(calls)")\n'
        src=cls.native_root/(name+'.swift');src.write_text(code);out=cls.native_root/name
        r=subprocess.run(['swiftc',str(src),'-o',str(out)],capture_output=True,text=True,timeout=60)
        if r.returncode:raise RuntimeError('Actual Swift fixture compilation error: '+r.stderr)
        return out

    @classmethod
    def tearDownClass(cls):
        cls.native_tmp.cleanup()

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='wms607-updater-case-');self.root=Path(self.tmp.name)
        self.app=self.root/'app';self.state=self.root/'state';self.backups=self.root/'backups';self.bin=self.root/'bin'
        for p in (self.app,self.state,self.backups,self.bin):p.mkdir()
        self.fx={'os':'Darwin','machine':'arm64','hardware_arm64':1,'translated':0,'running':True,'process_path':str(self.app/'wms-print')}
        self.records=[];self.native_records=[]
        self.write_system();(self.root/'commands.jsonl').write_text('')
        (self.app/'wms-print').write_text(BINARY.replace('PYTHON',sys.executable));(self.app/'wms-print').chmod(0o755)
        (self.app/'build.json').write_text(json.dumps({'source_commit':INSTALLED,'runtime':'direct','console':True,'architecture':'arm64'}))
        (self.app/'old-only.txt').write_text('previous-only-file');(self.app/'history.html').write_text('previous history')
        (self.app/'history-link').symlink_to('history.html');(self.app/'private-mode').write_text('mode');(self.app/'private-mode').chmod(0o600)
        (self.state/'config').mkdir();(self.state/'config/operator.json').write_text('{"fixture":"PRIVATE_CONFIG_DO_NOT_LOG"}')
        (self.backups/'existing-archive').write_text('do not overwrite')
        for name in ('uname','sysctl','curl','file','lipo','lsof','ps','kill','df','ditto','cp','tar','rsync','mkdir','mv','sudo','spctl','xattr','defaults','lpadmin','brew','pip','pip3','pkill','killall','lp','lpr','lpstat','cancel','open','codesign'):
            p=self.bin/name;p.write_text(COMMANDS.replace('PYTHON',sys.executable));p.chmod(0o755)
        self.seed_journal();self.original_app=snapshot(self.app);self.original_state=snapshot(self.state)
        self.pristine=self.root/'pristine-app';shutil.copytree(self.app,self.pristine,symlinks=True)
        self.make_manifest()

    def tearDown(self):
        if EVIDENCE:
            p=Path(EVIDENCE);p.mkdir(parents=True,exist_ok=True)
            record={'case':self.id(),'source_sha256':self.source_hash,'test_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                    'entry_sha256':hashlib.sha256(ENTRY.read_bytes()).hexdigest() if ENTRY.is_file() else None,'entry_present':ENTRY.is_file(),'executions':self.records,'native_journal_records':self.native_records,
                    'app':snapshot(self.app),'state':snapshot(self.state),'commands':self.commands()}
            text=json.dumps(record,ensure_ascii=False,indent=2).replace(str(self.root),'$CASE')
            (p/(self._testMethodName+'.json')).write_text(text)
        self.tmp.cleanup()

    def write_system(self):
        (self.root/'system.json').write_text(json.dumps(self.fx))

    def native_call(self,key,mode='replay',legacy=False):
        r=subprocess.run([str(self.legacy if legacy else self.native),str(self.state),key,mode],capture_output=True,text=True,timeout=5)
        self.native_records.append({'producer':'public-.4' if legacy else 'actual-current-Printer','key':key,'mode':mode,'exit':r.returncode,'stdout':r.stdout,'stderr':r.stderr})
        self.assertEqual(r.returncode,0,r.stderr)
        return r.stdout

    def seed_journal(self):
        self.assertIn('Fixture-41',self.native_call('legacy-accepted',legacy=True))
        self.assertIn('"accepted"',self.native_call('current-accepted','seed'))
        self.assertIn('"unknown"',self.native_call('current-unknown','seed'))

    def make_manifest(self, metadata=None):
        artifacts={}
        for arch in ('arm64','x86_64'):
            package=self.root/(arch+'.zip')
            meta={'source_commit':TARGET,'runtime':'direct','console':True,'architecture':arch}
            meta.update(metadata or {})
            with zipfile.ZipFile(package,'w') as z:
                for name,data,mode in [('wms-print',BINARY.replace('PYTHON',sys.executable),0o100755),('build.json',json.dumps(meta),0o100644),('history.html','target history',0o100644)]:
                    info=zipfile.ZipInfo('wms-print/'+name);info.external_attr=mode<<16;z.writestr(info,data)
            artifacts[arch]={'url':'https://fixture.invalid/releases/immutable/'+arch+'.zip','sha256':hashlib.sha256(package.read_bytes()).hexdigest()}
        self.manifest={'source_commit':TARGET,'artifacts':artifacts}
        (self.root/'manifest.json').write_text(json.dumps(self.manifest))

    def commands(self):
        return [json.loads(x) for x in (self.root/'commands.jsonl').read_text().splitlines()]

    def require_entry(self):
        self.assertTrue(ENTRY.is_file(), 'Direct updater entrypoint is NOT IMPLEMENTED at BASE; no behavioural execution/RED is claimed')

    def run_update(self):
        self.require_entry()
        text=ENTRY.read_text()
        for flag in ('--app-dir','--state-dir','--backup-dir','--manifest'):
            self.assertIn(flag,text,'Required temporary-filesystem integration boundary absent')
        # Absolute OS-command paths are external boundary replacements only.
        for name in ('curl','uname','sysctl','file','lipo','lsof','ps','kill','df','ditto','cp','tar','rsync','mkdir','mv','sudo','spctl','xattr','defaults','lpadmin','brew','pip','pip3','pkill','killall','lp','lpr','lpstat','cancel','open','codesign'):
            text=re.sub(r'/(?:usr/bin|usr/sbin|bin|sbin)/'+name+r'\b',str(self.bin/name),text)
        copy=self.root/('entry-copy-'+uuid.uuid4().hex+'.sh');copy.write_text(text)
        env={'PATH':str(self.bin)+':/usr/bin:/bin:/usr/sbin:/sbin','TMPDIR':str(self.root),
             'WMS607_FX_ROOT':str(self.root),'WMS607_FX_BIN':str(self.bin)}
        wrapper='function kill(){ "$WMS607_FX_BIN/kill" "$@"; }; export -f kill; exec /bin/bash "$@"'
        r=subprocess.run(['/bin/bash','-c',wrapper,'fixture',str(copy),'--app-dir',str(self.app),'--state-dir',str(self.state),
                          '--backup-dir',str(self.backups),'--manifest',str(self.root/'manifest.json')],env=env,capture_output=True,text=True,timeout=15)
        self.records.append({'exit':r.returncode,'stdout':r.stdout,'stderr':r.stderr})
        self.assertNotIn('PRIVATE_CONFIG_DO_NOT_LOG',r.stdout+r.stderr)
        self.assertFalse(any(c[0] in ('lp','lpr','cancel') for c in self.commands()),'Updater must not submit/cancel printing')
        return r

    def assert_old_preserved(self):
        self.assertEqual(snapshot(self.app),self.original_app)
        self.assertEqual(snapshot(self.state),self.original_state)
        fx=json.loads((self.root/'system.json').read_text())
        self.assertEqual((fx.get('running'),fx.get('process_path')),(self.fx.get('running'),self.fx.get('process_path')))
        self.assertEqual((self.backups/'existing-archive').read_text(),'do not overwrite')

    def assert_target(self):
        self.assertEqual(json.loads((self.app/'build.json').read_text())['source_commit'],TARGET)
        self.assertFalse((self.app/'old-only.txt').exists(),'No mixed old/target application')
        fx=json.loads((self.root/'system.json').read_text());self.assertTrue(fx['running'])
        self.assertEqual(fx['process_path'],str(self.app/'wms-print'))
        self.assertEqual(snapshot(self.state),self.original_state)
        stops=[c for c in self.commands() if c[0]=='kill' and '-0' not in c]
        self.assertTrue(stops,'Initial update must stop the owned old process')
        self.assertTrue(all('42424242' in c and not any(x.isdigit() and x!='42424242' for x in c[1:]) for c in stops))
        self.assertTrue(any(c[0]=='curl' and any('127.0.0.1' in x for x in c) for c in self.commands()),'Actual updater must verify health as well as process identity')

    def assert_archived(self):
        self.assertEqual((self.backups/'existing-archive').read_text(),'do not overwrite')
        # Observable files/permissions/symlinks, not an internal archive-name API.
        roots=[self.backups]
        unpack=self.root/'read-backups';unpack.mkdir(exist_ok=True)
        for archive in list(self.backups.rglob('*')):
            if not archive.is_file():continue
            destination=unpack/str(len(roots));destination.mkdir(exist_ok=True)
            if zipfile.is_zipfile(archive):
                with zipfile.ZipFile(archive) as z:
                    for i in z.infolist():
                        self.assertFalse(Path(i.filename).is_absolute() or '..' in Path(i.filename).parts)
                        p=destination/i.filename;p.parent.mkdir(parents=True,exist_ok=True);mode=i.external_attr>>16
                        if stat.S_ISLNK(mode):p.symlink_to(z.read(i).decode())
                        elif not i.is_dir():p.write_bytes(z.read(i));p.chmod(stat.S_IMODE(mode) or 0o644)
                roots.append(destination)
            elif tarfile.is_tarfile(archive):
                with tarfile.open(archive) as t:t.extractall(destination,filter='data')
                roots.append(destination)
        directories=[d for root in roots for d in [root,*root.rglob('*')] if d.is_dir()]
        found=[]
        for directory in directories:
            if directory.is_dir() and (directory/'build.json').exists():found.append(snapshot(directory))
        self.assertIn(self.original_app,found,'Complete prior application including modes/links must be recoverable')
        states=[snapshot(d) for d in directories if (d/'direct-jobs.json').exists()]
        self.assertIn(self.original_state,states,'Consistent prior Direct state/config backup missing')

    def test_uc1_hardware_selection_arm_intel_rosetta_and_unsupported(self):
        self.require_entry()
        for machine,arm,translated,arch in [('arm64',1,0,'arm64'),('x86_64',1,1,'arm64'),('x86_64',0,0,'x86_64')]:
            with self.subTest(machine=machine,translated=translated):
                shutil.rmtree(self.app);shutil.copytree(self.pristine,self.app,symlinks=True)
                self.fx.update(machine=machine,hardware_arm64=arm,translated=translated,running=True,process_path=str(self.app/'wms-print'));self.write_system()
                r=self.run_update();self.assertEqual(r.returncode,0,r.stderr);self.assert_target()
                downloads=[x for x in self.commands() if x[0]=='curl' and any('fixture.invalid' in a for a in x)]
                self.assertTrue(any(arch+'.zip' in a for a in downloads[-1]))
        for changes in ({'os':'Linux'},{'os':'Darwin','machine':'ppc','hardware_arm64':0}):
            self.fx.update(changes);self.write_system();before=[snapshot(p) for p in (self.app,self.state,self.backups)]
            self.assertNotEqual(self.run_update().returncode,0);self.assertEqual([snapshot(p) for p in (self.app,self.state,self.backups)],before)

    def test_uc2_pins_invalid_archive_metadata_and_selftest_fail_closed(self):
        self.require_entry()
        for failure in ('checksum','source','runtime','console','arch','metadata_arch','python','metadata_json','missing_metadata','corrupt','download','selftest'):
            with self.subTest(failure=failure):
                self.fx={'os':'Darwin','machine':'arm64','hardware_arm64':1,'running':True,'process_path':str(self.app/'wms-print')}
                edits={'source':{'source_commit':'f'*40},'runtime':{'runtime':'paired'},'console':{'console':False},'arch':{'fixture_binary_arch':'x86_64'},'metadata_arch':{'architecture':'x86_64'}}
                self.make_manifest(edits.get(failure));self.write_system()
                if failure in ('python','metadata_json','missing_metadata'):
                    zpath=self.root/'arm64.zip'
                    with zipfile.ZipFile(zpath) as z:items={i.filename:(z.read(i),i.external_attr) for i in z.infolist()}
                    if failure=='python':items['wms-print/_internal/Python.framework/Python']=(b'embedded Python',0o100755<<16)
                    if failure=='metadata_json':items['wms-print/build.json']=(b'{not json',0o100644<<16)
                    if failure=='missing_metadata':items.pop('wms-print/build.json')
                    with zipfile.ZipFile(zpath,'w') as z:
                        for name,(data,mode) in items.items():
                            info=zipfile.ZipInfo(name);info.external_attr=mode;z.writestr(info,data)
                    self.manifest['artifacts']['arm64']['sha256']=hashlib.sha256(zpath.read_bytes()).hexdigest()
                if failure=='checksum':self.manifest['artifacts']['arm64']['sha256']='0'*64
                if failure=='corrupt':
                    (self.root/'arm64.zip').write_bytes(b'not zip');self.manifest['artifacts']['arm64']['sha256']=hashlib.sha256(b'not zip').hexdigest()
                if failure in ('download','selftest'):self.fx[failure+'_fail']=True;self.write_system()
                (self.root/'manifest.json').write_text(json.dumps(self.manifest))
                before_commands=len(self.commands())
                self.assertNotEqual(self.run_update().returncode,0);self.assert_old_preserved()
                self.assertFalse(any(c[0]=='kill' and '-0' not in c for c in self.commands()[before_commands:]),'Invalid artifact must not stop old process')
        self.make_manifest();self.fx.pop('selftest_fail',None);self.write_system()
        self.assertEqual(self.run_update().returncode,0);self.assert_target()

    def test_uc3_lossless_backup_and_archive_or_space_failure(self):
        self.require_entry()
        for failure in ('archive_fail','no_space'):
            with self.subTest(failure=failure):
                self.fx[failure]=True;self.write_system();self.assertNotEqual(self.run_update().returncode,0);self.assert_old_preserved();self.fx.pop(failure)
        self.write_system();self.assertEqual(self.run_update().returncode,0);self.assert_archived();self.assert_target()

    def test_uc4_foreign_port_owner_and_health200_wrong_process(self):
        self.require_entry()
        self.fx['process_path']=str(self.root/'foreign/wms-print');self.write_system()
        self.assertNotEqual(self.run_update().returncode,0);self.assert_old_preserved()
        self.assertFalse(any(c[0]=='kill' and '-0' not in c for c in self.commands()))
        self.fx['process_path']=str(self.app/'wms-print');self.fx['wrong_running_path']=True;self.write_system()
        self.assertNotEqual(self.run_update().returncode,0);self.assertEqual(snapshot(self.app),self.original_app)

    def test_uc5_replace_and_start_rollback_preserve_current_journal(self):
        self.require_entry()
        self.fx['replace_fail']=True;self.write_system()
        self.assertNotEqual(self.run_update().returncode,0);self.assert_old_preserved()
        self.fx.pop('replace_fail');self.fx['start_fail']=True;self.write_system()
        self.assertNotEqual(self.run_update().returncode,0);self.assertEqual(snapshot(self.app),self.original_app)
        self.assertTrue((self.state/'late-unknown.json').exists(),'Current unknown/receipt must survive rollback')
        for name,value in self.original_state.items():self.assertEqual(snapshot(self.state)[name],value)

    def test_uc6_repeat_concurrent_and_interrupted_update_recover(self):
        self.require_entry()
        self.fx['interrupt']=True;self.write_system();self.assertNotEqual(self.run_update().returncode,0)
        self.fx.pop('interrupt');self.write_system()
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda _:self.run_update(),range(2)))
        self.assertTrue(any(r.returncode==0 for r in results));self.assert_target();self.assert_archived()
        archived=snapshot(self.backups);commands=list(self.commands())
        self.assertEqual(self.run_update().returncode,0);self.assertEqual(snapshot(self.backups),archived)
        self.assertFalse(any(c[0]=='kill' and '-0' not in c for c in self.commands()[len(commands):]),'Verified target repeat must preserve running target')

    def test_uc7_actual_journal_replay_after_update_and_failed_restart(self):
        self.require_entry()
        self.assertEqual(self.run_update().returncode,0);self.assert_target();self.assert_archived()
        self.assert_journal_replay()
        # A new immutable target with start failure exercises compatible old bytes rollback.
        self.manifest['source_commit']='a'*40
        self.make_manifest({'source_commit':'a'*40});self.manifest['source_commit']='a'*40
        (self.root/'manifest.json').write_text(json.dumps(self.manifest));self.fx['start_fail']=True;self.fx['failure_source']='a'*40;self.write_system()
        before=snapshot(self.app);self.assertNotEqual(self.run_update().returncode,0);self.assertEqual(snapshot(self.app),before)
        self.assert_journal_replay()

    def assert_journal_replay(self):
        for key,status,receipt in [('legacy-accepted','accepted','Fixture-41'),('current-accepted','accepted','Fixture-42'),('current-unknown','unknown',None)]:
            out=self.native_call(key)
            self.assertIn('SUBMISSIONS:0',out);self.assertIn('"'+status+'"',out)
            if receipt:self.assertIn(receipt,out)
            old=self.native_call(key,legacy=True)
            self.assertIn('SUBMISSIONS:0',old)
            self.assertIn(receipt if receipt else 'ERROR:',old)

    def test_uc8_no_security_printer_or_dependencies_change_permission_recovery(self):
        self.require_entry()
        self.fx['permission_denied']=True;self.write_system();r=self.run_update();self.assertNotEqual(r.returncode,0)
        self.assertRegex((r.stdout+r.stderr).lower(),r'permission|privacy|security|разреш|конфиденц')
        self.assertEqual(snapshot(self.app),self.original_app)
        forbidden={'sudo','lpadmin','brew','pip','pip3','pkill','killall','lp','lpr','cancel'}
        self.assertFalse(any(c[0] in forbidden or (c[0]=='spctl' and '--master-disable' in c) or (c[0]=='defaults' and any(x in c for x in ('write','delete'))) or (c[0]=='xattr' and any('r' in x for x in c[1:] if x.startswith('-'))) for c in self.commands()))
        self.fx.pop('permission_denied');self.write_system();self.assertEqual(self.run_update().returncode,0);self.assert_target()

    def test_preservation_actual_public_and_current_journal_replay(self):
        self.assert_journal_replay()

    def test_preservation_actual_direct_build_metadata(self):
        # Execute existing full builder main; compiler/sign/archive/OS are external.
        data=source('tools/print-agent/build_console.py');override=os.environ.get('WMS607_UPDATER_BUILD_COPY')
        if override:data=Path(override).read_bytes()
        module=types.ModuleType('actual_direct_builder');module.__file__=str(ROOT/'build_console.py')
        exec(compile(data,module.__file__,'exec'),module.__dict__)
        module.ROOT=self.root/'builder';module.ROOT.mkdir();module.REPO=self.root
        for name in ('history.html','wms_print_direct_macos.swift','wms_cups_observe.c'):(module.ROOT/name).write_text('fixture external compiler input')
        calls=[]
        def run(args,**kwargs):
            calls.append(args)
            if '-o' in args:Path(args[args.index('-o')+1]).write_text('external compiler fixture')
            if args[0]=='ditto' and '-xk' in args:Path(args[-1]).mkdir(parents=True,exist_ok=True)
            return subprocess.CompletedProcess(args,0)
        with patch.object(module.sys,'platform','darwin'),patch.object(module.platform,'machine',return_value='arm64'),patch.object(module.subprocess,'check_output',side_effect=['',TARGET+'\n']),patch.object(module.subprocess,'run',side_effect=run):
            module.main()
        meta=json.loads((module.ROOT/'dist-console/wms-print/build.json').read_text())
        self.assertEqual((meta['source_commit'],meta['runtime'],meta['console'],meta['architecture']),(TARGET,'direct',True,'arm64'))
        self.assertFalse(meta['physical_print_verified']);self.assertFalse((module.ROOT/'dist-console/wms-print/_internal').exists())
        self.assertTrue(any(c[0]=='swiftc' for c in calls));self.assertFalse(any('PyInstaller' in c for c in calls))


if __name__=='__main__':unittest.main()
