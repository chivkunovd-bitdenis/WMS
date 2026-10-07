const { execFileSync } = require('node:child_process');
const { stripTypeScriptTypes } = require('node:module');
const { runInNewContext } = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const source = '6da0eb63b143d71d789c25a20ee04e3c49cbf14b';
const raw = execFileSync('git', ['show', `${source}:frontend/src/utils/wms680PrintGeometry.test.ts`], { encoding: 'utf8' });
const chunk = raw.slice(raw.indexOf('function compact('), raw.indexOf('const forms ='));
const context = { expect: (actual, message) => ({
  toBeGreaterThan: expected => assert.ok(actual > expected, message),
  toContain: expected => assert.ok(actual.includes(expected), 'original check rejects missing complete name'),
}) };
runInNewContext(stripTypeScriptTypes(chunk, { mode: 'strip' }), context);
let rejected = false, reason;
try { context.assertRealPdfGeometry(fs.readFileSync(path.join(__dirname, 'cross-row.xml'), 'utf8'), 'PACKAGING-LONG-NAME-01-680'); }
catch (error) { rejected = true; reason = error.message; }
assert.ok(rejected && reason === 'original check rejects missing complete name');
fs.writeFileSync(path.join(__dirname, 'pdf-before-control.json'), JSON.stringify({ source, same_real_pdf: 'cross-row.pdf', rejected, reason }, null, 2) + '\n');
console.log('Original check rejected the same real PDF; new helper silently accepts it');
