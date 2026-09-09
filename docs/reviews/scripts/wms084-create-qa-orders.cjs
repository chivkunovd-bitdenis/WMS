#!/usr/bin/env node
'use strict';
// Only the approved emulator seller; no seed/reset or credential output.
const { execFileSync } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
const execute = process.argv[2] === '--create-approved-two';
const py = `import os,json,sqlite3,hashlib,urllib.request
from wb_emulator.settings import get_settings
from wb_emulator.services.orders_store import load_order_templates
cfg=get_settings()
c=sqlite3.connect('file:'+str(cfg.db_path)+'?mode=ro',uri=True)
c.row_factory=sqlite3.Row
templates=[t for t in load_order_templates() if t.get('seller','seller_a')=='seller_a' and int(t['chrtId'])==111005]
assert templates and all('createdAt' not in t for t in templates)
assert all(t.get('supplierStatus','new')=='new' for t in templates[:2])
old_ids=[r[0] for r in c.execute('SELECT wb_order_id FROM emulator_orders')]
def state():
 rows=[dict(r) for r in c.execute('SELECT * FROM emulator_orders WHERE wb_order_id IN ('+','.join('?' for _ in old_ids)+') ORDER BY wb_order_id',old_ids)]
 stock=c.execute("SELECT amount FROM emu_stocks WHERE seller_key='seller_a' AND warehouse_id=501001 AND chrt_id=111005").fetchone()
 return {'orders_count':c.execute('SELECT count(*) FROM emulator_orders').fetchone()[0],'old_orders_digest':hashlib.sha256(json.dumps(rows,sort_keys=True).encode()).hexdigest(),'selected_stock':stock[0] if stock else None}
before=state()
assert before['selected_stock'] is not None and before['selected_stock']>=2
assert os.environ.get('WB_EMULATOR_ADMIN_TOKEN','').strip()
out={'before':before,'template_count':len(templates),'fresh_createdAt':True,'warehouse':501001,'chrt':111005,'seller':'seller_a'}
if ${execute ? 'True' : 'False'}:
 req=urllib.request.Request('http://127.0.0.1:8000/__admin/orders?seller=seller_a&count=2&warehouse_id=501001&chrt_id=111005',method='POST',headers={'X-Admin-Token':os.environ['WB_EMULATOR_ADMIN_TOKEN'].strip()})
 with urllib.request.urlopen(req,timeout=30) as r: result=json.load(r)
 out['created']=result['created'];out['rejected_no_stock']=result['rejected_no_stock']
 out['orders']=[{k:o.get(k) for k in ['id','createdAt','chrtId','warehouseId','supplierStatus','wbStatus']} for o in result['orders']]
 out['after']=state()
 assert out['after']['old_orders_digest']==before['old_orders_digest']
 assert out['after']['selected_stock']==before['selected_stock']-2
 assert result['created']==2 and result['rejected_no_stock']==0
print('WMS084_PREP='+json.dumps(out))`;
const raw=execFileSync('railway',['ssh','--project','c28e681d-4535-4c96-ac97-c7b600a7f8e4','--environment','58a08b66-1290-45a2-8737-e3d7408389e5','--service','582b4add-d338-424c-be03-9bb66af6c8f0','--','python','-c',py],{encoding:'utf8',timeout:45000,stdio:['ignore','pipe','pipe']});
const data=JSON.parse(raw.split('\n').find(l=>l.startsWith('WMS084_PREP=')).slice(12));
if(execute)fs.writeFileSync(path.resolve(__dirname,'../wms084-stage-browser-20260909/order-preparation.json'),JSON.stringify(data,null,2)+'\n');
console.log(JSON.stringify(data));
