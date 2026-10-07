const {execFileSync}=require('node:child_process');
const {stripTypeScriptTypes}=require('node:module');
const {runInNewContext}=require('node:vm');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const target='4190460c97db0db439712b17a083c5b474ee3d74';
const file='frontend/src/utils/wms680PrintGeometry.test.ts';
const expected='PACKAGING-LONG-NAME-01-680';
const expect=(a,message)=>({toBeTruthy:()=>assert.ok(a,message),toBe:v=>assert.equal(a,v,message),toBeGreaterThan:v=>assert.ok(a>v,message),toBeGreaterThanOrEqual:v=>assert.ok(a>=v,message),toBeLessThan:v=>assert.ok(a<v,message),toBeLessThanOrEqual:v=>assert.ok(a<=v,message)});
const sources=['4ed0c391135c95b67879c954195034b9c43d4980',target];
const helpers=sources.map(source=>{
 const raw=execFileSync('git',['show',`${source}:${file}`],{encoding:'utf8'}),context={expect};
 runInNewContext(stripTypeScriptTypes(raw.slice(raw.indexOf('function compact('),raw.indexOf('const forms ='))),context);
 return {source,context};
});
const cases=[['original-reviewer-121.769526pt',fs.readFileSync(path.join(__dirname,'../remaining-review-c4fa-20261007/cross-row.xml'),'utf8'),false]];
for(const name of ['cross-row','cross-column','truncated-cell','wrapped-cell']) cases.push([name,execFileSync('git',['show',`${target}:docs/evidence/WMS-680/pdf-cell-ownership-20261007/${name}.xml`],{encoding:'utf8'}),name==='wrapped-cell']);
const results=cases.map(([name,xml,accept])=>{
 const checks=helpers.map(({source,context})=>{
  let accepted=true,error=null;try{context.assertRealPdfGeometry(xml,expected)}catch(e){accepted=false;error=e.message}
  return {source,accepted,error};
 });
 assert.equal(checks[1].accepted,accept,name);
 if(name==='original-reviewer-121.769526pt')assert.equal(checks[0].accepted,true);
 return {name,required_acceptance:accept,checks};
});
fs.writeFileSync(path.join(__dirname,'r2-replay.json'),JSON.stringify(results,null,2)+'\n');
console.log('PASS: exact original real PDF rejected; cross-column/truncated rejected; same-cell wrap accepted');
