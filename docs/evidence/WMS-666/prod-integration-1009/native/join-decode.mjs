import { readFile, writeFile } from 'node:fs/promises';
import { createRequire } from 'node:module';
import { createHash } from 'node:crypto';
import assert from 'node:assert/strict';
const require=createRequire(new URL('../../../../../frontend/package.json',import.meta.url));
const {PNG}=require('pngjs'),{RGBLuminanceSource,BinaryBitmap,HybridBinarizer,DataMatrixReader,QRCodeReader,DecodeHintType}=require('@zxing/library');
const dir=import.meta.dirname;
const read=async file=>JSON.parse(await readFile(dir+'/'+file,'utf8'));
const ledger=await read('handler-ledger.json'),sink=(await readFile(dir+'/sink-receipts.jsonl','utf8')).trim().split('\n').map(JSON.parse);
function decode(url){const bytes=Buffer.from(url.split(',')[1],'base64'),png=PNG.sync.read(bytes);for(const h of [Math.floor(png.height*.44),png.height]){const pixels=new Uint8ClampedArray(png.width*h);for(let i=0;i<pixels.length;i++)pixels[i]=(png.data[4*i]+2*png.data[4*i+1]+png.data[4*i+2])/4*(png.data[4*i+3]/255)+255*(1-png.data[4*i+3]/255);const b=new BinaryBitmap(new HybridBinarizer(new RGBLuminanceSource(pixels,png.width,h)));for(const R of [QRCodeReader,DataMatrixReader])for(const hints of [undefined,new Map([[DecodeHintType.PURE_BARCODE,true]])])try{return new R().decode(b,hints).getText()}catch{}}throw Error('No pixel-decodable QR/DataMatrix');}
const expectedQr=['*DUIkWJJF','*DUIkNEXT'],cises=['010460000000000121SERIAL-A\u001d91ABCD\u001d92signed-A','010460000000000221SERIAL-B\u001d91EFGH\u001d92signed-B'];
const joins=[];
for(const file of ['supply_id-A.json','supply_ids-A-B.json']){
 const input=await read(file);assert.equal(input.printLog.length,6);
 for(const job of input.printLog){const order=job.idempotencyKey.includes('wb-a-order')?0:1,type=job.idempotencyKey.includes(':copy')?'CIS':'QR';let decoded;try{decoded=decode(job.imageDataUrl)}catch(e){throw Error(job.idempotencyKey+': '+e)}assert.equal(decoded,type==='CIS'?cises[order]:expectedQr[order]);const hash=createHash('sha256').update(Buffer.from(job.imageDataUrl.split(',')[1],'base64')).digest('hex');const l=ledger.find(r=>r.id===job.idempotencyKey),s=sink.find(r=>r.receipt===l?.receipt);assert(l&&s);assert.equal(hash,l.hash);assert.equal(hash,s.sink_png_sha256);joins.push({case:file,order_id:['wb-a-order','wb-next-order'][order],job_key:job.idempotencyKey,type,decoded,width_mm:job.widthMm,height_mm:job.heightMm,rendered_png_sha256:hash,handler_hash:l.hash,handler_receipt:l.receipt,sink_hash:s.sink_png_sha256,join_valid:true});}
}
await writeFile(dir+'/native-joins.json',JSON.stringify({candidate_sha:(await read('source-identity.json')).candidate_sha,status:'PASS',accepted_jobs:joins.length,independent_pixel_decode:true,joins},null,2)+'\n');
console.log('12 QR/CIS handler/sink hash joins: PASS');
const manual=[];
for(const [file,orderIndexes] of [['ordinary-manual-html.json',[0]],['group-manual-html.json',[0,1]]]){
 const tapes=await read(file);assert.equal(tapes.length,orderIndexes.length);
 for(let i=0;i<tapes.length;i++){
  const html=tapes[i],blocks=[...html.matchAll(/<section\b[^>]*data-tape-block="([^"]+)"[\s\S]*?<\/section>/g)];
  const codes=blocks.map(m=>({block:m[1],decoded:decode(m[0].match(/<img[^>]*src="([^"]+)"/)[1])}));
  assert.deepEqual(codes.map(c=>c.block),['wb_qr','cz','cz']);
  assert.deepEqual(codes.map(c=>c.decoded),[expectedQr[orderIndexes[i]],cises[orderIndexes[i]],cises[orderIndexes[i]]]);
  manual.push({case:file,order_id:['wb-a-order','wb-next-order'][orderIndexes[i]],blocks:codes,html_sha256:createHash('sha256').update(html).digest('hex'),boundary:'browser HTML/window.print',native_handler_jobs:0});
 }
}
await writeFile(dir+'/manual-decoded.json',JSON.stringify({candidate_sha:(await read('source-identity.json')).candidate_sha,status:'PASS',manual},null,2)+'\n');
console.log('3 scoped manual tapes: QR + two exact CIS copies independently decoded: PASS');
