// WMS-672 additive R3/R4 native-iframe error contract. No browser/printer calls.
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createRequire} from 'node:module';
import {test} from 'node:test';
const require = createRequire(new URL('../package.json', import.meta.url));
const {JSDOM} = require('jsdom');
const ts = require('typescript');
const screenSource = readFileSync(new URL('../src/screens/ff/FfInboundRequestView.tsx', import.meta.url), 'utf8');
const utilitySource = readFileSync(new URL('../src/utils/printBarcodeLabel.ts', import.meta.url), 'utf8');
const tree = ts.createSourceFile('screen.tsx', screenSource, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
let initializer;
function visit(node) {
  if (ts.isVariableDeclaration(node) && node.name.getText(tree) === 'printInboundInternalLabels') initializer = node.initializer;
  ts.forEachChild(node, visit);
}
visit(tree);
assert.ok(initializer && ts.isArrowFunction(initializer), 'exact real screen operation required');
const compile = source => ts.transpileModule(source, {compilerOptions: {
  target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS,
}}).outputText;
const validPng = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aBVcAAAAASUVORK5CYII=';
const nativeReason = 'The source image cannot be decoded.';
const genericReason = 'Не удалось напечатать этикетки.';

async function fixture({n = 300, failedIndex, badAsset = false, malformed, hold = false} = {}) {
  const dom = new JSDOM('<body></body>', {url:'https://synthetic.wms.test/', runScripts:'dangerously', pretendToBeVisual:true});
  const w = dom.window;
  const state = {started:0, ready:0, maxPending:0, pending:0, marks:[], saves:[], transfers:[], busy:false, error:null, frames:[], nativeError:null};
  let release;
  const gate = hold ? new Promise(resolve => {release = resolve;}) : Promise.resolve();
  const boxes = Array.from({length:n}, (_, i) => ({id:`native-box-${i+1}`, number:i+1,
    barcode:`INB-${String(i+1).padStart(12,'0')}`, kind:'box', label_printed_at:null}));
  const exports = {};
  w.exports = exports;
  w.eval(compile(utilitySource));
  Object.assign(w, {
    printBarcodeLabels:exports.printBarcodeLabels, inboundLabelPrinting:{current:false},
    setBusy:value => {state.busy=value;}, setError:value => {state.error=value;},
    readIntake:() => ({}), saveInboundLabelAttempt:(_token, _id, attempt) => {
      state.saves.push({...attempt, readyAtSave:state.ready});
    }, token:'synthetic', requestId:'native-document', authHeaders:{},
    apiUrl:path => path, randomId:() => 'native-attempt', detail:{boxes},
    numberedInboundBoxLabels:true, inboundBoxDisplayLabel:number => String(number),
    renderBarcodeDataUrl:barcode => badAsset && barcode===boxes[failedIndex-1]?.barcode
      ? 'data:image/png;base64,AAAA' : validPng,
    readApiErrorMessage:async () => 'synthetic API error', loadDetail:async () => {},
    fetch:async (path, init) => {
      assert.equal(init.method,'POST');
      assert.equal(state.transfers.length,1,'marks follow one successful transfer');
      assert.equal(state.ready,n,'every image ready before first mark');
      state.marks.push(path); return {ok:true};
    },
  });
  const append = w.document.body.appendChild.bind(w.document.body);
  w.document.body.appendChild = node => {
    const result=append(node);
    if(node.tagName==='IFRAME') state.frames.push(node);
    return result;
  };
  w.eval(compile(`globalThis.__screenPrint = ${initializer.getText(tree)};`));
  const operation = w.__screenPrint(boxes,{id:'58x40',widthMm:58,heightMm:40});
  assert.equal(state.frames.length,1,'actual utility constructs one complete iframe');
  const frame = state.frames[0];
  const onload = frame.onload;
  frame.onload=null; // jsdom has no srcdoc navigation; deliver its real HTML once.
  frame.contentDocument.open(); frame.contentDocument.write(frame.srcdoc); frame.contentDocument.close();
  const fw = frame.contentWindow;
  Object.defineProperty(fw.HTMLImageElement.prototype,'decode',{configurable:true,value:async function(){
    const index=++state.started;
    state.pending++; state.maxPending=Math.max(state.maxPending,state.pending);
    await gate;
    state.pending--;
    if(index===failedIndex){
      if(badAsset) assert.equal(this.src,'data:image/png;base64,AAAA');
      const error = malformed === undefined ? new fw.DOMException(nativeReason,'EncodingError') : malformed;
      state.nativeError=error;
      throw error;
    }
    state.ready++;
  }});
  fw.focus=()=>{};
  fw.print=()=>{
    assert.equal(state.ready,n,'all N successful native readiness results before transfer');
    assert.equal(state.saves.length,1,'source is saved before external handoff');
    assert.equal(state.saves[0].readyAtSave,n,'no early durable success');
    state.transfers.push(frame.srcdoc);
  };
  onload.call(frame,new fw.Event('load'));
  return {dom,w,state,boxes,operation,release:()=>release?.(),close:()=>dom.window.close()};
}

for(const [index,badAsset] of [[150,false],[299,false],[150,true]]) {
  test(`C5 native iframe EncodingError ${index} ${badAsset?'invalid PNG':'valid PNG source'} preserves reason and aborts entire tape`,async()=>{
    const f=await fixture({failedIndex:index,badAsset});
    try {
      await f.operation;
      assert.ok(f.state.nativeError instanceof f.state.frames[0].contentWindow.DOMException);
      assert.equal(f.state.nativeError instanceof f.w.Error,false,'native error crosses iframe realm');
      assert.equal(f.state.busy,false,'operator exits waiting state');
      assert.equal(f.w.inboundLabelPrinting.current,false,'known preparation failure can be explicitly retried');
      assert.deepEqual(f.state.transfers,[]);
      assert.deepEqual(f.state.marks,[]);
      assert.deepEqual(f.state.saves,[],'failed preparation leaves no successful attempt');
      assert.equal(f.w.document.querySelectorAll('iframe').length,0,'failed source cleaned');
      assert.equal(f.state.error,nativeReason,'screen must retain available native error reason');
    } finally {f.close();}
  });
}
for(const [name,value] of [['blank message',{message:''}],['nonstring message',{message:42}],['no message',{}]]) {
  test(`C5 ${name} retains existing generic preparation error and zero external actions`,async()=>{
    const f=await fixture({failedIndex:1,malformed:value});
    try {
      await f.operation;
      assert.equal(f.state.error,genericReason);
      assert.equal(f.state.busy,false);
      assert.deepEqual(f.state.transfers,[]);assert.deepEqual(f.state.marks,[]);assert.deepEqual(f.state.saves,[]);
      assert.equal(f.w.document.querySelectorAll('iframe').length,0);
    } finally {f.close();}
  });
}
test('C4/R4 300 held images overlap but complete readiness and source precede one transfer and all marks',async()=>{
  const f=await fixture({hold:true});
  try {
    assert.ok(f.state.started>=2,'parallel readiness overlap remains required; no numeric group size fixed');
    assert.equal(f.state.ready,0);
    assert.equal(f.state.busy,true);
    assert.deepEqual(f.state.transfers,[]);assert.deepEqual(f.state.marks,[]);assert.deepEqual(f.state.saves,[]);
    f.release();await f.operation;
    assert.equal(f.state.ready,300);
    assert.equal(f.state.transfers.length,1);
    const html=new f.w.DOMParser().parseFromString(f.state.transfers[0],'text/html');
    assert.deepEqual([...html.querySelectorAll('.label')].map(v=>v.dataset.barcode),f.boxes.map(v=>v.barcode));
    assert.deepEqual(f.state.marks,f.boxes.map(v=>`/operations/inbound-intake-requests/native-document/boxes/${v.id}/mark-label-printed`));
    assert.equal(f.state.saves.at(-1).state,'complete');
    assert.equal(f.state.busy,false);
    assert.equal(f.state.error,null);
    assert.equal(f.w.document.querySelectorAll('iframe').length,1,'source lives until afterprint');
  } finally {f.release();f.close();}
});
