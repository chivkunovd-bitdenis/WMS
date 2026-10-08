import assert from 'node:assert/strict'
import { createHash } from 'node:crypto'
import { createRequire } from 'node:module'
import { readFile, writeFile } from 'node:fs/promises'
import { join, resolve } from 'node:path'

const base = resolve('docs/evidence/WMS-666/native-print-proof-2026-10-08')
const caseDir = join(base, 'run-b6d23148/qr-only-continuity-native-api')
const native = join(caseDir, 'native')
const continuation = join(native, 'continuation')
const require = createRequire('/Users/deniscivkunov/Projects/WMS/.worktrees/wms666-native-final-runtime/frontend/package.json')
const { PNG } = require('pngjs')
const { RGBLuminanceSource, BinaryBitmap, HybridBinarizer, QRCodeReader } = require('@zxing/library')
const decode = png => {
  const gray = new Uint8ClampedArray(png.width * png.height)
  for (let i = 0; i < gray.length; i += 1) {
    const alpha = png.data[i * 4 + 3] / 255
    const value = (png.data[i * 4] + png.data[i * 4 + 1] + png.data[i * 4 + 2]) / 3
    gray[i] = Math.round(value * alpha + 255 * (1 - alpha))
  }
  return new QRCodeReader().decode(new BinaryBitmap(new HybridBinarizer(new RGBLuminanceSource(gray, png.width, png.height)))).getText()
}
const sha = bytes => createHash('sha256').update(bytes).digest('hex')
const seed = JSON.parse(await readFile(join(caseDir, 'seed-public.json'), 'utf8'))
const initial = JSON.parse(await readFile(join(native, 'db-before.json'), 'utf8'))
const afterA = JSON.parse(await readFile(join(native, 'after-A.json'), 'utf8'))
const afterARescan = JSON.parse(await readFile(join(continuation, 'before-B-after-reload.json'), 'utf8'))
const afterB = JSON.parse(await readFile(join(continuation, 'after-A-rescan.json'), 'utf8'))
const finalNative = JSON.parse(await readFile(join(continuation, 'summary.json'), 'utf8'))
const finalUi = JSON.parse(await readFile(join(continuation, 'dom-inspection/result.json'), 'utf8'))
const firstApi = JSON.parse(await readFile(join(native, 'api-requests.json'), 'utf8'))
const receiptRows = (await readFile(join(native, 'sink-receipts.jsonl'), 'utf8')).trim().split('\n').map(JSON.parse)
const handlerRequests = (await readFile(join(native, 'requests.jsonl'), 'utf8')).trim().split('\n').map(JSON.parse)
const scanMap = new Map()
for (const row of [...firstApi, ...finalNative.api_events]) {
  if (row.method === 'POST' && row.status === 200 && row.path.endsWith('/scan-auto-print') && row.response?.scan_id) {
    scanMap.set(row.response.scan_id, { order_id: row.response.order_id, barcode: row.request?.barcode })
  }
}
const aScan = firstApi.find(row => row.path.endsWith('/scan-auto-print') && row.status === 200 && row.response?.scan_id === receiptRows[0]?.job_key)
const bScanId = receiptRows[1]?.job_key
const bScan = finalNative.api_events.find(row => row.path.endsWith('/scan-auto-print') && row.status === 200 && row.response?.scan_id === bScanId)
assert(aScan, 'first native receipt belongs to A actual sticker selection')
assert(bScan, 'second native receipt belongs to B actual product selection')
assert.equal(bScan.request.barcode, seed.barcode)
assert.equal(bScan.response.order_id, seed.order_ids[1])
assert.equal(receiptRows.length, 2)
assert.equal(handlerRequests.length, 2)
const output = []
for (const [index, receipt] of receiptRows.entries()) {
  const request = handlerRequests.find(row => row.body?.idempotencyKey === receipt.job_key)
  assert(request, 'each accepted receipt joins exactly one native HTTP request by idempotency key')
  const input = Buffer.from(request.body.imageDataUrl.split(',')[1], 'base64')
  const outputPng = await readFile(join(native, receipt.png))
  assert.equal(sha(input), receipt.sha256, 'saved sink PNG is byte-equal to the Handler input')
  assert.equal(sha(outputPng), receipt.sha256)
  const expected = seed.order_sticker_barcodes[index]
  const sourcePng = await readFile(join(caseDir, seed.synthetic_order_stickers[index].file))
  assert.equal(sha(sourcePng), seed.synthetic_order_stickers[index].sha256)
  const inputText = decode(PNG.sync.read(input)); const outputText = decode(PNG.sync.read(outputPng)); const sourceText = decode(PNG.sync.read(sourcePng))
  assert.equal(sourceText, expected)
  assert.equal(inputText, expected)
  assert.equal(outputText, expected)
  output.push({ order_id: index === 0 ? seed.order_ids[0] : seed.order_ids[1], scan_id: receipt.job_key, receipt: receipt.receipt, source_png_sha256: sha(sourcePng), handler_input_sha256: sha(input), sink_png_sha256: sha(outputPng), decoded: { seed_asset: sourceText, handler_input: inputText, sink_output: outputText } })
}
const poolStates = rows => rows.map(row => ({ id: row.id, status: row.status })).sort((a, b) => a.id.localeCompare(b.id))
const beforeARescan = poolStates(afterA.db.codes); const afterARescanPool = poolStates(afterARescan.db.codes)
assert.deepEqual(afterARescanPool, beforeARescan, 'rescanning A did not allocate or change pool codes')
const markingBindings = rows => rows.map(row => ({ id: row.id, order_id: row.order_id, cis: row.cis, code_id: row.code_id })).sort((a, b) => a.id.localeCompare(b.id))
assert.deepEqual(markingBindings(afterARescan.db.markings), markingBindings(afterA.db.markings), 'the same current CIS bindings remained; no replacement marking was allocated during A rescan')
const markingStatusChanges = afterARescan.db.markings.map(current => {
  const previous = afterA.db.markings.find(row => row.id === current.id)
  return { marking_id: current.id, from: previous?.status ?? null, to: current.status }
})
assert(markingStatusChanges.some(row => row.from === 'unknown' && row.to === 'accepted'), 'explicit synthetic provider sync changed A marking status to accepted')
assert.deepEqual(initial.stock, afterA.db.stock)
assert.deepEqual(afterA.db.stock, afterB.db.stock)
assert.deepEqual(afterA.db.stock, finalNative.final.db.stock)
const ordersFinal = finalNative.final.db.orders.filter(row => seed.order_ids.includes(row.id))
assert(ordersFinal.every(row => row.pack_status === 'packed'))
assert.equal(finalUi.handler.accepted_png_count, 2)
assert.deepEqual(finalUi.state.activeRow, [])
assert.equal(finalUi.state.activeTarget, null)
assert.deepEqual(finalUi.state.scanInput, { value: '', placeholder: 'Сканируйте штрихкод товара' })
assert.equal(finalUi.state.undo.disabled, true)
assert.equal(finalUi.state.message, null)
const report = {
  product_sha: finalNative.product_sha,
  runtime_sha: finalNative.runtime_sha,
  source_and_runtime: 'The browser UI and real WMS Print Direct Handler were pinned to the same immutable product P; only the Handler printer-submit boundary was replaced by a PNG/receipt sink.',
  fixture_boundary: 'Synthetic fixture and synthetic accepting readback via the explicit UI button «Проверить в WB»; no outbound marketplace request or physical paper is proven.',
  physical_inputs: [
    { kind: 'output QR barcode', value: seed.order_sticker_barcodes[0], order_id: seed.order_ids[0], result: 'A selected again; handler receipt count stayed 1 at that step; no A replay job was submitted.' },
    { kind: 'product barcode', value: seed.barcode, order_id: seed.order_ids[1], scan_id: bScanId, result: 'B selected; operator entered its current pool CIS in B row; one B QR job accepted and order packed.' },
  ],
  png_and_receipt_joins: output,
  pool_before_after_A_rescan: { before: beforeARescan, after: afterARescanPool, unchanged: true, before_snapshot: 'after-A.json', after_snapshot: 'continuation/before-B-after-reload.json' },
  markings_before_after_A_rescan: { bindings_before: markingBindings(afterA.db.markings), bindings_after: markingBindings(afterARescan.db.markings), binding_identity_unchanged: true, observed_status_changes: markingStatusChanges, note: 'The synthetic provider sync advanced the existing A marking from unknown to accepted; it did not change marking/code identity.' },
  stock_before_after: { before: initial.stock, after: finalNative.final.db.stock, unchanged: true },
  final_post_reload_dom: { active_row: finalUi.state.activeRow, active_target: finalUi.state.activeTarget, scanner: finalUi.state.scanInput, undo_disabled: finalUi.state.undo.disabled, kiz_message: finalUi.state.message, both_orders_packed: true },
  handler_total_receipts: finalUi.handler.accepted_png_count,
  chronology_note: 'A fresh rescan creates a distinct operator scan attempt. Intermediate failure/undo evidence is preserved; the final captured state is after a successful undo followed by reload, which restored an idle product-barcode input. Do not describe the intermediate «undo disabled» wait as proof of same-page quiescence.',
}
await writeFile(join(continuation, 'decoded-continuity-contract.json'), JSON.stringify(report, null, 2) + '\n')
console.log(JSON.stringify({ receipts: output, pool_unchanged_on_A_rescan: true, stock_unchanged: true, final_neutral_after_reload: report.final_post_reload_dom }, null, 2))
