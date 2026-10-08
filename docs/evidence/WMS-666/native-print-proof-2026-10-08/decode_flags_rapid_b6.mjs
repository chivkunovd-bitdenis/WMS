import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import { createHash } from 'node:crypto'
import { readFile, writeFile } from 'node:fs/promises'
import { join, resolve } from 'node:path'

const evidenceRoot = resolve('docs/evidence/WMS-666/native-print-proof-2026-10-08/run-b6d23148/flags-rapid')
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
    return new Reader().decode(new BinaryBitmap(new HybridBinarizer(new RGBLuminanceSource(gray, width, height)))).getText()
  } catch {
    return null
  }
}

const seed = JSON.parse(await readFile(join(evidenceRoot, 'seed-public.json'), 'utf8'))
const evidence = JSON.parse(await readFile(join(evidenceRoot, 'flags-rapid-evidence.json'), 'utf8'))
const receipts = (await readFile(join(evidenceRoot, 'native/sink-receipts.jsonl'), 'utf8')).trim().split('\n').map(JSON.parse)
const requests = (await readFile(join(evidenceRoot, 'native/requests.jsonl'), 'utf8')).trim().split('\n').map(JSON.parse)
const inputs = []
for (const request of requests) {
  const bytes = Buffer.from(request.body.imageDataUrl.split(',')[1], 'base64')
  const png = PNG.sync.read(bytes)
  inputs.push({
    job_key: request.body.idempotencyKey,
    sha256: createHash('sha256').update(bytes).digest('hex'),
    qr: decode(QRCodeReader, png, true),
    cis: decode(DataMatrixReader, png, false, 0.44),
    width_mm: request.body.widthMm,
    height_mm: request.body.heightMm,
  })
}
const outputs = []
for (const receipt of receipts) {
  const bytes = await readFile(join(evidenceRoot, 'native', receipt.png))
  const png = PNG.sync.read(bytes)
  const input = inputs.find(row => row.sha256 === receipt.sha256)
  outputs.push({
    ...receipt,
    qr: decode(QRCodeReader, png, true),
    cis: decode(DataMatrixReader, png, false, 0.44),
    input,
  })
}
const expectedByOrder = new Map(evidence.scanResponses.map(row => [row.order_id, row]))
const apiOrderIndex = new Map(seed.order_ids.map((id, index) => [id, index]))
assert.equal(evidence.offResult.scanCalls, 0)
assert.equal(evidence.offResult.status.accepted_png_count, 0)
assert.equal(evidence.scanResponses.length, 2)
assert.equal(outputs.length, 6)
assert.equal(new Set(evidence.scanResponses.map(row => row.idempotency_key)).size, 2)
assert.equal(new Set(evidence.scanResponses.map(row => row.order_id)).size, 2)
for (const output of outputs) {
  assert(output.input, `receipt ${output.job_key} must byte-match a PNG sent to WMS Print Direct`)
  const scanId = output.job_key.split(':')[0]
  const scan = evidence.scanResponses.find(row => row.scan_id === scanId)
  assert(scan, `receipt ${output.job_key} belongs to one of the two real product scans`)
  const orderIndex = apiOrderIndex.get(scan.order_id)
  assert.notEqual(orderIndex, undefined)
  const decodedQr = seed.synthetic_order_stickers[orderIndex].text
  if (output.job_key.includes(':chz')) {
    const marking = scan.printed_codes[0]
    assert.equal(output.qr, null)
    assert.equal(output.cis, marking.cis_code)
    assert.equal(output.input.cis, marking.cis_code)
  } else {
    assert.equal(output.qr, decodedQr)
    assert.equal(output.cis, null)
    assert.equal(output.job_key, scan.scan_id)
  }
}
for (const scan of evidence.scanResponses) {
  const copies = outputs.filter(row => row.job_key.startsWith(`${scan.scan_id}:chz`))
  assert.equal(copies.length, 2)
  assert.equal(new Set(copies.map(row => row.cis)).size, 1, 'one CIS is emitted twice for two configured copies')
}
assert.equal(evidence.dbBefore.stock, evidence.dbAfter.stock, 'packing and print claims do not change stock')
assert(evidence.dbAfter.orders.filter(row => seed.order_ids.includes(row.id)).every(row => row.pack_status === 'packed'))
assert.equal(evidence.task.lines[0].qty_marking_printed, 2)

const report = {
  product_sha: evidence.productP,
  runtime_checkout_sha: evidence.runtimeCheckout,
  physical_paper: 'NOT_TESTED',
  outputs,
  checks: {
    both_flags_off_no_claim_or_job: true,
    two_rapid_product_scans_two_orders: true,
    one_qr_plus_two_same_cis_copies_per_order: true,
    direct_input_png_matches_handler_receipt_bytes: true,
    stock_unchanged: true,
    packed_orders: 2,
  },
}
await writeFile(join(evidenceRoot, 'decoded-output-contract.json'), JSON.stringify(report, null, 2))
process.stdout.write(JSON.stringify({
  checks: report.checks,
  decoded: outputs.map(row => ({ job_key: row.job_key, qr: row.qr, cis: row.cis, sha256: row.sha256, receipt: row.receipt })),
}, null, 2) + '\n')
