import { readdir, readFile, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { createRequire } from 'node:module';
const require = createRequire(resolve('frontend/package.json'));
const { PNG } = require('pngjs');
const dir = process.env.WMS672_EVIDENCE_DIR;
const summary = [];
for (const fixture of await readdir(dir)) {
  if (!fixture.startsWith('fixture-')) continue;
  for (const file of await readdir(resolve(dir, fixture))) {
    if (!file.endsWith('.json') || !file.startsWith('page-')) continue;
    const data = JSON.parse(await readFile(resolve(dir, fixture, file), 'utf8'));
    const errors = data.events.filter(event => ['native-reject', 'screen-catch', 'promise-catch'].includes(event.kind));
    for (const [index, event] of errors.entries()) {
      if (!event.src?.startsWith('data:image/png;base64,')) continue;
      const bytes = Buffer.from(event.src.split(',')[1], 'base64');
      await writeFile(resolve(dir, fixture, `rejected-${index}.png`), bytes);
      try { const png = PNG.sync.read(bytes, { checkCRC: true }); event.png = { valid: true, width: png.width, height: png.height, bytes: bytes.length }; }
      catch (error) { event.png = { valid: false, error: error.message, bytes: bytes.length }; }
    }
    summary.push({ fixture, file, started: data.started, decoded: data.decoded, alert: data.alert, transfers: data.transfers, iframes: data.iframes, errors: errors.map(({ src, outerHTML, stack, ...event }) => event) });
  }
}
await writeFile(resolve(dir, 'summary.json'), JSON.stringify(summary, null, 2));
console.log(JSON.stringify(summary, null, 2));
