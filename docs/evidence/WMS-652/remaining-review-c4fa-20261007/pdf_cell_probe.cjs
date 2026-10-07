// Execute exact immutable helpers; no changed implementation or dependency install.
const { execFileSync } = require('node:child_process');
const { stripTypeScriptTypes } = require('node:module');
const { runInNewContext } = require('node:vm');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const source = 'c4faeb3a58c42e2d2e04bff790230532e8970b90';
const raw = execFileSync('git', ['show', `${source}:frontend/src/utils/wms680PrintGeometry.test.ts`], { encoding: 'utf8' });
const chunk = raw.slice(raw.indexOf('function compact('), raw.indexOf('const forms ='));
function expect(actual, message) {
  return {
    toBeTruthy: () => assert.ok(actual, message),
    toBe: expected => assert.equal(actual, expected, message),
    toBeGreaterThan: expected => assert.ok(actual > expected, message),
    toBeGreaterThanOrEqual: expected => assert.ok(actual >= expected, message),
    toBeLessThan: expected => assert.ok(actual < expected, message),
    toBeLessThanOrEqual: expected => assert.ok(actual <= expected, message),
  };
}
const context = { expect };
runInNewContext(stripTypeScriptTypes(chunk, { mode: 'strip' }), context);
const word = (text, left, top) => `<word xMin="${left}" yMin="${top}" xMax="${left + 90}" yMax="${top + 10}">${text}</word>`;
const expected = 'PACKAGING-LONG-NAME-01-680';
const cases = [
  { name: 'complete wrapped text, adjacent lines', fragments: [word('PACKAGING-LONG-', 10, 50), word('NAME-01-680', 10, 62)], mustReject: false },
  { name: 'truncated name', fragments: [word('PACKAGING-LONG-', 10, 50)], mustReject: true },
  { name: 'truncated row A plus suffix in distinct row B', fragments: [word('PACKAGING-LONG-', 10, 50), word('NAME-01-680', 10, 400)], mustReject: true },
  { name: 'suffix in another column', fragments: [word('PACKAGING-LONG-', 10, 50), word('NAME-01-680', 120, 62)], mustReject: true },
];
const results = cases.map(c => {
  const xml = `<page width="600" height="800">${c.fragments.join('')}${word('АРТИКУЛ', 350, 20)}${word('ЦВЕТ', 450, 20)}${word('РАЗМЕР', 500, 20)}</page>`;
  let accepted = true, rejection = null;
  try { context.assertRealPdfGeometry(xml, expected); }
  catch (error) { accepted = false; rejection = error.message; }
  return { source, scenario: c.name, mustReject: c.mustReject, accepted, rejection, xml };
});
assert.equal(results[0].accepted, true);
assert.equal(results[1].accepted, false);
assert.equal(results[2].accepted, true); // The defect: two different rows accepted as one cell.
assert.equal(results[3].accepted, false);
fs.writeFileSync(path.join(__dirname, 'pdf-cell-probe.json'), JSON.stringify(results, null, 2) + '\n');
console.log('FAIL reproduced: complete-name check accepts a truncated row joined to a different row');
