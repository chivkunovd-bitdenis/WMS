import { createHash } from 'node:crypto';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { createRequire } from 'node:module';
import { join } from 'node:path';

const require = createRequire(new URL('../../../../frontend/package.json', import.meta.url));
const bwip = require('bwip-js');
const { PNG } = require('pngjs');
const { RGBLuminanceSource, BinaryBitmap, HybridBinarizer, QRCodeReader, DataMatrixReader } = require('@zxing/library');
const runDir = process.argv[2];
if (!runDir) throw Error('Usage: node verify_group_native_evidence.mjs <captured-run-directory>');
const readJson = async path => JSON.parse(await readFile(path, 'utf8'));
const sha256 = value => createHash('sha256').update(value).digest('hex');
function decodePng(bytes) {
  const png = PNG.sync.read(bytes);
  const height = Math.floor(png.height * 0.44);
  for (const region of [{ height }, { height: png.height }]) {
    const gray = new Uint8ClampedArray(png.width * region.height);
    for (let i = 0; i < gray.length; i++) gray[i] = (png.data[i * 4] + 2 * png.data[i * 4 + 1] + png.data[i * 4 + 2]) / 4;
    const bitmap = new BinaryBitmap(new HybridBinarizer(new RGBLuminanceSource(gray, png.width, region.height)));
    for (const Reader of [DataMatrixReader, QRCodeReader]) {
      try { return new Reader().decode(bitmap).getText(); } catch {}
    }
  }
  throw Error('PNG has no independently decodable QR/Data Matrix payload');
}

const summary = await readJson(join(runDir, 'WMS666-whole-process-bare-group-manual-before-scan.json'));
const dbOrders = new Map(summary.finalDb.orders.map(order => [order.id, order]));
const providerTrace = summary.trace.find(row => row.kind === 'bare-group-manual-prepare-sticker-chain');
const wbRequests = providerTrace.wbRequests;
const stickerRows = new Map(wbRequests.flatMap(request => request.stickers).map(row => [row.orderId, row]));
const orderIds = [800392, 800393];
const orderByBarcode = new Map([...dbOrders.values()].map(order => [order.sticker_barcode, order]));
const nativeRequests = (await readFile(join(runDir, 'native/requests.jsonl'), 'utf8')).trim().split('\n').map(JSON.parse);
const sinkReceipts = (await readFile(join(runDir, 'native/sink-receipts.jsonl'), 'utf8')).trim().split('\n').map(JSON.parse);
const sinkByKey = new Map(sinkReceipts.map(row => [row.job_key, row]));
const fixturesDir = join(runDir, 'fixtures');
await mkdir(fixturesDir, { recursive: true });
const htmlPath = join(runDir, 'WMS666-whole-process-bare-group-manual-before-scan.html');
const html = await readFile(htmlPath, 'utf8');
const manualHtmlCodes = [...html.matchAll(/data-tape-block="cz"[\s\S]*?<img src="data:image\/png;base64,([^"]+)"/g)]
  .map(match => {
    const bytes = Buffer.from(match[1], 'base64');
    return { decoded: decodePng(bytes), png_sha256: sha256(bytes), bytes: bytes.length };
  });
const manualTapeRequests = summary.requestLog.filter(row => row.path.endsWith('/order-print-tape'));
if (manualTapeRequests.length !== 2 || manualHtmlCodes.length !== 4) {
  throw Error(`Expected two real manual tape responses and four rendered CIS images, got ${manualTapeRequests.length}/${manualHtmlCodes.length}`);
}
const manualTapeGroups = manualTapeRequests.map(tape => {
  const expected = tape.response.orders[0].printed_codes[0].cis_code;
  const orderId = tape.response.orders[0].order_id;
  const outputs = manualHtmlCodes.splice(0, 2);
  if (tape.status !== 200 || tape.response.order_errors?.length || outputs.length !== 2 || outputs.some(output => output.decoded !== expected)) {
    throw Error(`Manual HTML tape does not contain two exact copies of the CIS returned for order ${orderId}`);
  }
  return { order_id: orderId, supply_id: tape.body.order_ids[0], copies_requested: tape.body.layout_json.units[0].copies,
    returned_marking: tape.response.orders[0].printed_codes[0], rendered_outputs: outputs };
});
const manualPdfPaths = ['supply_ids-bare-manual-1-render.pdf', 'supply_ids-bare-manual-after-task-render.pdf'];
const manualPdfs = await Promise.all(manualPdfPaths.map(async path => {
  const bytes = await readFile(join(runDir, path));
  return { path, sha256: sha256(bytes), bytes: bytes.length };
}));
const joined = [];
for (const marketplaceOrderId of orderIds) {
  const provider = stickerRows.get(marketplaceOrderId);
  const order = orderByBarcode.get(provider?.barcode);
  if (!provider || !order) throw Error(`Missing provider or DB row for marketplace order ${marketplaceOrderId}`);
  const sourcePng = await bwip.toBuffer({
    bcid: 'qrcode', text: provider.barcode, scale: 4, padding: 4, backgroundcolor: 'FFFFFF',
  });
  const sourceHash = sha256(sourcePng);
  if (sourceHash !== provider.sha256) throw Error(`Rebuilt provider PNG hash differs for ${marketplaceOrderId}`);
  const asset = summary.finalDb.print_assets.find(row => row.order_id === order.id);
  if (sourceHash !== asset?.checksum?.replace(/^sha256:/, '')) throw Error(`Persisted asset checksum differs for ${marketplaceOrderId}`);
  if (decodePng(sourcePng) !== provider.barcode || order.sticker_barcode !== provider.barcode) {
    throw Error(`Provider QR payload and persisted sticker_barcode differ for ${marketplaceOrderId}`);
  }
  const providerPath = join(fixturesDir, `regenerated-provider-order-${marketplaceOrderId}.png`);
  await writeFile(providerPath, sourcePng);
  const successfulClaim = summary.requestLog.find(row => row.path.endsWith('/scan-auto-print') && row.status === 200 && row.response?.order_id === order.id);
  if (!successfulClaim) throw Error(`No successful physical scan claim for order ${order.id}`);
  const currentCis = summary.finalDb.markings.find(row => row.order_id === order.id)?.cis;
  if (!currentCis) throw Error(`No current CIS binding for order ${order.id}`);
  const orderJobs = nativeRequests.filter(row => row.body?.idempotencyKey === successfulClaim.response.scan_id ||
    row.body?.idempotencyKey?.startsWith(`${successfulClaim.response.scan_id}:`));
  if (orderJobs.length !== 3) throw Error(`Expected QR plus two CIS copies for order ${order.id}, got ${orderJobs.length}`);
  const nativeRows = [];
  for (const request of orderJobs) {
    const bytes = Buffer.from(request.body.imageDataUrl.split(',')[1], 'base64');
    const receipt = sinkByKey.get(request.body.idempotencyKey);
    if (!receipt) throw Error(`No durable sink receipt for native key ${request.body.idempotencyKey}`);
    const decoded = decodePng(bytes);
    if (sha256(bytes) !== receipt.sha256) throw Error(`Handler PNG/receipt hash mismatch for ${request.body.idempotencyKey}`);
    const isQr = request.body.idempotencyKey === successfulClaim.response.scan_id;
    if (isQr ? decoded !== provider.barcode : decoded !== currentCis) {
      throw Error(`Native ${isQr ? 'QR' : 'CIS'} output does not match its order binding for ${order.id}`);
    }
    nativeRows.push({
      native_key: request.body.idempotencyKey,
      output_kind: isQr ? 'order QR' : 'current CIS copy',
      decoded_qr: decoded,
      png_sha256: sha256(bytes),
      receipt: receipt.receipt,
      sink_png: receipt.png,
      created_at_utc: receipt.accepted_at_utc,
    });
  }
  if (nativeRows.filter(row => row.output_kind === 'order QR').length !== 1 ||
      nativeRows.filter(row => row.output_kind === 'current CIS copy').length !== 2) {
    throw Error(`Expected one order QR and two CIS copies for ${marketplaceOrderId}`);
  }
  joined.push({
    marketplace_order_id: marketplaceOrderId,
    provider_barcode: provider.barcode,
    provider_png_sha256: provider.sha256,
    provider_png_bytes: provider.pngBytes,
    provider_png_regenerated_from_versioned_emulator_source: providerPath.split('/').slice(-2).join('/'),
    provider_png_rebuild_sha256_matches_observed_http_response: sourceHash === provider.sha256,
    provider_png_independent_qr_decode: decodePng(sourcePng),
    persisted_asset_id: asset?.id,
    persisted_asset_sha256: asset?.checksum,
    human_readable_sticker_code: order.sticker_code,
    persisted_encoded_sticker_barcode: order.sticker_barcode,
    current_cis: currentCis,
    native_handler_outputs: nativeRows,
  });
}

const result = {
  case: 'grouped manual HTML tape -> actual native handler scan',
  product_sha: summary.productSha,
  runner_git_sha: summary.sha,
  database: 'wms_test_666_browser_proof (isolated synthetic fixture)',
  manual_tape_html_outputs: manualTapeGroups,
  manual_html_pdf_artifacts: manualPdfs,
  provider_to_asset_to_handler_qr_joins: joined,
  native_output_count: sinkReceipts.length,
  scan_attempts: summary.requestLog.filter(row => row.path.endsWith('/scan-auto-print')).map(row => ({
    captured_at: row.captured_at,
    status: row.status,
    supply_id: row.path.match(/fbs-supplies\/([^/]+)\/scan-auto-print/)?.[1],
    order_id: row.response?.order_id ?? null,
    error_code: row.response?.detail?.code ?? null,
  })),
  physical_inputs: summary.trace.find(row => row.kind === 'native-group-input-boundaries')?.physicalScans.map(row => ({
    scan_index: row.index,
    barcode: row.barcode,
    scanner_was_neutral_before_and_after: row.inputBefore.value === '' && row.inputAfter.value === '',
    order_id: row.settledOrder.id,
    pack_status: row.settledOrder.pack_status,
    api_attempts: row.apiAttempts.length,
    native_outputs: row.nativeOutputs.length,
    api_idle_after_completion: row.idle.active === 0,
    visible_alerts: row.alerts,
  })) ?? [],
  stock_unchanged: JSON.stringify(providerTrace.before.stock) === JSON.stringify(summary.finalDb.stock),
  final_database: summary.finalDb,
  whole_runner_result: (await readJson(join(runDir, 'result.json'))).cases,
  note: 'The whole-process runner later encounters an out-of-scope cargo-box POST 403 missing_marketplace_token. This evidence report validates the already-completed grouped manual/native scan segment independently and preserves that later failure separately.',
};
await writeFile(join(runDir, 'group-native-evidence-join.json'), JSON.stringify(result, null, 2) + '\n');
process.stdout.write(JSON.stringify({
  orders: joined.map(row => ({ order: row.marketplace_order_id, qr: row.persisted_encoded_sticker_barcode,
    provider_sha: row.provider_png_sha256, handler_keys: row.native_handler_outputs.map(output => output.native_key) })),
  physical_inputs: result.physical_inputs,
  whole_runner_result: result.whole_runner_result,
}) + '\n');
