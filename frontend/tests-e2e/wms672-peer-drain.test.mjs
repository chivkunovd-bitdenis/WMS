// WMS-672 additive active-peer drain contract. Frozen native-errors suite unchanged.
// Actual utility and screen operation; controlled decode boundary, no native browser proof.
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

async function fixture({synchronous = false} = {}) {
  const n = 300;
  const failedIndex = 2;
  const dom = new JSDOM('<body></body>', {url:'https://synthetic.wms.test/', runScripts:'dangerously', pretendToBeVisual:true});
  const w = dom.window;
  const state = {started:0, ready:0, maxPending:0, pending:0, marks:[], saves:[], transfers:[], busy:false, error:null, frames:[], nativeError:null, propagated:null, finished:false, cleanup:[], lateError:null};
  let release, rejectObserved;
  const gate = new Promise(resolve => {release = resolve;});
  const failureObserved = new Promise(resolve => {rejectObserved = resolve;});
  const boxes = Array.from({length:n}, (_, i) => ({id:`native-box-${i+1}`, number:i+1,
    barcode:`INB-${String(i+1).padStart(12,'0')}`, kind:'box', label_printed_at:null}));
  const exports = {};
  w.exports = exports;
  w.eval(compile(utilitySource));
  Object.assign(w, {
    printBarcodeLabels:(...args) => exports.printBarcodeLabels(...args).catch(error => {
      state.propagated = error; throw error;
    }), inboundLabelPrinting:{current:false},
    setBusy:value => {state.busy=value;}, setError:value => {state.error=value;},
    readIntake:() => ({}), saveInboundLabelAttempt:(_token, _id, attempt) => {
      state.saves.push({...attempt, readyAtSave:state.ready});
    }, token:'synthetic', requestId:'native-document', authHeaders:{},
    apiUrl:path => path, randomId:() => 'native-attempt', detail:{boxes},
    numberedInboundBoxLabels:true, inboundBoxDisplayLabel:number => String(number),
    renderBarcodeDataUrl:() => validPng,
    readApiErrorMessage:async () => 'synthetic API error', loadDetail:async () => {},
    fetch:async (path, init) => {
      assert.equal(init.method,'POST');
      assert.equal(state.transfers.length,1,'marks follow one successful transfer');
      assert.equal(state.ready,n,'every image ready before first mark');
      state.marks.push(path); return {ok:true};
    },
  });
  const remove = w.document.body.removeChild.bind(w.document.body);
  w.document.body.removeChild = node => {
    if(node.tagName === 'IFRAME') state.cleanup.push({pending:state.pending, ready:state.ready});
    return remove(node);
  };
  const append = w.document.body.appendChild.bind(w.document.body);
  w.document.body.appendChild = node => {
    const result=append(node);
    if(node.tagName==='IFRAME') state.frames.push(node);
    return result;
  };
  w.eval(compile(`globalThis.__screenPrint = ${initializer.getText(tree)};`));
  const operation = w.__screenPrint(boxes,{id:'58x40',widthMm:58,heightMm:40})
    .then(() => {state.finished = true;});
  assert.equal(state.frames.length,1,'actual utility constructs one complete iframe');
  const frame = state.frames[0];
  const onload = frame.onload;
  frame.onload=null; // jsdom has no srcdoc navigation; deliver its real HTML once.
  frame.contentDocument.open(); frame.contentDocument.write(frame.srcdoc); frame.contentDocument.close();
  const fw = frame.contentWindow;
  Object.defineProperty(fw.HTMLImageElement.prototype,'decode',{configurable:true,value:function(){
    const index=++state.started;
    if(index === failedIndex) {
      const error = new fw.DOMException(nativeReason, 'EncodingError');
      state.nativeError = error;
      rejectObserved();
      if(synchronous) throw error;
      return Promise.reject(error);
    }
    state.pending++; state.maxPending=Math.max(state.maxPending,state.pending);
    return gate.then(() => {
      state.pending--;
      if(index === 1 && !synchronous) {
        state.lateError = new fw.DOMException('A later peer also failed.', 'EncodingError');
        throw state.lateError;
      }
      state.ready++;
    });
  }});
  fw.focus=()=>{};
  fw.print=()=>{
    assert.equal(state.ready,n,'all N successful native readiness results before transfer');
    assert.equal(state.saves.length,1,'source is saved before external handoff');
    assert.equal(state.saves[0].readyAtSave,n,'no early durable success');
    state.transfers.push(frame.srcdoc);
  };
  onload.call(frame,new fw.Event('load'));
  return {dom,w,state,boxes,operation,failureObserved,release:()=>release(),close:()=>dom.window.close()};
}

// Event-loop turns observe the already delivered failure; peers stay held by an
// explicit promise, never by a timeout or a native-decoder timing assumption.
const flush = async () => {for(let i=0;i<4;i++) await new Promise(resolve => setImmediate(resolve));};
for(const synchronous of [false,true]) {
  test(`C5 ${synchronous?'synchronous decode throw':'first native EncodingError with a later peer rejection'} drains held active peers before cleanup and retry readiness`,async(context)=>{
    const f=await fixture({synchronous});
    try {
      await f.failureObserved; await flush();
      assert.ok(f.state.pending>=1, 'at least one actual started decode peer remains held');
      assert.equal(f.state.ready,0);
      assert.ok(f.state.nativeError instanceof f.state.frames[0].contentWindow.DOMException);
      assert.equal(f.state.nativeError instanceof f.w.Error,false);
      assert.deepEqual(f.state.transfers,[]); assert.deepEqual(f.state.marks,[]); assert.deepEqual(f.state.saves,[]);
      const held={connected:f.state.frames[0].isConnected, finished:f.state.finished,
        busy:f.state.busy, active:f.w.inboundLabelPrinting.current, cleanup:[...f.state.cleanup],
        started:f.state.started};
      f.release(); await f.operation;
      context.diagnostic(JSON.stringify({held, afterRelease:{pending:f.state.pending, ready:f.state.ready, cleanup:f.state.cleanup, finished:f.state.finished}}));
      // Assertions after release let the broken baseline safely drain too.
      assert.equal(held.connected,true, 'failed tape source must live until held active decode peers settle');
      assert.equal(held.finished,false, 'operation must not complete while its own active peers are pending');
      assert.equal(held.busy,true, 'operator waiting state remains until preparation is fully stopped');
      assert.equal(held.active,true, 'explicit retry cannot overlap still-running abandoned preparation');
      assert.deepEqual(held.cleanup,[], 'no frame teardown while its decode work is active');
      assert.equal(f.state.pending,0);
      assert.equal(f.state.ready,f.state.started-(synchronous?1:2), 'every started nonfailing peer finishes');
      if(!synchronous) assert.ok(f.state.lateError, 'earlier input peer fails later with a distinct cause');
      assert.equal(f.state.started,held.started, 'known failure starts no later decode cohort');
      assert.equal(f.state.propagated,f.state.nativeError, 'original failure identity survives draining');
      assert.equal(f.state.error,nativeReason, 'original available reason survives screen handling');
      assert.deepEqual(f.state.transfers,[]); assert.deepEqual(f.state.marks,[]); assert.deepEqual(f.state.saves,[]);
      assert.equal(f.state.cleanup.length,1);
      assert.equal(f.state.cleanup[0].pending,0, 'cleanup follows peer settlement');
      assert.equal(f.w.document.querySelectorAll('iframe').length,0);
      assert.equal(f.state.busy,false); assert.equal(f.w.inboundLabelPrinting.current,false);
    } finally {f.release(); await f.operation; f.close();}
  });
}
