"""Bounded immutable AST/replay proof, without rerunning PostgreSQL."""
import ast
import asyncio
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
RED = 'fb05f4dc22a1fb6b62ab0d52be2729ae4b449f3c'
GREEN = 'e2495dfa50767f156e6f54d91889c6067d6d5625'
FILE = 'backend/tests/test_wms662_cancellation_lock_order.py'
REG = 'backend/tests/test_wms662_cancellation_lock_order_regression.py'
def git(*args):
    return subprocess.check_output(['git', *args]).decode()
def source(ref, path=FILE):
    return git('show', f'{ref}:{path}')
def schedule(ref):
    node = next(n for n in ast.parse(source(ref)).body if isinstance(n, ast.ClassDef) and n.name == 'LockSchedule')
    ns = {'asyncio': asyncio, 'text': lambda s:s}
    exec(compile(ast.Module(body=[node], type_ignores=[]), FILE, 'exec'), ns)
    return ns
old, new = [ast.parse(source(ref)) for ref in (RED,GREEN)]
test = lambda tree: next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name.startswith('test_f6_cancel_'))
assert ast.dump(ast.Module(body=test(old).decorator_list,type_ignores=[])) == ast.dump(ast.Module(body=test(new).decorator_list,type_ignores=[]))
assert source(RED).split('    assert not schedule.errors,',1)[1] == source(GREEN).split('    assert not schedule.errors,',1)[1]
assert git('rev-list','--parents','-n','1',GREEN).split()[1] == RED
regression = next(n for n in ast.parse(source(RED,REG)).body if isinstance(n,ast.AsyncFunctionDef))
regression.decorator_list = []
results = []
async def original_regression(ref):
    ns = schedule(ref)
    class Observer:
        async def scalar(self, statement, params):
            assert 'pg_blocking_pids' in statement
            assert params == {'cancel_pid':902,'handoff_pid':901}
            return True
    class Context:
        async def __aenter__(self): return Observer()
        async def __aexit__(self,*args): return False
    # Execute the exact frozen test function and its observer definitions.
    definitions = [n for n in ast.parse(source(RED,REG)).body if isinstance(n,ast.ClassDef)]
    f6 = SimpleNamespace(LockSchedule=ns['LockSchedule'])
    class Patch:
        def setattr(self, module, name, value):
            setattr(module,name,value)
            ns[name] = value
    env = {'f6':f6}
    exec(compile(ast.Module(body=definitions+[regression],type_ignores=[]),REG,'exec'),env)
    try:
        await env[regression.name](Patch())
        return 'PASS'
    except AttributeError as exc:
        assert ref == RED and 'observed_pids' in str(exc)
        return 'RED AttributeError observed_pids'
async def edge(kind):
    ns = schedule(GREEN)
    obj = ns['LockSchedule']()
    obj.pids = {'handoff':901,'cancel':902}
    if kind == 'same-pid': obj.pids['handoff'] = 902
    class Observer:
        async def scalar(self, statement, params):
            if kind == 'unconfirmed':
                obj.release.set()
                return False
            if kind == 'mutation-during-await': obj.pids['handoff'] = 902
            return True
    class Context:
        async def __aenter__(self): return Observer()
        async def __aexit__(self,*args): return False
    ns['SessionLocal'] = Context
    release = obj.release.set
    if kind == 'mutation-during-await':
        def checked_release():
            assert obj.observed_pids == {'handoff':901,'cancel':902}
            release()
        obj.release.set = checked_release
    await obj.wait_for_contention()
    # Same independent-connection conditions used by the actual F6 assertion.
    accepted = obj.contended and obj.observed_pids is not None and set(obj.observed_pids) == {'handoff','cancel'} and len(set(obj.observed_pids.values())) == 2
    assert accepted == (kind == 'mutation-during-await')
    if kind == 'unconfirmed': assert obj.observed_pids is None and not obj.contended
    return dict(scenario=kind,accepted=bool(accepted),observed=obj.observed_pids,live=obj.pids)
async def run():
    red,green = await original_regression(RED),await original_regression(GREEN)
    assert red.startswith('RED') and green == 'PASS'
    return {'red':RED,'green':GREEN,'original_frozen_regression':[red,green],
        'parameter_decorators_identical':True,'all_business_assertions_after_SQL_errors_identical':True,
        'replays':[await edge(k) for k in ['mutation-during-await','unconfirmed','same-pid']],
        'limit':'AST replay exercises actual fixture methods; does not simulate a real PG race or claim product PASS'}
result = asyncio.run(run())
(HERE/'audit.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
