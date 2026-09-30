import * as bwipjs from 'bwip-js'
import { printDirectQr } from '../utils/printDirectQr'
import { findTestLabel, TEST_LABELS } from './catalog'
import './style.css'

const app = document.querySelector<HTMLDivElement>('#app')!
app.innerHTML = `<main><form id="scan-form">
  <input id="scan" aria-label="Штрихкод товара" autocomplete="off" autofocus placeholder="Штрихкод товара"/>
</form><div id="error" role="alert" hidden></div></main>`
const input = document.querySelector<HTMLInputElement>('#scan')!
const errorMessage = document.querySelector<HTMLDivElement>('#error')!
// Prepare QR before a scan; the native app fits it to the default printer media.
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
  const startedAt = performance.now()
  void printDirectQr({
    imageDataUrl: prepared.get(value)!,
    idempotencyKey: crypto.randomUUID(),
    widthMm: 58,
    heightMm: 40,
  }).then(() => {
    app.dataset.lastPrintMs = String(Math.round(performance.now() - startedAt))
    app.dataset.printedCount = String(Number(app.dataset.printedCount || 0) + 1)
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
