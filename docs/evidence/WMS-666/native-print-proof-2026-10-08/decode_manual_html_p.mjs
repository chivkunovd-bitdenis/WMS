import { createRequire } from 'node:module'
import { readFile, writeFile } from 'node:fs/promises'
import { createHash } from 'node:crypto'
import { resolve } from 'node:path'

const require = createRequire(new URL('../../../../frontend/package.json', import.meta.url))
const { PNG } = require('pngjs')
const { RGBLuminanceSource, BinaryBitmap, HybridBinarizer, DataMatrixReader, QRCodeReader } = require('@zxing/library')
const folder = resolve('docs/evidence/WMS-666/native-print-proof-2026-10-08/run-5066f1dc/manual')
const html = await readFile(`${folder}/manual-print.html`, 'utf8')
const cis = '010460043993125321KIZTAPE0000000000'
const images = [...html.matchAll(/data:image\/png;base64,([^" ]+)/g)].map((match, index) => {
  const bytes = Buffer.from(match[1], 'base64')
  return { index, bytes, path: `${folder}/manual-input-${index + 1}.png` }
})
const decode = (reader, image) => {
  const rgba = PNG.sync.read(image)
  const gray = new Uint8ClampedArray(rgba.width * rgba.height)
  for (let i = 0; i < gray.length; i++) gray[i] = Math.round((rgba.data[i * 4] + rgba.data[i * 4 + 1] + rgba.data[i * 4 + 2]) / 3)
  try { return new reader().decode(new BinaryBitmap(new HybridBinarizer(new RGBLuminanceSource(gray, rgba.width, rgba.height)))).getText() } catch { return null }
}
const decoded = []
for (const image of images) {
  await writeFile(image.path, image.bytes)
  const raster = PNG.sync.read(image.bytes)
  decoded.push({ index: image.index + 1, sha256: createHash('sha256').update(image.bytes).digest('hex'), bytes: image.bytes.length, width: raster.width, height: raster.height, dataMatrix: decode(DataMatrixReader, image.bytes), qr: decode(QRCodeReader, image.bytes) })
}
const report = { expectedCis: cis, htmlCisOccurrences: html.split(cis).length - 1, embeddedImageCount: images.length, copiesShownByPdf: 2, decodedImages: decoded, boundary: 'HTML saved by actual application printMarkingCodeTape after beforeDispatch validation; PDF rendered by headless Chromium, not a physical printer' }
await writeFile(`${folder}/manual-render-decode.json`, JSON.stringify(report, null, 2))
console.log(JSON.stringify(report, null, 2))
