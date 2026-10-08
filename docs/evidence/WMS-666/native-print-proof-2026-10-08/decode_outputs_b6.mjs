import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import { createHash } from 'node:crypto'
import { readFile, writeFile } from 'node:fs/promises'
import { join, resolve } from 'node:path'

const proofRoot = resolve('docs/evidence/WMS-666/native-print-proof-2026-10-08/run-b6d23148')
const require = createRequire('/Users/deniscivkunov/Projects/WMS/.worktrees/wms666-native-final-runtime/frontend/package.json')
const { PNG } = require('pngjs')
const { RGBLuminanceSource, BinaryBitmap, HybridBinarizer, QRCodeReader, DataMatrixReader } = require('@zxing/library')

function decode(Reader, png, compositeWhite, heightRatio = 1) {
  const width = png.width
  const height = Math.floor(png.height * heightRatio)
  const gray = new Uint8ClampedArray(width * height)
  for (let i = 0; i < gray.length; i += 1) {
    const alpha = png.data[i * 4 + 3] / 255
    const channel = (png.data[i * 4] + png.data[i * 4 + 1] + png.data[i * 4 + 2]) / 3
    gray[i] = Math.round(compositeWhite ? channel * alpha + 255 * (1 - alpha) : channel)
  }
  try {
    const bitmap = new BinaryBitmap(new HybridBinarizer(new RGBLuminanceSource(gray, width, height)))
    return new Reader().decode(bitmap).getText()
  } catch {
    return null
  }
}

const receipts = (await readFile(join(proofRoot, 'native/sink-receipts.jsonl'), 'utf8')).trim().split('\n').map(JSON.parse)
const requests = (await readFile(join(proofRoot, 'native/requests.jsonl'), 'utf8')).trim().split('\n').map(JSON.parse)
const expected = JSON.parse(await readFile(join(proofRoot, 'seed-public.json'), 'utf8'))
const scanInputs = JSON.parse(await readFile(join(proofRoot, 'order-sticker-scan/scan-inputs.json'), 'utf8'))
const decodedInputs = []
for (const request of requests) {
  const bytes = Buffer.from(request.body.imageDataUrl.split(',')[1], 'base64')
  const png = PNG.sync.read(bytes)
  decodedInputs.push({
    job_key: request.body.idempotencyKey,
    sha256: createHash('sha256').update(bytes).digest('hex'),
    bytes: bytes.length,
    qr: decode(QRCodeReader, png, true),
    cis: decode(DataMatrixReader, png, false, 0.44),
    explicit_copies_field: request.body.copies ?? request.body.copyCount ?? null,
    width_mm: request.body.widthMm,
    height_mm: request.body.heightMm,
  })
}
const decodedReceipts = []
for (const receipt of receipts) {
  const bytes = await readFile(join(proofRoot, 'native', receipt.png))
  const png = PNG.sync.read(bytes)
  const input = decodedInputs.find(row => row.sha256 === receipt.sha256)
  decodedReceipts.push({
    ...receipt,
    width: png.width,
    height: png.height,
    qr: decode(QRCodeReader, png, true),
    cis: decode(DataMatrixReader, png, false, 0.44),
    input,
  })
}
assert.equal(decodedReceipts.length, 1)
assert.equal(decodedReceipts[0].qr, expected.sticker_codes[0])
assert.equal(decodedReceipts[0].qr, scanInputs.persisted_sticker_code)
assert.equal(decodedReceipts[0].input?.qr, expected.sticker_codes[0])
assert.equal(decodedReceipts[0].input?.job_key, decodedReceipts[0].job_key)
assert.equal(decodedInputs.length, 1)
assert.equal(scanInputs.order_sticker_barcode, expected.sticker_codes[0])

const report = {
  product_sha: expected.product_sha,
  runtime_checkout_sha: expected.product_sha,
  physical_paper: 'NOT_TESTED',
  case: 'React order-sticker scan, manual KIZ bind, QR-only native print through WMS Print Direct Handler',
  expected_sticker_qr: expected.sticker_codes[0],
  actual_print_http_requests: requests.length,
  actual_handler_receipts: receipts.length,
  native_receipts: decodedReceipts,
  decoded_inputs: decodedInputs,
}
await writeFile(join(proofRoot, 'order-sticker-scan/decoded-outputs.json'), JSON.stringify(report, null, 2))
process.stdout.write(JSON.stringify({
  receipt_count: decodedReceipts.length,
  receipt: decodedReceipts[0],
  expected_sticker_qr: expected.sticker_codes[0],
}, null, 2) + '\n')
