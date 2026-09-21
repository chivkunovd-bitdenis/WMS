"""Evidence-only classifier. Static links are candidates, never execution proof."""
import ast,json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
OUT=Path(__file__).parent
matches=[]
pattern=re.compile(r'tenant|foreign|cross_seller|seller_isolation|scope|mixed_seller|mixed_sellers|without_delegation|other_seller|shop_switch|owner_and|profile_permissions')
for p in sorted((ROOT/'backend/tests').glob('test_*.py')):
    source=p.read_text(); tree=ast.parse(source)
    for n in tree.body:
        if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name.startswith('test_') and pattern.search(n.name):
            matches.append({'nodeid':str(p.relative_to(ROOT))+'::'+n.name,'line':n.lineno,
                            'name':n.name,'source_literals':[x.value for x in ast.walk(n) if isinstance(x,ast.Constant) and isinstance(x.value,str) and x.value.startswith('/')]})
(OUT/'isolation-completion-selected-tests.json').write_text(json.dumps(matches,ensure_ascii=False,indent=2)+'\n')
(OUT/'isolation-completion-selected-tests.txt').write_text('\n'.join(x['nodeid'] for x in matches)+'\n')
print('Selected targeted boundary test functions:',len(matches))
routes=json.loads((OUT/'isolation-runtime-route-inventory.json').read_text())
static=json.loads((OUT/'isolation-route-inventory.json').read_text())
static_by_route={(x['method'],x['path']):x for x in static}
groups={
 'auth':'identity','staff_accounts':'identity','seller_staff_accounts':'identity','sellers':'identity',
 'tenant_settings':'tenant_settings','subscription':'subscription','client_errors':'diagnostics','health':'public',
 'products':'catalog','fbs_stock_rule_reset':'catalog','scan_resolver':'scan',
 'warehouses':'warehouse_containers','inbound_intake':'receiving_distribution','inbound_package_catalog':'receiving_distribution',
 'inbound_marking':'marking','kiz_reprints':'marking','marking_codes':'marking','marking_credentials':'marking_credentials',
 'inventory_counts':'inventory','inventory_balances':'inventory','inventory_movements':'inventory','stock_transfer':'inventory',
 'outbound_shipment':'shipment','marketplace_unload_requests':'unload','ozon_returns':'returns',
 'packaging_tasks':'packing','fbs_orders':'fbs_orders','fbs_supplies':'fbs_supply_pick_boxes','fbs_sellers':'fbs_bindings',
 'fbs_marking':'fbs_marking','fbs_kiz':'fbs_marking','fbs_print_assets':'print','fbs_print_jobs':'print','warehouse_print':'print',
 'reports':'reports_exports','billing':'billing','billing_invoices_v2':'billing','storage':'storage',
 'discrepancy_acts':'discrepancy','document_events':'history','background_jobs':'jobs','notifications':'notifications',
 'wb_mp_warehouses':'marketplace','wildberries_integration':'marketplace','ozon_integration':'marketplace'}
for row in routes:
 module=row['handler'].split('.')[-2]
 row['family']=groups[module]
 declaration=static_by_route.get((row['method'],row['path']),{})
 row['source_file']=declaration.get('file')
 row['source_line']=declaration.get('line')
 row['source_guards']=declaration.get('direct_depends',[])
 row['auth_dependencies']=['HTTPBearer' if 'HTTPBearer object at' in x else x for x in row['auth_dependencies']]
 row['auth_dependencies']=sorted(set(row['auth_dependencies']))
 row['class']='public' if row.get('anonymous_check') else ('read' if row['method']=='GET' else 'mutation_or_command')
 row['scope_evidence']='server guard + family analysis; method/body-specific matrix below'
 # These are explicit path strings in named test bodies only; inherited helpers/fstrings
 # may be missed. They are a navigation aid and not an assertion of test completeness.
 row['static_test_candidates']=[x['nodeid'] for x in matches if row['path'] in x['source_literals']]
(OUT/'isolation-completion-endpoints.json').write_text(json.dumps(routes,ensure_ascii=False,indent=2)+'\n')
lines=['# WMS-501 · Классификация каждого runtime метода','',
 'Полный реестр; read означает HTTP GET, mutation_or_command включает POST-команды/preview, не обещает факт изменения. Dependencies показывают фактические runtime guards. Ссылка теста по семейству и собственные probes приведены в основном отчете.','',
 '| Семейство | Метод | Путь | Класс | Guards (runtime) | Guards (исходник, раскрывает _dep) | Код |','|---|---|---|---|---|---|---|']
for r in routes:
 lines.append('| '+r['family']+' | '+r['method']+' | `'+r['path']+'` | '+r['class']+' | '+', '.join('`'+x+'`' for x in r['auth_dependencies'] if x not in ['get_db','HTTPBearer'])+' | '+', '.join('`'+x+'`' for x in r['source_guards'] if x!='get_db')+' | '+str(r['source_file'])+':'+str(r['source_line'])+' |')
(OUT/'isolation-completion-endpoints.md').write_text('\n'.join(lines)+'\n')
assert len(routes)==414
