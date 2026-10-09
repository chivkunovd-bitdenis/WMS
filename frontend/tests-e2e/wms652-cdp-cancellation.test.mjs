// WMS-652 additive transport contract. Execute the real CDP class, never the
// browser runner/top-level Chrome. WebSocket messages and timer expiry are inputs.
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createRequire} from 'node:module';
import {runInNewContext} from 'node:vm';
import {test} from 'node:test';

const require = createRequire(new URL('../package.json', import.meta.url));
const ts = require('typescript');
const source = readFileSync(new URL('./wms652-critical/browser.mjs', import.meta.url), 'utf8');
const tree = ts.createSourceFile('browser.mjs', source, ts.ScriptTarget.Latest, true, ts.ScriptKind.JS);
const actualClass = tree.statements.find(node => ts.isClassDeclaration(node) && node.name?.text === 'CDP');
assert.ok(actualClass, 'extract the actual CDP operation, not a replacement transport');
const actualSleep = tree.statements.find(node => ts.isVariableStatement(node)
  && node.declarationList.declarations.some(declaration => ts.isIdentifier(declaration.name) && declaration.name.text === 'sleep'));
assert.ok(actualSleep, 'extract the actual bounded wait used by the CDP operation');
// Inert function declarations may support the class; no top-level variables,
// browser startup, imports, fixture execution or business operation is evaluated.
const declarations = tree.statements.filter(ts.isFunctionDeclaration).map(node => node.getText(tree)).join('\n');
const actualCode = `${declarations}\n${actualSleep.getText(tree)}\n${actualClass.getText(tree)}\nCDP`;
const nativeError = {code: -32602, message: 'Invalid InterceptionId.'};
const fetchId = 'interception-job-3.0', networkId = '3156.3';
const flush = async () => {for (let i = 0; i < 4; i++) await new Promise(setImmediate);};

function fixture() {
  const errors = [], commands = [], timers = new Map();
  let ws, timerId = 0;
  class ControlledWebSocket {
    constructor() {ws = this; queueMicrotask(() => this.onopen?.({}));}
    send(raw) {commands.push(JSON.parse(raw));}
    close() {}
  }
  const CDP = runInNewContext(actualCode, {WebSocket: ControlledWebSocket, errors,
    assert, Buffer, URL, queueMicrotask, setImmediate,
    setTimeout: (callback, delay) => {
      const id = ++timerId; timers.set(id, callback);
      // Advance only the bounded 300ms cancellation-observation window. The
      // 12s command timeout stays explicitly controlled by each test.
      if (delay === 300) setImmediate(() => {if (timers.has(id)) {timers.delete(id); callback();}});
      return id;
    },
    clearTimeout: id => timers.delete(id)});
  const cdp = new CDP('ws://synthetic.invalid/no-connection');
  const emit = (method, params) => ws.onmessage({data: JSON.stringify({method, params})});
  const paused = (mapping = networkId) => emit('Fetch.requestPaused', {
    requestId: fetchId, ...(mapping === null ? {} : {networkId: mapping}),
    frameId: 'frame-observed', resourceType: 'Fetch',
    request: {url: 'http://synthetic.invalid/held', method: 'GET'},
  });
  const cancel = ({id = networkId, canceled = true, errorText = 'net::ERR_ABORTED'} = {}) =>
    emit('Network.loadingFailed', {requestId: id, type: 'Fetch', canceled, errorText});
  const navigation = () => {
    emit('Page.frameNavigated', {frame: {id: 'frame-observed', loaderId: 'new-loader', url: 'http://synthetic.invalid/new'}});
    emit('Runtime.executionContextsCleared', {});
  };
  const reply = (command, error, result = {}) => ws.onmessage({data: JSON.stringify(
    error ? {id: command.id, error} : {id: command.id, result})});
  async function call({id = fetchId, method = 'Fetch.fulfillRequest', error = nativeError, result, timeout = false} = {}) {
    const before = commands.length;
    const params = method === 'Fetch.fulfillRequest' ? {requestId: id, responseCode: 200, body: 'e30='}
      : {requestId: id, ...(method === 'Fetch.failRequest' ? {errorReason: 'ConnectionClosed'} : {})};
    const promise = cdp.send(method, params)
      .then(value => ({kind: 'resolved', value}), value => ({kind: 'rejected', value}));
    await flush();
    assert.equal(commands.length, before + 1, 'one native call; no hidden retry');
    const command = commands.at(-1);
    assert.equal(command.method, method); assert.equal(command.params.requestId, id);
    if (timeout) {
      assert.equal(timers.size, 1, 'expire the real outstanding command timer');
      const [key, callback] = [...timers][0]; timers.delete(key); callback();
    } else reply(command, error, result);
    const outcome = await promise;
    await flush();
    assert.equal(commands.length, before + 1, 'native refusal/success never retries');
    assert.equal(timers.size, 0, 'terminal command leaves no held timeout');
    return outcome;
  }
  async function callback({error = nativeError, method = 'Fetch.fulfillRequest', timeout = false} = {}) {
    let outcome;
    const before = commands.length;
    cdp.on('Contract.fulfill', async () => {
      try {const value = await cdp.send(method, method === 'Fetch.fulfillRequest'
        ? {requestId: fetchId, responseCode: 200, body: 'e30='} : {requestId: fetchId}); outcome = {kind: 'resolved', value};}
      catch (value) {outcome = {kind: 'rejected', value}; throw value;}
    });
    emit('Contract.fulfill', {});
    await flush();
    assert.equal(commands.length, before + 1);
    if (timeout) {
      assert.equal(timers.size, 1);
      const [key, expire] = [...timers][0]; timers.delete(key); expire();
    } else reply(commands.at(-1), error);
    await flush();
    assert.ok(outcome, 'actual CDP event callback settles');
    assert.equal(commands.length, before + 1, 'callback does not retry native fulfillment');
    assert.equal(timers.size, 0);
    return outcome;
  }
  return {cdp, errors, commands, emit, paused, cancel, navigation, call, callback};
}

function diagnostic(value) {return `${String(value)}\n${JSON.stringify(value)}`;}
function strictFailure(outcome, expected = nativeError) {
  assert.equal(outcome.kind, 'rejected', 'unproven/other transport failures stay rejected');
  assert.notEqual(outcome.value?.retired, true, 'unproven/other failures cannot acquire retired disposition');
  assert.ok(diagnostic(outcome.value).includes(String(expected.code)), 'native code remains available');
  assert.ok(diagnostic(outcome.value).includes(expected.message), 'native message remains available');
}
function retired(outcome) {
  // A public observable marker works on either a returned terminal outcome or a
  // typed rejected error. It does not prescribe internal maps/helpers/exports.
  assert.equal(outcome.value?.retired, true, 'independently proven canceled token has a clear retired disposition');
  assert.ok(diagnostic(outcome.value).includes('-32602'));
  assert.ok(diagnostic(outcome.value).includes('Invalid InterceptionId.'));
  assert.notEqual(outcome.value.accepted, true); assert.notEqual(outcome.value.submitted, true);
  assert.equal(outcome.value.receipt, undefined, 'retirement is never an accepted business receipt');
}

test('CDP1 exact observed Fetch-to-Network abort returns a distinct retired disposition with native diagnostic and no retry', async () => {
  const f = fixture(); f.paused(); f.cancel();
  const outcome = await f.call();
  assert.equal(f.commands.length, 1);
  retired(outcome);
});

test('CDP2 actual callback collector excludes only proven canceled retirement and retains an identical unknown-ID error', async () => {
  const known = fixture(); known.paused(); known.cancel();
  const knownOutcome = await known.callback();
  const unknown = fixture(); unknown.cancel();
  const unknownOutcome = await unknown.callback();
  strictFailure(unknownOutcome);
  assert.equal(unknown.errors.length, 1, 'same native signature without an observed mapping remains a strict callback error');
  assert.ok(unknown.errors[0].includes('Invalid InterceptionId.'));
  assert.deepEqual(known.errors, [], 'proven transport retirement alone does not fail the business callback collector');
  retired(knownOutcome);
});

test('CDP3 unknown identity, incomplete evidence, completed tokens, other protocol errors and timeouts remain strict failures', async context => {
  const scenarios = [
    ['never observed FetchID', f => f.cancel()],
    ['missing network mapping', f => {f.paused(null); f.cancel();}],
    ['different network cancellation', f => {f.paused(); f.cancel({id: 'different-network'});}],
    ['navigation and context clear alone', f => {f.paused(); f.navigation();}],
    ['canceled false even ERR_ABORTED', f => {f.paused(); f.cancel({canceled: false});}],
    ['different canceled failure text', f => {f.paused(); f.cancel({errorText: 'net::ERR_CONNECTION_CLOSED'});}],
    ['deliberate ConnectionClosed lost acknowledgment', async f => {
      f.paused(); const result = await f.call({method: 'Fetch.failRequest', error: null, result: {}});
      assert.equal(result.kind, 'resolved'); assert.equal(f.commands.at(-1).params.errorReason, 'ConnectionClosed');
      f.cancel({canceled: false, errorText: 'net::ERR_CONNECTION_CLOSED'});
    }],
    ['successful completed token cannot retire a duplicate', async f => {
      f.paused(); const result = await f.call({error: null, result: {}});
      assert.equal(result.kind, 'resolved'); f.cancel();
    }],
    ['matching abort with other error code', f => {f.paused(); f.cancel();}, {error: {code: -32000, message: 'Invalid InterceptionId.'}}],
    ['matching abort with other error message', f => {f.paused(); f.cancel();}, {error: {code: -32602, message: 'Invalid parameters.'}}],
    ['matching abort for a different terminal method', f => {f.paused(); f.cancel();}, {method: 'Fetch.continueRequest'}],
    ['matching abort does not explain timeout', f => {f.paused(); f.cancel();}, {timeout: true}],
  ];
  for (const [name, setup, options = {}] of scenarios) {
    const f = fixture(); await setup(f);
    const outcome = await f.call(options);
    if (options.timeout) {
      assert.equal(outcome.kind, 'rejected', name); assert.notEqual(outcome.value?.retired, true, name);
      assert.ok(diagnostic(outcome.value).includes('CDP timeout Fetch.fulfillRequest'));
    } else strictFailure(outcome, options.error ?? nativeError);
    const callbackOutcome = await f.callback(options);
    assert.equal(callbackOutcome.kind, 'rejected', `${name}: callback also remains rejected`);
    assert.notEqual(callbackOutcome.value?.retired, true, name);
    assert.equal(f.errors.length, 1, `${name}: strict collector must retain this failure`);
    context.diagnostic(`${name}: strict refusal preserved`);
  }
});

test('CDP4 native fulfillment success after navigation preserves the exact valid response and one command', async () => {
  const f = fixture(); f.paused(); f.navigation();
  const nativeResult = {responseObserved: 'native-command-result', marker: 652};
  const outcome = await f.call({error: null, result: nativeResult});
  assert.equal(outcome.kind, 'resolved');
  assert.equal(JSON.stringify(outcome.value), JSON.stringify(nativeResult), 'navigation alone does not retire a live interception');
  assert.notEqual(outcome.value?.retired, true);
  assert.deepEqual(f.errors, []); assert.equal(f.commands.length, 1);
});

test('CDP5 proven canceled retirement is consumed once; the same token duplicate stays a strict callback failure without retry', async context => {
  const f = fixture(); f.paused(); f.cancel();
  const first = await f.call();
  retired(first);
  assert.equal(f.commands.length, 1);
  const duplicate = await f.callback();
  context.diagnostic(JSON.stringify({firstRetired: first.value.retired,
    duplicateKind: duplicate.kind, duplicateRetired: duplicate.value?.retired,
    nativeDiagnostic: diagnostic(duplicate.value), commands: f.commands.length,
    callbackErrors: f.errors}));
  strictFailure(duplicate);
  assert.equal(f.commands.length, 2, 'one original attempt and one deliberate duplicate; no hidden retries');
  assert.equal(f.errors.length, 1, 'an already-retired token cannot exclude a second native failure from the strict collector');
  assert.ok(f.errors[0].includes('-32602'));
  assert.ok(f.errors[0].includes('Invalid InterceptionId.'));
});

async function inFlightAmbiguousOwner(context, observedFetchId) {
  const f = fixture(); f.paused(); f.cancel();
  const pending = f.cdp.send('Fetch.fulfillRequest', {
    requestId: fetchId, responseCode: 200, body: 'e30=',
  }).then(value => ({kind: 'resolved', value}), value => ({kind: 'rejected', value}));
  await flush();
  assert.equal(f.commands.length, 1, 'the original command is already on the native wire');
  const command = f.commands[0];
  assert.equal(command.method, 'Fetch.fulfillRequest');
  assert.equal(command.params.requestId, fetchId);
  f.emit('Fetch.requestPaused', {
    requestId: observedFetchId, networkId, frameId: 'frame-observed', resourceType: 'Fetch',
    request: {url: 'http://synthetic.invalid/held', method: 'GET'},
  });
  f.cdp.ws.onmessage({data: JSON.stringify({id: command.id, error: nativeError})});
  const outcome = await pending;
  await flush();
  context.diagnostic(JSON.stringify({observedFetchId, kind: outcome.kind,
    retired: outcome.value?.retired, nativeDiagnostic: diagnostic(outcome.value),
    commands: f.commands.length}));
  assert.equal(f.commands.length, 1, 'ambiguous ownership cannot trigger a retry');
  assert.ok(diagnostic(outcome.value).includes('-32602'), 'original native code is retained');
  assert.ok(diagnostic(outcome.value).includes('Invalid InterceptionId.'), 'original native message is retained');
  assert.notEqual(outcome.value?.accepted, true);
  assert.notEqual(outcome.value?.submitted, true);
  assert.equal(outcome.value?.receipt, undefined);
  strictFailure(outcome);
}

test('CDP6 reused observed FetchID after native send and before error reply remains a strict failure', async context => {
  await inFlightAmbiguousOwner(context, fetchId);
});

test('CDP7 second observed FetchID owning the same NetworkID after native send and before error reply remains a strict failure', async context => {
  await inFlightAmbiguousOwner(context, 'another-observed-interception');
});

test('case boundary waits for both observed post-pack reads to finish; earlier or merely fulfilled reads do not settle it', async () => {
  const requestLog = [
    {method: 'GET', path: '/operations/fbs-supplies/wb-b/workspace', requestId: 'earlier-read'},
    {method: 'POST', path: '/operations/packaging-tasks/task-wb-b/lines/line-next/pack'},
  ];
  const cdp = {paused: new Map([
    ['earlier-read', {networkId: 'old-network', disposition: 'network-completed'}],
  ])};
  let turns = 0;
  const settle = runInNewContext(`${declarations}\nsettlePackingReadback`, {
    assert, requestLog, cdp,
    sleep: async () => {
      turns++;
      if (turns === 1) {
        for (const [id, path] of [['workspace', '/operations/fbs-supplies/wb-b/workspace'],
          ['task', '/operations/packaging-tasks/task-wb-b']]) {
          requestLog.push({method: 'GET', path, requestId: id});
          cdp.paused.set(id, {disposition: 'completed'});
        }
      } else if (turns === 2) {
        cdp.paused.set('workspace', {networkId: 'workspace-network', disposition: 'network-completed'});
        cdp.paused.set('task', {networkId: 'task-network', disposition: 'completed'});
      } else {
        cdp.paused.get('task').disposition = 'network-completed';
      }
    },
  });
  await settle('wb-b');
  assert.equal(turns, 3, 'neither an earlier read, missing NetworkID nor command fulfillment is readback completion');
});
