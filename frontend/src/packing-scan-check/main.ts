import { LABEL_SIZES, loadLabelSizeId, saveLabelSizeId, type LabelSizeId } from '../utils/labelSize'
import * as bwipjs from 'bwip-js'
import { printPreparedQr } from '../utils/printPreparedQr'
import { findTestLabel, TEST_LABELS } from './catalog'
import './style.css'

const app = document.querySelector<HTMLDivElement>('#app')!
app.innerHTML = `<main><form id="scan-form">
  <input id="scan" aria-label="Штрихкод товара" autocomplete="off" autofocus placeholder="Штрихкод товара"/>
  <select id="size" aria-label="Размер этикетки">${LABEL_SIZES.map((size) => `<option value="${size.id}">${size.label}</option>`).join('')}</select>
</form><div id="error" role="alert" hidden></div></main>`
const input = document.querySelector<HTMLInputElement>('#scan')!
const errorMessage = document.querySelector<HTMLDivElement>('#error')!
const sizeSelect = document.querySelector<HTMLSelectElement>('#size')!
sizeSelect.value = loadLabelSizeId()
sizeSelect.addEventListener('change', () => saveLabelSizeId(sizeSelect.value as LabelSizeId))
// QR rasterization happens once, before a scan, then uses exactly the same
// prepared-image browser printing as real packing labels.
const prepared = new Map(TEST_LABELS.map((label) => {
  const canvas = document.createElement('canvas')
  bwipjs.toCanvas(canvas, { bcid: 'qrcode', text: label.qr, scale: 6, padding: 8 })
  return [label.barcode, canvas.toDataURL('image/png')]
}))
let latestScan = 0
function acceptScan(raw: string) {
  const value = raw.trim()
  if (!value) return
  input.value = ''
  input.focus({ preventScroll: true })
  errorMessage.hidden = true
  const scan = ++latestScan
  if (!findTestLabel(value)) {
    errorMessage.textContent = `Неизвестный штрихкод: ${value}`
    errorMessage.hidden = false
    return
  }
  const size = LABEL_SIZES.find((item) => item.id === sizeSelect.value)!
  void printPreparedQr({
    imageDataUrl: prepared.get(value)!,
    idempotencyKey: crypto.randomUUID(),
    widthMm: size.widthMm,
    heightMm: size.heightMm,
  }).catch((error: unknown) => {
    // Never hide a failed print with a later successful scan.
    errorMessage.textContent = error instanceof Error ? error.message : 'Принтер не принял этикетку'
    errorMessage.hidden = false
    if (scan === latestScan) input.focus({ preventScroll: true })
  })
}
document.querySelector('#scan-form')!.addEventListener('submit', (event) => {
  event.preventDefault()
  acceptScan(input.value)
})

// Keyboard-wedge scanners keep working after a click outside the input.
let buffer = ''
let lastKeyAt = 0
document.addEventListener('keydown', (event) => {
  if (event.target === input || event.ctrlKey || event.metaKey || event.altKey) return
  const now = performance.now()
  if (now - lastKeyAt > 100) buffer = ''
  lastKeyAt = now
  if (event.key === 'Enter') {
    if (buffer.length >= 8) { event.preventDefault(); acceptScan(buffer) }
    buffer = ''
  } else if (event.key.length === 1) buffer += event.key
}, true)
input.focus()
