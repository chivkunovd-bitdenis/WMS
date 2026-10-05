'use strict';

// Independent, pre-implementation WMS-665 contract. No real Chrome, Apple
// Events, certificates, network or production data are used by these tests.
const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const { launch } = require('../avpack-macos-launcher.js');

const URL_EXACT = 'https://sellerfocus.pro/seller/honest-sign/withdrawals';
const SECRET = 'synthetic-secret-do-not-print-665';
const READY = Object.freeze({
  status: 'certificate_dialog_open', targetCount: 80,
  noSend: true, signed: false, sent: false,
});
const HELPER_SOURCE = `
  window.__injections += 1;
  window.AvpackSoldKizFilter = {
    createHelper() {
      return { async run(options) {
        window.__executions.push(options);
        if (window.__failHelper) throw new Error('${SECRET}');
        if (window.__hangHelper) return new Promise(() => {});
        return window.__helperResult;
      }};
    }
  };
`;

function fixture(options = {}) {
  const calls = [];
  const sandbox = {
    URL,
    location: new URL(options.pageUrl ?? URL_EXACT),
    __injections: 0,
    __executions: [],
    __helperResult: options.result ?? { ...READY },
    __failHelper: options.failHelper ?? false,
    __hangHelper: options.hangHelper ?? false,
  };
  sandbox.window = sandbox;
  sandbox.globalThis = sandbox;
  if (options.state) sandbox.__WMS665_MAC_RUN__ = { ...options.state };
  const context = vm.createContext(sandbox, { microtaskMode: 'afterEvaluate' });
  let waits = 0;
  const chrome = {
    running() {
      calls.push({ kind: 'running' });
      if (options.failRunning) throw new Error(SECRET);
      return options.running ?? true;
    },
    tabs() {
      calls.push({ kind: 'tabs' });
      if (options.failTabs) throw new Error(SECRET);
      return options.tabs ?? [{ id: 42, url: URL_EXACT }];
    },
    evaluate(id, source) {
      calls.push({ kind: 'evaluate', id, source });
      assert.equal(id, 42, 'launcher must evaluate only the resolved exact tab');
      if (options.failEvaluate || (options.failProbe && source.includes('WMS665_PROBE'))) {
        throw new Error(SECRET);
      }
      const result = vm.runInContext(source, context, { timeout: 200 });
      if (options.malformedStatus && source.includes('__WMS665_MAC_RUN__') && !source.includes(HELPER_SOURCE)) {
        return '{broken';
      }
      return result;
    },
  };
  return {
    sandbox, calls,
    get waits() { return waits; },
    run(overrides = {}) {
      return Promise.resolve().then(() => {
        const result = launch({
          chrome, helperSource: HELPER_SOURCE, maxPolls: 3,
          wait() { waits += 1; vm.runInContext('void 0', context); },
          ...overrides,
        });
        assert.ok(!result || typeof result.then !== 'function', 'JXA launch must return synchronously');
        return result;
      });
    },
  };
}

async function rejectsSafely(f) {
  await assert.rejects(f.run(), (error) => {
    const rendered = `${String(error)} ${JSON.stringify(error)}`;
    assert.ok(error instanceof Error);
    assert.ok(error.message.length > 0 && error.message.length < 1000);
    assert.ok(!rendered.includes(SECRET), 'raw browser/helper errors must not escape');
    return true;
  });
}

test('launches the helper once in execute mode and returns only unsigned unsent 80-dialog success', async () => {
  const f = fixture({ result: { ...READY, token: SECRET, message: SECRET } });
  const result = await f.run();
  assert.equal(result.status, READY.status);
  assert.equal(result.targetCount, 80);
  assert.equal(result.signed, false);
  assert.equal(result.sent, false);
  assert.ok(!JSON.stringify(result).includes(SECRET));
  assert.equal(f.sandbox.__injections, 1);
  assert.equal(f.sandbox.__executions.length, 1);
  assert.equal(JSON.stringify(f.sandbox.__executions[0]), JSON.stringify({ mode: 'execute' }));
  const evaluations = f.calls.filter((call) => call.kind === 'evaluate');
  assert.ok(evaluations[0].source.includes('WMS665_PROBE'), 'permission probe precedes any injection');
  assert.ok(!evaluations[0].source.includes(HELPER_SOURCE));
  assert.ok(evaluations.filter((call) => !call.source.includes(HELPER_SOURCE)).every(
    (call) => !/localStorage|sessionStorage|document\.|fetch\(|cadesplugin/.test(call.source)
  ), 'status polling must not read credentials, inspect certificates or act on the page');
});

test('allows query and hash on the exact registry URL and ignores unrelated tabs', async () => {
  const f = fixture({ tabs: [
    { id: 1, url: 'https://example.org' },
    { id: 42, url: `${URL_EXACT}?date_from=2026-09-18#registry` },
  ] });
  assert.equal((await f.run()).targetCount, 80);
});

for (const url of [
  'http://sellerfocus.pro/seller/honest-sign/withdrawals',
  'https://sellerfocus.pro.evil.test/seller/honest-sign/withdrawals',
  'https://evil.test/sellerfocus.pro/seller/honest-sign/withdrawals',
  `${URL_EXACT}/operations`,
  'https://sellerfocus.pro/seller/honest-sign/withdrawals-other',
  'not a URL',
]) {
  test(`rejects non-target tab ${url} before injection`, async () => {
    const f = fixture({ tabs: [{ id: 42, url }] });
    await rejectsSafely(f);
    assert.equal(f.sandbox.__injections, 0);
    assert.equal(f.calls.filter((call) => call.kind === 'evaluate').length, 0);
  });
}

for (const tabs of [[], [{ id: 42, url: URL_EXACT }, { id: 43, url: URL_EXACT }]]) {
  test(`rejects ${tabs.length} matching tabs before injection`, async () => {
    const f = fixture({ tabs });
    await rejectsSafely(f);
    assert.equal(f.calls.filter((call) => call.kind === 'evaluate').length, 0);
  });
}

test('does not launch Chrome if it is not already running', async () => {
  const f = fixture({ running: false });
  await rejectsSafely(f);
  assert.deepEqual(f.calls.map((call) => call.kind), ['running']);
});

for (const failure of ['failRunning', 'failTabs', 'failEvaluate', 'failProbe']) {
  test(`fails fast and redacts Apple Events or Automation error at ${failure}`, async () => {
    const f = fixture({ [failure]: true });
    await rejectsSafely(f);
    assert.equal(f.sandbox.__injections, 0);
    assert.equal(f.waits, 0);
  });
}

test('repeated launch after successful preparation does not inject or execute twice', async () => {
  const f = fixture();
  await f.run();
  assert.equal((await f.run()).status, READY.status);
  assert.equal(f.sandbox.__injections, 1);
  assert.equal(f.sandbox.__executions.length, 1);
});

test('an already running launch is never injected again and polling is bounded', async () => {
  const f = fixture({ state: { status: 'running', signed: false, sent: false } });
  await rejectsSafely(f);
  assert.equal(f.sandbox.__injections, 0);
  assert.equal(f.sandbox.__executions.length, 0);
  assert.ok(f.waits <= 3);
  assert.ok(f.calls.filter((call) => call.kind === 'evaluate').length <= 6);
});

test('helper rejection is redacted, never retried and never reported as success', async () => {
  const f = fixture({ failHelper: true });
  await rejectsSafely(f);
  assert.equal(f.sandbox.__executions.length, 1);
  assert.ok(!JSON.stringify(f.sandbox.__WMS665_MAC_RUN__).includes(SECRET));
  await rejectsSafely(f);
  assert.equal(f.sandbox.__executions.length, 1);
});

test('a hung helper times out with bounded polling and no automatic retry', async () => {
  const f = fixture({ hangHelper: true });
  await rejectsSafely(f);
  assert.equal(f.sandbox.__executions.length, 1);
  assert.ok(f.waits <= 3);
  assert.ok(f.calls.filter((call) => call.kind === 'evaluate').length <= 7);
  await rejectsSafely(f);
  assert.equal(f.sandbox.__executions.length, 1);
});

for (const patch of [
  { status: 'ready' }, { targetCount: 79 }, { targetCount: 81 },
  { signed: true }, { sent: true }, { signed: undefined }, { sent: undefined },
]) {
  test(`does not accept unsafe or incomplete helper result ${JSON.stringify(patch)}`, async () => {
    const f = fixture({ result: { ...READY, ...patch } });
    await rejectsSafely(f);
    assert.equal(f.sandbox.__executions.length, 1);
  });
}

test('does not accept malformed browser status as readiness', async () => {
  const f = fixture({ malformedStatus: true });
  await rejectsSafely(f);
  assert.ok(f.sandbox.__executions.length <= 1);
});
