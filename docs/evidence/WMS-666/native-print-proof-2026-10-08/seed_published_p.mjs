import { createRequire } from 'node:module'
import { mkdir, writeFile } from 'node:fs/promises'
import { createHash } from 'node:crypto'
import { resolve } from 'node:path'

const repo = resolve(process.env.WMS666_RUNTIME_CHECKOUT || '/Users/deniscivkunov/Projects/WMS/.worktrees/wms666-native-final-runtime')
const require = createRequire(`${repo}/frontend/package.json`)
const bwip = require('bwip-js')
const { PNG } = require('pngjs')
const { RGBLuminanceSource, BinaryBitmap, HybridBinarizer, QRCodeReader } = require('@zxing/library')
const out = resolve('docs/evidence/WMS-666/native-print-proof-2026-10-08', process.env.WMS666_EVIDENCE_RUN ?? process.argv[2] ?? 'run-final')
await mkdir(`${out}/fixtures`, { recursive: true })
// These exact synthetic QR values are also persisted as FbsOrder.sticker_code.
const texts = ['*WMS666-FINAL-ORDER-A', '*WMS666-FINAL-ORDER-B']
const pngs = []
for (const [index, text] of texts.entries()) {
  const image = PNG.sync.read(await bwip.toBuffer({ bcid: 'qrcode', text, scale: 3 }))
  for (let i = 0; i < image.width * image.height; i += 1) {
    const alpha = image.data[i * 4 + 3] / 255
    for (let channel = 0; channel < 3; channel += 1) image.data[i * 4 + channel] = Math.round(image.data[i * 4 + channel] * alpha + 255 * (1 - alpha))
    image.data[i * 4 + 3] = 255
  }
  const bytes = PNG.sync.write(image)
  const rgba = PNG.sync.read(bytes)
  const luminance = new Uint8ClampedArray(rgba.width * rgba.height)
  for (let i = 0; i < luminance.length; i += 1) {
    const alpha = rgba.data[i * 4 + 3] / 255
    const gray = (rgba.data[i * 4] + rgba.data[i * 4 + 1] + rgba.data[i * 4 + 2]) / 3
    luminance[i] = Math.round(gray * alpha + 255 * (1 - alpha))
  }
  const decoded = new QRCodeReader().decode(new BinaryBitmap(new HybridBinarizer(new RGBLuminanceSource(luminance, rgba.width, rgba.height)))).getText()
  if (decoded !== text) throw new Error(`Synthetic order sticker QR mismatch: expected ${text}, got ${decoded}`)
  const file = `fixtures/order-sticker-${index + 1}.png`
  await writeFile(`${out}/${file}`, bytes)
  pngs.push({ text, file, bytes: bytes.length, sha256: createHash('sha256').update(bytes).digest('hex'), base64: bytes.toString('base64') })
}
const response = await fetch('http://127.0.0.1:16692/seed', {
  method: 'POST', headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ codes: 4, stickers: pngs.map(x => x.base64), sticker_codes: texts }),
})
if (!response.ok) throw new Error(`seed failed with HTTP ${response.status}: ${await response.text()}`)
const value = await response.json()
const publicSeed = {
  product_sha: process.env.WMS666_PRODUCT_SHA ?? 'UNSET',
  supply_id: value.supply_id, order_ids: value.order_ids, supply_ids: value.supply_ids,
  task_id: value.task_id, line_id: value.line_id, barcode: value.barcode,
  sticker_codes: value.sticker_codes,
  order_sticker_barcodes: value.order_sticker_barcodes,
  synthetic_order_stickers: pngs.map(({ text, file, bytes, sha256 }) => ({ text, file, bytes, sha256 })),
  auth_headers_persisted: false,
}
await writeFile(`${out}/seed-public.json`, `${JSON.stringify(publicSeed, null, 2)}\n`)
console.log(JSON.stringify(publicSeed, null, 2))
