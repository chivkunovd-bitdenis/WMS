"""Only dispatch to this audit's disposable PG DB; no caller env inheritance."""
import os,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
OUT=Path(__file__).parent
PY='/Users/deniscivkunov/Projects/WMS/backend/.venv/bin/python'
assert ROOT == Path('/Users/deniscivkunov/Projects/WMS/.worktrees/wms501-performance-isolation-audit')
env={'PATH':'/usr/bin:/bin:/usr/sbin:/sbin','PYTHONPATH':f'{ROOT}/backend:{ROOT}/backend/tests:{OUT}',
     'WMS_ALLOW_PUBLIC_REGISTRATION':'true','APP_ENV':'development',
     'JWT_SECRET_KEY':'wms501-isolated-test-secret-at-least-32-characters',
     'WMS_TEST_DATABASE_URL':'postgresql+psycopg_async://deniscivkunov@127.0.0.1:55451/wms501_isolation2',
     'WMS_TEST_DATA_DIR':str(ROOT/'.audit-runtime/isolation-completion-data')}
mode=sys.argv[1] if len(sys.argv)>1 else 'selected'
args=(OUT/'isolation-completion-selected-tests.txt').read_text().splitlines() if mode=='selected' else ['-o','asyncio_mode=auto','-p','conftest',str(OUT/'isolation-completion-probes.py')]
cmd=[PY,'-m','pytest','-q','-c',str(ROOT/'backend/pyproject.toml'),'--tb=short','-p','isolation-completion-offline',f'--junitxml={OUT}/isolation-completion-{mode}.xml',*args,*sys.argv[2:]]
print('Isolated loopback PostgreSQL wms501_isolation2; external sockets blocked; mode='+mode,flush=True)
raise SystemExit(subprocess.run(cmd,cwd=ROOT,env=env).returncode)
