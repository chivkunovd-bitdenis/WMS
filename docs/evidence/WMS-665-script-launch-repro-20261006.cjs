'use strict';

// Investigation only. No real browser, network, certificate, tenant session,
// marking code, database or withdrawal operation is accessed.
const assert = require('node:assert/strict');
const { execFileSync } = require('node:child_process');
const vm = require('node:vm');

const OLD = '70c505acf6f7ce8202b94fcb16cc05545324eb3f';
const FIX = 'c42f4d318c094253ce82ba6947c80a342cda57e0';
const PAGE = 'https://wms.sellerfocus.pro/seller/honest-sign/withdrawals';
const READY = {
  status: 'certificate_dialog_open', targetCount: 80,
  noSend: true, signed: false, sent: false,
};
const gitSource = (sha, name) => execFileSync(
  'git', ['show', `${sha}:scripts/ops/${name}`], { encoding: 'utf8' },
);
function load(source) {
  const context = vm.createContext({ module: { exports: {} } });
  vm.runInContext(source, context);
  return context.module.exports;
}
function browser(urls, calls) {
  return {
    running: () => true,
    tabs: () => urls.map((url, id) => ({ id, url })),
    evaluate: () => { calls.evaluate += 1; return JSON.stringify(READY); },
  };
}

async function main() {
  for (const [name, urls] of [
    ['one correct production tab', [PAGE]],
    ['no tabs', []],
    ['two old-domain tabs', [PAGE.replace('wms.', ''), PAGE.replace('wms.', '')]],
  ]) {
    const calls = { evaluate: 0 };
    let error;
    try {
      load(gitSource(OLD, 'avpack-macos-launcher.js')).launch({
        chrome: browser(urls, calls), helperSource: 'synthetic helper', wait() {},
      });
    } catch (caught) { error = caught; }
    assert.equal(error?.name, 'MacLauncherError');
    assert.match(error.message, /Откройте ровно одну вкладку https:\/\/sellerfocus\.pro/);
    assert.equal(calls.evaluate, 0);
    console.log(JSON.stringify({ version: OLD, fixture: name, error: error.message, ...calls }));
  }
  const calls = { evaluate: 0 };
  const result = load(gitSource(FIX, 'avpack-macos-launcher.js')).launch({
    chrome: browser([PAGE], calls), helperSource: 'synthetic helper', wait() {},
  });
  assert.equal(result.status, READY.status);
  assert.equal(calls.evaluate, 1);
  console.log(JSON.stringify({ version: FIX, fixture: 'one correct production tab', ...calls, result }));

  // Also exercise the system JavaScript for Automation interpreter with stubs.
  // Application('Google Chrome') is never used; no Apple Events are sent.
  if (process.platform === 'darwin') {
    for (const sha of [OLD, FIX]) {
      const code = `const module = { exports: {} };\n${gitSource(sha, 'avpack-macos-launcher.js')}\n` +
        `module.exports.launch({ chrome: {
          running: () => true,
          tabs: () => [{id: 1, url: ${JSON.stringify(PAGE)}}],
          evaluate: () => ${JSON.stringify(JSON.stringify(READY))}
        }, helperSource: 'synthetic helper', wait: () => {} });`;
      try {
        const output = execFileSync('/usr/bin/osascript', ['-l', 'JavaScript'], {
          input: code, encoding: 'utf8', stdio: ['pipe', 'pipe', 'pipe'],
        });
        assert.equal(sha, FIX);
        console.log(JSON.stringify({ interpreter: 'system JXA with stubs', version: sha, exit: 0, output: output.trim() }));
      } catch (error) {
        assert.equal(sha, OLD);
        assert.match(String(error.stderr), /MacLauncherError/);
        assert.match(String(error.stderr), /\(-2700\)/);
        console.log(JSON.stringify({ interpreter: 'system JXA with stubs', version: sha, exit: error.status, error: String(error.stderr).trim() }));
      }
    }
  }

  const filter = load(gitSource(FIX, 'avpack-sold-kiz-filter.js'));
  const reads = [];
  const rows = Array.from(filter.TARGET_ROW_IDS, (row_id) => ({
    row_id, status: 'not_withdrawn', operation_id: null, cis: 'SYNTHETIC-CIS',
  }));
  const root = {
    location: new URL(PAGE), Response,
    localStorage: { getItem: () => 'synthetic-fixture-token' },
    fetch: async (url, init) => {
      assert.equal(init.method, 'GET');
      reads.push(new URL(url).pathname);
      return { ok: true, json: async () => url.includes('/api/auth/me') ? {
        tenant_id: 'd6e1ad21-8afa-4acf-8d0b-907b9f2adcfe',
        seller_id: '0b8da5d8-f43a-42f5-a2ec-43173ea844bd',
        active_seller_id: '0b8da5d8-f43a-42f5-a2ec-43173ea844bd',
        role: 'fulfillment_seller', withdrawal_enabled: true,
      } : { rows, total: rows.length } };
    },
  };
  const helper = filter.createHelper({
    root,
    ui: {
      inspectSelection: async () => ({ selectedCount: 0 }),
      refreshSelectAllAndOpen: async (count, verifySession) => {
        verifySession();
        return { selectedCount: count, dialogOpen: true };
      },
    },
  });
  const dry = await helper.run({ mode: 'dry-run' });
  const prepared = await helper.run({ mode: 'execute' });
  assert.equal(dry.status, 'ready');
  assert.equal(prepared.status, READY.status);
  assert.equal(prepared.signed, false);
  assert.equal(prepared.sent, false);
  console.log(JSON.stringify({ fixture: 'synthetic registry and UI only', reads, dry, prepared }));
  console.log('PASS: original failure reproduced; published fix clears URL stage; no live effects.');
}
main().catch((error) => { console.error(error); process.exitCode = 1; });
