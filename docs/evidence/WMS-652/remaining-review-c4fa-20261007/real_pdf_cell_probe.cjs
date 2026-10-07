// One real local PDF negative fixture. No product edits; only this owned process.
const { spawn, execFileSync } = require('node:child_process');
const { stripTypeScriptTypes } = require('node:module');
const { runInNewContext } = require('node:vm');
const { once } = require('node:events');
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const assert = require('node:assert/strict');
const source = 'c4faeb3a58c42e2d2e04bff790230532e8970b90';
const raw = execFileSync('git', ['show', `${source}:frontend/src/utils/wms680PrintGeometry.test.ts`], { encoding: 'utf8' });
const chunk = raw.slice(raw.indexOf('function compact('), raw.indexOf('const forms ='));
const expect = (actual, message) => ({
  toBeTruthy: () => assert.ok(actual, message),
  toBe: v => assert.equal(actual, v, message),
  toBeGreaterThan: v => assert.ok(actual > v, message),
  toBeGreaterThanOrEqual: v => assert.ok(actual >= v, message),
  toBeLessThan: v => assert.ok(actual < v, message),
  toBeLessThanOrEqual: v => assert.ok(actual <= v, message),
});
const context = { expect };
runInNewContext(stripTypeScriptTypes(chunk, { mode: 'strip' }), context);
const chrome = ['/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', '/usr/bin/google-chrome', '/usr/bin/chromium'].find(fs.existsSync);
assert.ok(chrome, 'existing Chrome required');
const html = '<!doctype html><meta charset="utf-8"><style>@page{size:A4 landscape;margin:10mm}table{border-collapse:collapse;width:100%;table-layout:fixed;font:14px Arial}th,td{text-align:left;padding:4px;vertical-align:top}td{height:170px}th:first-child{width:40%}</style><table><thead><tr><th>Товар</th><th>АРТИКУЛ</th><th>ЦВЕТ</th><th>РАЗМЕР</th></tr></thead><tbody><tr><td>PACKAGING-LONG-</td><td></td><td></td><td></td></tr><tr><td>NAME-01-680</td><td></td><td></td><td></td></tr></tbody></table>';
const input = path.join(__dirname, 'cross-row.html');
const pdf = path.join(__dirname, 'cross-row.pdf');
fs.writeFileSync(input, html);
const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'wms652-review-pdf-'));
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
(async () => {
  const child = spawn(chrome, ['--headless=new', '--disable-gpu', '--no-sandbox', '--no-pdf-header-footer', '--no-first-run', '--disable-background-networking', '--disable-component-update', '--disable-sync', `--user-data-dir=${profile}`, `--print-to-pdf=${pdf}`, `file://${input}`], { stdio: 'ignore' });
  const exited = once(child, 'exit');
  try {
    const deadline = Date.now() + 30000;
    while (!fs.existsSync(pdf) || !fs.readFileSync(pdf).subarray(-32).includes(Buffer.from('%%EOF'))) {
      assert.ok(Date.now() < deadline, 'own Chrome did not write complete PDF');
      await delay(100);
    }
    const xml = execFileSync('pdftotext', ['-bbox-layout', pdf, '-'], { encoding: 'utf8' });
    fs.writeFileSync(path.join(__dirname, 'cross-row.xml'), xml);
    const expected = 'PACKAGING-LONG-NAME-01-680';
    context.assertRealPdfGeometry(xml, expected);
    const fragments = context.pdfTextFragments(context.pdfWords(xml), expected);
    assert.equal(fragments.length, 2);
    assert.ok(fragments[1].top - fragments[0].bottom > 100, 'actual distinct rows required');
    fs.writeFileSync(path.join(__dirname, 'real-pdf-cell-probe.json'), JSON.stringify({ source, actual_pdf: 'cross-row.pdf', expected, fragments, accepted_by_full_geometry_check: true, row_gap_points: fragments[1].top - fragments[0].bottom, verdict: 'FAIL: no table cell contains the full name' }, null, 2) + '\n');
    console.log('FAIL reproduced using real Chrome PDF: two separate table rows accepted as one complete name');
  } finally {
    if (child.exitCode === null && child.signalCode === null) {
      child.kill('SIGTERM');
      await Promise.race([exited, delay(5000)]);
      if (child.exitCode === null && child.signalCode === null) child.kill('SIGKILL');
    }
    await exited;
    fs.rmSync(profile, { recursive: true, force: true });
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
