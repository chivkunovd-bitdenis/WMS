import { LABEL_SIZES } from '../utils/labelSize'
import { findTestLabel } from './catalog'
import './style.css'

const app = document.querySelector<HTMLDivElement>('#app')!
app.innerHTML = `<main><form id="scan-form">
  <input id="scan" aria-label="Штрихкод товара" autocomplete="off" autofocus placeholder="Штрихкод товара"/>
  <select id="size" aria-label="Размер этикетки">${LABEL_SIZES.map((size) => `<option value="${size.id}">${size.label}</option>`).join('')}</select>
</form><div id="error" role="alert" hidden></div></main>`
const input = document.querySelector<HTMLInputElement>('#scan')!
const errorMessage = document.querySelector<HTMLDivElement>('#error')!
function acceptScan(raw: string) {
  const value = raw.trim()
  if (!value) return
  input.value = ''
  // A browser print dialog is forbidden here. Until a direct printer connection
  // is configured, do not send, queue or claim successful printing.
  errorMessage.textContent = findTestLabel(value)
    ? 'Принтер не подключён'
    : `Неизвестный штрихкод: ${value}`
  errorMessage.hidden = false
  input.focus({ preventScroll: true })
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
