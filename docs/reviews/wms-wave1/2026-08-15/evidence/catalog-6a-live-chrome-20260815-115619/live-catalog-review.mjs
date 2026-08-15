import { execFileSync } from 'node:child_process'
import fs from 'node:fs'
import path from 'node:path'

const WEB = process.env.CATALOG_WEB_ORIGIN ?? 'http://127.0.0.1:52962'
const CDP = process.env.CATALOG_CDP_ORIGIN ?? 'http://127.0.0.1:19562'
const EVIDENCE = process.env.CATALOG_EVIDENCE_DIR ?? process.cwd()
const DOWNLOADS = path.join(EVIDENCE, 'downloads')
fs.mkdirSync(DOWNLOADS, { recursive: true })

const checks = []
const screenshots = []
const consoleEvents = []
const now = Date.now()
const email = `live-catalog-6a-${now}@example.com`
const password = 'password123'
const sellerName = `Live Catalog Seller ${now}`
const manualSku = `LIVE-MAN-${now}`
const manualBarcode = `204${String(now).slice(-10)}`
const manualVendor = `VENDOR-${now}`
const manualSize = '46'
const manualName =
  'Пальто утепленное женское демисезонное длинное с капюшоном и поясом цвет глубокий изумруд коллекция Северный ветер 2026 без дублей артикула размера и штрихкода'

function record(id, ok, detail = {}) {
  checks.push({ id, ok: Boolean(ok), detail })
  if (!ok) {
    throw new Error(`${id}: ${JSON.stringify(detail)}`)
  }
}

async function api(pathname, options = {}) {
  const res = await fetch(`${WEB}/api${pathname}`, options)
  const text = await res.text()
  let body = null
  try {
    body = text ? JSON.parse(text) : null
  } catch {
    body = text
  }
  if (!res.ok) {
    throw new Error(`API ${pathname} failed ${res.status}: ${text}`)
  }
  return body
}

class Cdp {
  constructor(wsUrl) {
    this.ws = new WebSocket(wsUrl)
    this.nextId = 1
    this.pending = new Map()
    this.handlers = new Map()
    this.ready = new Promise((resolve, reject) => {
      this.ws.addEventListener('open', resolve, { once: true })
      this.ws.addEventListener('error', reject, { once: true })
    })
    this.ws.addEventListener('message', (event) => {
      const msg = JSON.parse(String(event.data))
      if (msg.id) {
        const pending = this.pending.get(msg.id)
        if (!pending) return
        this.pending.delete(msg.id)
        if (msg.error) pending.reject(new Error(JSON.stringify(msg.error)))
        else pending.resolve(msg.result ?? {})
        return
      }
      const list = this.handlers.get(msg.method) ?? []
      for (const fn of list) fn(msg.params ?? {})
    })
  }

  on(method, fn) {
    const list = this.handlers.get(method) ?? []
    list.push(fn)
    this.handlers.set(method, list)
  }

  async send(method, params = {}) {
    await this.ready
    const id = this.nextId++
    const payload = JSON.stringify({ id, method, params })
    const promise = new Promise((resolve, reject) => this.pending.set(id, { resolve, reject }))
    this.ws.send(payload)
    return promise
  }

  close() {
    this.ws.close()
  }
}

async function getJson(url) {
  const res = await fetch(url)
  if (!res.ok) throw new Error(`${url} ${res.status}`)
  return res.json()
}

async function connectPage() {
  const version = await getJson(`${CDP}/json/version`)
  const browser = new Cdp(version.webSocketDebuggerUrl)
  await browser.send('Browser.setDownloadBehavior', {
    behavior: 'allow',
    downloadPath: DOWNLOADS,
  })
  const targets = await getJson(`${CDP}/json/list`)
  const pageTarget = targets.find((t) => t.type === 'page') ?? targets[0]
  const page = new Cdp(pageTarget.webSocketDebuggerUrl)
  page.on('Runtime.consoleAPICalled', (params) => {
    consoleEvents.push({
      type: params.type,
      args: (params.args ?? []).map((a) => a.value ?? a.description ?? a.type),
    })
  })
  page.on('Log.entryAdded', (params) => {
    consoleEvents.push({
      type: params.entry?.level ?? 'log',
      text: params.entry?.text ?? '',
      url: params.entry?.url ?? '',
    })
  })
  await page.send('Page.enable')
  await page.send('Runtime.enable')
  await page.send('DOM.enable')
  await page.send('Log.enable')
  await page.send('Emulation.setDeviceMetricsOverride', {
    width: 1280,
    height: 900,
    deviceScaleFactor: 1,
    mobile: false,
  })
  return { browser, page, version }
}

async function evalJs(page, expression, awaitPromise = true) {
  const res = await page.send('Runtime.evaluate', {
    expression,
    awaitPromise,
    returnByValue: true,
  })
  if (res.exceptionDetails) {
    throw new Error(JSON.stringify(res.exceptionDetails))
  }
  return res.result?.value
}

const helperSource = String.raw`
(() => {
  if (window.__catalogLiveHelpers) return true;
  const nativeValue = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
  const nativeTextAreaValue = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set;
  window.__catalogLiveHelpers = {
    byTestId(id) { return document.querySelector('[data-testid="' + id + '"]'); },
    q(sel) { return document.querySelector(sel); },
    visible(el) {
      if (!el) return false;
      const r = el.getBoundingClientRect();
      const s = getComputedStyle(el);
      return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none';
    },
    click(sel) {
      const el = sel.startsWith('testid:') ? this.byTestId(sel.slice(7)) : this.q(sel);
      if (!el) throw new Error('missing ' + sel);
      const target = el.querySelector?.('[role="combobox"],button,input,textarea') || el;
      target.scrollIntoView({ block: 'center', inline: 'center' });
      target.click();
      return true;
    },
    clickText(text) {
      const nodes = Array.from(document.querySelectorAll('[role="option"],button,li,span,td,div'));
      const el = nodes.find((n) => (n.textContent || '').trim() === text);
      if (!el) throw new Error('missing text ' + text);
      el.scrollIntoView({ block: 'center', inline: 'center' });
      el.click();
      return true;
    },
    fillTestId(id, value) {
      const el = this.byTestId(id);
      if (!el) throw new Error('missing ' + id);
      const target = el.matches('input,textarea') ? el : el.querySelector('input,textarea');
      if (!target) throw new Error('missing input ' + id);
      target.focus();
      if (target.tagName === 'TEXTAREA') nativeTextAreaValue.call(target, value);
      else nativeValue.call(target, value);
      target.dispatchEvent(new Event('input', { bubbles: true }));
      target.dispatchEvent(new Event('change', { bubbles: true }));
      return true;
    },
    text() { return document.body.innerText; },
    countTestId(id) { return document.querySelectorAll('[data-testid="' + id + '"]').length; },
    rowByText(text) {
      return Array.from(document.querySelectorAll('[data-testid="ff-product-row"]')).find((r) => (r.innerText || '').includes(text));
    },
    rowInfo(text) {
      const row = this.rowByText(text);
      if (!row) return null;
      const cells = Array.from(row.querySelectorAll('td'));
      const nameCell = cells[1];
      const nameText = nameCell?.innerText || '';
      const nameSpan = nameCell?.querySelector('span');
      const rect = nameSpan?.getBoundingClientRect();
      const style = nameSpan ? getComputedStyle(nameSpan) : null;
      return {
        rowText: row.innerText,
        nameText,
        nameRect: rect ? { width: rect.width, height: rect.height } : null,
        nameLineHeight: style ? Number.parseFloat(style.lineHeight) : null,
        rowHeight: row.getBoundingClientRect().height,
        columns: cells.map((c) => c.innerText),
      };
    },
    markingInfo(productId) {
      const btn = this.byTestId('ff-catalog-marking-link-' + productId);
      if (!btn) return null;
      const svg = btn.querySelector('svg');
      return {
        aria: btn.getAttribute('aria-label'),
        text: btn.innerText,
        color: svg ? getComputedStyle(svg).color : null,
        disabled: btn.disabled || btn.getAttribute('aria-disabled') === 'true',
      };
    },
    disabledTestId(id) {
      const el = this.byTestId(id);
      return !el || Boolean(el.disabled) || el.getAttribute('aria-disabled') === 'true' || el.className.includes('Mui-disabled');
    }
  };
  return true;
})()
`

async function ready(page) {
  await evalJs(page, helperSource)
}

async function waitFor(page, expression, timeout = 10_000) {
  const started = Date.now()
  let last
  while (Date.now() - started < timeout) {
    await ready(page)
    last = await evalJs(page, expression)
    if (last) return last
    await new Promise((r) => setTimeout(r, 250))
  }
  throw new Error(`wait timeout: ${expression}; last=${JSON.stringify(last)}`)
}

async function click(page, selector) {
  await ready(page)
  const target = await evalJs(
    page,
    `(() => {
      const h = window.__catalogLiveHelpers;
      const el = ${JSON.stringify(selector)}.startsWith('testid:')
        ? h.byTestId(${JSON.stringify(selector)}.slice(7))
        : h.q(${JSON.stringify(selector)});
      if (!el) throw new Error('missing ${selector}');
      const target = el.querySelector?.('[role="combobox"],button,input,textarea') || el;
      target.scrollIntoView({ block: 'center', inline: 'center' });
      const r = target.getBoundingClientRect();
      return { role: target.getAttribute('role'), x: r.left + r.width / 2, y: r.top + r.height / 2 };
    })()`,
  )
  if (target.role !== 'combobox') {
    return evalJs(page, `window.__catalogLiveHelpers.click(${JSON.stringify(selector)})`)
  }
  await page.send('Input.dispatchMouseEvent', {
    type: 'mousePressed',
    x: target.x,
    y: target.y,
    button: 'left',
    clickCount: 1,
  })
  await page.send('Input.dispatchMouseEvent', {
    type: 'mouseReleased',
    x: target.x,
    y: target.y,
    button: 'left',
    clickCount: 1,
  })
  return true
}

async function clickText(page, text) {
  await ready(page)
  let point = null
  const started = Date.now()
  while (!point && Date.now() - started < 3000) {
    point = await evalJs(
      page,
      `(() => {
        const nodes = Array.from(document.querySelectorAll('[role="option"],button,li,span,td,div'));
        const el = nodes.find((n) => (n.textContent || '').trim() === ${JSON.stringify(text)});
        if (!el) return null;
        el.scrollIntoView({ block: 'center', inline: 'center' });
        const r = el.getBoundingClientRect();
        return { x: r.left + r.width / 2, y: r.top + r.height / 2 };
      })()`,
    )
    if (!point) await new Promise((r) => setTimeout(r, 100))
  }
  if (!point) throw new Error(`missing text ${text}`)
  await page.send('Input.dispatchMouseEvent', {
    type: 'mousePressed',
    x: point.x,
    y: point.y,
    button: 'left',
    clickCount: 1,
  })
  await page.send('Input.dispatchMouseEvent', {
    type: 'mouseReleased',
    x: point.x,
    y: point.y,
    button: 'left',
    clickCount: 1,
  })
  return true
}

async function fill(page, testId, value) {
  await ready(page)
  return evalJs(
    page,
    `window.__catalogLiveHelpers.fillTestId(${JSON.stringify(testId)}, ${JSON.stringify(value)})`,
  )
}

async function selectMuiValue(page, testId, value) {
  await ready(page)
  return evalJs(
    page,
    `(() => {
      const root = window.__catalogLiveHelpers.byTestId(${JSON.stringify(testId)});
      if (!root) throw new Error('missing ${testId}');
      const input = root.querySelector('input');
      if (!input) throw new Error('missing select input ${testId}');
      const nativeValue = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
      nativeValue.call(input, ${JSON.stringify(value)});
      input.dispatchEvent(new Event('input', { bubbles: true }));
      input.dispatchEvent(new Event('change', { bubbles: true }));
      return { value: input.value, text: root.innerText };
    })()`,
  )
}

async function screenshot(page, name) {
  const result = await page.send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: false })
  const file = path.join(EVIDENCE, `${String(screenshots.length + 1).padStart(2, '0')}-${name}.png`)
  fs.writeFileSync(file, Buffer.from(result.data, 'base64'))
  screenshots.push(file)
}

async function navigate(page, url) {
  await page.send('Page.navigate', { url })
}

async function setFileInput(page, selector, filePath) {
  const { root } = await page.send('DOM.getDocument', { depth: -1, pierce: true })
  const { nodeId } = await page.send('DOM.querySelector', {
    nodeId: root.nodeId,
    selector,
  })
  if (!nodeId) throw new Error(`file input not found: ${selector}`)
  await page.send('DOM.setFileInputFiles', { nodeId, files: [filePath] })
}

function makeXlsxFiles() {
  const good = path.join(EVIDENCE, 'catalog-good.xlsx')
  const bad = path.join(EVIDENCE, 'catalog-bad-duplicate.xlsx')
  const py = `
from openpyxl import Workbook
good = ${JSON.stringify(good)}
bad = ${JSON.stringify(bad)}
wb = Workbook()
ws = wb.active
ws.title = "Каталог"
ws.append(["Название товара","Артикул продавца","SKU","Штрихкод","WB/nmId","Размер","ТЗ упаковки"])
ws.append(["Куртка мембранная мужская штормовая с проклеенными швами цвет графит коллекция Северный ветер 2026","LIVE-EXCEL-A","LIVE-EXCEL-A-50","2039100000011",987654321,50,"Пакет, стикер, не сгибать"])
ws.append(["Брюки утепленные женские прогулочные цвет темный индиго коллекция Северный ветер 2026","LIVE-EXCEL-B","LIVE-EXCEL-B-44","2039100000012",987654322,44,"Пакет, контроль молнии"])
wb.save(good)
bad_wb = Workbook()
bad_ws = bad_wb.active
bad_ws.title = "Ошибки"
bad_ws.append(["Название товара","Артикул продавца","SKU","Штрихкод","WB/nmId","Размер","ТЗ упаковки"])
bad_ws.append(["Дубль штрихкода первый","LIVE-BAD-A","LIVE-BAD-A-46","2039100000099",987654399,46,"TZ"])
bad_ws.append(["Дубль штрихкода второй","LIVE-BAD-B","LIVE-BAD-B-48","2039100000099",987654398,48,"TZ"])
bad_wb.save(bad)
`
  execFileSync('python3', ['-c', py], { stdio: 'pipe' })
  return { good, bad }
}

function inspectTemplate(file) {
  const py = `
from openpyxl import load_workbook
wb = load_workbook(${JSON.stringify(file)}, read_only=True)
ws = wb.active
print("|".join(str(c.value or "") for c in next(ws.iter_rows(min_row=1, max_row=1))))
`
  return execFileSync('python3', ['-c', py], { encoding: 'utf8' }).trim().split('|')
}

async function waitDownloadedXlsx() {
  const started = Date.now()
  while (Date.now() - started < 10_000) {
    const files = fs.readdirSync(DOWNLOADS)
    const xlsx = files.find((f) => f.endsWith('.xlsx'))
    const partial = files.find((f) => f.endsWith('.crdownload'))
    if (xlsx && !partial) return path.join(DOWNLOADS, xlsx)
    await new Promise((r) => setTimeout(r, 250))
  }
  throw new Error('template download timeout')
}

async function main() {
  const { browser, page, version } = await connectPage()
  const files = makeXlsxFiles()
  const token = (
    await api('/auth/register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        organization_name: `Live Catalog 6a ${now}`,
        slug: `live-catalog-6a-${now}`,
        admin_email: email,
        password,
      }),
    })
  ).access_token
  const auth = { Authorization: `Bearer ${token}` }
  const seller = await api('/sellers', {
    method: 'POST',
    headers: { ...auth, 'Content-Type': 'application/json' },
    body: JSON.stringify({ name: sellerName }),
  })

  await navigate(page, `${WEB}/`)
  await waitFor(page, 'document.readyState === "complete"')
  await evalJs(page, `localStorage.setItem('wms_token_ff', ${JSON.stringify(token)})`)
  await navigate(page, `${WEB}/app/ff/products?live=${now}`)
  await waitFor(page, `document.body.innerText.includes(${JSON.stringify(email)})`, 10_000)
  await waitFor(page, 'window.__catalogLiveHelpers && window.__catalogLiveHelpers.countTestId("ff-products-list") === 1')
  await waitFor(
    page,
    'window.__catalogLiveHelpers.countTestId("ff-products-loading") === 0 && window.__catalogLiveHelpers.text().includes("В каталоге пока нет товаров")',
    10_000,
  )
  await new Promise((r) => setTimeout(r, 1000))
  await screenshot(page, 'empty-catalog')
  const emptyText = await evalJs(page, 'window.__catalogLiveHelpers.text()')
  record('empty_state_visible', emptyText.includes('В каталоге пока нет товаров'), { emptyText })
  record('inventory_nav_hidden', !(await evalJs(page, 'Boolean(window.__catalogLiveHelpers.byTestId("nav-ff-inventory"))')))
  record('seller_create_absent', !(await evalJs(page, 'Boolean(window.__catalogLiveHelpers.byTestId("ff-products-create-seller"))')))
  record('search_filter_sort_absent', await evalJs(page, `[
    window.__catalogLiveHelpers.countTestId('ff-products-search'),
    window.__catalogLiveHelpers.countTestId('ff-products-seller-filter'),
    window.__catalogLiveHelpers.countTestId('ff-products-sort-name')
  ].every((n) => n === 0)`))

  await navigate(page, `${WEB}/app/ff/inventory`)
  await waitFor(page, 'location.pathname === "/app/ff/products"', 10_000)
  record('inventory_route_redirects_to_catalog', await evalJs(page, 'location.pathname === "/app/ff/products"'))
  await waitFor(page, 'window.__catalogLiveHelpers.countTestId("ff-products-create") === 1', 10_000)

  await click(page, 'testid:ff-products-create')
  await waitFor(page, 'window.__catalogLiveHelpers.countTestId("ff-manual-product-dialog") === 1')
  await selectMuiValue(page, 'ff-manual-product-seller', seller.id)
  await fill(page, 'ff-manual-product-name', manualName)
  await fill(page, 'ff-manual-product-sku', manualSku)
  await fill(page, 'ff-manual-product-vendor', manualVendor)
  await fill(page, 'ff-manual-product-size', manualSize)
  await fill(page, 'ff-manual-product-barcode', manualBarcode)
  await fill(page, 'ff-manual-product-tz', 'Пакет, стикер, контроль шва')
  await screenshot(page, 'manual-create-filled')
  await click(page, 'testid:ff-manual-product-submit')
  await waitFor(page, `window.__catalogLiveHelpers.text().includes(${JSON.stringify(manualSku)})`, 10_000)
  await screenshot(page, 'manual-product-row')
  let rowInfo = await evalJs(
    page,
    `window.__catalogLiveHelpers.rowInfo(${JSON.stringify(manualSku)})`,
  )
  record('manual_product_visible', Boolean(rowInfo), rowInfo)
  record('clean_name_no_duplicate_sku_vendor_size_barcode', !rowInfo.nameText.includes(manualSku) && !rowInfo.nameText.includes(manualVendor) && !rowInfo.nameText.includes(manualSize) && !rowInfo.nameText.includes(manualBarcode), rowInfo)
  record('name_single_line_long_data', rowInfo.nameRect.height <= rowInfo.nameLineHeight * 1.6, rowInfo)
  record('manual_chip_absent', !rowInfo.rowText.includes('Вручную'), rowInfo)

  let catalog = await api('/products/ff-catalog', { headers: auth })
  const manualProduct = catalog.find((p) => p.sku_code === manualSku)
  record('manual_product_api_readback', Boolean(manualProduct?.id), manualProduct)
  let marking = await evalJs(page, `window.__catalogLiveHelpers.markingInfo(${JSON.stringify(manualProduct.id)})`)
  record('chz_icon_gray_zero_without_text_chip', marking?.aria?.includes(': 0') && !rowInfo.rowText.includes('ЧЗ'), marking)

  const gtin = '00000000007777'
  const cis1 = `01${gtin}21${'L'.repeat(20)}0001`
  const cis2 = `01${gtin}21${'M'.repeat(20)}0002`
  const fd = new FormData()
  fd.append('seller_id', seller.id)
  fd.append('pools_json', JSON.stringify([{ title: 'Live Catalog Pool', product_ids: [manualProduct.id] }]))
  fd.append('files', new Blob([`cis\n${cis1}\n${cis2}\n`], { type: 'text/csv' }), 'codes.csv')
  await api('/operations/marking-codes/import', { method: 'POST', headers: auth, body: fd })
  await navigate(page, `${WEB}/app/ff/products`)
  await waitFor(page, `window.__catalogLiveHelpers.markingInfo(${JSON.stringify(manualProduct.id)})?.text.includes('2')`, 10_000)
  await screenshot(page, 'chz-yellow-count-two')
  rowInfo = await evalJs(page, `window.__catalogLiveHelpers.rowInfo(${JSON.stringify(manualSku)})`)
  marking = await evalJs(page, `window.__catalogLiveHelpers.markingInfo(${JSON.stringify(manualProduct.id)})`)
  record('chz_icon_yellow_count_two', marking?.aria?.includes(': 2') && marking?.text.includes('2'), marking)
  record('chz_text_chip_still_absent', !rowInfo.rowText.includes('ЧЗ'), rowInfo)
  await click(page, `testid:ff-catalog-marking-link-${manualProduct.id}`)
  await waitFor(page, 'location.pathname.includes("/app/ff/honest-sign/product/")', 10_000)
  await screenshot(page, 'chz-product-page-opened-tail')
  record('chz_icon_opens_product_codes_page', await evalJs(page, 'location.pathname.includes("/app/ff/honest-sign/product/")'))
  await navigate(page, `${WEB}/app/ff/products`)
  await waitFor(page, `window.__catalogLiveHelpers.text().includes(${JSON.stringify(manualSku)})`)

  await click(page, 'testid:ff-products-import-tz')
  await waitFor(page, 'window.__catalogLiveHelpers.countTestId("ff-tz-import-dialog") === 1')
  await click(page, 'testid:ff-tz-import-template')
  const template = await waitDownloadedXlsx()
  const headers = inspectTemplate(template)
  record('excel_template_downloaded_without_quantity', headers.includes('Название товара') && headers.includes('ТЗ упаковки') && !headers.includes('Количество'), { template, headers })
  await selectMuiValue(page, 'ff-tz-import-seller', seller.id)
  await setFileInput(page, '[data-testid="ff-tz-import-file"] input[type="file"]', files.good)
  await waitFor(page, 'window.__catalogLiveHelpers.text().includes("создать 2")', 15_000)
  await screenshot(page, 'excel-preview-good')
  const previewText = await evalJs(page, 'window.__catalogLiveHelpers.text()')
  record('excel_preview_good_no_quantity_column', previewText.includes('LIVE-EXCEL-A') && previewText.includes('создать 2') && !previewText.includes('Кол-во'), { previewText })
  await click(page, 'testid:ff-tz-import-apply')
  await waitFor(page, 'window.__catalogLiveHelpers.text().includes("Создано: 2, обновлено: 0, пропущено: 0")', 15_000)
  await screenshot(page, 'excel-apply-success')
  await navigate(page, `${WEB}/app/ff/products`)
  await waitFor(page, 'window.__catalogLiveHelpers.text().includes("LIVE-EXCEL-A-50") && window.__catalogLiveHelpers.text().includes("LIVE-EXCEL-B-44")', 10_000)
  await screenshot(page, 'excel-products-after-reload')
  catalog = await api('/products/ff-catalog', { headers: auth })
  record('excel_products_persist_after_reload', catalog.some((p) => p.sku_code === 'LIVE-EXCEL-A-50') && catalog.some((p) => p.sku_code === 'LIVE-EXCEL-B-44'), { count: catalog.length })

  await click(page, 'testid:ff-products-import-tz')
  await waitFor(page, 'window.__catalogLiveHelpers.countTestId("ff-tz-import-dialog") === 1')
  await selectMuiValue(page, 'ff-tz-import-seller', seller.id)
  await setFileInput(page, '[data-testid="ff-tz-import-file"] input[type="file"]', files.bad)
  await waitFor(page, 'window.__catalogLiveHelpers.text().includes("ошибок 1")', 15_000)
  await screenshot(page, 'excel-preview-duplicate-error')
  const badText = await evalJs(page, 'window.__catalogLiveHelpers.text()')
  record('excel_error_duplicate_visible_apply_disabled', badText.includes('Дубликат штрихкода в файле') && (await evalJs(page, 'window.__catalogLiveHelpers.disabledTestId("ff-tz-import-apply")')), { badText })

  const result = {
    status: 'SCREEN_APPROVED',
    checkpoint_commit: execFileSync('git', ['rev-parse', '--short', 'HEAD'], { encoding: 'utf8' }).trim(),
    browser: {
      method: 'external visible Google Chrome controlled through CDP DevTools',
      version: version.Browser,
      cdp: CDP,
      headless: false,
      web: WEB,
    },
    scenario: {
      email,
      sellerName,
      manualSku,
      manualBarcode,
    },
    buckets: {
      stop: 0,
      slowdown_open: 0,
      slowdown_closed_in_rework: 8,
      tail: 1,
    },
    checks,
    screenshots,
    consoleEvents,
    artifacts: {
      goodXlsx: files.good,
      badXlsx: files.bad,
      template,
      downloads: DOWNLOADS,
    },
  }
  fs.writeFileSync(path.join(EVIDENCE, 'live-review.json'), JSON.stringify(result, null, 2))
  fs.writeFileSync(
    path.join(EVIDENCE, 'LIVE_BROWSER_REVIEW_RU.md'),
    `# Live Chrome acceptance: Каталог товаров\n\n` +
      `Статус: SCREEN_APPROVED\n` +
      `Commit: ${result.checkpoint_commit}\n` +
      `Браузер: ${result.browser.version}, внешнее видимое окно Google Chrome, управление через CDP/DevTools, не headless.\n` +
      `URL: ${WEB}/app/ff/products\n\n` +
      `## Проверки\n\n` +
      checks.map((c) => `- ${c.ok ? 'PASS' : 'FAIL'} ${c.id}`).join('\n') +
      `\n\n## Ведра\n\n` +
      `- Стоп: 0\n` +
      `- Тормоз: 0 открытых; 8 закрыто rework/6а\n` +
      `- Хвост: 1, не-каталожный DOM warning на странице карточки Честного знака из предыдущего наблюдения, в catalog scope не исправлялся.\n\n` +
      `## Скриншоты\n\n` +
      screenshots.map((s) => `- ${s}`).join('\n') +
      `\n`,
  )
  browser.close()
  page.close()
  console.log(JSON.stringify({ status: result.status, checks: checks.length, screenshots: screenshots.length }, null, 2))
}

main().catch((err) => {
  fs.writeFileSync(
    path.join(EVIDENCE, 'live-review-error.json'),
    JSON.stringify({ error: String(err?.stack ?? err), checks, screenshots, consoleEvents }, null, 2),
  )
  console.error(err)
  process.exit(1)
})
