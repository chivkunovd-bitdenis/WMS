"""Audit-only fault wrapper. Product ASGI is unchanged; loopback disposable DB only."""
import asyncio
import json
import os
from pathlib import Path
import re
import time
import uuid

assert os.environ.get('DATABASE_URL') == 'postgresql+psycopg_async://deniscivkunov@127.0.0.1:55451/wms501_browser2'
from app.main import create_app
ROOT=Path(__file__).resolve().parents[3]
CONTROL=ROOT/'.audit-runtime/browser-fault.json'
LOG=ROOT/'docs/evidence/WMS-501/browser-http.jsonl'
product=create_app()

def record(**values):
    with LOG.open('a') as f:f.write(json.dumps({'time':time.time(),**values})+'\n')

async def app(scope,receive,send):
    if scope['type']!='http':return await product(scope,receive,send)
    path,method=scope['path'],scope['method']
    rid=uuid.uuid4().hex[:8]
    rule={}
    if CONTROL.exists():
        config=json.loads(CONTROL.read_text())
        if method==config.get('method') and re.search(config.get('path_regex','(?!)'),path) and config.get('remaining',0)>0:
            rule=dict(config); config['remaining']-=1; CONTROL.write_text(json.dumps(config))
    record(event='start',request=rid,path=path,method=method,rule=rule.get('name'))
    if rule.get('before_delay_s'):await asyncio.sleep(rule['before_delay_s'])
    if rule.get('fail_status'):
        status=rule['fail_status']; body=b'{"detail":"wms501_synthetic_fault"}'
        await send({'type':'http.response.start','status':status,'headers':[(b'content-type',b'application/json')]})
        await send({'type':'http.response.body','body':body})
        record(event='end',request=rid,path=path,method=method,status=status,synthetic=True)
        return
    if rule.get('after_fail_status'):
        messages=[]
        async def buffered(message):messages.append(message)
        await product(scope,receive,buffered)
        original_status=next(m['status'] for m in messages if m['type']=='http.response.start')
        record(event='product_committed_response_replaced',request=rid,path=path,method=method,status=original_status,synthetic_status=rule['after_fail_status'])
        await send({'type':'http.response.start','status':rule['after_fail_status'],'headers':[(b'content-type',b'application/json')]})
        await send({'type':'http.response.body','body':b'{"detail":"wms501_lost_success_response"}'})
        record(event='end',request=rid,path=path,method=method,status=rule['after_fail_status'],synthetic=True)
        return
    async def observed(message):
        if message['type']=='http.response.start':
            record(event='product_response',request=rid,path=path,method=method,status=message['status'])
            if rule.get('after_delay_s'):await asyncio.sleep(rule['after_delay_s'])
        await send(message)
        if message['type']=='http.response.body' and not message.get('more_body'):
            record(event='end',request=rid,path=path,method=method)
    await product(scope,receive,observed)

if __name__=='__main__':
    import uvicorn
    uvicorn.run(app,host='127.0.0.1',port=18451,access_log=False)
