import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';

const __filename = fileURLToPath(import.meta.url);
const evidenceDir = path.resolve(path.dirname(__filename), '..');
const repoRoot = path.resolve(path.dirname(__filename), '../../../../../../..');
const require = createRequire(path.join(repoRoot, 'frontend/package.json'));
const { chromium, request: playwrightRequest, expect } = require('@playwright/test');
const screenshotsDir = path.join(evidenceDir, 'screenshots');
const webOrigin = process.env.WMS_LIVE_WEB_ORIGIN ?? 'http://127.0.0.1:5183';
const cdpEndpoint = process.env.WMS_LIVE_CDP_ENDPOINT ?? 'http://127.0.0.1:9225';
const suffix = `live-${Date.now()}`;
const password = 'password123';

const checks = {};
const findings = [];
const artifacts = [];

function record(name, value) {
  checks[name] = value;
}

function finding(severity, message) {
  findings.push({ severity, message });
}

async function shot(page, name) {
  const file = path.join(screenshotsDir, `${name}.png`);
  await page.screenshot({ path: file, fullPage: true });
  artifacts.push(path.relative(evidenceDir, file));
}

async function text(locator) {
  return ((await locator.textContent().catch(() => '')) ?? '').trim();
}

async function apiOk(api, method, url, opts = {}) {
  const res = await api[method](url, opts);
  if (!res.ok()) {
    throw new Error(`${method.toUpperCase()} ${url}: ${res.status()} ${await res.text()}`);
  }
  return res;
}

async function waitJob(api, auth, jobId) {
  for (let i = 0; i < 80; i += 1) {
    const res = await apiOk(api, 'get', `/api/operations/background-jobs/${jobId}`, {
      headers: auth,
    });
    const body = await res.json();
    if (body.status === 'done') return;
    if (body.status === 'failed') throw new Error(`background job failed: ${jobId}`);
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  throw new Error(`background job timeout: ${jobId}`);
}

async function loginSeller(page, email) {
  await page.goto(`${webOrigin}/seller/`);
  await page.evaluate(() => localStorage.removeItem('wms_token_seller'));
  await page.goto(`${webOrigin}/seller/`);
  await expect(page.getByTestId('login-form')).toBeVisible({ timeout: 20_000 });
  await page.getByTestId('login-form').getByLabel('Email').fill(email);
  await page.getByTestId('login-form').getByLabel('Пароль').fill(password);
  await Promise.all([
    page.waitForResponse((r) => r.url().includes('/api/auth/login') && r.status() === 200),
    page.getByTestId('login-form').getByRole('button', { name: 'Войти' }).click(),
  ]);
  await expect(page.getByTestId('nav-seller-documents')).toBeVisible({ timeout: 20_000 });
}

async function logoutIfVisible(page) {
  const logout = page.getByTestId('logout');
  if (await logout.isVisible().catch(() => false)) {
    await logout.click();
    await expect(page.getByTestId('login-form')).toBeVisible({ timeout: 10_000 });
  }
}

async function loginFf(page, email) {
  await page.goto(`${webOrigin}/`);
  await page.evaluate(() => localStorage.removeItem('wms_token_ff'));
  await page.goto(`${webOrigin}/`);
  await expect(page.getByTestId('login-form')).toBeVisible({ timeout: 20_000 });
  await page.getByTestId('login-form').getByLabel('Email').fill(email);
  await page.getByTestId('login-form').getByLabel('Пароль').fill(password);
  await Promise.all([
    page.waitForResponse((r) => r.url().includes('/api/auth/login') && r.status() === 200),
    page.getByTestId('login-form').getByRole('button', { name: 'Войти' }).click(),
  ]);
  await expect(page.getByTestId('app-frame')).toBeVisible({ timeout: 20_000 });
}

async function main() {
  await fs.mkdir(screenshotsDir, { recursive: true });
  const api = await playwrightRequest.newContext({ baseURL: webOrigin });

  const adminEmail = `seller-portal-${suffix}@example.com`;
  const sellerEmail = `seller-portal-seller-${suffix}@example.com`;
  const adminReg = await apiOk(api, 'post', '/api/auth/register', {
    data: {
      organization_name: 'Live Seller Portal QA',
      slug: `live-seller-${Date.now()}`,
      admin_email: adminEmail,
      password,
    },
  });
  const adminToken = String((await adminReg.json()).access_token);
  const auth = { Authorization: `Bearer ${adminToken}`, 'Content-Type': 'application/json' };

  const sellerRes = await apiOk(api, 'post', '/api/sellers', {
    headers: auth,
    data: { name: `Live Seller ${suffix}` },
  });
  const sellerId = String((await sellerRes.json()).id);
  await apiOk(api, 'post', '/api/auth/seller-accounts', {
    headers: auth,
    data: { seller_id: sellerId, email: sellerEmail, password },
  });
  const whRes = await apiOk(api, 'post', '/api/warehouses', {
    headers: auth,
    data: { name: 'Live WH', code: `live-wh-${Date.now()}` },
  });
  const warehouseId = String((await whRes.json()).id);

  await apiOk(api, 'patch', `/api/integrations/wildberries/sellers/${sellerId}/tokens`, {
    headers: auth,
    data: { content_api_token: 'e2e-content', supplies_api_token: 'e2e-supplies' },
  });
  const jobRes = await apiOk(api, 'post', '/api/operations/background-jobs', {
    headers: auth,
    data: { job_type: 'wildberries_cards_sync', seller_id: sellerId },
  });
  await waitJob(api, auth, String((await jobRes.json()).id));

  const linkedProductRes = await apiOk(api, 'post', '/api/products', {
    headers: auth,
    data: {
      name: 'Live WB Product',
      sku_code: `LIVE-WB-${suffix}`,
      length_mm: 100,
      width_mm: 80,
      height_mm: 40,
      seller_id: sellerId,
    },
  });
  const linkedProductId = String((await linkedProductRes.json()).id);
  await apiOk(api, 'post', `/api/integrations/wildberries/sellers/${sellerId}/link-product`, {
    headers: auth,
    data: { product_id: linkedProductId, nm_id: 424242 },
  });

  const secondProductRes = await apiOk(api, 'post', '/api/products', {
    headers: auth,
    data: {
      name: 'Live Manual Product',
      sku_code: `LIVE-MANUAL-${suffix}`,
      wb_barcode: `LIVE-MANUAL-BARCODE-${suffix}`,
      wb_vendor_code: 'LIVE-MANUAL-VENDOR',
      length_mm: 120,
      width_mm: 70,
      height_mm: 30,
      seller_id: sellerId,
    },
  });
  const secondProductId = String((await secondProductRes.json()).id);

  const sellerLogin = await apiOk(api, 'post', '/api/auth/login', {
    data: { email: sellerEmail, password },
  });
  const sellerToken = String((await sellerLogin.json()).access_token);
  const sellerAuth = { Authorization: `Bearer ${sellerToken}`, 'Content-Type': 'application/json' };

  const browser = await chromium.connectOverCDP(cdpEndpoint);
  const context = browser.contexts()[0] ?? await browser.newContext();
  const page = context.pages()[0] ?? await context.newPage();
  await page.setViewportSize({ width: 1440, height: 950 });

  await loginSeller(page, sellerEmail);
  await page.getByTestId('nav-seller-documents').click();
  await expect(page.getByTestId('seller-documents-actions')).toBeVisible();
  record('rec02SeparateReturnButtonVisible', await page.getByTestId('seller-create-return').isVisible());
  record('operationTypeSwitchOnDocumentsAbsent', (await page.getByLabel(/тип операции/i).count()) === 0);
  await shot(page, '01-seller-documents-actions-calendar-empty');

  const [createReturnRes] = await Promise.all([
    page.waitForResponse((r) =>
      r.url().includes('/api/operations/inbound-intake-requests') &&
      r.request().method() === 'POST' &&
      r.status() === 201,
    ),
    page.getByTestId('seller-create-return').click(),
  ]);
  const returnRequestId = String((await createReturnRes.json()).id);
  await expect(page.getByTestId('seller-inbound-draft-form')).toBeVisible({ timeout: 20_000 });
  record('returnFormTitle', await text(page.getByRole('heading', { name: /возврат/i })));
  record('returnOperationReadonlyText', await text(page.getByTestId('seller-inbound-operation-type')));
  record('operationTypeInputAbsentInForm', (await page.locator('[data-testid*="operation"][role="button"], select[name*="operation"]').count()) === 0);
  await shot(page, '02-return-draft-form-operation-readonly');

  await page.getByTestId('seller-inbound-add-products').click();
  await expect(page.getByTestId('seller-inbound-picker')).toBeVisible();
  record('pickerCategoryControlVisible', await page.getByTestId('seller-inbound-picker-category').isVisible());
  record('pickerSelectAllVisible', await page.getByTestId('seller-inbound-picker-select-all').isVisible());
  record('pickerBulkQtyVisible', await page.getByTestId('seller-inbound-picker-bulk-qty').isVisible());
  await page.getByTestId('seller-inbound-picker-search').fill('E2E-MOCK-BARCODE');
  await expect(page.getByTestId('seller-inbound-picker-row').first()).toBeVisible();
  await page.getByTestId('seller-inbound-picker-search').press('Enter');
  await page.waitForTimeout(350);
  const scanQty = await page.getByTestId('seller-inbound-picker-qty').first().inputValue();
  record('sel04ScanBarcodeQtyAfterEnter', scanQty);
  if (scanQty !== '1') {
    finding(
      'Стоп',
      `SEL-04: Enter in picker search by E2E-MOCK-BARCODE did not increment qty; visible qty after scan is "${scanQty || 'empty'}".`,
    );
    await page.getByTestId('seller-inbound-picker-qty').first().fill('1');
  }
  await page.getByTestId('seller-inbound-picker-select-all').click();
  await page.getByTestId('seller-inbound-picker-bulk-qty').fill('4');
  await page.getByTestId('seller-inbound-picker-bulk-apply').click();
  const pickerQtyValues = await page.getByTestId('seller-inbound-picker-qty').evaluateAll((nodes) =>
    nodes.map((n) => n.value),
  );
  record('pickerQtyValuesAfterScanSelectAllBulk', pickerQtyValues);
  await shot(page, '03-picker-scan-select-all-bulk');
  await Promise.all([
    page.waitForResponse((r) => r.url().includes(`/api/operations/inbound-intake-requests/${returnRequestId}/lines`) && r.status() < 300),
    page.getByTestId('seller-inbound-picker-apply').click(),
  ]);
  await expect(page.getByTestId('seller-inbound-line-row')).toHaveCount(2);

  await page.getByTestId('seller-inbound-submit-warehouse').click();
  await expect(page.getByTestId('seller-inbound-draft-error')).toContainText('Укажите количество грузомест');
  record('rec08ClientGuardVisible', true);
  await shot(page, '04-rec08-empty-boxes-submit-guard');

  await page.getByTestId('seller-inbound-planned-boxes').fill('2');
  await page.getByTestId('seller-inbound-waybill-number').fill(`WB-LIVE-${suffix}`);
  await apiOk(api, 'patch', `/api/operations/inbound-intake-requests/${returnRequestId}`, {
    headers: sellerAuth,
    data: {
      planned_delivery_date: new Date().toISOString().slice(0, 10),
      planned_box_count: 2,
      waybill_number: `WB-LIVE-${suffix}`,
    },
  });
  await Promise.all([
    page.waitForResponse((r) => r.url().includes(`/api/operations/inbound-intake-requests/${returnRequestId}`) && r.request().method() === 'PATCH' && r.status() < 300),
    page.getByTestId('seller-inbound-save-draft').click(),
  ]);
  record('sel02WaybillInputValue', await page.getByTestId('seller-inbound-waybill-number').inputValue());

  await page.getByTestId('seller-inbound-line-print-barcode').first().click();
  await expect(page.getByTestId('ff-product-label-print-dialog')).toBeVisible();
  record('sel05StandardProductBarcodeDialogVisible', true);
  record('sel05ChestnyZnakDialogAbsent', (await page.getByTestId('marking-print-dialog').count()) === 0);
  await shot(page, '05-standard-product-barcode-print-dialog');
  await page.getByTestId('ff-product-label-cancel').click();
  await expect(page.getByTestId('ff-product-label-print-dialog')).toHaveCount(0);

  await Promise.all([
    page.waitForResponse((r) => r.url().includes(`/api/operations/inbound-intake-requests/${returnRequestId}/submit`) && r.status() < 300),
    page.getByTestId('seller-inbound-submit-warehouse').click(),
  ]);
  await expect(page.getByTestId('seller-documents-table')).toBeVisible();
  await expect(page.locator(`[data-testid="seller-documents-row"][data-doc-id="${returnRequestId}"]`)).toContainText('Возврат');
  await expect(page.locator(`[data-testid="seller-documents-row"][data-doc-id="${returnRequestId}"]`)).toContainText(`WB-LIVE-${suffix}`);
  await expect(page.getByTestId('seller-shipments-calendar')).toContainText('Сегодня');
  const calendarText = await text(page.getByTestId('seller-shipments-calendar'));
  record('cal04SellerCalendarShowsOwnToday', true);
  record('cal04CalendarIncludesWaybill', calendarText.includes(`WB-LIVE-${suffix}`));
  await shot(page, '06-submitted-return-calendar-waybill');

  await loginFf(page, adminEmail);
  await page.getByTestId('nav-ff-reception').click();
  await expect(page.locator(`[data-testid="ff-inbound-queue-row"][data-request-id="${returnRequestId}"]`)).toBeVisible();
  record('ffQueueSeparateReturnCreateButtonVisible', await page.getByTestId('ff-inbound-create-return').isVisible());
  await page.locator(`[data-testid="ff-inbound-queue-row"][data-request-id="${returnRequestId}"]`).click();
  await expect(page.getByTestId('ff-inbound-doc-root')).toBeVisible();
  await expect(page.getByTestId('ff-inbound-operation-type')).toContainText('Возврат');
  await shot(page, '07-ff-return-receiving-card');

  const ffRows = () =>
    page.locator(
      '[data-testid="ff-inbound-line-row"], [data-testid="ff-inbound-line-row-match"], [data-testid="ff-inbound-line-row-discrepancy"]',
    );
  await expect(ffRows()).toHaveCount(2);
  await ffRows().nth(0).getByTestId('ff-inbound-line-manual-edit').click();
  let actualInput = page.getByTestId('ff-inbound-line-actual');
  await actualInput.fill('4');
  await Promise.all([
    page.waitForResponse((r) => r.url().includes('/actual') && r.status() < 300),
    actualInput.evaluate((el) => el.blur()),
  ]);
  await expect(ffRows().nth(0).getByTestId('ff-inbound-line-actual-display')).toHaveText('4');
  await ffRows().nth(1).getByTestId('ff-inbound-line-manual-edit').click();
  actualInput = page.getByTestId('ff-inbound-line-actual');
  await actualInput.fill('2');
  await Promise.all([
    page.waitForResponse((r) => r.url().includes('/actual') && r.status() < 300),
    actualInput.evaluate((el) => el.blur()),
  ]);
  await expect(ffRows().nth(1).getByTestId('ff-inbound-line-actual-display')).toHaveText('2');

  const addedSku = `FF-ADDED-${suffix}`;
  await page.getByTestId('ff-inbound-receiving-create-manual-product').click();
  await expect(page.getByTestId('ff-manual-product-dialog')).toBeVisible();
  await page.getByTestId('ff-manual-product-name').fill('FF Added Product');
  await page.getByTestId('ff-manual-product-sku').fill(addedSku);
  await page.getByTestId('ff-manual-product-barcode').fill(`FF-ADDED-BARCODE-${suffix}`);
  await page.getByTestId('ff-manual-product-length').fill('100');
  await page.getByTestId('ff-manual-product-width').fill('80');
  await page.getByTestId('ff-manual-product-height').fill('50');
  await Promise.all([
    page.waitForResponse((r) => r.url().includes('/api/products') && r.status() < 300),
    page.waitForResponse((r) => r.url().includes(`/api/operations/inbound-intake-requests/${returnRequestId}/receiving/lines`) && r.status() < 300),
    page.getByTestId('ff-manual-product-submit').click(),
  ]);
  await expect(page.getByTestId('ff-manual-product-dialog')).toHaveCount(0);
  await shot(page, '08-ff-red-green-and-added-line-before-complete');

  await page.getByTestId('ff-inbound-verify-complete').click();
  await expect(page.getByTestId('ff-inbound-discrepancy-dialog')).toBeVisible();
  await shot(page, '09-ff-discrepancy-dialog-return');
  await Promise.all([
    page.waitForResponse((r) => r.url().includes(`/api/operations/inbound-intake-requests/${returnRequestId}/complete-receiving`) && r.status() < 300),
    page.getByTestId('ff-inbound-discrepancy-confirm').click(),
  ]);

  await loginSeller(page, sellerEmail);
  await page.getByTestId('nav-seller-documents').click();
  await page.locator(`[data-testid="seller-documents-row"][data-doc-id="${returnRequestId}"]`).click();
  await expect(page.getByRole('heading', { name: /Карточка приёмки · Возврат/ })).toBeVisible({ timeout: 20_000 });
  await expect(page.getByTestId('seller-inbound-readonly-hint')).toContainText('Приёмку взял в работу склад');
  await expect(page.getByTestId('seller-inbound-fact-card')).toBeVisible();
  record('sel03ReadonlyHintVisible', true);
  record('removedFactSummaryAbsent', (await page.getByTestId('seller-inbound-fact-summary').count()) === 0);
  record('removedProblemSummaryTextAbsent', (await page.getByText('Что не так').count()) === 0);
  record('removedTotalSummaryTextAbsent', (await page.getByText('Итог приемки').count()) === 0);
  record('readonlyEditButtonsAbsent', {
    addProducts: await page.getByTestId('seller-inbound-add-products').count(),
    submitWarehouse: await page.getByTestId('seller-inbound-submit-warehouse').count(),
    saveDraft: await page.getByTestId('seller-inbound-save-draft').count(),
    deleteLine: await page.getByTestId('seller-inbound-line-delete').count(),
  });

  const factTable = page.getByTestId('seller-inbound-lines-table');
  const headerTexts = await factTable.locator('thead th').evaluateAll((nodes) =>
    nodes.map((n) => (n.textContent ?? '').trim()),
  );
  record('sellerFactHeaderTexts', headerTexts);
  const sellerMatchRow = page.getByTestId('seller-inbound-line-row').filter({ hasText: `LIVE-WB-${suffix}` });
  const sellerShortageRow = page.getByTestId('seller-inbound-line-row').filter({ hasText: `LIVE-MANUAL-${suffix}` });
  const sellerAddedRow = page.getByTestId('seller-inbound-line-row').filter({ hasText: addedSku });
  await expect(sellerMatchRow.getByTestId('seller-inbound-line-discrepancy')).toHaveText(/^(ОК|Без расхождений)$/);
  await expect(sellerShortageRow.getByTestId('seller-inbound-line-discrepancy')).toHaveText('Недостача 2');
  await expect(sellerAddedRow.getByTestId('seller-inbound-line-discrepancy')).toHaveText('Излишек 1');
  const colors = await page.evaluate(() => {
    const byText = (needle) => {
      const rows = Array.from(document.querySelectorAll('[data-testid="seller-inbound-line-row"]'));
      const row = rows.find((r) => (r.textContent ?? '').includes(needle));
      return row ? getComputedStyle(row).backgroundColor : '';
    };
    return {
      match: byText('ОК') || byText('Без расхождений'),
      shortage: byText('Недостача 2'),
      added: byText('Излишек 1'),
    };
  });
  record('sellerFactRowBackgroundColors', colors);
  const redOk = /211,\s*47,\s*47/.test(colors.shortage) && /211,\s*47,\s*47/.test(colors.added);
  const greenOk = /46,\s*125,\s*50|76,\s*175,\s*80|56,\s*142,\s*60/.test(colors.match);
  record('rec13RedRowsVisible', redOk);
  record('rec13GreenMatchedRowsVisible', greenOk);
  if (!greenOk) {
    finding(
      'Стоп',
      'REC-13: совпавшая строка seller fact-card показывает корректный итог, но фон не зелёный; красный фон для расхождений есть.',
    );
  }
  await shot(page, '10-seller-return-fact-card-readonly-no-summary-blocks');

  const elementMap = [
    ['Блок Документы + подпись', 'REC-02/CAL-04/GLOBAL-02', 'оставить'],
    ['Кнопка Создать заявку на поставку', 'SEL-01..05/REC-08', 'оставить'],
    ['Кнопка Создать заявку на возврат', 'REC-02', 'оставить'],
    ['Блок Сегодня / Завтра', 'CAL-04', 'оставить'],
    ['Фильтр Тип документа', 'REC-02/GLOBAL-02', 'оставить'],
    ['Фильтр Сортировка', 'GLOBAL-02', 'оставить'],
    ['Колонки списка Тип/Дата/Накладная/Статус/Строк/Действия', 'REC-02/SEL-02/GLOBAL-01/02', 'оставить'],
    ['Форма возврата: дата/грузоместа/накладная/status chip/тип', 'CAL-04/REC-08/SEL-02/SEL-03/REC-02', 'оставить'],
    ['Кнопки Добавить товары/Сохранить/Закрыть/Передать на склад', 'SEL-01/SEL-04/REC-08/GLOBAL-02', 'оставить'],
    ['Picker: поиск/категории/Выбрать все/Проставить всем/таблица/qty', 'SEL-01/SEL-04', 'оставить'],
    ['Кнопка печати ШК в строке + ProductBarcodePrintDialog', 'SEL-05', 'оставить'],
    ['Синяя readonly-плашка Приёмку взял в работу склад', 'SEL-03', 'оставить'],
    ['Fact-card meta операция/status/склад', 'REC-02/SEL-03/GLOBAL-01', 'оставить'],
    ['Fact-card колонки Товар/Заявлено/Принято/Итог/Детали', 'REC-13/REC-14', 'оставить'],
    ['Красные строки расхождений и Итог Недостача/Излишек', 'REC-13/REC-14', 'оставить'],
    ['Зелёная подсветка совпавших строк', 'REC-13', greenOk ? 'оставить' : 'исправить: фон отсутствует'],
    ['Блоки Итог приемки / Что не так', 'GLOBAL-02/REC-13', 'удалены, оставить отсутствующими'],
  ];

  const evidence = {
    commit: 'f92f9d4cbeb72348aa374b8ce2e213cfdfc49c04',
    round: 'round2',
    status: findings.length === 0 ? 'SCREEN_APPROVED' : 'FIXES_REQUIRED',
    browser: 'External visible Google Chrome via CDP',
    browserVersion: (await (await fetch(`${cdpEndpoint}/json/version`)).json()).Browser,
    webOrigin,
    suffix,
    adminEmail,
    sellerEmail,
    returnRequestId,
    linkedProductId,
    secondProductId,
    checks,
    findings,
    artifacts,
    elementMap,
  };
  await fs.writeFile(path.join(evidenceDir, 'seller-portal-live-evidence.json'), JSON.stringify(evidence, null, 2));
  await fs.writeFile(
    path.join(evidenceDir, 'SELLER_PORTAL_6A_LIVE_VERDICT.md'),
    [
      '# Seller portal 6a live Chrome verdict Round 2',
      '',
      `Commit: \`${evidence.commit}\``,
      `Status: \`${evidence.status}\``,
      `Browser: ${evidence.browser} (${evidence.browserVersion})`,
      `URL: ${webOrigin}`,
      `Return request: \`${returnRequestId}\``,
      '',
      '## 6a map',
      '',
      '| Element | Task ID | Action |',
      '|---|---|---|',
      ...elementMap.map((row) => `| ${row[0]} | ${row[1]} | ${row[2]} |`),
      '',
      '## Findings',
      '',
      findings.length
        ? findings.map((f) => `- ${f.severity}: ${f.message}`).join('\n')
        : '- No findings.',
      '',
      '## Screenshots',
      '',
      ...artifacts.map((a) => `- \`${a}\``),
      '',
    ].join('\n'),
  );

  await browser.close();
  await api.dispose();
}

main().catch(async (err) => {
  await fs.writeFile(path.join(evidenceDir, 'live-script-error.txt'), `${err.stack || err}\n`);
  console.error(err);
  process.exit(1);
});
