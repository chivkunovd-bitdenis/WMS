import puppeteer from 'puppeteer-core'
import { mkdirSync, writeFileSync } from 'node:fs'
import { execFileSync } from 'node:child_process'
import assert from 'node:assert/strict'
const out = process.env.WMS673_PROOF_DIR
mkdirSync(out, { recursive: true })
const browser = await puppeteer.launch({
  executablePath: '/usr/bin/google-chrome', headless: false,
  ignoreDefaultArgs: ['--disable-print-preview'],
  args: ['--no-sandbox', '--window-size=1600,1000', '--enable-print-preview', '--no-first-run'],
  defaultViewport: { width: 1500, height: 900 },
})
const evidence = { browser: await browser.version(), source: process.env.WMS_SOURCE_SHA, cases: [] }
try {
  for (const kind of ['single', 'group']) {
    const page = await browser.newPage()
    const errors = []
    page.on('pageerror', e => errors.push(e.message))
    // Popup stays real; capture the product's automatic print call before device dispatch.
    await page.evaluateOnNewDocument(() => {
      const originalOpen = window.open
      window.open = function(...args) {
        const popup = originalOpen.apply(this, args)
        if (popup) {
          popup.__nativePrint = popup.print.bind(popup)
          popup.print = () => { popup.__printCalls = (popup.__printCalls ?? 0) + 1 }
        }
        return popup
      }
    })
    await page.goto(`http://127.0.0.1:5173/acceptance/index.html?kind=${kind}`)
    await page.waitForSelector('[data-testid="fbs-pick-list-print"]', { timeout: 60000 })
    await page.waitForFunction(() => !document.querySelector('[data-testid="fbs-pick-list-print"]').disabled)
    await page.screenshot({ path: `${out}/${kind}-actual-component.png` })
    const repeats = []
    for (let repeat = 1; repeat <= 2; repeat++) {
      const targetPromise = browser.waitForTarget(t => t.opener() === page.target())
      await page.click('[data-testid="fbs-pick-list-print"]')
      const popup = await (await targetPromise).page()
      await popup.waitForFunction(() => window.__printCalls === 1 && document.querySelectorAll('thead th').length === 11)
      await popup.evaluate(() => document.fonts.ready)
      const content = await popup.evaluate(() => ({
        headers: [...document.querySelectorAll('thead th')].map(t => t.textContent),
        rows: [...document.querySelectorAll('tbody tr')].map(tr => [...tr.children].map(td => td.textContent)),
        sizeStyle: { width: getComputedStyle(document.querySelector('td.size')).width, fontSize: getComputedStyle(document.querySelector('td.size')).fontSize },
        printCalls: window.__printCalls,
      }))
      assert.equal(content.headers.length, 11)
      assert.deepEqual(content.headers.slice(3, 6), ['Размер', 'Цвет', 'Ячейка / тара'])
      assert.equal(content.rows[0][3], 'Универсальный')
      assert.equal(content.rows[0][4], 'Красный & синий насыщенный длинный цвет')
      assert.equal(content.sizeStyle.fontSize, '20px')
      if (kind === 'group') {
        assert.equal(content.rows.length, 4)
        assert.deepEqual(content.rows.slice(2).map(r => r[4]), ['Красный', 'Синий'])
      } else assert.equal(content.rows.length, 2)
      writeFileSync(`${out}/${kind}-${repeat}.html`, await popup.content())
      await popup.screenshot({ path: `${out}/${kind}-${repeat}-popup.png`, fullPage: true })
      await popup.pdf({ path: `${out}/${kind}-${repeat}.pdf`, preferCSSPageSize: true, printBackground: true })
      // Open genuine Chromium print preview, then cancel without printing.
      const previewPromise = browser.waitForTarget(t => t.url().startsWith('chrome://print'), { timeout: 30000 })
      await popup.evaluate(() => { setTimeout(() => window.__nativePrint(), 0) })
      const previewTarget = await previewPromise
      // Chromium exposes its native print UI as target type `other`, not `page`.
      const session = await previewTarget.createCDPSession()
      const evaluatePreview = async (fn) => {
        const value = await session.send('Runtime.evaluate', { expression: `(${fn.toString()})()`, returnByValue: true, awaitPromise: true })
        if (value.exceptionDetails) throw new Error(JSON.stringify(value.exceptionDetails))
        return value.result.value
      }
      // The C7 scenario explicitly asks for A4 landscape in native preview.
      // Select that paper ticket in the isolated browser, before photographing it.
      await evaluatePreview(() => {
        const app = document.querySelector('print-preview-app')
        app.setSetting('mediaSize', { width_microns: 210000, height_microns: 297000,
          name: 'ISO_A4', custom_display_name: 'A4' })
        app.setSetting('layout', true)
      })
      const previewReady = () => {
        const app = document.querySelector('print-preview-app')
        const area = app?.shadowRoot?.querySelector('print-preview-preview-area')
        return area && area.previewState === 'display-preview'
      }
      let ready = false
      for (let attempt = 0; attempt < 120; attempt++) {
        if (await evaluatePreview(previewReady)) { ready = true; break }
        await new Promise(resolve => setTimeout(resolve, 500))
      }
      await new Promise(resolve => setTimeout(resolve, 1000))
      execFileSync('import', ['-window', 'root', `${out}/${kind}-${repeat}-native-preview.png`])
      const previewState = await evaluatePreview(() => {
        const app = document.querySelector('print-preview-app')
        const area = app.shadowRoot.querySelector('print-preview-preview-area')
        const deepText = root => [...root.children].map(e => e.shadowRoot ? deepText(e.shadowRoot) : e.children.length ? deepText(e) : e.textContent).join(' ')
        return { title: document.title, url: location.href, previewState: area.previewState,
          layout: app.getSettingValue?.('layout'), mediaSize: app.getSettingValue?.('mediaSize'),
          documentInfo: app.documentInfo_ ?? app.documentInfo,
          previewDocumentInfo: area.documentInfo_ ?? area.documentInfo,
          infoKeys: Object.keys(app).filter(k => /document|page|layout/i.test(k)),
          text: deepText(app.shadowRoot) }
      })
      writeFileSync(`${out}/${kind}-${repeat}-preview.json`, JSON.stringify(previewState, null, 2))
      assert(ready, `Native print preview failed to become ready: ${JSON.stringify(previewState)}`)
      assert.equal(previewState.mediaSize.width_microns, 210000)
      assert.equal(previewState.mediaSize.height_microns, 297000)
      assert.equal(previewState.layout, true)
      await evaluatePreview(() => {
        // Return the protocol response before the Cancel action destroys this target.
        setTimeout(() => document.querySelector('print-preview-app').shadowRoot.querySelector('print-preview-sidebar').shadowRoot.querySelector('print-preview-button-strip').shadowRoot.querySelector('.cancel-button').click(), 0)
      })
      await browser.waitForTarget(t => t === popup.target())
      for (let attempt = 0; browser.targets().includes(previewTarget) && attempt < 100; attempt++) {
        await new Promise(resolve => setTimeout(resolve, 100))
      }
      assert(!browser.targets().includes(previewTarget), 'Cancel must close the native preview')
      await popup.close()
      repeats.push(content)
    }
    assert.deepEqual(repeats[0], repeats[1])
    const transport = await page.evaluate(() => ({ requests: window.acceptance.requests, unchanged: JSON.stringify(window.acceptance.fixtures) === window.acceptance.before }))
    assert.equal(transport.unchanged, true)
    assert(transport.requests.every(r => r.method === 'GET'))
    assert.equal(errors.length, 0, JSON.stringify(errors))
    evidence.cases.push({ kind, repeats, transport, errors })
    await page.close()
  }
  evidence.pass = true
} finally {
  writeFileSync(`${out}/browser-proof.json`, JSON.stringify(evidence, null, 2))
  await browser.close()
}
