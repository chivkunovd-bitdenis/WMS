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

function decode(Reader, png, ratio = 1) {
  const height = Math.floor(png.height * ratio)
  const gray = new Uint8ClampedArray(png.width * height)
  for (let i = 0; i < gray.length; i += 1) {
    const alpha = png.data[i * 4 + 3] / 255
    const channel = (png.data[i * 4] + png.data[i * 4 + 1] + png.data[i * 4 + 2]) / 3
    gray[i] = Math.round(channel * alpha + 255 * (1 - alpha))
  }
  try {
    return new Reader().decode(new BinaryBitmap(new HybridBinarizer(new RGBLuminanceSource(gray, png.width, height)))).getText()
  } catch {
    return null
  }
}

const seed = JSON.parse(await readFile(join(caseDir, 'seed-public.json'), 'utf8'))
const dir = join(caseDir, 'native')
const api = JSON.parse(await readFile(join(dir, 'api-requests.json'), 'utf8'))
const before = JSON.parse(await readFile(join(dir, 'db-before.json'), 'utf8'))
const after = JSON.parse(await readFile(join(dir, 'db-after.json'), 'utf8'))
const afterManual = JSON.parse(await readFile(join(dir, 'pool-after-manual-bind-before-scan.json'), 'utf8'))
const beforeSecondKiz = JSON.parse(await readFile(join(dir, 'second-intent-before-kiz.json'), 'utf8')).current_snapshot
const beforeSecondDispatch = JSON.parse(await readFile(join(dir, 'db-after-kiz-commit-02-before-dispatch.json'), 'utf8'))
const requests = (await readFile(join(dir, 'requests.jsonl'), 'utf8')).trim().split('\n').map(JSON.parse)
const receipts = (await readFile(join(dir, 'sink-receipts.jsonl'), 'utf8')).trim().split('\n').map(JSON.parse)
const scans = api.filter(row => row.path?.endsWith('/scan-auto-print') && row.method === 'POST' && row.status === 200)
assert(scans.length >= 1, 'real UI scan intent reached the actual API')
const commits = api.filter(row => row.path?.endsWith('/fbs-orders/kiz/commit') && row.method === 'POST' && row.status === 200)
const bindings = new Map()
for (const commit of commits) for (const pair of commit.request?.pairs ?? []) bindings.set(pair.order_id, pair.value)
const reprintClaims = api.filter(row => row.path?.endsWith('/reprint-claim') && row.method === 'POST' && row.response?.claimed)
assert(reprintClaims.length >= 1, 'server claimed an explicit exact-current reprint')
const bindingValue = bindings.get(seed.order_ids[0])
assert(bindingValue, 'the operator UI sent the selected current CIS through the real manual KIZ commit endpoint')
const code = afterManual.codes.find(row => row.cis === bindingValue)
assert(code, 'the committed current CIS was one of the actual seller pool entries')
const ui = JSON.parse(await readFile(join(dir, 'ui-before-scan.json'), 'utf8'))
const expectedQrEnabled = scans[0]?.request?.print_qr === true
const expectedPerIntent = Number(expectedQrEnabled) + Number(ui.reprintCopies)
assert.equal(receipts.length, scans.length * expectedPerIntent, 'every completed scan intent produced only its configured QR and exact-reprint copies')
assert.equal(requests.length, receipts.length)
assert(scans.every(scan => scan.request.print_qr === expectedQrEnabled && scan.request.print_chz === false && scan.request.reprint_chz === true))
assert.equal(ui.reprintCopies, '2')
const expectedKeys = scans.flatMap(scan => [...(expectedQrEnabled ? [scan.response.scan_id] : []), `${scan.response.scan_id}:copy`, `${scan.response.scan_id}:copy:c2`])
assert.deepEqual(receipts.map(row => row.job_key), expectedKeys)
const outputRecords = []
for (const receipt of receipts) {
  const bytes = await readFile(join(dir, receipt.png))
  assert.equal(createHash('sha256').update(bytes).digest('hex'), receipt.sha256)
  const request = requests.find(row => row.body.idempotencyKey === receipt.job_key)
  assert(request, 'each native receipt maps to the exact React HTTP /print request')
  const input = Buffer.from(request.body.imageDataUrl.split(',')[1], 'base64')
  assert.equal(createHash('sha256').update(input).digest('hex'), receipt.sha256, 'emulated handler stores input PNG bytes unchanged')
  const png = PNG.sync.read(bytes)
  const qr = decode(QRCodeReader, png)
  const cis = decode(DataMatrixReader, png, 0.44)
  const owningScan = scans.find(scan => receipt.job_key === scan.response.scan_id || receipt.job_key.startsWith(`${scan.response.scan_id}:copy`))
  assert(owningScan, 'native job key belongs to one exact server scan intent')
  const stickerIndex = seed.order_ids.indexOf(owningScan.response.order_id)
  if (receipt.job_key === owningScan.response.scan_id) assert.equal(qr, seed.sticker_codes[stickerIndex])
  else assert.equal(cis, bindings.get(owningScan.response.order_id) ?? reprintClaims.find(row => row.request?.attempt_key === receipt.job_key)?.response?.kiz)
  outputRecords.push({ job_key: receipt.job_key, order_id: owningScan.response.order_id, receipt: receipt.receipt, sha256: receipt.sha256, qr, cis, bytes: receipt.bytes })
}
assert.deepEqual(beforeSecondKiz.codes, afterManual.codes, 'A exact reprint leaves every pool code unchanged before operator begins B KIZ binding')
assert.deepEqual(beforeSecondKiz.markings, afterManual.markings, 'A exact reprint leaves the current binding unchanged before B KIZ binding')
const secondBindDelta = beforeSecondDispatch.codes.filter(row => beforeSecondKiz.codes.some(old => old.id === row.id && old.status !== row.status))
assert.equal(secondBindDelta.length, 1, 'the following operator KIZ action consumes exactly one available pool CIS for B')
assert.equal(secondBindDelta[0].status, 'applied')
assert.deepEqual(after.codes, beforeSecondDispatch.codes, 'native reprint dispatch consumes no further seller-pool code after the binding snapshot')
assert.deepEqual(after.markings, beforeSecondDispatch.markings, 'native reprint leaves the pre-dispatch current bindings unchanged')
assert.equal(after.codes.length, before.codes.length)
assert.equal(after.codes.find(row => row.id === code.id)?.status, 'applied')
assert.equal(after.stock, before.stock)
const report = {
  product_sha: 'b6d23148f1571d08d13d83c6179c385e2f6a1efc',
  runtime_checkout_sha: 'b6d23148f1571d08d13d83c6179c385e2f6a1efc',
  case: `${scans.length} completed UI intents with ${expectedQrEnabled ? 'QR plus' : 'only'} exact-current reprint; reprintChzCopies=${ui.reprintCopies}, printChz disabled`,
  scan_ids: scans.map(scan => scan.response.scan_id),
  target_order_ids: scans.map(scan => scan.response.order_id),
  scan_inputs: scans.map(scan => ({ barcode: scan.request.barcode, order_id: scan.response.order_id })),
  exact_current_cis: bindingValue,
  native_jobs: outputRecords,
  pool_after_row_KIZ_intent_A_and_before_product_scan_B: afterManual.codes,
  pool_after_A_exact_reprint_and_before_B_kiz: JSON.parse(await readFile(join(dir, 'second-intent-before-kiz.json'), 'utf8')).current_snapshot.codes,
  pool_after_B_operator_bind_before_native_dispatch: beforeSecondDispatch.codes,
  pool_after_all_native_dispatch: after.codes,
  pool_code_rows_before_after: { before_count: afterManual.codes.length, after_count: after.codes.length },
  stock_before_after: { before: before.stock, after: after.stock },
  provider_boundary: 'manual current-code sync was explicitly synthetic; no outbound WB request is proven here',
  physical_paper: 'NOT_TESTED',
}
await writeFile(join(dir, 'decoded-reprint-contract.json'), `${JSON.stringify(report, null, 2)}\n`)
console.log(JSON.stringify({ case: report.case, target_order_id: report.target_order_id, exact_current_cis: report.exact_current_cis, jobs: outputRecords }, null, 2))
