import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import { createHash } from 'node:crypto'
import { readFile, writeFile } from 'node:fs/promises'
import { join, resolve } from 'node:path'

const caseDir = resolve('docs/evidence/WMS-666/native-print-proof-2026-10-08', process.argv[2])
assert(caseDir.startsWith(resolve('docs/evidence/WMS-666/native-print-proof-2026-10-08/run-b6d23148')))
const require = createRequire('/Users/deniscivkunov/Projects/WMS/.worktrees/wms666-native-final-runtime/frontend/package.json')
const { PNG } = require('pngjs')
const { RGBLuminanceSource, BinaryBitmap, HybridBinarizer, QRCodeReader, DataMatrixReader } = require('@zxing/library')

function decode(Reader, png, compositeWhite, heightRatio = 1) {
  const height = Math.floor(png.height * heightRatio)
  const gray = new Uint8ClampedArray(png.width * height)
  for (let i = 0; i < gray.length; i += 1) {
    const alpha = png.data[i * 4 + 3] / 255
    const channel = (png.data[i * 4] + png.data[i * 4 + 1] + png.data[i * 4 + 2]) / 3
    gray[i] = Math.round(compositeWhite ? channel * alpha + 255 * (1 - alpha) : channel)
  }
  try {
    return new Reader().decode(new BinaryBitmap(new HybridBinarizer(new RGBLuminanceSource(gray, png.width, height)))).getText()
  } catch {
    return null
  }
}

const seed = JSON.parse(await readFile(join(caseDir, 'seed-public.json'), 'utf8'))
const evidence = JSON.parse(await readFile(join(caseDir, 'native/source-and-seed.json'), 'utf8'))
const api = JSON.parse(await readFile(join(caseDir, 'native/api-requests.json'), 'utf8'))
const dbBefore = JSON.parse(await readFile(join(caseDir, 'native/db-before.json'), 'utf8'))
const dbAfter = JSON.parse(await readFile(join(caseDir, 'native/db-after.json'), 'utf8'))
const rawRequests = (await readFile(join(caseDir, 'native/requests.jsonl'), 'utf8')).trim().split('\n').map(JSON.parse)
const rawReceipts = (await readFile(join(caseDir, 'native/sink-receipts.jsonl'), 'utf8')).trim().split('\n').map(JSON.parse)
const scan = api.find(row => row.path?.endsWith('/scan-auto-print') && row.method === 'POST' && row.status === 200)
assert(scan, 'a real successful scan-auto-print API response was recorded')
const expectedQr = scan.response.qr_asset ? seed.sticker_codes[0] : null
const expectedCis = scan.response.printed_codes?.[0]?.cis_code ?? null
assert(expectedQr || expectedCis, 'the enabled mode returned a QR asset or exact printed CIS')
assert.equal(rawReceipts.length, expectedCis ? 2 : 1)
assert.equal(rawRequests.length, rawReceipts.length)
const decoded = []
for (const receipt of rawReceipts) {
  const pngBytes = await readFile(join(caseDir, 'native', receipt.png))
  const png = PNG.sync.read(pngBytes)
  const request = rawRequests.find(row => {
    const bytes = Buffer.from(row.body.imageDataUrl.split(',')[1], 'base64')
    return createHash('sha256').update(bytes).digest('hex') === receipt.sha256
  })
  assert(request, 'accepted PNG receipt is byte-equal to a real HTTP request body')
  const bytes = Buffer.from(request.body.imageDataUrl.split(',')[1], 'base64')
  const input = PNG.sync.read(bytes)
  const qr = decode(QRCodeReader, png, true)
  const cis = decode(DataMatrixReader, png, false, 0.44) ?? decode(DataMatrixReader, png, true, 0.44)
  if (expectedQr) assert.equal(qr, expectedQr)
  if (expectedCis) assert.equal(cis, expectedCis)
  decoded.push({ job_key: receipt.job_key, receipt: receipt.receipt, sha256: receipt.sha256, qr, cis, input_bytes: bytes.length, output_bytes: pngBytes.length, input_width: input.width, input_height: input.height })
}
assert.equal(dbBefore.stock, dbAfter.stock)
const report = {
  product_sha: evidence.product_sha,
  runtime_checkout_sha: evidence.runtime_checkout_sha,
  physical_paper: 'NOT_TESTED',
  case: expectedQr ? 'QR-only native print' : 'CHZ-only native print with two copies',
  target_order_id: scan.response.order_id,
  enabled_outputs: { qr: Boolean(expectedQr), chz: Boolean(expectedCis), cis: expectedCis },
  receipts: decoded,
  stock_before: dbBefore.stock,
  stock_after: dbAfter.stock,
}
await writeFile(join(caseDir, 'native/decoded-output-contract.json'), JSON.stringify(report, null, 2))
console.log(JSON.stringify({ case: report.case, target_order_id: report.target_order_id, enabled_outputs: report.enabled_outputs, receipts: decoded }, null, 2))
