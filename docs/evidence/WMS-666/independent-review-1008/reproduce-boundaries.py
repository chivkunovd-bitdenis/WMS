"""Replay the bounded reviewer evidence; no database/provider/printer access."""
import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace as Row

ROOT = Path(__file__).parent
record = json.loads((ROOT / 'gs1-ambiguity-mechanical.json').read_text())
for name in ('baseline', 'candidate'):
    scope = {}
    exec(compile((ROOT / f'gs1-{name}-pure-source.txt').read_text(), name, 'exec'), scope)
    for case, evidence in record.items():
        if 'raw' not in evidence:
            continue
        actual = scope['normalize_scanned_cis'](evidence['raw'])
        assert list(actual) == evidence[name], (name, case, actual)
    gs = '\x1d'
    sig88 = 'MTIzNDU2Nzg5MGFiY2RlZmdoaWprbG1ub3BxcnN0dXY=' + 'MTIzNDU2Nzg5MGFiY2RlZmdoaWprbG1ub3BxcnN0dXZ3'
    raw = f'010460601234567821foot12391K7pQ92{sig88}'
    expected = f'010460601234567821foot123{gs}91K7pQ{gs}92{sig88}'
    assert scope['normalize_scanned_cis'](raw) == (expected, ['gs_structure_restored'])

scope = {'defaultdict': defaultdict, 'Any': object, 'FbsOrder': Row,
         'FbsOrderMarking': Row, 'OZON_REQUIREMENTS_KEY': 'ozon_requirements'}
exec(compile((ROOT / 'ozon-current-reader-pure-source.txt').read_text(), 'reader', 'exec'), scope)
record = json.loads((ROOT / 'ozon-tie-mechanical.json').read_text())
rows = [Row(**row, order_product_id='position', kind='sgtin', meta_status='accepted',
            meta_details_json={'exemplar_id': row['exemplar_id']})
        for row in record['fixture']]
for row in rows:
    row.created_at = datetime.fromisoformat(row.created_at)
order = Row(product_positions=[Row(id='position', quantity=3, ozon_sku=123)],
            required_meta_json=['sgtin'], meta_details_json={})
reader = scope['current_markings'](order, rows)
validator = sorted(rows, key=lambda row: (row.created_at, row.id), reverse=True)[:3]
assert [row.id for row in reader] == record['actual_reader_selected']
assert [row.id for row in validator] == record['validator_order_and_slice_selected']
assert '001-current-exemplar3' in {row.id for row in reader} - {row.id for row in validator}
print('PASS: 14 recorded normalization results + two no-GS88 repairs; reproduced Ozon tie mismatch.')
