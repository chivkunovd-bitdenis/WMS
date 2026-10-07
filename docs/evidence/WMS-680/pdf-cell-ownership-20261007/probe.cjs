// Replays exact frozen helpers against actual Chrome PDFs; no product edits.
const { spawn, execFileSync } = require('node:child_process');
const { stripTypeScriptTypes } = require('node:module');
const { runInNewContext } = require('node:vm');
const { once } = require('node:events');
const { createHash } = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const assert = require('node:assert/strict');
const sources = ['4ed0c391135c95b67879c954195034b9c43d4980', '535e8a970928e8834147553ad4c0139fcc5f10da'];
const testPath = 'frontend/src/utils/wms680PrintGeometry.test.ts';
const expected = 'PACKAGING-LONG-NAME-01-680';
const chrome = ['/usr/bin/google-chrome', '/usr/bin/chromium', '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'].find(fs.existsSync);
assert.ok(chrome, 'installed Chrome required');
const expect = (actual, message) => ({
  toBeTruthy: () => assert.ok(actual, message),
  toBe: value => assert.equal(actual, value, message),
  toBeGreaterThan: value => assert.ok(actual > value, message),
  toBeGreaterThanOrEqual: value => assert.ok(actual >= value, message),
  toBeLessThan: value => assert.ok(actual < value, message),
  toBeLessThanOrEqual: value => assert.ok(actual <= value, message),
});
const helpers = sources.map(source => {
  const raw = execFileSync('git', ['show', `${source}:${testPath}`], { encoding: 'utf8' });
  const context = { expect };
  runInNewContext(stripTypeScriptTypes(raw.slice(raw.indexOf('function compact('), raw.indexOf('const forms =')), { mode: 'strip' }), context);
  return { source, blob: execFileSync('git', ['rev-parse', `${source}:${testPath}`], { encoding: 'utf8' }).trim(), sha256: createHash('sha256').update(raw).digest('hex'), context };
});
const cases = [
  ['cross-row', '<tr><td>PACKAGING-LONG-</td><td></td><td></td><td></td></tr><tr><td>NAME-01-680</td><td></td><td></td><td></td></tr>', false],
  ['cross-column', '<tr><td>PACKAGING-LONG-</td><td>NAME-01-680</td><td></td><td></td></tr>', false],
  ['wrapped-cell', '<tr><td>PACKAGING-LONG-<br>NAME-01-680</td><td></td><td></td><td></td></tr>', true],
  ['truncated-cell', '<tr><td>PACKAGING-LONG-</td><td></td><td></td><td></td></tr>', false],
];
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
(async () => {
  const results = [];
  for (const [name, rows, mustAccept] of cases) {
    const html = `<!doctype html><meta charset="utf-8"><style>@page{size:A4 landscape;margin:10mm}table{border-collapse:collapse;width:100%;table-layout:fixed;font:14px Arial}th,td{text-align:left;padding:4px;vertical-align:top}td{height:170px}th:first-child{width:40%}</style><table><thead><tr><th>Товар</th><th>АРТИКУЛ</th><th>ЦВЕТ</th><th>РАЗМЕР</th></tr></thead><tbody>${rows}</tbody></table>`;
    const input = path.join(__dirname, `${name}.html`);
    const output = path.join(__dirname, `${name}.pdf`);
    fs.writeFileSync(input, html);
    const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'wms680-cell-proof-'));
    const child = spawn(chrome, ['--headless=new', '--disable-gpu', '--no-sandbox', '--no-pdf-header-footer', '--no-first-run', '--disable-background-networking', '--disable-component-update', '--disable-sync', `--user-data-dir=${profile}`, `--print-to-pdf=${output}`, `file://${input}`], { stdio: 'ignore' });
    const exited = once(child, 'exit');
    try {
      const deadline = Date.now() + 30000;
      while (!fs.existsSync(output) || !fs.readFileSync(output).subarray(-32).includes(Buffer.from('%%EOF'))) {
        assert.ok(Date.now() < deadline, 'Chrome PDF timeout');
        await delay(100);
      }
      const xml = execFileSync('pdftotext', ['-bbox-layout', output, '-'], { encoding: 'utf8' });
      fs.writeFileSync(path.join(__dirname, `${name}.xml`), xml);
      const checks = helpers.map(({ source, context }) => {
        let accepted = true, rejection = null;
        try { context.assertRealPdfGeometry(xml, expected); } catch (error) { accepted = false; rejection = error.message; }
        return { source, accepted, rejection, fragments: context.pdfTextFragments(context.pdfWords(xml), expected) || null };
      });
      assert.equal(checks[1].accepted, mustAccept, name);
      assert.equal(checks[0].accepted, name === 'cross-row' || mustAccept, 'old helper proof');
      results.push({ name, expected, mustAccept, html_sha256: createHash('sha256').update(html).digest('hex'), pdf_sha256: createHash('sha256').update(fs.readFileSync(output)).digest('hex'), xml_sha256: createHash('sha256').update(xml).digest('hex'), checks });
    } finally {
      if (child.exitCode === null && child.signalCode === null) {
        child.kill('SIGTERM');
        await Promise.race([exited, delay(5000)]);
        if (child.exitCode === null && child.signalCode === null) child.kill('SIGKILL');
      }
      await exited;
      fs.rmSync(profile, { recursive: true, force: true });
    }
  }
  const report = { sources: helpers.map(({ source, blob, sha256 }) => ({ source, blob, sha256 })), chrome, results };
  fs.writeFileSync(path.join(__dirname, 'results.json'), JSON.stringify(report, null, 2) + '\n');
  console.log(JSON.stringify(report, null, 2));
})().catch(error => { console.error(error); process.exitCode = 1; });
