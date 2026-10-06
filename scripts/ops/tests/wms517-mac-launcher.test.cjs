'use strict';

// WMS-517 R26/R27 pre-implementation contract, derived from WMS-665 c42f4d3.
// URL, redaction, JXA permission, no-retry and artifact guards are retained.
// Fixed80 expectations are superseded explicitly by R27 dynamic N. No real Chrome, Apple
// Events, certificates, network or production data are used by these tests.
const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');
const directory = process.env.WMS517_MAC_SOURCE_DIR ?? path.join(__dirname, '..');
const { launch } = require(path.join(directory, 'avpack-macos-launcher.js'));

const URL_EXACT = 'https://wms.sellerfocus.pro/seller/honest-sign/withdrawals';
const SECRET = 'synthetic-secret-do-not-print-665';
const READY = Object.freeze({
  status: 'certificate_dialog_open', targetCount: 84,
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

test('launches the helper once in execute mode and returns only unsigned unsent dynamic-dialog success', async () => {
  const f = fixture({ result: { ...READY, token: SECRET, message: SECRET } });
  const result = await f.run();
  assert.equal(result.status, READY.status);
  assert.equal(result.targetCount, 84);
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

for (const suffix of ['', '/', '?date_from=2026-09-18#registry', '#registry', '/?date_from=2026-09-18', '/#registry']) {
  const name = suffix === '?date_from=2026-09-18#registry'
    ? 'allows query and hash on the exact registry URL and ignores unrelated tabs'
    : `accepts the correct production registry URL variant ${suffix || '(exact)'} and ignores unrelated tabs`;
  test(name, async () => {
    const f = fixture({ pageUrl: `${URL_EXACT}${suffix}`, tabs: [
      { id: 1, url: 'https://example.org' },
      { id: 2, url: 'https://sellerfocus.pro/seller/honest-sign/withdrawals' },
      { id: 42, url: `${URL_EXACT}${suffix}` },
    ] });
    assert.equal((await f.run()).targetCount, 84);
    assert.equal(f.sandbox.__executions.length, 1);
    assert.ok(f.calls.filter(call => call.kind === 'evaluate').every(call => call.id === 42));
  });
}

for (const url of [
  'https://sellerfocus.pro/seller/honest-sign/withdrawals',
  'http://wms.sellerfocus.pro/seller/honest-sign/withdrawals',
  'https://wms.sellerfocus.pro.evil.test/seller/honest-sign/withdrawals',
  'https://evil.test/sellerfocus.pro/seller/honest-sign/withdrawals',
  `${URL_EXACT}/operations`,
  'https://wms.sellerfocus.pro/seller/honest-sign/withdrawals-other',
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
  { status: 'ready' }, { targetCount: 0 }, { targetCount: -1 }, { targetCount: 1.5 }, { targetCount: '84' }, { targetCount: null }, { targetCount: undefined }, { targetCount: Infinity },
  { noSend: false }, { noSend: undefined }, { signed: true }, { sent: true }, { signed: undefined }, { sent: undefined },
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
  const commandPath = path.join(directory, 'avpack-sold-kiz.command');
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
    assert.deepEqual(decoded, fs.readFileSync(path.join(directory, filename)));
  }
  // Source is embedded, never downloaded at launch. The wrapper must not
  // install runtimes or modify the user's permissions or keychain.
  assert.doesNotMatch(command, /\b(?:curl|wget|node|nodejs|npm|npx|python\d*|pip\d*|brew)\b/i);
  assert.doesNotMatch(command, /\b(?:tccutil|sudo|security)\b|defaults\s+write|doShellScript|fetch\s*\(|XMLHttpRequest|NSURLSession|NSURLConnection/i);
});

test('all launch artifacts and the runbook use the correct production URL without the old working link', () => {
  for (const filename of [
    'avpack-sold-kiz-filter.js', 'avpack-macos-launcher.js',
    'build-avpack-macos-command.cjs', 'avpack-sold-kiz.command',
  ]) {
    const source = fs.readFileSync(path.join(directory, filename), 'utf8');
    assert.ok(source.includes('https://wms.sellerfocus.pro'), `${filename} must point Vitaliy to production`);
    assert.ok(!source.includes('https://sellerfocus.pro'), `${filename} must not direct him to the 404 host`);
  }
});

test('the command generator reproduces the saved executable exactly without writing any real file', () => {
  const writes = [];
  const modes = [];
  const generatorFs = {
    readFileSync(filename) {
      assert.ok(['avpack-sold-kiz-filter.js', 'avpack-macos-launcher.js'].some(
        name => filename === path.join(directory, name)));
      return fs.readFileSync(filename);
    },
    writeFileSync(filename, content, options) { writes.push({ filename, content, options }); },
    chmodSync(filename, mode) { modes.push({ filename, mode }); },
  };
  const generator = fs.readFileSync(path.join(directory, 'build-avpack-macos-command.cjs'), 'utf8');
  vm.runInNewContext(generator, {
    __dirname: directory,
    require(name) {
      if (name === 'node:fs') return generatorFs;
      if (name === 'node:path') return path;
      throw new Error(`Unexpected generator dependency: ${name}`);
    },
  }, { timeout: 1000 });
  const commandPath = path.join(directory, 'avpack-sold-kiz.command');
  assert.equal(writes.length, 1);
  assert.equal(writes[0].filename, commandPath);
  assert.equal(writes[0].content, fs.readFileSync(commandPath, 'utf8'));
  assert.equal(writes[0].options.encoding, 'utf8');
  assert.equal(writes[0].options.mode, 0o755);
  assert.deepEqual(modes, [{ filename: commandPath, mode: 0o755 }]);
});

test('redirect after permission probe blocks browser helper loading before any target data is exposed', async () => {
  const f = fixture({ redirectAfterProbe: true });
  await rejectsSafely(f);
  assert.equal(f.sandbox.__injections, 0);
  assert.equal(f.sandbox.__executions.length, 0);
});

for (const redirectAfterExecutions of [0, 1, 2]) {
  test(`JXA rechecks current tab URL before execution number ${redirectAfterExecutions + 1}`, () => {
    const command = fs.readFileSync(path.join(directory, 'avpack-sold-kiz.command'), 'utf8');
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
  const command = fs.readFileSync(path.join(directory, 'avpack-sold-kiz.command'), 'utf8');
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

function runJxaFocusScenario({ replaceAfterReady = false, failAt } = {}) {
  const command = fs.readFileSync(path.join(directory, 'avpack-sold-kiz.command'), 'utf8');
  const jxa = command.split("<<'WMS665_JXA'\n")[1]?.split('\nWMS665_JXA')[0];
  assert.ok(jxa);
  let ready = false;
  const executions = [];
  const focus = [];
  const messages = [];
  const target = {
    id: () => 42,
    url: () => ready && replaceAfterReady ? 'https://foreign.example/' : URL_EXACT,
    execute({ javascript }) {
      executions.push({ id: 42, source: javascript });
      if (executions.length === 1) return 'null';
      if (executions.length === 2) return JSON.stringify({ status: 'running', signed: false, sent: false });
      ready = true;
      return JSON.stringify(READY);
    },
  };
  const replacement = {
    id: () => 41,
    url: () => ready && replaceAfterReady ? URL_EXACT : 'https://example.org/',
    execute({ javascript }) { executions.push({ id: 41, source: javascript }); return JSON.stringify(READY); },
  };
  const targetWindow = {
    tabs() {
      if (ready && failAt === 'tabs') throw new Error(SECRET);
      return [replacement, target];
    },
    set activeTabIndex(value) {
      if (failAt === 'activeTabIndex') throw new Error(SECRET);
      focus.push({ kind: 'tab', value });
    },
    set index(value) {
      if (failAt === 'index') throw new Error(SECRET);
      focus.push({ kind: 'window', value });
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
    Application: () => ({
      running: () => true, windows: () => [targetWindow],
      activate() {
        if (failAt === 'activate') throw new Error(SECRET);
        focus.push({ kind: 'activate' });
      },
    }),
    console: { log: (message) => messages.push(message) },
  });
  let error;
  try { vm.runInContext(jxa, context, { timeout: 1000 }); } catch (caught) { error = caught; }
  return { error, executions, focus, messages };
}

test('JXA refuses a replacement matching tab after readiness instead of focusing a different identity', () => {
  const result = runJxaFocusScenario({ replaceAfterReady: true });
  assert.ok(result.error, 'replacement of the prepared tab must stop the command');
  assert.deepEqual(result.focus, [], 'neither replacement tab nor any window may be focused');
  assert.deepEqual(result.messages, [], 'a replacement tab must never produce a success message');
  assert.deepEqual(result.executions.map(({ id }) => id), [42, 42, 42]);
});

test('JXA redacts focus setters activation and repeated tab lookup failures without another execute', () => {
  const outcomes = ['activeTabIndex', 'index', 'activate', 'tabs'].map((failAt) => ({
    failAt, ...runJxaFocusScenario({ failAt }),
  }));
  for (const outcome of outcomes) {
    assert.ok(outcome.error, `${outcome.failAt} must report a safe failure`);
    assert.ok(String(outcome.error.message).length > 0 && String(outcome.error.message).length < 1000);
    assert.deepEqual(outcome.messages, [], `${outcome.failAt} must not print success`);
    assert.deepEqual(outcome.executions.map(({ id }) => id), [42, 42, 42], 'focus errors must never retry execution');
  }
  assert.ok(outcomes.every(({ error }) => !`${String(error)} ${JSON.stringify(error)}`.includes(SECRET)),
    'no raw exception from focus or repeated enumeration may escape');
  assert.equal(new Set(outcomes.map(({ error }) => error.message)).size, 1,
    'all focus failures must use one fixed safe diagnostic');
});

for (const count of [1, 80, 81, 84, 305]) {
  test(`SC17 launcher accepts fresh positive integer dialog count ${count}`, async () => {
    const f = fixture({ result: { ...READY, targetCount: count, token: SECRET } });
    assert.equal((await f.run()).targetCount, count);
    assert.equal(f.sandbox.__executions.length, 1);
    assert.equal((await f.run()).targetCount, count);
    assert.equal(f.sandbox.__executions.length, 1, 'repeated launch must not reinject');
    assert.ok(!JSON.stringify(f.sandbox.__WMS665_MAC_RUN__).includes(SECRET));
  });
}
