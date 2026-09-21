"""Read synthetic browser server state; uses only audit token/loopback."""
import json,sys,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
f=json.loads((ROOT/'docs/evidence/WMS-501/browser-fixtures.json').read_text())
token=(ROOT/'.audit-runtime/browser-token').read_text()
def get(path):
 r=urllib.request.Request('http://127.0.0.1:18451'+path,headers={'Authorization':'Bearer '+token})
 return json.load(urllib.request.urlopen(r))
out={}
for key,doc in f['inbounds'].items():
 d=get('/operations/inbound-intake-requests/'+doc['id']);out[key]={'status':d['status'],'lines':[{'product_id':x['product_id'],'actual_qty':x['actual_qty'],'expected_qty':x['expected_qty']} for x in d['lines']]}
d=get('/operations/marketplace-unload-requests/'+f['outbound']['id']);out['outbound']={'status':d['status'],'lines':[{'product_id':x['product_id'],'quantity':x['quantity']} for x in d['lines']]}
path=ROOT/('docs/evidence/WMS-501/browser-state-'+sys.argv[1]+'.json');path.write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
