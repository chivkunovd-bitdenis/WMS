"""Offline reconciliation of fresh production reads; never performs a mutation."""
import csv
import hashlib
import json
from collections import Counter
from decimal import Decimal
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = HERE.parent / 'native-recovery-adapter-20261007/inputs'
matrix = json.loads((BASE / 'matrix.json').read_text())
expected = {x['order_id']: x for x in matrix['positions']}
def rows(path):
    return list(csv.DictReader(path.open()))
def canonical(items, keys):
    return {x['id']: {k: None if x.get(k) in ('', None) else
        str(Decimal(x[k]).normalize()) if k in ('physical_quantity', 'billing_quantity', 'item_quantity')
        else x[k] for k in keys} for x in items}
bkeys = ('id', 'source_id', 'service_code', 'physical_quantity', 'billing_quantity', 'amount')
fkeys = ('id', 'document_id', 'source_event_id', 'item_quantity')
bbase = canonical(rows(BASE / 'billing.csv'), bkeys)
fbase = canonical(rows(BASE / 'facts.csv'), fkeys)
assert len(bbase) == 52 and len(fbase) == 26
proofs = HERE / 'attempt1-native/fresh-proofs'
cards = {x['card']['posting_number']: x['card'] for p in proofs.glob('posting-*.json')
         for x in [json.loads(p.read_text())] if x['status'] == 'ok' and x['http_status'] == 200}
assert len(cards) == 31
movements = {x['id']: x for x in rows(HERE / 'linked-movements.csv')}
assert len(movements) == 26
results = []
for name in ('accounting-before-20261007T075312Z', 'accounting-after-20261007T080200Z'):
    folder = HERE / name
    manifest = json.loads((folder / 'manifest.json').read_text())
    assert manifest['writes'] == 0 and len(manifest['queries']) == 11
    for q in manifest['queries']:
        assert q['status'] == 'ok'
        assert hashlib.sha256((folder / (q['name'] + '.csv')).read_bytes()).hexdigest() == q['sha256']
    ledger = rows(folder / 'ledger.csv')
    positions = rows(folder / 'orders_positions_reserves.csv')
    assert len(ledger) == len(positions) == 31
    assert {x['fbs_order_id'] for x in ledger} == set(expected)
    assert {x['id'] for x in positions} == set(expected)
    assert canonical(rows(folder / 'billing_entries.csv'), bkeys) == bbase
    assert canonical(rows(folder / 'operation_facts.csv'), fkeys) == fbase
    assert not rows(folder / 'unlinked_fbs_movements.csv')
    assert not rows(folder / 'other_negative_since_audit.csv')
    assert all(Decimal(x['balances_quantity']) == Decimal(x['all_movement_delta'])
               for x in rows(folder / 'balances_vs_all_movements.csv'))
    assert all(Decimal(x[k]) == 0 for x in positions
               for k in ('reserved_quantity', 'legacy_reserved', 'position_reserved'))
    all_ids = set()
    new = []
    reconciled = []
    for row in ledger:
        base = expected[row['fbs_order_id']]
        card = cards[base['posting_number']]
        assert card['products'] == [dict(sku=base['sku'], quantity=base['quantity'], offer_id=base['offer_id'])]
        assert not card['related_postings']['related_posting_numbers'] and not card['related_weight_postings']
        proved = 1 if card['status'] in ('delivering', 'delivered') else 0
        assert proved == base['proved_unique_quantity']
        assert card['status'] in ('delivering', 'delivered', 'cancelled')
        assert row['id'] == base['ledger_id'] and not row['reversed_at'] and not row['reversal_movement_id']
        assert int(row['shortage_quantity']) == int(row['negative_quantity']) == 0
        recipes = json.loads(row['ozon_positions_json'])
        assert len(recipes) == 1
        recipe = recipes[0]
        assert recipe['product_id'] == base['product_id']
        assert recipe['storage_location_id'] == matrix['scope']['sorting_location_id']
        assert recipe['source_warehouse_id'] == matrix['scope']['warehouse_id']
        assert recipe['source_mode'] == 'sorting_loose' and not recipe.get('container_id')
        assert not recipe.get('container_kind') and not recipe.get('negative_quantity') and not recipe.get('reversal_movement_id')
        mid = recipe.get('movement_id')
        done = int(recipe['quantity']) if mid else 0
        assert done == proved
        assert set(base['recipe_movement_ids']).issubset({mid} if mid else set())
        if base['shipment_movement_id']:
            assert row['shipment_movement_id'] == base['shipment_movement_id']
        if mid:
            assert mid not in all_ids and row['shipment_movement_id'] == mid
            all_ids.add(mid)
            actual = movements[mid]
            assert all(actual[k] == matrix['scope'][k] for k in ('tenant_id', 'seller_id', 'warehouse_id'))
            assert actual['storage_location_id'] == matrix['scope']['sorting_location_id']
            assert actual['product_id'] == base['product_id']
            assert Decimal(actual['quantity_delta']) == -1 and actual['movement_type'] == 'fbs_shipment'
            if mid not in base['recipe_movement_ids']:
                new.append(dict(posting=base['posting_number'], sku=base['sku'], movement_id=mid,
                                movement_created_at=actual['created_at'], ledger_written_off_at=row['written_off_at']))
        reconciled.append(dict(order_id=row['fbs_order_id'], posting=base['posting_number'],
                               proved=proved, conducted=done, remaining=proved-done, movement_id=mid))
    assert all_ids == set(movements)
    observed = [x for x in rows(folder / 'supply_operations.csv') if x['operation_kind'] == 'observed_handoff']
    assert len(observed) == 1 and observed[0]['state'] == 'confirmed' and not observed[0]['error_code']
    results.append(dict(read=folder.name, started_at=manifest['started_at'], finished_at=manifest['finished_at'],
        proved_units=sum(x['proved'] for x in reconciled), conducted_units=sum(x['conducted'] for x in reconciled),
        remaining=0, cancelled_excluded=5, unique_actual_expense_movements=len(all_ids),
        existing_12_expense_links_preserved=True, new_since_0626=new,
        new_since_0626_by_sku=dict(Counter(str(x['sku']) for x in new)),
        all_52_billing_ids_quantity_amount_preserved=True, all_26_fact_ids_quantity_preserved=True,
        all_reservation_channels_zero=True, all_six_balances_equal_full_movement_history=True,
        orphan_expense_rows=0, unattributed_negative_rows=0,
        positions=reconciled, sorting_balances=rows(folder / 'balances_locations.csv')))
state = json.loads((HERE / 'attempt1-native/state.json').read_text())
assert state['checkpoint_outcome'] == state['stock_outcome'] == 'NOT_STARTED'
assert state['safe_error_code'] == 'external_status_changed'
assert results[0]['positions'] == results[1]['positions']
output = dict(verdict='PASS_ADDRESSED_PRODUCTION_READBACK', writes_by_this_adapter_attempt=0,
    attribution='Native production observed_handoff already completed remaining14 by06:27; collector does not identify initiating actor.',
    no_duplicate_mutation_required=True, repeated_read_delta=0, results=results,
    publication='Provider stock-publish outcome not independently inspected; no publication success claim.')
(HERE / 'readback-verification.json').write_text(json.dumps(output, indent=2) + '\n')
print('PASS:26 actual expenses /0missing; repeated read delta0;52billing+26facts preserved; reserves0; no duplicate mutation')
