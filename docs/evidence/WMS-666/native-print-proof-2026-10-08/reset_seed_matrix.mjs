import { createRequire } from 'node:module';
import { createHash } from 'node:crypto';
import { mkdir, writeFile } from 'node:fs/promises';

const require = createRequire(new URL('../../../../frontend/package.json', import.meta.url));
const bwip = require('bwip-js');
const { PNG } = require('pngjs');
const base = new URL('./run-28a799-final-matrix/', import.meta.url).pathname;
await mkdir(base, { recursive: true });

const texts = ['*WMS666-MATRIX-A', '*WMS666-MATRIX-B'];
const stickers = [];
const publicStickerInfo = [];
for (let i = 0; i < texts.length; i += 1) {
  const image = PNG.sync.read(await bwip.toBuffer({ bcid: 'qrcode', text: texts[i], scale: 3 }));
  for (let p = 0; p < image.width * image.height; p += 1) {
    const alpha = image.data[p * 4 + 3] / 255;
    for (let channel = 0; channel < 3; channel += 1) {
      image.data[p * 4 + channel] = Math.round(image.data[p * 4 + channel] * alpha + 255 * (1 - alpha));
    }
    image.data[p * 4 + 3] = 255;
  }
  const bytes = PNG.sync.write(image);
  await writeFile(`${base}seed-sticker-${i + 1}.png`, bytes);
  stickers.push(bytes.toString('base64'));
  publicStickerInfo.push({ text: texts[i], bytes: bytes.length, sha256: createHash('sha256').update(bytes).digest('hex') });
}

const idle = await fetch('http://127.0.0.1:16692/idle').then((response) => response.json());
if (idle.active !== 0) throw new Error(`API fixture is busy: ${idle.active} active requests`);
const response = await fetch('http://127.0.0.1:16692/seed', {
  method: 'POST', headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ codes: 4, stickers }),
});
if (!response.ok) throw new Error(`synthetic seed failed: ${response.status}`);
const seed = await response.json();
const safe = {
  supply_id: seed.supply_id,
  order_ids: seed.order_ids,
  supply_ids: seed.supply_ids,
  task_id: seed.task_id,
  line_id: seed.line_id,
  barcode: seed.barcode,
  synthetic_order_stickers: publicStickerInfo,
  credentials_saved: false,
};
await writeFile(`${base}seed-public.json`, `${JSON.stringify(safe, null, 2)}\n`);
const db = await fetch('http://127.0.0.1:16692/snapshot').then((r) => r.json());
await writeFile(`${base}db-before.json`, `${JSON.stringify(db, null, 2)}\n`);
console.log(JSON.stringify(safe, null, 2));
