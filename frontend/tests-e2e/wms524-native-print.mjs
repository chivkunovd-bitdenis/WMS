const { chromium } = await import(process.env.PLAYWRIGHT_MODULE || 'playwright');
const acceptBatch = process.env.CANCEL_BATCH !== '1';
const browser = await chromium.launch({ channel: 'chrome', headless: false });
try {
  const diagnosticCdp = await browser.newBrowserCDPSession();
  const context = await browser.newContext();
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  let confirmations = 0;
  page.on('dialog', async d => {
    confirmations += 1;
    if (context.pages().length !== 1) throw new Error('Print popup opened before batch confirmation');
    console.log('CONFIRM_BEFORE_POPUP ' + d.message());
    if (acceptBatch) await d.accept(); else await d.dismiss();
  });
  await page.route('**/api/**', route => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ separate_marking_print: false, codes: [] }) }));
  await page.route('**/test-qr.png', route => route.fulfill({ contentType: 'image/png', body: Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4z8DwHwAFgAI/ScLbtAAAAABJRU5ErkJggg==', 'base64') }));
  await page.goto(process.env.WMS_TEST_URL || 'http://127.0.0.1:15244/');
  await page.evaluate(async () => {
    const { default: React } = await import('/node_modules/.vite/deps/react.js');
    const { default: ReactDOM } = await import('/node_modules/.vite/deps/react-dom_client.js');
    const { createRoot } = ReactDOM;
    const { MarkingPrintDialog } = await import('/src/components/MarkingPrintDialog.tsx');
    const label = { barcode: '2037100575556', product_name: 'Тест печати FBS', sku_code: 'LEG_BL_AVL', wb_brand: 'Fadin', wb_size: '58/60' };
    const ctx = {
      token: 'local-fixture', productId: 'test', documentNumber: 'FBS 23.09.2026',
      qtyNeedPack: 58, markingAvailable: 368, qtyMarkingPrinted: 58,
      requiresHonestSign: true, skuCode: 'LEG_BL_AVL', productName: 'Тест печати FBS', productLabel: label,
      onPrinted: () => { window.__printed = true; },
      fbsTape: {
        orders: Array.from({ length: 58 }, (_, i) => ({ orderId: 'test-order-' + i, wbOrderId: 123 + i, marketplace: 'wb', requiresHonestSign: true, productLabel: label })),
        includeOrderQr: true,
        print: async () => { window.__fixtureRequests = (window.__fixtureRequests || 0) + 1; return ({ orders: Array.from({ length: 58 }, (_, i) => ({ order_id: 'test-order-' + i, wb_order_id: 123 + i, requires_honest_sign: true, qr_asset: { preview_url: '/test-qr.png', applied_at: '2026-09-24' },
          printed_codes: [{ id: 'test-code-' + i, cis_code: '010460000000000121AAAAAAAAAAAAAAAAAAAA0001', has_label_artifact: false, order_product_id: null }] })), order_errors: [], shortage: 0 }); },
        confirmQrApplied: async () => {},
      },
    };
    const host = document.createElement('div'); document.body.appendChild(host);
    createRoot(host).render(React.createElement(MarkingPrintDialog, { open: true, reprint: false, ctx, busy: false, onBusyChange: () => {}, onClose: () => { window.__dialogClosed = true; } }));
  });
  await page.getByTestId('marking-print-cz-qty').locator('input').fill('3');
  await page.getByTestId('marking-print-wb-qty').locator('input').fill('3');
  await page.getByTestId('marking-print-confirm').click();
  if (confirmations !== 1) throw new Error('Expected large-batch confirmation');
  if (!acceptBatch) {
    const calls = await page.evaluate(() => window.__fixtureRequests || 0);
    if (calls !== 0 || context.pages().length !== 1) throw new Error('Cancel opened popup or called API');
    console.log('PASS: cancel has no popup and no print request');
  } else {
    let preview = false;
    for (let attempt = 0; attempt < 50; attempt += 1) {
      const { targetInfos } = await diagnosticCdp.send('Target.getTargets');
      preview = targetInfos.some(t => t.url === 'chrome://print/') &&
        targetInfos.some(t => t.url.startsWith('chrome-untrusted://print/') && t.url.endsWith('/print.pdf'));
      if (preview) break;
      await new Promise(resolve => setTimeout(resolve, 200));
    }
    if (!preview) throw new Error('Native Chrome print preview/PDF did not open');
    console.log('PASS: 58-order batch opens native Chrome print preview and PDF');
  }
  if (errors.length) throw new Error(errors.join('\n'));
} finally { await browser.close(); }

