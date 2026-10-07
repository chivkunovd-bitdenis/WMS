'use strict';
// Preserve the 106 WMS-665 checks as a pinned historical record. This is NOT
// acceptance of R27, and none of the old product code enters the release tree.
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { execFileSync, spawnSync } = require('node:child_process');
const SHA = 'c42f4d318c094253ce82ba6947c80a342cda57e0';
const files = [
  'scripts/ops/avpack-kiz-helper.js', 'scripts/ops/avpack-macos-launcher.js',
  'scripts/ops/avpack-sold-kiz-filter.js', 'scripts/ops/avpack-sold-kiz.command',
  'scripts/ops/build-avpack-macos-command.cjs',
  'scripts/ops/tests/avpack-kiz-helper.test.cjs',
  'scripts/ops/tests/avpack-macos-launcher.test.cjs',
  'scripts/ops/tests/avpack-sold-kiz-filter.test.cjs',
  'docs/reviews/WMS-665-AVPACK-RUNBOOK.md',
];
const repository = path.resolve(__dirname, '../../..');
const temporary = fs.mkdtempSync(path.join(os.tmpdir(), 'wms517-mac-historical-'));
try {
  for (const file of files) {
    const destination = path.join(temporary, file);
    fs.mkdirSync(path.dirname(destination), { recursive: true });
    fs.writeFileSync(destination, execFileSync('git', ['show', `${SHA}:${file}`], { cwd: repository }));
    if (file.endsWith('.command')) fs.chmodSync(destination, 0o755);
  }
  const r27 = process.argv.includes('--r27');
  const tests = r27
    ? ['wms517-sold-kiz-filter.test.cjs', 'wms517-mac-launcher.test.cjs', 'wms517-mac-dom.test.cjs'].map(f => path.join(__dirname, f))
    : files.filter(f => f.endsWith('.test.cjs')).map(f => path.join(temporary, f));
  const result = spawnSync(process.execPath, ['--test', '--test-reporter=tap', ...tests],
    { encoding: 'utf8', timeout: 30000,
      env: r27 ? { ...process.env, WMS517_MAC_SOURCE_DIR: path.join(temporary, 'scripts/ops') } : process.env });
  process.stdout.write(result.stdout ?? ''); process.stderr.write(result.stderr ?? '');
  if (result.error) throw result.error;
  process.exitCode = result.status ?? 1;
} finally { fs.rmSync(temporary, { recursive: true, force: true }); }
