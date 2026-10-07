'use strict';

// WMS-517 R28: delivery contract. No browser, certificate or external submit.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const crypto = require('node:crypto');
const { spawnSync } = require('node:child_process');
const directory = path.join(__dirname, '..');
const sourceSha = '7a2fa31d83e06b2724edbcca1aaead0914ad5e56';
const digest = '6e60684bbe8318178f0c97d34507f9a93f811c74ed3e2631ae249ac02a8505c9';
const artifact = fs.readFileSync(path.join(directory, 'avpack-sold-kiz.command'));
const command = () => fs.readFileSync(path.join(directory, 'avpack-sold-kiz-terminal.txt'), 'utf8').trimEnd();

test('SC19 one Terminal line pins published exact source and SHA256 with HTTPS-only fail-closed download', () => {
  const line = command();
  assert.equal(line.split('\n').length, 1);
  assert.ok(line.includes(`https://raw.githubusercontent.com/chivkunovd-bitdenis/WMS/${sourceSha}/scripts/ops/avpack-sold-kiz.command`));
  assert.ok(line.includes(digest));
  assert.equal(crypto.createHash('sha256').update(artifact).digest('hex'), digest);
  assert.match(line, /set -eu/);
  assert.match(line, /\/usr\/bin\/curl -fsSL --proto '=https' --proto-redir '=https'/);
  assert.match(line, /--connect-timeout 10 --max-time 60/);
  assert.match(line, /\/usr\/bin\/shasum -a 256 -c -/);
  assert.match(line, /\/bin\/zsh "\$f"/);
  assert.doesNotMatch(line, /\b(?:sudo|security|defaults|tccutil|node|npm|python|brew)\b|--retry|\|\s*(?:bash|zsh)/);
});

function runLoader(mode, launchStatus = 0) {
  const temporary = fs.mkdtempSync(path.join(os.tmpdir(), 'wms517-loader-test-'));
  const quoted = (value) => `'${value.replace(/'/g, "'\\''")}'`;
  try {
    const payload = path.join(temporary, 'payload');
    const original = path.join(temporary, 'original.command');
    const calls = path.join(temporary, 'calls');
    fs.writeFileSync(original, artifact);
    const stub = (name, source) => {
      const filename = path.join(temporary, name);
      fs.writeFileSync(filename, `#!/bin/zsh\nset -eu\n${source}\n`, { mode: 0o755 });
      return quoted(filename);
    };
    const mktemp = stub('mktemp', `: > ${quoted(payload)}\nprint -r -- ${quoted(payload)}`);
    const curl = stub('curl', `print curl >> ${quoted(calls)}\n[[ "$#" = 12 && "\${11}" = '-o' && "\${12}" = ${quoted(payload)} ]]\n${mode === 'download-failure' ? `printf partial > ${quoted(payload)}\nexit 22` : `/bin/cp ${quoted(original)} ${quoted(payload)}${mode === 'tampered' ? `\nprintf tampered >> ${quoted(payload)}` : ''}`}`);
    const launch = stub('launch', `[[ "$#" = 1 && "$1" = ${quoted(payload)} ]]\n/usr/bin/cmp "$1" ${quoted(original)}\nprint launch >> ${quoted(calls)}\nexit ${launchStatus}`);
    const line = command()
      .replace('/usr/bin/mktemp', mktemp)
      .replace('/usr/bin/curl', curl)
      .replace('/bin/zsh "$f"', `${launch} "$f"`);
    const result = spawnSync('/bin/zsh', ['-c', line], { encoding: 'utf8' });
    return {
      result,
      calls: fs.existsSync(calls) ? fs.readFileSync(calls, 'utf8').trim().split('\n') : [],
      cleaned: !fs.existsSync(payload),
    };
  } finally {
    fs.rmSync(temporary, { recursive: true, force: true });
  }
}

test('SC19 verified downloaded artifact executes once and temporary download is removed', () => {
  const outcome = runLoader('valid');
  assert.equal(outcome.result.status, 0, outcome.result.stderr);
  assert.deepEqual(outcome.calls, ['curl', 'launch']);
  assert.equal(outcome.cleaned, true);
});
for (const mode of ['download-failure', 'tampered']) {
  test(`SC19 ${mode} never executes or retries and removes temporary download`, () => {
    const outcome = runLoader(mode);
    assert.notEqual(outcome.result.status, 0);
    assert.deepEqual(outcome.calls, ['curl']);
    assert.equal(outcome.cleaned, true);
  });
}
test('SC19 native launcher failure remains failure and still removes temporary download', () => {
  const outcome = runLoader('valid', 42);
  assert.equal(outcome.result.status, 42, outcome.result.stderr);
  assert.deepEqual(outcome.calls, ['curl', 'launch']);
  assert.equal(outcome.cleaned, true);
});
