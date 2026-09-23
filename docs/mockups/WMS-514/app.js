const initialOrders = [
  { id: '1', order: '7428150391', product: 'Платье женское миди с поясом', article: 'LVN-DRS-042', barcode: '4680012345001', size: 'M', stickerHead: 'WB-392', stickerTail: '8175', stock: 6, kiz: null, printed: false, selected: false, state: '', tone: '' },
  { id: '2', order: '7428150448', product: 'Платье женское миди с поясом', article: 'LVN-DRS-042', barcode: '4680012345001', size: 'L', stickerHead: 'WB-392', stickerTail: '8291', stock: 5, kiz: '…91AF', printed: true, selected: false, state: 'ЧЗ привязан · принят WB', tone: '' },
  { id: '3', order: '7428150522', product: 'Худи оверсайз с начёсом', article: 'LVN-HDY-118', barcode: '4680012345094', size: 'S', stickerHead: 'WB-418', stickerTail: '0342', stock: 3, kiz: null, printed: false, selected: false, state: '', tone: '' },
  { id: '4', order: '7428150609', product: 'Лонгслив базовый хлопковый', article: 'LVN-LNG-007', barcode: '4680012345186', size: 'ONE SIZE', stickerHead: 'WB-418', stickerTail: '0468', stock: 2, kiz: null, printed: false, selected: false, state: '', tone: '' },
]

let orders = structuredClone(initialOrders)
let activeOrderId = null
let waitingForKiz = false
let busy = false
let printTarget = null

const ordersNode = document.querySelector('#orders')
const scanForm = document.querySelector('#scan-form')
const scanCode = document.querySelector('#scan-code')
const scanMessage = document.querySelector('#scan-message')
const printQr = document.querySelector('#print-qr')
const printKiz = document.querySelector('#print-kiz')
const printDialog = document.querySelector('#print-dialog')

const saved = JSON.parse(localStorage.getItem('wms514-current-screen-settings') || 'null')
if (saved) {
  printQr.checked = Boolean(saved.qr)
  printKiz.checked = Boolean(saved.kiz)
}

function saveSettings() {
  localStorage.setItem('wms514-current-screen-settings', JSON.stringify({ qr: printQr.checked, kiz: printKiz.checked }))
}

printQr.addEventListener('change', saveSettings)
printKiz.addEventListener('change', saveSettings)

function escapeHtml(value) {
  return String(value).replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;').replaceAll("'", '&#039;')
}

function render() {
  ordersNode.innerHTML = orders.map((item) => `
    <div class="order-row ${item.id === activeOrderId ? 'active' : ''} ${item.tone}" data-order="${item.id}">
      <input class="order-select" type="checkbox" aria-label="Выбрать заказ ${item.order}" data-select="${item.id}" ${item.selected ? 'checked' : ''} />
      <div class="product-photo">${item.product[0]}</div>
      <div class="order-product">
        <strong>${escapeHtml(item.product)}</strong>
        <span>${item.article} · ${item.barcode} · заказ ${item.order}</span>
        ${item.state ? `<span class="row-state ${item.tone === 'error' ? 'error-text' : ''}">${escapeHtml(item.state)}</span>` : ''}
      </div>
      <div class="size-cell"><span class="cell-label">Размер</span><span class="cell-value">${item.size}</span></div>
      <div class="marking-stock"><span class="cell-label">Доступно ЧЗ</span><span class="cell-value">${item.stock} · нужно 1</span></div>
      <div class="sticker-cell"><span class="cell-label">Стикер</span><span class="cell-value sticker-code">${item.stickerHead} <b>${item.stickerTail}</b></span></div>
      <div class="kiz-cell"><span class="cell-label">ЧЗ</span><span class="cell-value ${item.kiz ? 'kiz-code' : ''}">${item.kiz || '—'}</span></div>
      <div class="printed-check">${item.printed ? '✓' : ''}</div>
      <div class="row-actions">
        <button data-action="tz" data-id="${item.id}">ТЗ</button>
        <button data-action="qr" data-id="${item.id}">QR</button>
        <button class="icon" data-action="print" data-id="${item.id}" aria-label="Печать ЧЗ и ШК">▣</button>
        <button class="icon" data-action="more" data-id="${item.id}" aria-label="Перепечатать">⋮</button>
      </div>
    </div>
  `).join('')

  const printed = orders.filter((item) => item.printed).length
  document.querySelector('#printed-count').textContent = String(printed)
  document.querySelector('#ready-count').textContent = String(printed)
  document.querySelector('.progress span').style.width = `${printed / orders.length * 100}%`
  const selected = orders.filter((item) => item.selected).length
  document.querySelector('#select-all').textContent = selected === orders.length ? 'Снять выбор' : 'Выбрать всё'
  document.querySelector('#print-selected').textContent = selected ? `Печать выбранного (${selected})` : `Печать всего (${orders.length})`
}

function message(text, tone = '') {
  scanMessage.textContent = text
  scanMessage.className = `scan-message ${tone}`
}

function toast(text) {
  const node = document.querySelector('#toast')
  node.textContent = text
  node.hidden = false
  setTimeout(() => { node.hidden = true }, 2200)
}

function setBusy(value) {
  busy = value
  scanCode.disabled = value
  printQr.disabled = value
  printKiz.disabled = value
}

function sleep(ms) { return new Promise((resolve) => setTimeout(resolve, ms)) }

async function processProductBarcode(code) {
  const sameProduct = orders.filter((item) => item.barcode === code)
  if (!sameProduct.length) return false

  const item = sameProduct.find((order) => !order.tone) || sameProduct[0]
  activeOrderId = item.id
  item.tone = 'active'
  item.state = 'Заказ выбран по ШК товара'
  render()

  const qrEnabled = printQr.checked
  const kizEnabled = printKiz.checked
  if (!qrEnabled && !kizEnabled) {
    item.tone = ''
    item.state = 'Заказ выбран · автопечать выключена'
    message(`Заказ WB № ${item.order} выбран. Обе галочки выключены — печать не запускалась.`, 'success')
    render()
    return true
  }

  setBusy(true)
  message(`Заказ WB № ${item.order} выбран — запускаем выбранную печать.`)
  await sleep(650)
  if (qrEnabled) item.printed = true
  if (kizEnabled && !item.kiz) {
    item.kiz = `…${7100 + Number(item.id) * 17}`
    item.stock -= 1
  }
  item.tone = 'success'
  item.state = [qrEnabled ? 'QR отправлен на принтер' : '', kizEnabled ? 'ЧЗ отправлен на принтер' : ''].filter(Boolean).join(' · ')
  message(`Заказ WB № ${item.order}: ${item.state}.`, 'success')
  setBusy(false)
  render()
  scanCode.focus()
  return true
}

function beginExistingFlow(item) {
  activeOrderId = item.id
  waitingForKiz = true
  item.tone = 'active'
  item.state = 'QR заказа принят · ожидается Честный знак'
  scanCode.value = ''
  scanCode.placeholder = 'Сканируйте Честный знак'
  message(`Заказ WB № ${item.order} активен — сканируйте Честный знак, код уйдёт на проверку в WB.`)
  render()
  scanCode.focus()
}

async function finishExistingFlow(code) {
  const item = orders.find((order) => order.id === activeOrderId)
  if (!item) return
  setBusy(true)
  message(`Проверяем ЧЗ для заказа WB № ${item.order}…`)
  await sleep(600)
  item.kiz = `…${code.slice(-4).toUpperCase()}`
  item.tone = 'success'
  item.state = 'ЧЗ привязан · принят WB'
  waitingForKiz = false
  activeOrderId = null
  scanCode.value = ''
  scanCode.placeholder = 'Сканируйте QR стикера заказа'
  setBusy(false)
  message(`ЧЗ внесён в заказ WB № ${item.order}.`, 'success')
  render()
  scanCode.focus()
}

scanForm.addEventListener('submit', async (event) => {
  event.preventDefault()
  if (busy) return
  const code = scanCode.value.trim()
  if (!code) return
  if (waitingForKiz) {
    await finishExistingFlow(code)
    return
  }
  if (await processProductBarcode(code)) {
    scanCode.select()
    return
  }
  const order = orders.find((item) => `WB-${item.order}` === code.toUpperCase())
  if (order) {
    beginExistingFlow(order)
    return
  }
  message('Скан не найден в текущей поставке. Печать не запущена.', 'error')
})

ordersNode.addEventListener('change', (event) => {
  const input = event.target.closest('[data-select]')
  if (!input) return
  const item = orders.find((order) => order.id === input.dataset.select)
  if (item) item.selected = input.checked
  render()
})

ordersNode.addEventListener('click', (event) => {
  const button = event.target.closest('[data-action]')
  if (!button) return
  const item = orders.find((order) => order.id === button.dataset.id)
  if (!item) return
  if (button.dataset.action === 'qr') openPrint(item, 'qr')
  else if (button.dataset.action === 'print') openPrint(item, item.kiz ? 'kiz' : 'construct')
  else if (button.dataset.action === 'more') toast(`Действия перепечати для заказа ${item.order}`)
  else toast(`Техническое задание для ${item.product}`)
})

document.querySelector('#select-all').addEventListener('click', () => {
  const all = orders.every((item) => item.selected)
  orders.forEach((item) => { item.selected = !all })
  render()
})

document.querySelector('#print-selected').addEventListener('click', () => {
  const selected = orders.filter((item) => item.selected)
  const targets = selected.length ? selected : orders
  targets.forEach((item) => { item.printed = true })
  toast(`QR отправлены на принтер: ${targets.length}`)
  render()
})

document.querySelector('#pack-all').addEventListener('click', () => toast('Существующее действие «Всё упаковано» не изменено'))

function openPrint(item, type) {
  printTarget = { item, type }
  const title = document.querySelector('#dialog-title')
  const preview = document.querySelector('#label-preview')
  const text = document.querySelector('#dialog-text')
  if (type === 'qr') {
    title.textContent = 'Печать QR заказа'
    preview.innerHTML = `<div><span>WB · заказ ${item.order}</span><strong>${item.stickerHead} ${item.stickerTail}</strong><div class="bars"></div></div>`
    text.textContent = 'Будет напечатана одна копия стикера этого заказа.'
  } else if (type === 'kiz') {
    title.textContent = 'Перепечатать Честный знак'
    preview.innerHTML = `<div><span>ЧЕСТНЫЙ ЗНАК</span><strong>${item.kiz}</strong><div class="bars"></div></div>`
    text.textContent = 'Используется уже привязанный код. Новый ЧЗ не выдаётся.'
  } else {
    title.textContent = 'Печать ЧЗ и ШК'
    preview.innerHTML = `<div><span>${item.product}</span><strong>${item.barcode}</strong><div class="bars"></div></div>`
    text.textContent = 'Существующий конструктор печати работает независимо от новых галочек.'
  }
  printDialog.showModal()
}

document.querySelector('#dialog-confirm').addEventListener('click', () => {
  if (!printTarget) return
  if (printTarget.type === 'qr') printTarget.item.printed = true
  toast('Задание отправлено на принтер')
  render()
  printTarget = null
})

printDialog.addEventListener('click', (event) => { if (event.target === printDialog) printDialog.close() })

render()
scanCode.focus()
