"""Join saved Ozon proofs with fresh scoped WMS accounting; no network/application imports."""
import ast
import csv
import hashlib
import json
import subprocess
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

HERE = Path(__file__).resolve().parent
CANDIDATE = Path('/Users/deniscivkunov/Projects/WMS/.worktrees/priority-five-release-20261006')
REFRESH = HERE / 'accounting-refresh-20261006-attempt1'
LIVE = HERE / 'live-ozon-run-20261006-attempt1'


def read_csv(name):
    with (REFRESH / (name + '.csv')).open() as source:
        return list(csv.DictReader(source))


def main():
    candidate_sha = subprocess.check_output(['git', '-C', str(CANDIDATE), 'rev-parse', 'HEAD'], text=True).strip()
    service_path = 'backend/app/services/fbs_observed_handoff_service.py'
    service = subprocess.check_output(['git', '-C', str(CANDIDATE), 'show', candidate_sha + ':' + service_path])
    tree = ast.parse(service)
    negative = next(n for n in tree.body if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'NEGATIVE' for t in n.targets))
    function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'ozon_proves_handoff')
    namespace = {'Any': object, 'NEGATIVE': frozenset(ast.literal_eval(negative.value.args[0]))}
    exec(compile(ast.Module(body=[function], type_ignores=[]), service_path, 'exec'), namespace)
    classifier = json.loads((HERE / 'fresh-read-position-classification.json').read_text())
    manifest = json.loads((REFRESH / 'manifest.json').read_text())
    assert all(q['status'] == 'ok' and not q['truncated'] for q in manifest['queries'])
    for q in manifest['queries']:
        assert hashlib.sha256((REFRESH / q['csv_file']).read_bytes()).hexdigest() == q['sha256']
    orders = {r['external_order_id']: r for r in read_csv('orders_positions_reserves')}
    ledgers = {r['external_order_id']: r for r in read_csv('ledger')}
    assert len(orders) == len(ledgers) == len(classifier['positions']) == 31
    assert not read_csv('unlinked_fbs_movements') and not read_csv('new_history_attribution') and not read_csv('other_negative_since_audit')
    balances = {r['product_id']: int(r['balances_quantity']) for r in read_csv('balances_vs_all_movements')}
    assert all(r['balances_quantity'] == r['all_movement_delta'] for r in read_csv('balances_vs_all_movements'))
    bills, facts = read_csv('billing_entries'), read_csv('operation_facts')
    assert len(bills) == 22 and all(b['entry_type']=='charge' and not b['reversal_of_id'] and Decimal(b['quantity']) == Decimal(b['physical_quantity']) == 1 for b in bills)
    plan = {'scope': classifier['scope'], 'warehouse_id':'2d968c65-4a8d-414e-9076-0f201c2dba63',
        'prepared_at': datetime.now(timezone.utc).isoformat(), 'actual_recovery':'NOT_PERFORMED',
        'mutation_authorized':False, 'evidence_snapshot_only':True,
        'execution_state':'WAIT_662_SUBSTATUS_FIX_AND_ISOLATED_NO_PUBLISH_RUNNER_REVIEW_THEN_LEAD_COMMAND',
        'candidate_sha':candidate_sha, 'evaluated_service':service_path, 'evaluated_service_sha256':hashlib.sha256(service).hexdigest(),
        'ozon_proof_started_at':classifier['started_at_utc'], 'ozon_proof_finished_at':classifier['finished_at_utc'],
        'wms_refresh_started_at':manifest['started_at'], 'wms_refresh_finished_at':manifest['finished_at'],
        'wms_manifest_sha256':hashlib.sha256((REFRESH/'manifest.json').read_bytes()).hexdigest(),
        'positions':[]}
    delta, current_delta, reserve_removed = Counter(), Counter(), Counter()
    for p in classifier['positions']:
        row, ledger = orders[p['posting_number']], ledgers[p['posting_number']]
        for key, source_key in [('order_id','id'),('position_id','position_id'),('product_id','product_id')]:
            assert p[key] == row[source_key]
        assert int(row['ozon_sku']) == p['sku'] and int(row['quantity']) == p['quantity'] == 1 and row['offer_id'] == p['offer_id']
        assert ledger['fbs_order_id'] == row['id']
        assert not any(ledger[k] for k in ['shipment_movement_id','written_off_at','reversed_at','reversal_movement_id'])
        recipe = json.loads(ledger['ozon_positions_json'])
        assert len(recipe)==1 and not recipe[0].get('movement_id') and recipe[0]['product_id']==p['product_id'] and recipe[0]['quantity']==1
        proof_path = HERE / p['evidence_file']
        assert hashlib.sha256(proof_path.read_bytes()).hexdigest() == p['evidence_sha256']
        proof = json.loads(proof_path.read_text())
        card = proof['card']
        assert proof['http_status']==200 and proof['status']=='ok' and card['related_postings_present'] and not card['related_postings']['related_posting_numbers'] and not card['related_weight_postings']
        observed = p['observed_positive_quantity']
        assert observed == int(card['status'] in {'delivering','driver_pickup','delivered'})
        safe = observed if row['status'] not in {'cancelled','defect'} else 0
        accepted = int(namespace['ozon_proves_handoff'](card)) if safe else 0
        existing_bills = [b for b in bills if b['source_id']==p['order_id']]
        existing_facts = [f for f in facts if f['document_id']==p['order_id']]
        assert len(existing_facts) in {0,1}
        reserved = int(row['position_reserved'])
        r = {k:p[k] for k in ['posting_number','order_id','position_id','product_id','sku','offer_id','quantity','ozon_status','ozon_substatus','evidence_file','evidence_sha256']}
        r.update(local_status=row['status'],ledger_id=ledger['id'],recipe_source=recipe[0],
            already_conducted_quantity=0,proved_unique_quantity=safe,missing_delta=safe,
            current662_accepts=bool(accepted),current662_missing_delta=accepted,
            execution_blocker='662_SUBSTATUS_FILTER' if safe and not accepted else None,
            reserved_before=reserved,reserved_after=reserved-safe if reserved else 0,
            existing_billing=[{'id':b['id'],'service_code':b['service_code'],'physical_quantity':b['physical_quantity'],'billing_quantity':b['billing_quantity'],'amount':b['amount'] or None} for b in existing_bills],
            missing_billing_services=[s for s in ['fbs_order','packing'] if safe and s not in {b['service_code'] for b in existing_bills}],
            existing_operation_fact_ids=[f['id'] for f in existing_facts],new_operation_fact_required=bool(safe and not existing_facts),
            cancellation=p['cancellation'], mutation_authorized=False)
        plan['positions'].append(r)
        delta[p['product_id']] += safe
        current_delta[p['product_id']] += accepted
        reserve_removed[p['product_id']] += reserved if safe else 0
    plan['totals']={'positions':31,'proved_positive_units':sum(delta.values()),'already_conducted_units':0,'missing_delta':sum(delta.values()),
        'current662_missing_delta':sum(current_delta.values()),'blocked_by_substatus_units':sum(delta.values())-sum(current_delta.values()),
        'cancelled_excluded':4,'awaiting_packaging_excluded':1,'reserve_before':sum(int(r['position_reserved']) for r in orders.values()),
        'reserve_after_full26':sum(int(r['position_reserved']) for r in orders.values())-sum(reserve_removed.values()),
        'existing_operation_facts':len(facts),'new_operation_facts_expected':sum(p['new_operation_fact_required'] for p in plan['positions']),
        'existing_billing_entries':len(bills),'new_billing_entries_expected':sum(len(p['missing_billing_services']) for p in plan['positions']),
        'final_billing_entries_expected':52, 'final_operation_facts_expected':26, 'existing_billing_amount_null_entries':sum(not b['amount'] for b in bills)}
    plan['inventory_by_product']=[{'product_id':pid,'sku':next(p['sku'] for p in plan['positions'] if p['product_id']==pid),
        'balance_before':balance,'missing_delta':delta[pid],'balance_after_full26':balance-delta[pid],
        'current662_missing_delta':current_delta[pid], 'reserve_removed':reserve_removed[pid]} for pid,balance in balances.items()]
    plan['operation_sequence']=[
        'After lead command and verified integrated deployed SHA: fresh bound posting read outside stock locks; reject changed composition/proof.',
        'Narrow application runtime: only exact31 orders and exact supply; isolated capture of stock-publish dispatcher intentions; no broker dispatch or external mutations.',
        'ozon_targets + make_observation on current order scope; require targets equal approved26 plan; no forged targets or substatus normalization.',
        'save_observations exact tenant/seller/31 order ids: durable observed:{supply_id} checkpoint; resume existing checkpoint after unknown outcome.',
        'lock_order_batch_packaging_rows exact31; lock_handoff_batch_products exact tenant/seller/31; reread scope/ledger/reserves/billing and historical absence under standard locks.',
        'conduct_supply(session, exact_supply); require per-position completed26, reserve1 and billing quantities26 per service before commit; reject partial/changed plan.',
        'Commit only local transaction, persist captured stock-publish intentions as deferred NOT_DISPATCHED; no direct SQL writes or Ozon mutations.',
        'Independent gateway readback: delta26 movements/ledger; balances product table; reserve1; active billing/facts26; repeat same approved scope gives missingdelta0 and no second charges.'
    ]
    (HERE/'recovery_plan_exact.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(plan['totals'],ensure_ascii=False))
    print(json.dumps(plan['inventory_by_product'],ensure_ascii=False))


if __name__ == '__main__':
    main()
