'use strict';

// Independent, pre-implementation WMS-665 contract. No real Chrome, Apple
// Events, certificates, network or production data are used by these tests.
const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');
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
      if (options.redirectAfterProbe && source.includes('WMS665_PROBE')) {
        sandbox.location = new URL('https://foreign.example/');
      }
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

test('one executable macOS command embeds exact reviewed sources and needs only system JXA', () => {
  const commandPath = path.join(__dirname, '../avpack-sold-kiz.command');
  const command = fs.readFileSync(commandPath, 'utf8');
  assert.ok((fs.statSync(commandPath).mode & 0o111) !== 0, 'the command must be executable');
  assert.match(command, /^#!\/bin\/zsh\r?\n/);
  assert.match(command, /\/usr\/bin\/osascript -l JavaScript\b/);
  for (const [symbol, filename] of [
    ['HELPER_BASE64', 'avpack-sold-kiz-filter.js'],
    ['LAUNCHER_BASE64', 'avpack-macos-launcher.js'],
  ]) {
    const declarations = [...command.matchAll(new RegExp(`^const ${symbol} = '([A-Za-z0-9+/]+={0,2})';$`, 'gm'))];
    assert.equal(declarations.length, 1, `exactly one unambiguous ${symbol} source is required`);
    const encoded = declarations[0][1];
    const decoded = Buffer.from(encoded, 'base64');
    assert.equal(decoded.toString('base64'), encoded, 'base64 must be canonical and complete');
    assert.deepEqual(decoded, fs.readFileSync(path.join(__dirname, '..', filename)));
  }
  // Source is embedded, never downloaded at launch. The wrapper must not
  // install runtimes or modify the user's permissions or keychain.
  assert.doesNotMatch(command, /\b(?:curl|wget|node|nodejs|npm|npx|python\d*|pip\d*|brew)\b/i);
  assert.doesNotMatch(command, /\b(?:tccutil|sudo|security)\b|defaults\s+write|doShellScript|fetch\s*\(|XMLHttpRequest|NSURLSession|NSURLConnection/i);
});

test('redirect after permission probe blocks browser helper loading before any target data is exposed', async () => {
  const f = fixture({ redirectAfterProbe: true });
  await rejectsSafely(f);
  assert.equal(f.sandbox.__injections, 0);
  assert.equal(f.sandbox.__executions.length, 0);
});

for (const redirectAfterExecutions of [0, 1, 2]) {
  test(`JXA rechecks current tab URL before execution number ${redirectAfterExecutions + 1}`, () => {
    const command = fs.readFileSync(path.join(__dirname, '../avpack-sold-kiz.command'), 'utf8');
    const jxa = command.split("<<'WMS665_JXA'\n")[1]?.split('\nWMS665_JXA')[0];
    assert.ok(jxa, 'test must execute the actual command JXA adapter');
    let urlReads = 0;
    const executions = [];
    const tab = {
      id: () => 42,
      url() {
        urlReads += 1;
        // Inventory sees the correct page. A later browser navigation changes
        // the current URL before probe, injection or status polling.
        return urlReads === 1 || executions.length < redirectAfterExecutions
          ? URL_EXACT : 'https://foreign.example/';
      },
      execute({ javascript }) {
        executions.push(javascript);
        if (executions.length === 1) return 'null';
        if (executions.length === 2) return JSON.stringify({ status: 'running', signed: false, sent: false });
        return JSON.stringify(READY);
      },
    };
    const objc = (value) => value;
    objc.NSData = { alloc: { initWithBase64EncodedStringOptions: (value) => Buffer.from(value, 'base64') } };
    objc.NSString = { alloc: { initWithDataEncoding: (data) => data.toString('utf8') } };
    objc.NSUTF8StringEncoding = 4;
    objc.NSThread = { sleepForTimeInterval() {} };
    const context = vm.createContext({
      $: objc,
      ObjC: { import() {}, unwrap: (value) => value },
      Application: () => ({ running: () => true, windows: () => [{ tabs: () => [tab] }] }),
      console: { log() {} },
    });
    assert.throws(() => vm.runInContext(jxa, context, { timeout: 1000 }));
    assert.equal(executions.length, redirectAfterExecutions,
      'no probe, helper or poll JavaScript may be passed to Chrome on a foreign URL');
  });
}

test('successful JXA preparation brings the exact target tab and its background window to the front', () => {
  const command = fs.readFileSync(path.join(__dirname, '../avpack-sold-kiz.command'), 'utf8');
  const jxa = command.split("<<'WMS665_JXA'\n")[1]?.split('\nWMS665_JXA')[0];
  assert.ok(jxa);
  const executedIds = [];
  let activations = 0;
  let targetExecutions = 0;
  const makeTab = (id, url) => ({
    id: () => id,
    url: () => url,
    execute() {
      executedIds.push(id);
      assert.equal(id, 42, 'unrelated tabs must never receive JavaScript');
      targetExecutions += 1;
      if (targetExecutions === 1) return 'null';
      if (targetExecutions === 2) return JSON.stringify({ status: 'running', signed: false, sent: false });
      return JSON.stringify(READY);
    },
  });
  const frontTab = makeTab(10, 'https://example.org/');
  const unrelatedBackgroundTab = makeTab(41, 'https://example.net/');
  const targetTab = makeTab(42, URL_EXACT);
  const frontWindow = { id: () => 100, index: 1, activeTabIndex: 1, tabs: () => [frontTab] };
  const targetWindow = { id: () => 200, index: 2, activeTabIndex: 1, tabs: () => [unrelatedBackgroundTab, targetTab] };
  const objc = (value) => value;
  objc.NSData = { alloc: { initWithBase64EncodedStringOptions: (value) => Buffer.from(value, 'base64') } };
  objc.NSString = { alloc: { initWithDataEncoding: (data) => data.toString('utf8') } };
  objc.NSUTF8StringEncoding = 4;
  objc.NSThread = { sleepForTimeInterval() {} };
  const context = vm.createContext({
    $: objc,
    ObjC: { import() {}, unwrap: (value) => value },
    Application: () => ({
      running: () => true,
      windows: () => [frontWindow, targetWindow],
      activate() { activations += 1; },
    }),
    console: { log() {} },
  });
  vm.runInContext(jxa, context, { timeout: 1000 });
  assert.ok(targetExecutions >= 3, 'the ready result must come from the target tab');
  assert.ok(executedIds.every((id) => id === 42));
  assert.equal(targetWindow.activeTabIndex, 2, 'the target is the second tab, not the old active tab');
  assert.equal(targetWindow.index, 1, 'the previously background target window must be brought forward');
  assert.equal(activations, 1, 'Chrome must be brought in front of Terminal after readiness');
  assert.equal(frontWindow.activeTabIndex, 1, 'the unrelated window selection must stay untouched');
});
