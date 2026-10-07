"""Read-only package consumer: no native execution, tests, build or CI dispatch."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import stat
import struct
import subprocess
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parent
SOURCE = 'a475a7342c0da72dd49b2990bd998c522ecc2c2b'
HARNESS = '1c2bddd844ff6baf331eae53b3a44304d834cc01'
RUN = 37583326182
parser = argparse.ArgumentParser()
parser.add_argument('architecture', choices=['arm64', 'x86_64'])
args = parser.parse_args()
arch = args.architecture


def sha(data):
    return hashlib.sha256(data).hexdigest()


def git(path):
    return subprocess.check_output(['git', 'show', SOURCE + ':' + path], cwd=ROOT)


def report_ids(data, count):
    root = ET.fromstring(data)
    assert tuple(root.get(k) for k in ('tests', 'failures', 'errors', 'skipped')) == (str(count), '0', '0', '0')
    assert not any(len(list(root.iter(tag))) for tag in ('failure', 'error', 'skipped'))
    ids = [c.get('classname') + '::' + c.get('name') for c in root.iter('testcase')]
    assert len(ids) == len(set(ids)) == count
    return ids


directory = ROOT / 'artifacts' / arch
wrapper = directory / 'original-wrapper.zip'
metadata = json.loads((ROOT / 'api/artifacts.json').read_text())['artifacts']
name = f'WMS607-Direct-{arch}-{SOURCE}-{RUN}-1'
matched = [a for a in metadata if a['name'] == name]
assert len(matched) == 1
artifact = matched[0]
assert not artifact['expired'] and artifact['workflow_run']['id'] == RUN
assert artifact['workflow_run']['head_sha'] == HARNESS
wrapper_data = wrapper.read_bytes()
assert len(wrapper_data) == artifact['size_in_bytes']
assert 'sha256:' + sha(wrapper_data) == artifact['digest']
payload = directory / 'payload'
payload.mkdir(exist_ok=True)
members = []
with zipfile.ZipFile(wrapper) as archive:
    assert len(set(archive.namelist())) == len(archive.namelist())
    for entry in archive.infolist():
        path = PurePosixPath(entry.filename)
        assert not path.is_absolute() and '..' not in path.parts
        assert not stat.S_ISLNK(entry.external_attr >> 16)
        output = payload.joinpath(*path.parts)
        if entry.is_dir():
            output.mkdir(parents=True, exist_ok=True)
            continue
        data = archive.read(entry)
        output.parent.mkdir(parents=True, exist_ok=True)
        if not output.exists():
            output.write_bytes(data)
        assert output.read_bytes() == data
        members.append({'member': entry.filename, 'bytes': len(data), 'sha256': sha(data),
                        'ZIP_CRC32': entry.CRC, 'zip_external_attr': entry.external_attr})
assert len(list(payload.rglob('source.txt'))) == 1
receipt = next(payload.rglob('source.txt')).parent
assert (receipt / 'source.txt').read_text().strip() == SOURCE
assert (receipt / 'harness.txt').read_text().strip() == HARNESS
reports = []
all_ids = []
for filename, baseline, count in [('updater.xml', 'updater.xml', 10), ('stop.xml', 'green.xml', 4), ('existing.xml', 'existing.xml', 19)]:
    data = (receipt / filename).read_bytes()
    ids = report_ids(data, count)
    expected = report_ids(git('docs/evidence/WMS-607/updater-stop-fix-20261007/' + baseline), count)
    assert sorted(ids) == sorted(expected)
    reports.append({'report': filename, 'sha256': sha(data), 'PASS': count, 'IDs': ids})
    all_ids.extend(ids)
data = (receipt / 'startup-owner.xml').read_bytes()
ids = report_ids(data, 3)
contract = json.loads(git('docs/evidence/WMS-607/startup-owner-test-contract-20261007/contract.json'))
assert sorted(ids) == sorted(contract['suite']['xml_ids'])
reports.append({'report': 'startup-owner.xml', 'sha256': sha(data), 'PASS': 3, 'IDs': ids})
all_ids.extend(ids)
assert len(all_ids) == len(set(all_ids)) == 36
shell_sha = sha(git('tools/print-agent/update_macos_direct.sh'))
swift_sha = sha(git('tools/print-agent/wms_print_direct_macos.swift'))
raw = []
for folder, test, count in [('updater', 'test_macos_direct_updater_contract.py', 10), ('startup-owner', 'test_macos_direct_updater_start_owner_contract.py', 3)]:
    files = list((receipt / folder).glob('*.json'))
    assert len(files) == count
    for path in files:
        record = json.loads(path.read_text())
        assert record['test_sha256'] == sha(git('tools/print-agent/' + test))
        assert record['source_sha256'] == (swift_sha if folder == 'updater' else shell_sha)
        if folder == 'updater':
            assert record['entry_sha256'] == shell_sha
        raw.append({'path': str(path.relative_to(payload)), 'sha256': sha(path.read_bytes())})
http = list((receipt / 'http').glob('*.json'))
assert len(http) == 5
for path in http:
    assert json.loads(path.read_text())['provenance']['source_sha256'] == swift_sha
    raw.append({'path': str(path.relative_to(payload)), 'sha256': sha(path.read_bytes())})
native_archives = list(payload.rglob('WMS-Print-Console-Mac-*.zip'))
assert len(native_archives) == 1
native = native_archives[0]
provenance = json.loads((receipt / 'archive.json').read_text())
assert native.name == provenance['archive'] == f'WMS-Print-Console-Mac-{arch}.zip'
assert native.stat().st_size == provenance['size']
assert sha(native.read_bytes()) == provenance['sha256']
native_members = []
with zipfile.ZipFile(native) as archive:
    assert len(set(archive.namelist())) == len(archive.namelist())
    build = json.loads(archive.read('wms-print/build.json'))
    assert build == provenance['build']
    assert build == {'source_commit': SOURCE, 'platform': 'darwin', 'architecture': arch,
                     'runtime': 'direct', 'console': True, 'physical_print_verified': False}
    executable = archive.read('wms-print/wms-print')
    assert struct.unpack('<I', executable[:4])[0] == 0xFEEDFACF
    assert struct.unpack('<I', executable[4:8])[0] == {'arm64': 0x0100000C, 'x86_64': 0x01000007}[arch]
    assert archive.getinfo('wms-print/wms-print').external_attr >> 16 & 0o111
    updater = archive.read('wms-print/update_macos_direct.sh')
    assert updater == git('tools/print-agent/update_macos_direct.sh')
    assert not any('python' in n.lower() or '_internal' in n for n in archive.namelist())
    for entry in archive.infolist():
        data = archive.read(entry)
        native_members.append({'member': entry.filename, 'bytes': len(data), 'sha256': sha(data),
                               'ZIP_CRC32': entry.CRC, 'zip_external_attr': entry.external_attr})
assert 'WMS Print Direct macOS: package OK' in (receipt / 'build.log').read_text()
assert 'WMS Print Direct macOS: package OK' in (receipt / 'self-test.log').read_text()
jobs = json.loads((ROOT / 'api/jobs.json').read_text())['jobs']
matched = [j for j in jobs if arch in j['name']]
assert len(matched) == 1
job = matched[0]
assert job['run_id'] == RUN and job['run_attempt'] == 1
assert job['status'] == 'completed' and job['conclusion'] == 'success'
for step in job['steps']:
    assert step['status'] == 'completed' and step['conclusion'] == 'success', step
joblog = ROOT / 'jobs' / (arch + '-job.log')
assert joblog.is_file() and joblog.stat().st_size > 0
(directory / 'member-manifest.json').write_text(json.dumps({'wrapper_sha256': sha(wrapper_data), 'members': members,
                                                         'native_archive_members': native_members}, indent=2) + '\n')
result = {'architecture': arch, 'run_id': RUN, 'attempt': 1, 'SOURCE': SOURCE, 'HARNESS': HARNESS,
          'job_id': job['id'], 'job_conclusion': job['conclusion'], 'artifact_id': artifact['id'],
          'artifact_name': name, 'original_wrapper_sha256': sha(wrapper_data), 'original_wrapper_bytes': len(wrapper_data),
          'wrapper_payload_members': len(members), 'reports': reports, 'total_PASS': 36, 'FAIL': 0, 'ERROR': 0, 'SKIP': 0,
          'raw_source_identity_records': raw, 'original_native_archive': str(native.relative_to(ROOT)),
          'archive_sha256': sha(native.read_bytes()), 'archive_bytes': native.stat().st_size,
          'build': build, 'executable_sha256': sha(executable), 'MachO64_native_CPU_type_verified': True,
          'embedded_updater_sha256': sha(updater), 'embedded_updater_equals_accepted_SOURCE': True,
          'CI_codesign_unpacked_selftest_and_provenance_steps_success': True,
          'full_joblog_sha256': sha(joblog.read_bytes()), 'client_install_public_release_physical_print_verified': False}
(directory / 'verification.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps({k: result[k] for k in ('architecture', 'total_PASS', 'archive_sha256', 'archive_bytes', 'original_native_archive')}, indent=2))
