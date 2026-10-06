// Observational diagnosis only; real current operation/utility, controlled peer timing.
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync} from 'node:fs';
import {createRequire} from 'node:module';
import {createHash} from 'node:crypto';
const repo = new URL('../../../../',import.meta.url);
const require = createRequire(new URL('frontend/package.json',repo));
const {JSDOM}=require('jsdom');const ts=require('typescript');
const source=readFileSync(new URL('frontend/tests-e2e/wms672-native-errors.test.mjs',repo),'utf8');
const screenSource=readFileSync(new URL('frontend/src/screens/ff/FfInboundRequestView.tsx',repo),'utf8');
const utilitySource=readFileSync(new URL('frontend/src/utils/printBarcodeLabel.ts',repo),'utf8');
// Reuse frozen tester's real-function AST setup as a diagnostic COPY. No frozen file is written.
const setup=source.slice(source.indexOf('const tree ='),source.indexOf('for(const [index,badAsset]'));
const marker='    await gate;\n    state.pending--;';
assert.equal(setup.split(marker).length,2,'exact controlled boundary required');
// Known failure resolves independently of the other native readiness workers.
const observed=setup.replace(marker,'    if(index!==failedIndex) await gate;\n    state.pending--;');
const AsyncFunction=Object.getPrototypeOf(async function(){}).constructor;
const fixture=await new AsyncFunction('assert','JSDOM','ts','screenSource','utilitySource',observed+'\nreturn fixture;')(assert,JSDOM,ts,screenSource,utilitySource);
const f=await fixture({n:16,failedIndex:1,hold:true});
let operationFinished=false;f.operation.then(()=>{operationFinished=true;});
const snapshot=phase=>({phase,started:f.state.started,ready:f.state.ready,pending:f.state.pending,maxPending:f.state.maxPending,frameConnected:f.state.frames[0].isConnected,busy:f.state.busy,operationFinished,error:f.state.error,transfers:f.state.transfers.length,marks:f.state.marks.length,saves:f.state.saves.length});
const events=[];
try {
  await new Promise(resolve=>setTimeout(resolve,20));events.push(snapshot('known failure before held peers released'));
  f.release();await f.operation;await new Promise(resolve=>setTimeout(resolve,20));events.push(snapshot('after peer release'));
}finally{f.close();}
const result={model:'real current utility and AST-extracted screen, jsdom platform boundary; NOT Chromium native decoder',node:process.version,sourceHashes:{screen:createHash('sha256').update(screenSource).digest('hex'),utility:createHash('sha256').update(utilitySource).digest('hex'),frozenHarness:createHash('sha256').update(source).digest('hex')},events};
writeFileSync(new URL('probe.json',import.meta.url),JSON.stringify(result,null,2)+'\n');console.log(JSON.stringify(result,null,2));
