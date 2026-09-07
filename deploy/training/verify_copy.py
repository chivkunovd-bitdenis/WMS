"""Read-only checks of the restored training containers; run on the destination host."""
import hashlib
import io
import json
import subprocess
import tarfile
from pathlib import Path

root = Path('/opt/wms-training')
manifest = json.loads((root / 'private/file-manifests.json').read_text())


def python_in(service, script):
    result = subprocess.run(['docker', 'compose', 'exec', '-T', service, 'python', '-'],
                            cwd=root, input=script, text=True, capture_output=True, check=True)
    return json.loads(result.stdout)


report = {}
for service, kind, directory in [('api', 'api', '/app'), ('api', 'files', '/app/var'),
                                  ('wb-emulator', 'emulator', '/app')]:
    expected = manifest[kind]
    actual = python_in(service, f'''import hashlib,json
from pathlib import Path
root=Path({directory!r})
print(json.dumps({{name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in {list(expected)!r}}}))
''')
    assert actual == expected, f'{kind}: source file mismatch'
    report[kind + '_matching_files'] = len(expected)

web = subprocess.check_output(['docker', 'compose', 'exec', '-T', 'web', 'tar', '-C', '/srv', '-cf', '-', '.'], cwd=root)
with tarfile.open(fileobj=io.BytesIO(web)) as t:
    actual = {m.name.removeprefix('./'): hashlib.sha256(t.extractfile(m).read()).hexdigest()
              for m in t.getmembers() if m.isfile()}
assert actual == manifest['web'], 'Live frontend mismatch'
report['web_matching_files'] = len(actual)

expected = json.loads((root / 'private/source-row-counts.json').read_text())
expected['users'] += 1  # One new training operator, with all historic relations retained.
actual = python_in('api', f'''import json
from sqlalchemy import create_engine,text
from app.core.settings import settings
engine=create_engine(settings.database_url.replace('+psycopg_async','+psycopg'))
with engine.connect() as c:
 print(json.dumps({{name:c.execute(text('SELECT count(*) FROM "'+name+'"')).scalar_one() for name in {list(expected)!r}}}))
''')
assert actual == expected, {k: [v, actual.get(k)] for k, v in expected.items() if actual.get(k) != v}
report['matching_tables'] = len(expected)
report['rows_after_training_account'] = sum(actual.values())

for service, requirements in [('api', 'requirements-api.txt'), ('wb-emulator', 'requirements-emulator.txt')]:
    required = dict(line.strip().split('==', 1) for line in (root / requirements).read_text().splitlines() if line.strip())
    actual = python_in(service, f'''import importlib.metadata,json
print(json.dumps({{name:importlib.metadata.version(name) for name in {list(required)!r}}}))
''')
    assert required == actual, f'{service}: dependency mismatch'
    report[service + '_matching_dependencies'] = len(required)
    result = python_in(service, '''import json,socket
try:
 s=socket.create_connection(('1.1.1.1',443),timeout=3);s.close();result='UNEXPECTED_EXTERNAL_ACCESS'
except OSError as e:result=type(e).__name__
print(json.dumps(result))
''')
    assert result != 'UNEXPECTED_EXTERNAL_ACCESS', service
    report[service + '_external_access'] = 'blocked: ' + result

report['emulator_internal_health'] = python_in('api', '''import json,urllib.request
print(json.dumps(urllib.request.urlopen('http://wb-emulator:8000/health').status))
''')
assert report['emulator_internal_health'] == 200
print(json.dumps(report, indent=2))
