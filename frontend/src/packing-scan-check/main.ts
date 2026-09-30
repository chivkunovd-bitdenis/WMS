import bwipjs from 'bwip-js'
import { buildWbOrderQrLabelHtml, printTapeSections } from '../utils/printMarkingCodeLabel'
import { renderBarcodeDataUrl } from '../utils/renderBarcodeDataUrl'
import { LABEL_SIZES, resolveLabelSize, type LabelSizeId } from '../utils/labelSize'
import { TEST_LABELS, findTestLabel } from './catalog'
import './style.css'

const app = document.querySelector<HTMLDivElement>('#app')!
app.innerHTML = `<main>
  <h1>Скан → QR → печать</h1>
  <p>10 тестовых штрихкодов. QR подготовлены заранее. Рабочие заказы и Честные знаки не используются.</p>
  <form id="scan-form"><label for="scan">Штрихкод товара</label><div class="input-row"><input id="scan" autocomplete="off" autofocus placeholder="Сканируйте ШК и Enter"/><button>Проверить</button></div></form>
  <div class="options"><label><input id="auto-print" type="checkbox" checked/> Сразу печатать QR</label><label>Этикетка <select id="size">${LABEL_SIZES.map((size) => `<option value="${size.id}">${size.label}</option>`).join('')}</select></label></div>
  <div id="status" role="status">Готовим 10 QR…</div>
  <section class="result" hidden id="result"><img id="qr" alt="QR тестовой этикетки"/><div><strong id="qr-value"></strong><p id="timing"></p><button type="button" id="reprint">Напечатать ещё раз</button></div></section>
  <p class="note">Печать идёт через тот же механизм WMS. Браузер может открыть системное окно печати. Выход этикетки подтверждается на принтере.</p>
  <details open><summary>10 штрихкодов для проверки</summary><div class="catalog" id="catalog"></div></details>
</main>`
const input = document.querySelector<HTMLInputElement>('#scan')!
const status = document.querySelector<HTMLDivElement>('#status')!
const result = document.querySelector<HTMLElement>('#result')!
const qrImage = document.querySelector<HTMLImageElement>('#qr')!
const qrValue = document.querySelector<HTMLElement>('#qr-value')!
const timing = document.querySelector<HTMLElement>('#timing')!
const autoPrint = document.querySelector<HTMLInputElement>('#auto-print')!
const sizeSelect = document.querySelector<HTMLSelectElement>('#size')!
const reprint = document.querySelector<HTMLButtonElement>('#reprint')!

// Preparation happens before scanning. Both preview and printer get these same bytes.
const prepared = new Map<string, { qr: string; image: string; section: string }>()
for (const label of TEST_LABELS) {
  const canvas = document.createElement('canvas')
  bwipjs.toCanvas(canvas, { bcid: 'qrcode', text: label.qr, scale: 5, includetext: false })
  const image = canvas.toDataURL('image/png')
  const section = buildWbOrderQrLabelHtml(image)
    .replace('class="label label--wb-qr"', 'class="label label--wb-qr" style="display:flex;flex-direction:column;align-items:center;justify-content:center;padding:2mm;gap:1mm"')
    .replace('<img class="wb-qr-img"', '<strong style="font:700 9pt Arial;flex-shrink:0">ТЕСТ</strong><img style="max-height:calc(100% - 6mm);max-width:100%;width:auto;height:auto;object-fit:contain" class="wb-qr-img"')
  prepared.set(label.barcode, { qr: label.qr, image, section })
  const card = document.createElement('button')
  card.type = 'button'
  card.className = 'test-code'
  card.dataset.barcode = label.barcode
  card.innerHTML = `<img alt="ШК ${label.barcode}" src="${renderBarcodeDataUrl(label.barcode)}"/><span>${label.barcode}</span><small>${label.qr}</small>`
  card.addEventListener('click', () => acceptScan(label.barcode))
  document.querySelector('#catalog')!.append(card)
}
status.textContent = 'Готово к сканированию · все 10 QR загружены'
let current: { qr: string; image: string; section: string } | undefined
let printing = false
const queue: Array<{ raw: string; receivedAt: number; print: boolean; size: LabelSizeId }> = []

async function invokePrint(section: string, receivedAt: number, size: LabelSizeId) {
  printing = true
  reprint.disabled = true
  status.textContent = 'Передаём QR в окно печати…'
  try {
    await printTapeSections([section], resolveLabelSize(size))
    status.textContent = 'Вызов печати выполнен. Проверьте этикетку на принтере.'
    timing.textContent += ` · возврат вызова печати: ${Math.round(performance.now() - receivedAt)} мс (включая время окна печати)`
  } catch (error) {
    status.textContent = error instanceof Error ? error.message : 'Не удалось открыть печать. Повторите кнопкой ниже.'
  } finally {
    printing = false
    reprint.disabled = false
    input.focus({ preventScroll: true })
  }
}

let draining = false
async function drain() {
  if (draining) return
  draining = true
  try {
    while (queue.length) {
      const item = queue.shift()!
      const label = findTestLabel(item.raw)
      const selected = label ? prepared.get(label.barcode) : undefined
      if (!selected) {
        status.textContent = `Неизвестный ШК: ${item.raw}. Используйте один из 10 кодов ниже.`
        continue
      }
      current = selected
      const started = performance.now()
      qrImage.src = selected.image
      qrValue.textContent = `${label!.barcode} → ${selected.qr}`
      result.hidden = false
      status.textContent = 'QR показан'
      timing.textContent = `Обновление QR: ${(performance.now() - started).toFixed(1)} мс · ожидание очереди: ${Math.round(started - item.receivedAt)} мс`
      // Give the displayed QR a paint opportunity before the browser print UI opens.
      await new Promise<void>((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve())))
      timing.textContent += ` · до кадра QR: ${Math.round(performance.now() - item.receivedAt)} мс`
      if (item.print) await invokePrint(selected.section, item.receivedAt, item.size)
    }
  } finally { draining = false }
}

function acceptScan(raw: string) {
  const value = raw.trim()
  if (!value) return
  queue.push({ raw: value, receivedAt: performance.now(), print: autoPrint.checked, size: sizeSelect.value as LabelSizeId })
  input.value = ''
  void drain()
}

document.querySelector('#scan-form')!.addEventListener('submit', (event) => {
  event.preventDefault()
  acceptScan(input.value)
})
reprint.addEventListener('click', async () => {
  if (!current || printing || draining) return
  draining = true
  try { await invokePrint(current.section, performance.now(), sizeSelect.value as LabelSizeId) }
  finally { draining = false; void drain() }
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
  } else if (event.key.length === 1) {
    buffer += event.key
  }
}, true)
input.focus()
