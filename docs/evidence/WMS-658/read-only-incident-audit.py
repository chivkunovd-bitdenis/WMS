"""Bounded evidence collector; no credentials, external providers or DB writes.

Run manually with python3. Reads three exact AVPack imports through the existing
SSH/container path, enforces PostgreSQL READ ONLY, rolls back, decodes PDF in
memory, and saves metadata/hashes only beside this script. Never emits PDF bytes
or raw CIS. This is an investigation artifact, not application code or a test.
"""
import hashlib
import json
from pathlib import Path
import subprocess

REMOTE_SCRIPT = r'''
import asyncio,json,hashlib,re
from sqlalchemy import text
from app.db.session import SessionLocal
import fitz,zxingcpp
from PIL import Image
H=lambda b:hashlib.sha256(b).hexdigest()
async def main():
 result={'read_only':None,'batches':[]}
 async with SessionLocal() as s:
  await s.execute(text("SET TRANSACTION READ ONLY"))
  await s.execute(text("SET LOCAL statement_timeout = '15000ms'"))
  result['read_only']=await s.scalar(text('SHOW transaction_read_only'))
  if result['read_only']!='on':raise RuntimeError('read_only_not_enabled')
  ids=['6196dd4d-a3aa-44d2-86d8-ec30b0a8010a','ac18e0a1-3c2f-46f0-bd33-caa0051c017a','b66f0919-3a62-4096-a51e-e543ef9e7b73']
  original=[]
  for bid in ids:
   r=(await s.execute(text('select id,tenant_id,seller_id,filename,document_number,accepted_count,skipped_count,skip_reasons_json,uploaded_by_user_id,created_at from marking_code_imports where id=:id'),{'id':bid})).mappings().one()
   if str(r['tenant_id'])!='d6e1ad21-8afa-4acf-8d0b-907b9f2adcfe':raise RuntimeError('wrong_scope')
   out={k:v for k,v in r.items() if k!='skip_reasons_json'}
   raw=r['skip_reasons_json'] or ''
   out.update(skip_sha256=H(raw.encode()),skip_length=len(raw))
   obj=json.loads(raw) if raw else {}
   unmatched=obj.get('unmatched',[]) if isinstance(obj,dict) else []
   out.update(mode=obj.get('mode') if isinstance(obj,dict) else None,unmatched_count=len(unmatched),unmatched_keys=list(unmatched[0]) if unmatched else [],unmatched_reasons=sorted(set(str(x.get('reason')) for x in unmatched)))
   out['unmatched_with_label_artifact']=sum(bool(x.get('has_label_artifact')) for x in unmatched)
   if unmatched:original=[str(x.get('marking_code') or x.get('cis') or x.get('cis_code') or x.get('code') or '') for x in unmatched]
   out['source_files']=[dict(x) for x in (await s.execute(text('select id,original_filename,storage_key,size_bytes,sha256_hex from marking_code_import_files where import_batch_id=:id'),{'id':bid})).mappings()]
   rows=(await s.execute(text('select c.id,c.cis_code,c.gtin,c.product_id,c.pool_id,c.label_artifact_pdf,c.created_at,p.sku_code,p.wb_barcode,p.requires_honest_sign from marking_codes c left join products p on p.id=c.product_id where c.import_batch_id=:id order by c.id'),{'id':bid})).mappings().all()
   out.update(code_count=len(rows),artifact_count=sum(bool(x['label_artifact_pdf']) for x in rows),cis_lengths=sorted(set(len(x['cis_code']) for x in rows)),codes=[])
   for ix,r in enumerate(rows):
    cis=r['cis_code'];b=r['label_artifact_pdf']
    item={k:r[k] for k in ['id','product_id','pool_id','gtin','created_at','sku_code','wb_barcode','requires_honest_sign']}
    item.update(cis_sha256=H(cis.encode()),cis_len=len(cis),gs_count=cis.count(chr(29)),artifact_bytes=len(b) if b else 0,artifact_sha256=H(b) if b else None)
    if bid==ids[1]:item['equals_original_unmatched']=cis in original
    if b and (bid!=ids[2] or ix<3):
     doc=fitz.open(stream=b,filetype='pdf');pg=doc[0]
     pix=pg.get_pixmap(matrix=fitz.Matrix(300/72,300/72),alpha=False)
     im=Image.frombytes('RGB',[pix.width,pix.height],pix.samples)
     codes=zxingcpp.read_barcodes(im,formats=zxingcpp.BarcodeFormat.DataMatrix)
     visible='\n'.join(x for x in pg.get_text().splitlines() if re.search('[А-Яа-я]',x) or re.fullmatch('[0-9]+/[0-9]+',x))[:160]
     item.update(pages=len(doc),page_mm=[round(pg.rect.width*25.4/72,2),round(pg.rect.height*25.4/72,2)],label_text=visible,decoded=[{'bytes_sha256':H(x.bytes),'len':len(x.bytes),'equals_cis_utf8':x.bytes==cis.encode(),'equals_cis_latin1':x.bytes==cis.encode('latin1')} for x in codes])
     doc.close()
    out['codes'].append(item)
   result['batches'].append(out)
  result['gerus_pool_products']=[dict(x) for x in (await s.execute(text("select pool_id,product_id,tenant_id from marking_pool_products where pool_id='b075e045-6ad1-47fb-9374-364acb9f6f93'"))).mappings()]
  result['gerus_fbs_supply']=[dict(x) for x in (await s.execute(text("select id,tenant_id,seller_id,name,wb_supply_id,status from fbs_supplies where id='98d26d84-ca11-4b88-86be-b0fa98dafcd6'"))).mappings()]
  result['gerus_operator_print_assets']=[dict(x) for x in (await s.execute(text("select id,kind,status,checksum,content_type,created_at from fbs_print_assets where fbs_supply_id='98d26d84-ca11-4b88-86be-b0fa98dafcd6' and kind='operator_document' order by created_at limit 20"))).mappings()]
  result['gerus_print_events']=[dict(x) for x in (await s.execute(text("select e.id,e.code_id,e.event_type,e.print_batch_id,e.created_at from marking_code_events e join marking_codes c on c.id=e.code_id where c.import_batch_id='ac18e0a1-3c2f-46f0-bd33-caa0051c017a' and e.event_type in ('printed','reprinted') order by e.created_at limit 50"))).mappings()]
  await s.rollback()
 print('WMS658_METADATA='+json.dumps(result,default=str,ensure_ascii=False))
asyncio.run(main())
'''

if __name__ == '__main__':
    p = subprocess.run(
        ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10',
         'root@sellerfocus.pro', 'docker exec -i wms_prod-api-1 python -'],
        input=REMOTE_SCRIPT, text=True, capture_output=True, timeout=55,
    )
    if p.returncode:
        raise SystemExit(f'read-only audit failed, exit={p.returncode}; raw stderr suppressed')
    line = next(x for x in p.stdout.splitlines() if x.startswith('WMS658_METADATA='))
    data = json.loads(line.removeprefix('WMS658_METADATA='))
    dest = Path(__file__).with_name('production-readonly-incident-metadata-20261006.json')
    dest.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
    print(dest.name, 'sha256', hashlib.sha256(dest.read_bytes()).hexdigest())
    for batch in data['batches']:
        print(batch['id'], 'codes', batch['code_count'], 'artifacts', batch['artifact_count'],
              'source_files', len(batch['source_files']), 'cis_lengths', batch['cis_lengths'],
              'decoded', sum('decoded' in x for x in batch['codes']),
              'decoded_equal', sum(any(y['equals_cis_utf8'] for y in x.get('decoded', [])) for x in batch['codes']),
              'equals_unmatched', sum(x.get('equals_original_unmatched', False) for x in batch['codes']))
