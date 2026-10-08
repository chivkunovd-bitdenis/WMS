import assert from 'node:assert/strict'
import { createHash } from 'node:crypto'
import { createRequire } from 'node:module'
import { readFile, writeFile } from 'node:fs/promises'
import { resolve } from 'node:path'

const runDir = resolve(process.argv[2])
const nativeOut = resolve(process.argv[3])
const runtime = resolve(process.env.WMS666_RUNTIME_CHECKOUT || '/Users/deniscivkunov/Projects/WMS/.worktrees/wms666-native-final-runtime')
const require = createRequire(`${runtime}/frontend/package.json`)
const { PNG } = require('pngjs')
const { RGBLuminanceSource, BinaryBitmap, HybridBinarizer, QRCodeReader } = require('@zxing/library')
const sha = bytes => createHash('sha256').update(bytes).digest('hex')
const decodeQr = bytes => {
  const png = PNG.sync.read(bytes)
  const lum = new Uint8ClampedArray(png.width * png.height)
  for (let i = 0; i < lum.length; i++) {
    const alpha = png.data[i * 4 + 3] / 255
    const gray = (png.data[i * 4] + png.data[i * 4 + 1] + png.data[i * 4 + 2]) / 3
    lum[i] = Math.round(gray * alpha + 255 * (1 - alpha))
  }
  return new QRCodeReader().decode(new BinaryBitmap(new HybridBinarizer(new RGBLuminanceSource(lum, png.width, png.height)))).getText()
}
const seed = JSON.parse(await readFile(`${runDir}/seed-public.json`, 'utf8'))
const api = JSON.parse(await readFile(`${runDir}/native/api-events.json`, 'utf8'))
const requests = (await readFile(`${nativeOut}/requests.jsonl`, 'utf8')).trim().split('\n').filter(Boolean).map(JSON.parse)
const receipts = (await readFile(`${nativeOut}/sink-receipts.jsonl`, 'utf8')).trim().split('\n').filter(Boolean).map(JSON.parse)
const scanEvent = api.find(row => row.method === 'POST' && row.status === 200 && row.path.includes('/scan-auto-print') && !row.path.endsWith('/cancel') && !row.path.includes('/print-claim') && !row.path.includes('/print-started'))
assert(scanEvent?.response?.scan_id, 'successful scan claim identifies its server scan ID')
const scanId = scanEvent.response.scan_id
const request = requests.find(row => row.path === '/print' && row.body.idempotencyKey === scanId)
assert(request, 'native handler captured the claimed scan idempotency key')
const receipt = receipts.find(row => row.job_key === scanId)
assert(receipt, 'emulated submit receipt joins to the same request key')
const requestPng = Buffer.from(request.body.imageDataUrl.split(',')[1], 'base64')
const sinkPng = await readFile(`${nativeOut}/${receipt.png}`)
const sourcePng = await readFile(`${runDir}/fixtures/order-sticker-1.png`)
const decodedSource = decodeQr(sourcePng)
const decodedRequest = decodeQr(requestPng)
const decodedSink = decodeQr(sinkPng)
assert.equal(decodedSource, seed.sticker_codes[0])
assert.equal(seed.order_sticker_barcodes[0], decodedSource)
assert.equal(decodedRequest, decodedSource)
assert.equal(decodedSink, decodedSource)
assert.equal(sha(sourcePng), sha(requestPng))
assert.equal(sha(requestPng), sha(sinkPng))
const output = {
  product_sha: seed.product_sha,
  runtime_checkout_sha: JSON.parse(await readFile(`${nativeOut}/source-identity.json`, 'utf8')).runtime_checkout_sha,
  provenance: 'Seed helper creates QR from persisted sticker barcode text and independently decodes the source PNG before calling the real API seed route; API stores that barcode as sticker_barcode; React fetches the saved asset; actual Handler receives imageDataUrl; injected submit sink stores the bytes and its receipt.',
  target: { supply_id: seed.supply_id, order_id: seed.order_ids[0], sticker_code: seed.sticker_codes[0], sticker_barcode: seed.order_sticker_barcodes[0], scan_id: scanId },
  source_fixture: { path: 'fixtures/order-sticker-1.png', bytes: sourcePng.length, sha256: sha(sourcePng), decoded: decodedSource },
  native_request: { path: request.path, received_at_utc: request.received_at_utc, origin: request.origin, idempotency_key: request.body.idempotencyKey, png_bytes: requestPng.length, png_sha256: sha(requestPng), decoded: decodedRequest },
  submit_receipt: { accepted_at_utc: receipt.accepted_at_utc, receipt: receipt.receipt, job_key: receipt.job_key, png: receipt.png, png_bytes: sinkPng.length, png_sha256: sha(sinkPng), decoded: decodedSink },
  assertions: { same_qr_value: true, byte_identical_source_request_sink: true, same_scan_key_request_receipt: true },
}
await writeFile(`${runDir}/native/native-output-join.json`, `${JSON.stringify(output, null, 2)}\n`)
console.log(JSON.stringify(output, null, 2))
