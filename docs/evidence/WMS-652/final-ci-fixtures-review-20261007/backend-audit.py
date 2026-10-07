"""Immutable Ozon contract/UTC negative proof, without backend test rerun."""
import ast
from datetime import UTC, datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

HERE=Path(__file__).resolve().parent
C='bdfea8e006c9dd7a15341b9aef27abeaaefa3b02'
E='1e65ec682c4afd870b98edf85ca723b18115842b'
FILE='backend/tests/test_ozon_posting_contract.py'
def git(*args):return subprocess.check_output(['git',*args])
def source(ref,path=FILE):return git('show',f'{ref}:{path}')
parent=git('rev-parse',C+'^').decode().strip()
assert git('diff','--name-only',parent,C).decode().splitlines()==[FILE]
trees=[ast.parse(source(r)) for r in [parent,C]]
name='test_posting_barcode_price_and_creation_date_come_from_the_real_fields'
funcs=[{n.name:n for n in tree.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))} for tree in trees]
for n,node in funcs[0].items():
 if n!=name:assert ast.dump(node)==ast.dump(funcs[1][n])
before=[n for n in ast.walk(funcs[0][name]) if isinstance(n,ast.Assert)]
after=[n for n in ast.walk(funcs[1][name]) if isinstance(n,ast.Assert)]
after=[n for n in after if not (isinstance(n.test,ast.Compare) and ast.unparse(n.test.left).startswith('FbsOrder.__table__'))]
for node in after:
 if isinstance(node.test,ast.Compare) and isinstance(node.test.left,ast.Call) and isinstance(node.test.left.func,ast.Name) and node.test.left.func.id=='_utc_after_database_round_trip':
  assert ast.unparse(node.test.left.keywords[0].value)=='is_sqlite'
  node.test.left=node.test.left.args[0]
assert [ast.dump(n) for n in before]==[ast.dump(n) for n in after]
helper=funcs[1]['_utc_after_database_round_trip'];ns={'datetime':datetime,'UTC':UTC}
exec(compile(ast.Module(body=[helper],type_ignores=[]),FILE,'exec'),ns);normalize=ns[helper.name]
expected=datetime(2026,9,1,10,30,tzinfo=UTC)
assert normalize(expected.replace(tzinfo=None),is_sqlite=True)==expected
assert normalize(expected,is_sqlite=False)==expected
assert normalize(datetime(2026,9,1,13,30,tzinfo=timezone(timedelta(hours=3))),is_sqlite=False)==expected
negative=[]
for label,value,sqlite in [('sqlite-wrong-hour',datetime(2026,9,1,11,30),True),('postgres-wrong-hour',expected+timedelta(hours=1),False),('sqlite-wrong-day',datetime(2026,9,2,10,30),True)]:
 assert normalize(value,is_sqlite=sqlite)!=expected;negative.append(label)
for label,value,sqlite in [('postgres-lost-tz',expected.replace(tzinfo=None),False),('sqlite-unexpected-aware',expected,True)]:
 try:normalize(value,is_sqlite=sqlite)
 except AssertionError:negative.append(label)
 else:raise AssertionError(label+' silently accepted')
row=ast.unparse(funcs[1]['posting_row']);assert '2026-09-01T10:30:00Z' in row and '2026-09-04T10:30:00Z' in row
doc=source(E,'docs/evidence/wms652/ozon-posting-date-roundtrip-20261007.md')
(HERE/'backend-published-evidence.md').write_bytes(doc)
pg=Path('/Users/deniscivkunov/Projects/WMS/.agent-runs/night-20261006-01a112a8/f6-local-pg')
digests={'ozon-date-roundtrip.xml':'389f8b6b9f8a2df41a996c9e3c3fb4f88ee84daaca38102cc10b8cac47068e4a','ozon-date-roundtrip.log':'262eb7593124b35872166f12cbc341109c3acd1b0337453b2aadd798c88e8860'}
for n,h in digests.items():
 b=(pg/n).read_bytes();assert hashlib.sha256(b).hexdigest()==h;(HERE/n).write_bytes(b)
xml=ET.fromstring((pg/'ozon-date-roundtrip.xml').read_bytes());cases=list(xml.iter('testcase'))
assert len(cases)==1 and cases[0].get('name')==name
assert not any(list(xml.iter(n)) for n in ['failure','error','skipped'])
events=Path('/Users/deniscivkunov/Projects/WMS/.agent-runs/night-20261006-01a112a8/migration-merge/ozon-utc-representation-fix-events.jsonl')
outputs=[]
for line in events.read_text().splitlines():
 event=json.loads(line)
 def visit(v):
  if isinstance(v,dict):
   if 'aggregated_output' in v and any(x in v['aggregated_output'] for x in ['44 passed','tests/test_ozon_posting_contract.py:325: AssertionError']):outputs.append(v['aggregated_output'])
   for value in v.values():visit(value)
  elif isinstance(v,list):
   for value in v:visit(value)
 visit(event)
assert any('44 passed' in o for o in outputs) and any('AssertionError' in o for o in outputs)
(HERE/'backend-author-SQLite-output.log').write_text('\n'.join(outputs))
result={'correction':C,'evidence':E,'parent':parent,'only_test_file_changed':True,'other_test_functions_and_decorators_unchanged':True,'original_assertions_identical_after_exact_date_LHS_unwrap':True,'own_UTC_negatives_rejected':negative,'real_PG_receipt_passed':1,'raw_PG_sha256':digests,'saved_SQLite_44_PASS_and_refresh_RED_observed':True,'limit':'Own actual helper/AST proof; author SQLite/PG execution readbacks, not reviewer backend execution'}
(HERE/'backend-audit.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
