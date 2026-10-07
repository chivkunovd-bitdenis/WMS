"""Integrator-only native662 recovery adapter. No application imports without --execute."""
from pathlib import Path
from datetime import datetime, timezone
from decimal import Decimal
import argparse, asyncio, csv, hashlib, inspect, json, subprocess, sys, uuid

HERE = Path(__file__).resolve().parent
SOURCE = '4c532f0cccfb8f99b34d68d9630a3763038fbc5f'
SCOPE = dict(tenant_id='b80a893b-ab87-42b6-8fd7-6d41502c900f', seller_id='cf6d31c5-944b-4382-af34-636ca9aa8cc3',
             supply_id='b82d1e9a-30d2-4d7b-b52d-9775c3d266e3', warehouse_id='2d968c65-4a8d-414e-9076-0f201c2dba63',
             sorting_location_id='7d44fbc9-9c82-4ef1-bac7-4e47fe5de3c1')
SAFE_CODES = {'observed_handoff_scope_changed', 'observed_handoff_unknown', 'fbs_shipment_product_missing',
              'ozon_order_not_assembled', 'fbs_shipment_source_missing', 'fbs_shipment_insufficient_stock'}

class Stop(Exception):
    def __init__(self, code): self.code = code

def require(condition, code):
    if not condition: raise Stop(code)

def digest(data): return hashlib.sha256(data).hexdigest()
def now(): return datetime.now(timezone.utc).isoformat()
def safe_code(code): return code if code in SAFE_CODES else 'unknown_native_business_error'
def save(output, name, value):
    path=output/name;temporary=output/(name+'.part')
    temporary.write_text(json.dumps(value, indent=2, default=str)+'\n');temporary.replace(path)
def preserved(rows, kind):
    keys = ('id','source_id','service_code','physical_quantity','billing_quantity','amount') if kind=='billing' else ('id','document_id','source_event_id','item_quantity')
    return {str(row['id']):{key: (str(Decimal(str(row[key])).normalize()) if key in {'physical_quantity','billing_quantity','item_quantity'} and row[key] not in (None,'') else (None if row[key] in (None,'') else str(row[key]))) for key in keys} for row in rows}

async def execute(args, matrix, state):
    # Only normal installed application/configuration. No replacement Session/provider/publisher.
    from sqlalchemy import select, text
    from sqlalchemy.orm import selectinload
    from app.db.session import SessionLocal
    from app.models.fbs_order import FbsOrder
    from app.models.fbs_supply import FbsSupply
    from app.models.fbs_shipment_reversal_ledger import FbsShipmentReversalLedger as Ledger
    from app.models.fbs_wb_operation import FbsWbOperation
    from app.services.fbs_packaging_integration_service import lock_order_batch_packaging_rows
    from app.services.fbs_observed_handoff_service import (ozon_targets, make_observation, observation_scope,
        completed_quantities, save_observations, lock_handoff_batch_products, conduct_supply)
    from app.services.fbs_stock_publish_service import drain_background_stock_publish_tasks

    for function in (ozon_targets,make_observation,observation_scope,completed_quantities,save_observations,
                     lock_order_batch_packaging_rows,lock_handoff_batch_products,conduct_supply,drain_background_stock_publish_tasks):
        path=Path(inspect.getsourcefile(function)).resolve()
        require(path==args.app_root/Path(*function.__module__.split('.')).with_suffix('.py'),'native_import_location_mismatch')
    tenant,seller,supply_id,warehouse,sorting = [uuid.UUID(SCOPE[k]) for k in ('tenant_id','seller_id','supply_id','warehouse_id','sorting_location_id')]
    expected={uuid.UUID(r['order_id']):r for r in matrix['positions']};ids=sorted(expected);products={uuid.UUID(r['product_id']) for r in expected.values()}
    billing_baseline=preserved(list(csv.DictReader((HERE/'inputs/billing.csv').open())), 'billing')
    facts_baseline=preserved(list(csv.DictReader((HERE/'inputs/facts.csv').open())), 'facts')
    require(len(billing_baseline)==52 and len(facts_baseline)==26,'baseline_counts_changed')
    def phase(name, **extra):
        state.update(phase=name,updated_at=now(),**extra);save(args.output,'state.json',state)
        save(args.output,name+'.json',{'at':now(),**extra})

    phase('external_read_start',checkpoint_outcome='NOT_STARTED',stock_outcome='NOT_STARTED')
    # Execute the unmodified published reader before any stock/parent locks.
    r=subprocess.run([sys.executable,'-B',str(HERE/'inputs/collect_ozon_bound.py'),'--output',str(args.output/'fresh-proofs')],
                     cwd=args.app_root, capture_output=True)
    require((args.output/'fresh-proofs/manifest.json').is_file(),'reader_no_manifest')
    manifest=json.loads((args.output/'fresh-proofs/manifest.json').read_text())
    phase('external_read_returned',reader_exit=r.returncode,reader_status=manifest.get('execution_status'),
          reader_safe_failure_code=manifest.get('failure_code'),stdout_sha256=digest(r.stdout),stderr_sha256=digest(r.stderr))
    require(r.returncode==0 and manifest.get('execution_status')=='READ_COMPLETE_REQUIRES_ACCOUNTING_PLAN','fresh_reader_failed')
    require(len(manifest['requests'])==31 and not manifest.get('unread_postings'),'fresh_card_count_or_children_changed')
    cards={}
    for entry in manifest['requests']:
        filename=entry['file'];require(Path(filename).name==filename and filename.startswith('posting-'),'proof_filename_invalid')
        data=(args.output/'fresh-proofs'/filename).read_bytes();require(digest(data)==entry['sha256'],'proof_hash_mismatch')
        row=json.loads(data);require(row['status']=='ok' and row.get('http_status')==200,'unknown_external_proof')
        require(row.get('http_method')=='POST' and row.get('endpoint')=='/v3/posting/fbs/get','unexpected_external_read')
        card=row['card'];number=card['posting_number'];require(number not in cards,'duplicate_external_posting');cards[number]=card
    require(set(cards)=={r['posting_number'] for r in expected.values()},'posting_scope_changed')
    for row in expected.values():
        card=cards[row['posting_number']]
        require(card['status']==row['ozon_status'] and card.get('substatus')==row['ozon_substatus'],'external_status_changed')
        require(not card['related_postings']['related_posting_numbers'] and not card['related_weight_postings'],'children_changed')
        require(len(card['products'])==1 and int(card['products'][0]['sku'])==row['sku']
                and card['products'][0].get('offer_id')==row['offer_id'] and card['products'][0]['quantity']==row['quantity'],'external_composition_changed')
    scope_raw=(args.output/'fresh-proofs/scope_snapshot.json').read_bytes()
    require(digest(scope_raw)==manifest['scope_snapshot_sha256'],'fresh_scope_hash_mismatch')
    scope=json.loads(scope_raw);parent=scope['supply']
    require(all(str(parent[key])==SCOPE[name] for key,name in [('id','supply_id'),('tenant_id','tenant_id'),('seller_id','seller_id'),('warehouse_id','warehouse_id')])
        and parent['marketplace']=='ozon' and parent['source']=='wms','fresh_parent_scope_changed')
    scoped={r['order_id']:r for r in scope['positions']};require(len(scope['positions'])==len(scoped)==31 and set(scoped)=={str(i) for i in ids},'fresh_order_scope_changed')
    for oid,base in expected.items():
        row=scoped[str(oid)]
        require(all(str(row[key])==str(base[key]) for key in ['position_id','product_id','offer_id','quantity'])
            and int(row['ozon_sku'])==base['sku'] and row['warehouse_id']==SCOPE['warehouse_id'] and row['status']==base['local_status'],'fresh_position_scope_changed')
    phase('fresh_proofs_validated',cards=31,cancelled=5,positive_units=26)

    class NoAdditionalNetwork:
        async def fetch_statuses(self, **kwargs): raise Stop('additional_network_forbidden')
    async def load_scope(session):
        require(session.bind.dialect.name=='postgresql','requires_normal_postgresql')
        supply=await session.scalar(select(FbsSupply).where(FbsSupply.id==supply_id,FbsSupply.tenant_id==tenant).execution_options(populate_existing=True))
        require(supply is not None and supply.seller_id==seller and supply.warehouse_id==warehouse
                and supply.marketplace=='ozon' and supply.source=='wms','supply_scope_changed')
        orders=list(await session.scalars(select(FbsOrder).where(FbsOrder.supply_id==supply_id,FbsOrder.tenant_id==tenant)
            .options(selectinload(FbsOrder.product_positions)).order_by(FbsOrder.id).execution_options(populate_existing=True)))
        require(len(orders)==31 and {o.id for o in orders}==set(expected),'order_scope_changed')
        for order in orders:
            row=expected[order.id];require(order.seller_id==seller and order.warehouse_id==warehouse and order.marketplace=='ozon'
                and order.external_order_id==row['posting_number'] and order.status==row['local_status'],'order_association_or_status_changed')
            require(len(order.product_positions)==1,'position_scope_changed');p=order.product_positions[0]
            require(str(p.id)==row['position_id'] and str(p.product_id)==row['product_id'] and p.ozon_sku==row['sku']
                    and p.offer_id==row['offer_id'] and p.quantity==row['quantity'],'position_composition_changed')
            require(not ((order.meta_details_json or {}).get('ozon_assembly') or {}).get('posting_numbers'),'local_children_changed')
        return supply,orders

    observations={}
    async with SessionLocal() as session:
        _,orders=await load_scope(session)
        for order in orders:
            targets,children=await ozon_targets(order,cards[order.external_order_id],NoAdditionalNetwork(),'','')
            row=expected[order.id];wanted={uuid.UUID(row['product_id']):row['proved_unique_quantity']} if row['proved_unique_quantity'] else {}
            require(targets==wanted and not children,'native_targets_changed')
            observations[order.id]=make_observation(order,targets,cards[order.external_order_id],children)
        # This native function commits its checkpoint separately, as in the normal plan.
        phase('checkpoint_commit_pending',checkpoint_outcome='PENDING_OR_UNKNOWN')
        await save_observations(session,tenant,seller,observations)
        phase('checkpoint_commit_returned',checkpoint_outcome='COMMIT_RETURNED')

    query_names=('identity','orders_positions_reserves','ledger','balances_locations','balances_vs_all_movements',
                 'billing_entries','operation_facts','supply_operations','unlinked_fbs_movements')
    async def snapshot(session, orders, label):
        ledgers=list(await session.scalars(select(Ledger).where(Ledger.tenant_id==tenant,Ledger.fbs_order_id.in_(ids))
            .order_by(Ledger.fbs_order_id).with_for_update().execution_options(populate_existing=True)))
        require(len(ledgers)==31,'ledger_scope_changed')
        rows={}
        for name in query_names:
            result=await session.execute(text((HERE/'inputs/queries'/f'{name}.sql').read_text()))
            rows[name]=[dict(r) for r in result.mappings()]
            for r in rows[name]:
                if r.get('error_code'):r['error_code']=safe_code(r['error_code'])
        save(args.output,label+'-reads.json',rows)
        require(len(rows['ledger'])==31 and len(rows['orders_positions_reserves'])==31,'locked_row_count_changed')
        require(not rows['unlinked_fbs_movements'],'unattributed_expense')
        require(preserved(rows['billing_entries'],'billing')==billing_baseline,'billing_changed')
        require(preserved(rows['operation_facts'],'facts')==facts_baseline,'facts_changed')
        require(len(rows['balances_locations'])==len(products),'sorting_balance_scope_changed')
        for r in rows['balances_locations']:
            require(str(r['storage_location_id'])==str(sorting) and str(r['warehouse_id'])==str(warehouse) and r['code']=='__SORTING__'
                and not r['deleted_at'] and not r['container_id'] and not r['container_kind'],'sorting_source_changed')
        require(all(Decimal(r['balances_quantity'])==Decimal(r['all_movement_delta']) for r in rows['balances_vs_all_movements']),'balance_history_mismatch')
        by_order={l.fbs_order_id:l for l in ledgers};completed={};movement_ids=set()
        for order in orders:
            l=by_order[order.id];base=expected[order.id];pid=uuid.UUID(base['product_id'])
            require(str(l.id)==base['ledger_id'] and l.reversed_at is None and l.reversal_movement_id is None,'ledger_identity_or_reversal_changed')
            require(l.negative_quantity==0 and l.shortage_quantity==0,'shortage_or_negative_recipe')
            recipes=l.ozon_positions_json or []
            require(len(recipes)==1,'recipe_scope_changed')
            for recipe in recipes:
                require(recipe['product_id']==str(pid) and recipe['storage_location_id']==str(sorting) and recipe['source_warehouse_id']==str(warehouse)
                    and recipe.get('source_mode')=='sorting_loose' and not recipe.get('container_id') and not recipe.get('container_kind')
                    and int(recipe['quantity'])==base['quantity'] and not recipe.get('negative_quantity') and not recipe.get('reversal_movement_id'),'recipe_source_changed')
            done=completed_quantities(l);require(set(done).issubset({pid}),'completed_product_changed');quantity=done.get(pid,0)
            require(base['already_conducted_quantity']<=quantity<=base['proved_unique_quantity'],'conducted_proof_conflict')
            links={str(r['movement_id']) for r in recipes if r.get('movement_id')};require(set(base['recipe_movement_ids']).issubset(links),'previous_expense_lost')
            if base['shipment_movement_id']:require(str(l.shipment_movement_id)==base['shipment_movement_id'],'previous_header_movement_changed')
            require(not (movement_ids & links),'duplicate_movement_link');movement_ids.update(links);completed[str(order.id)]=quantity
        missing=sum(r['proved_unique_quantity']-completed[r['order_id']] for r in expected.values())
        require(0<=missing<=14,'missing_outside_approved_bound')
        movements=[]
        if movement_ids:
            result=await session.execute(text('SELECT id,tenant_id,seller_id,product_id,storage_location_id,warehouse_id,quantity_delta,movement_type,created_at FROM inventory_movements WHERE tenant_id=:tenant AND id=ANY(:ids)'),{'tenant':tenant,'ids':[uuid.UUID(i) for i in sorted(movement_ids)]})
            movements=[dict(r) for r in result.mappings()];require({str(r['id']) for r in movements}==movement_ids,'movement_link_missing')
            require(all(r['tenant_id']==tenant and r['seller_id']==seller and r['warehouse_id']==warehouse and r['storage_location_id']==sorting
                and r['product_id'] in products and r['movement_type']=='fbs_shipment' and r['quantity_delta']==-1 for r in movements),'movement_scope_or_quantity_changed')
        return {'rows':rows,'completed':completed,'missing':missing,'movement_ids':sorted(movement_ids),'movements':movements}

    commit_started=False
    try:
        async with SessionLocal() as session:
            phase('native_locks_pending',stock_outcome='NOT_COMMITTED')
            await lock_order_batch_packaging_rows(session,tenant,ids)
            supply,orders=await load_scope(session) # stop changed parent composition before native product expansion
            await lock_handoff_batch_products(session,tenant,seller,ids)
            supply,orders=await load_scope(session)
            before=await snapshot(session,orders,'locked-before');save(args.output,'locked-before.json',before)
            operation=await session.scalar(select(FbsWbOperation).where(FbsWbOperation.tenant_id==tenant,FbsWbOperation.seller_id==seller,
                FbsWbOperation.local_entity_id==supply_id,FbsWbOperation.operation_kind=='observed_handoff').execution_options(populate_existing=True))
            require(operation is not None and operation.idempotency_key=='observed:'+str(supply_id),'checkpoint_missing')
            evidence=(operation.response_summary_json or {}).get('orders') or {};require(set(evidence)=={str(i) for i in ids},'checkpoint_order_scope_changed')
            for order in orders:
                saved=evidence[str(order.id)];obs=observations[order.id]
                require(saved.get('scope')==observation_scope(order)==obs['scope'] and saved.get('targets',{})==obs['targets']
                    and not saved.get('children'),'checkpoint_scope_or_targets_changed')
            need={pid:sum(expected[o.id]['proved_unique_quantity']-before['completed'][str(o.id)] for o in orders if uuid.UUID(expected[o.id]['product_id'])==pid) for pid in products}
            balances={uuid.UUID(str(r['product_id'])):Decimal(r['quantity']) for r in before['rows']['balances_locations']}
            require(all(balances.get(pid,Decimal(0))>=qty for pid,qty in need.items()),'sorting_balance_insufficient')
            phase('conduct_pending',stock_outcome='NOT_COMMITTED',current_missing=before['missing'])
            # No manufactured targets, no SQL/direct reserve/status updates or publication interception.
            if before['missing']:
                await conduct_supply(session,supply)
            await session.flush()
            supply,orders=await load_scope(session);after=await snapshot(session,orders,'locked-after');save(args.output,'locked-after.json',after)
            new_ids=sorted(set(after['movement_ids'])-set(before['movement_ids']))
            phase('conduct_returned_uncommitted',stock_outcome='NOT_COMMITTED',conduct_called=bool(before['missing']),
                new_movement_ids=new_ids,new_expense_delta=-len(new_ids),remaining=after['missing'],
                native_business_error_present=operation.error_code is not None,
                native_business_error_code=safe_code(operation.error_code) if operation.error_code is not None else None)
            require(operation.error_code is None,'native_business_error')
            require(after['missing']==0,'native_conduct_incomplete')
            require(set(before['movement_ids']).issubset(after['movement_ids']) and len(new_ids)==before['missing'],'new_expense_count_conflict')
            after_balances={uuid.UUID(str(r['product_id'])):Decimal(r['quantity']) for r in after['rows']['balances_locations']}
            require(all(after_balances[pid]==balances[pid]-qty for pid,qty in need.items()),'unexpected_inventory_delta')
            require(all(Decimal(r['reserved_quantity'])==0 for r in after['rows']['orders_positions_reserves']),'remaining_position_reserve')
            phase('outer_commit_pending',stock_outcome='PENDING_OR_UNKNOWN',new_movement_ids=new_ids,new_expense_delta=-len(new_ids),remaining=0)
            commit_started=True
            await session.commit()
            phase('outer_commit_returned',stock_outcome='COMMIT_RETURNED')
    except Exception:
        # Session context rolls back an uncommitted stock transaction. An attempted commit may be unknown.
        phase('stock_not_acknowledged',stock_outcome='COMMIT_UNKNOWN_REQUIRES_READBACK' if commit_started else 'ROLLBACK_ON_SESSION_EXIT')
        raise
    finally:
        # Also drain if an after_commit handler raised after DB commit; never abandon its native in-process work.
        phase('native_publish_drain_pending')
        await drain_background_stock_publish_tasks()
        phase('native_publish_drain_returned',publication='NATIVE_DRAIN_RETURNED; broker/provider result not independently verified')
    phase('local_postconditions_committed',stock_outcome='COMMIT_RETURNED',remaining=0,
          acceptance='NOT_CLAIMED; integrator independent current accounting readback required')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute',action='store_true');parser.add_argument('--source-sha',required=True)
    parser.add_argument('--bindings-sha256',required=True);parser.add_argument('--adapter-sha256',required=True)
    parser.add_argument('--app-root',type=Path,default=Path('/app'));parser.add_argument('--output',type=Path,required=True)
    for key in SCOPE:parser.add_argument('--'+key.replace('_','-'),required=True)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=False,mode=0o700)
    state={'started_at':now(),'execute_requested':args.execute,'production_source':SOURCE,'scope':SCOPE,
           'checkpoint_outcome':'NOT_STARTED','stock_outcome':'NOT_STARTED','phase':'source_validation'}
    save(args.output,'state.json',state)
    try:
        require(args.source_sha==SOURCE and all(getattr(args,k)==v for k,v in SCOPE.items()),'source_or_exact_scope_argument_mismatch')
        require(digest(Path(__file__).read_bytes())==args.adapter_sha256,'adapter_copy_hash_mismatch')
        binding_raw=(HERE/'source-bindings.json').read_bytes();require(digest(binding_raw)==args.bindings_sha256,'bindings_hash_mismatch')
        bindings=json.loads(binding_raw);require(bindings['production_source']==SOURCE and bindings['scope']==SCOPE,'binding_scope_mismatch')
        for path,row in bindings['input_bindings'].items():require(digest((HERE/path).read_bytes())==row['sha256'],'input_copy_hash_mismatch')
        matrix=json.loads((HERE/'inputs/matrix.json').read_text());require(matrix['scope']==SCOPE and len(matrix['positions'])==31
            and len({r['order_id'] for r in matrix['positions']})==31 and len({r['position_id'] for r in matrix['positions']})==31
            and matrix['proved_unique_units']==26 and matrix['already_conducted_units']==12 and matrix['fresh_missing_delta']==14,'matrix_identity_changed')
        if not args.execute:
            state.update(phase='NOT_EXECUTED',finished_at=now());save(args.output,'state.json',state);return 0
        require(args.app_root.resolve()==Path('/app'),'requires_normal_installed_app')
        actual={path:digest((args.app_root/path).read_bytes()) for path in bindings['installed_native_files']}
        require(actual==bindings['installed_native_files'],'installed_native_source_mismatch')
        save(args.output,'installed-source.json',{'source':SOURCE,'actual_hashes':actual})
        asyncio.run(execute(args,matrix,state));state['finished_at']=now();save(args.output,'state.json',state);return 0
    except Exception as exc:
        state.update(phase='STOPPED',finished_at=now(),error_type=type(exc).__name__,safe_error_code=exc.code if isinstance(exc,Stop) else 'details_suppressed')
        save(args.output,'state.json',state);return 2
if __name__=='__main__':raise SystemExit(main())
