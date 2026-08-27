import { test, expect } from '@playwright/test';
import {
  BarcodeFormat,
  BinaryBitmap,
  DecodeHintType,
  HybridBinarizer,
  MultiFormatReader,
  RGBLuminanceSource,
} from '@zxing/library';
import { PNG } from 'pngjs';

import { waitForPatchOk, waitForPostOk, waitForPutOk } from './api-waits';
import {
  INBOUND_API,
  apiCreateSubmittedInbound,
  beginInboundReceiving,
  beginInboundReceivingWithBoxes,
  createInboundBoxes,
  expandInboundPackages,
  ffInboundBoxAddManualQty,
  loginFfAdmin,
  openFfInboundDoc,
  seedFfSellerInbound,
} from './inbound-boxes-helpers';

function decodeCode128FromPng(pngBytes: Buffer): string {
  const png = PNG.sync.read(pngBytes);
  const pixels = new Int32Array(png.width * png.height);
  for (let index = 0; index < pixels.length; index += 1) {
    const offset = index * 4;
    pixels[index] = (
      (png.data[offset + 3]! << 24)
      | (png.data[offset]! << 16)
      | (png.data[offset + 1]! << 8)
      | png.data[offset + 2]!
    );
  }
  const source = new RGBLuminanceSource(
    pixels,
    png.width,
    png.height,
  );
  const hints = new Map();
  hints.set(DecodeHintType.POSSIBLE_FORMATS, [BarcodeFormat.CODE_128]);
  return new MultiFormatReader()
    .decode(new BinaryBitmap(new HybridBinarizer(source)), hints)
    .getText();
}

// TC-NEW-C01 — поштучная приёмка: модал «Добавить в короб» → ручное кол-во → завершить приёмку.
test.describe('FF inbound box piece intake', () => {
  test('TC-NEW-C01 manual qty in two boxes then complete verification', async ({ page }) => {
    const seed = await seedFfSellerInbound(page);
    const rid = await apiCreateSubmittedInbound(page.request, seed, {
      plannedBoxes: 2,
      expectedQty: 5,
    });
    const h = { Authorization: `Bearer ${seed.token}` };
    await beginInboundReceiving(page.request, h, rid);

    await loginFfAdmin(page, seed.adminEmail, seed.password);
    await openFfInboundDoc(page, seed, { skipLogin: true });

    await expect(page.getByTestId('ff-inbound-status-chip')).toContainText('Приёмка');
    await expect(page.getByTestId('ff-inbound-document-technical-number')).toHaveCount(0);

    await ffInboundBoxAddManualQty(page, 3);
    await expect(
      page.getByTestId('ff-inbound-box-row').first().getByTestId('ff-inbound-box-line-qty'),
    ).toHaveText('3');
    await ffInboundBoxAddManualQty(page, 2);
    await expect(
      page.getByTestId('ff-inbound-box-row').nth(1).getByTestId('ff-inbound-box-line-qty'),
    ).toHaveText('2');

    await expect(page.getByTestId('ff-inbound-line-actual-display').first()).toHaveText('5', {
      timeout: 15_000,
    });
    await expect(page.getByTestId('ff-inbound-line-row-match')).toBeVisible();

    const [verifyRes] = await Promise.all([
      waitForPostOk(page, INBOUND_API, (u) => u.includes('/complete-receiving')),
      page.getByTestId('ff-inbound-verify-complete').click(),
    ]);
    expect(verifyRes.ok()).toBeTruthy();
    await expect(page.getByTestId('ff-inbound-status-chip')).toContainText('В сортировке');
  });

  test('TC-NEW-C01 verify with open box saves qty without closing box', async ({ page }) => {
    const seed = await seedFfSellerInbound(page);
    const rid = await apiCreateSubmittedInbound(page.request, seed, {
      plannedBoxes: 1,
      expectedQty: 4,
    });
    const h = { Authorization: `Bearer ${seed.token}` };
    await beginInboundReceiving(page.request, h, rid);

    await loginFfAdmin(page, seed.adminEmail, seed.password);
    await openFfInboundDoc(page, seed, { skipLogin: true });

    await expandInboundPackages(page);
    await page.getByTestId('ff-inbound-add-to-box').click();
    await page.getByTestId('ff-inbound-box-row').first().getByRole('button', { name: 'Наполнить' }).click();
    await expect(page.getByTestId('ff-inbound-box-add-dialog')).toBeVisible();
    const qtyInput = page.getByTestId('ff-inbound-box-add-manual-qty').first();
    await qtyInput.click();
    await qtyInput.pressSequentially('4');
    await Promise.all([
      waitForPutOk(page, INBOUND_API, (u) => u.includes('/boxes/') && u.includes('/lines/')),
      qtyInput.blur(),
    ]);

    await page.getByTestId('ff-inbound-box-add-dismiss').click();
    await expect(page.getByTestId('ff-inbound-box-add-dialog')).toBeHidden();

    const [verifyRes] = await Promise.all([
      waitForPostOk(page, INBOUND_API, (u) => u.includes('/complete-receiving')),
      page.getByTestId('ff-inbound-verify-complete').click(),
    ]);
    expect(verifyRes.ok()).toBeTruthy();
    await expect(page.getByTestId('ff-inbound-status-chip')).toContainText('В сортировке');
    await expect(page.getByTestId('ff-inbound-box-add-dialog')).toBeHidden();
  });

  test('TC-NEW-C01-N2 set line qty on previously closed box still works', async ({ page }) => {
    const seed = await seedFfSellerInbound(page);
    const rid = await apiCreateSubmittedInbound(page.request, seed, {
      plannedBoxes: 1,
      expectedQty: 2,
    });
    const h = { Authorization: `Bearer ${seed.token}` };
    const { boxes } = await beginInboundReceivingWithBoxes(page.request, h, rid, {
      boxCount: 1,
      closeEach: true,
    });
    const boxId = boxes[0]!.id;
    const put = await page.request.put(
      `${INBOUND_API}/${rid}/boxes/${boxId}/lines/${seed.productId}`,
      {
        headers: { ...h, 'Content-Type': 'application/json' },
        data: { quantity: 1 },
      },
    );
    expect(put.status()).toBe(200);
    const got = await page.request.get(`${INBOUND_API}/${rid}`, { headers: h });
    expect(got.ok()).toBeTruthy();
    const detail = (await got.json()) as {
      boxes: { id: string; lines: { quantity: number }[] }[];
      lines: { effective_actual_qty?: number }[];
    };
    const box = detail.boxes.find((b) => b.id === boxId);
    expect(box?.lines.some((ln) => ln.quantity === 1)).toBeTruthy();
    expect(detail.lines[0]?.effective_actual_qty).toBe(1);
  });

  test('TC-NEW-C02 manual line actual without opening box completes verification', async ({
    page,
  }) => {
    const seed = await seedFfSellerInbound(page);
    const rid = await apiCreateSubmittedInbound(page.request, seed, {
      plannedBoxes: 1,
      expectedQty: 3,
    });
    const h = { Authorization: `Bearer ${seed.token}` };
    await beginInboundReceiving(page.request, h, rid);

    await loginFfAdmin(page, seed.adminEmail, seed.password);
    await openFfInboundDoc(page, seed, { skipLogin: true });

    await page.getByTestId('ff-inbound-line-manual-edit').first().click();
    const actualField = page.getByTestId('ff-inbound-line-actual').first();
    await actualField.fill('3');
    await Promise.all([
      waitForPatchOk(page, INBOUND_API, (u) => u.includes('/actual')),
      actualField.press('Enter'),
    ]);

    await expect(page.getByTestId('ff-inbound-line-row-match')).toBeVisible();

    await page.getByTestId('ff-inbound-verify-complete').click();
    await expect(page.getByTestId('ff-inbound-discrepancy-dialog')).toBeVisible();
    await expect(page.getByTestId('ff-inbound-discrepancy-box-summary')).toContainText('Короба: 0 из 1');
    const [verifyRes] = await Promise.all([
      waitForPostOk(page, INBOUND_API, (u) => u.includes('/complete-receiving')),
      page.getByTestId('ff-inbound-discrepancy-confirm').click(),
    ]);
    expect(verifyRes.ok()).toBeTruthy();
    await expect(page.getByTestId('ff-inbound-status-chip')).toContainText('В сортировке');
  });
});

// TC-NEW-INTERNAL-LABEL-01 — все внутренние ШК коробов печатаются одной лентой;
// PNG из реального print HTML декодируется обратно в исходный Code 128.
test('TC-NEW-INTERNAL-LABEL-01 bulk box labels are large, decodable and one print job', async ({ page }, testInfo) => {
  const seed = await seedFfSellerInbound(page, `bulk-box-label-${Date.now()}`);
  const requestId = await apiCreateSubmittedInbound(page.request, seed, {
    plannedBoxes: 2,
    expectedQty: 2,
  });
  const headers = { Authorization: `Bearer ${seed.token}` };
  await beginInboundReceiving(page.request, headers, requestId);
  const boxes = await createInboundBoxes(page.request, headers, requestId, 2);

  await loginFfAdmin(page, seed.adminEmail, seed.password);
  await openFfInboundDoc(page, seed, { skipLogin: true });
  await expandInboundPackages(page);
  await expect(page.getByTestId('ff-inbound-boxes-print-all')).toBeEnabled();

  await page.evaluate(() => {
    const capture = window as unknown as {
      __WMS_CAPTURE_PRINT_HTML__?: boolean;
      __WMS_LAST_PRINT_HTML__?: string;
      __WMS_PRINT_JOB_COUNT__?: number;
      __WMS_PRINT_CLEANUP_EVENTS__?: string[];
    };
    capture.__WMS_CAPTURE_PRINT_HTML__ = true;
    capture.__WMS_LAST_PRINT_HTML__ = '';
    capture.__WMS_PRINT_JOB_COUNT__ = 0;
    capture.__WMS_PRINT_CLEANUP_EVENTS__ = [];
  });

  await page.getByTestId('ff-inbound-boxes-print-all').click();
  const dialog = page.getByTestId('ff-inbound-box-print-dialog');
  await expect(dialog).toBeVisible();
  await dialog.getByTestId('ff-inbound-box-print-dialog-confirm').click();

  await expect.poll(async () => page.evaluate(() => {
    const capture = window as unknown as { __WMS_LAST_PRINT_HTML__?: string };
    return capture.__WMS_LAST_PRINT_HTML__ ?? '';
  })).toContain(boxes[0]!.internal_barcode);

  const printHtml = await page.evaluate(() => {
    const capture = window as unknown as {
      __WMS_LAST_PRINT_HTML__?: string;
      __WMS_PRINT_JOB_COUNT__?: number;
    };
    return { html: capture.__WMS_LAST_PRINT_HTML__ ?? '', jobs: capture.__WMS_PRINT_JOB_COUNT__ ?? 0 };
  });
  expect(printHtml.html).toContain(`@page { size: 58mm 40mm; margin: 0; }`);
  expect(printHtml.html).toContain('.barcode { width: 100%; max-width: none;');
  expect(printHtml.html).toContain('page-break-after: always;');
  for (const box of boxes) expect(printHtml.html).toContain(`data-barcode="${box.internal_barcode}"`);
  expect((printHtml.html.match(/class="label/g) ?? []).length).toBe(2);

  // Живой Chromium рендерит сам print HTML с PNG, а не подменённый макет.
  const browser = page.context().browser();
  if (!browser) throw new Error('Chromium browser недоступен для проверки печати.');
  const printContext = await browser.newContext({
    viewport: { width: 600, height: 500 },
    // 203 dpi is the common low-resolution thermal-printer contract.
    deviceScaleFactor: 203 / 96,
  });
  const preview = await printContext.newPage();
  await preview.setContent(printHtml.html);
  const barcodeImage = preview.locator('img.barcode').first();
  await expect(barcodeImage).toBeVisible();
  const barcodeBox = await barcodeImage.boundingBox();
  expect(barcodeBox?.width).toBeGreaterThan(200);
  const renderedBarcodePng = await barcodeImage.screenshot({
    path: testInfo.outputPath('internal-box-label-58x40-203dpi.png'),
    scale: 'device',
  });
  expect(PNG.sync.read(renderedBarcodePng).width).toBeGreaterThanOrEqual(430);
  await preview.close();
  await printContext.close();

  await expect.poll(async () => page.evaluate(() => {
    const capture = window as unknown as { __WMS_PRINT_JOB_COUNT__?: number };
    return capture.__WMS_PRINT_JOB_COUNT__ ?? 0;
  })).toBe(1);
  expect(printHtml.jobs).toBeLessThanOrEqual(1);
  await expect.poll(async () => page.evaluate(() => {
    const capture = window as unknown as { __WMS_PRINT_CLEANUP_EVENTS__?: string[] };
    return capture.__WMS_PRINT_CLEANUP_EVENTS__ ?? [];
  })).toEqual(['afterprint']);

  expect(decodeCode128FromPng(renderedBarcodePng)).toBe(boxes[0]!.internal_barcode);
  await expect(dialog).toHaveCount(0);

  // Приёмка уже проведена, но оператор может открыть её в общем списке и
  // перепечатать внутренние этикетки: кнопка зависит только от наличия коробов.
  for (const box of boxes) {
    const line = await page.request.put(
      `${INBOUND_API}/${requestId}/boxes/${box.id}/lines/${seed.productId}`,
      { headers: { ...headers, 'Content-Type': 'application/json' }, data: { quantity: 1 } },
    );
    expect(line.ok()).toBeTruthy();
  }
  const completed = await page.request.post(`${INBOUND_API}/${requestId}/complete-receiving`, { headers });
  expect(completed.ok()).toBeTruthy();
  await page.getByTestId('ff-doc-dialog-close').click();
  await openFfInboundDoc(page, seed, { skipLogin: true });
  await expandInboundPackages(page);
  await expect(page.getByTestId('ff-inbound-status-chip')).toContainText('В сортировке');
  await expect(page.getByTestId('ff-inbound-boxes-print-all')).toBeEnabled();
});

// TC-NEW-INTERNAL-LABEL-02 — безопасная длина нового ШК остаётся читаемой на
// штатной этикетке 58x40 мм при 203 dpi, включая худшие рисунки полос.
test('TC-NEW-INTERNAL-LABEL-02 18-char box codes decode at 58x40 and 203 dpi', async ({ page }) => {
  await page.goto('/');
  const alphabet = '0123456789ABCDEFGHJKMNPQRSTVWXYZ';
  const deterministicSuffix = (seed: number): string => {
    let value = seed >>> 0;
    let suffix = '';
    for (let index = 0; index < 14; index += 1) {
      value = (Math.imul(value, 1_664_525) + 1_013_904_223) >>> 0;
      suffix += alphabet[value % alphabet.length];
    }
    return suffix;
  };
  const codes = [
    `INB-${'Z'.repeat(14)}`,
    `WHB-${'A0'.repeat(7)}`,
    'INB-01234567890123',
    'WHB-00000000000000',
    ...Array.from({ length: 256 }, (_, index) =>
      `${index % 2 === 0 ? 'INB' : 'WHB'}-${deterministicSuffix(index + 1)}`),
  ];
  const negativeCanary = 'WHB-A8SB4F33NCXJ506A';
  const renderedCodes = [...codes, negativeCanary];

  const dataUrls = await page.evaluate(async (values) => {
    const modulePath = '/src/utils/renderBarcodeDataUrl.ts';
    const renderer = await import(/* @vite-ignore */ modulePath) as {
      renderBarcodeDataUrl: (
        barcode: string,
        options: { variant: 'internalBox' },
      ) => string;
    };
    return values.map((barcode) =>
      renderer.renderBarcodeDataUrl(barcode, { variant: 'internalBox' }));
  }, renderedCodes);

  const browser = page.context().browser();
  if (!browser) throw new Error('Chromium browser недоступен для проверки печати.');
  const printContext = await browser.newContext({
    viewport: { width: 600, height: 500 },
    deviceScaleFactor: 203 / 96,
  });
  const preview = await printContext.newPage();
  const captureAt203Dpi = async (code: string, dataUrl: string): Promise<Buffer> => {
    await preview.setContent(`<style>
      html, body { margin: 0; }
      .label { width: 58mm; height: 40mm; box-sizing: border-box; }
      .wrap { width: 100%; height: 100%; box-sizing: border-box; padding: 1.5mm; display: grid; grid-template-rows: auto 1fr auto; gap: 1mm; justify-items: stretch; align-items: center; }
      .title, .code { text-align: center; }
      .barcode { width: 100%; max-width: none; height: auto; max-height: none; display: block; image-rendering: pixelated; }
    </style>
    <section class="label"><div class="wrap"><div class="title">Короб № 1</div><img class="barcode" src="${dataUrl}" alt="barcode" /><div class="code">${code}</div></div></section>`);
    return preview.locator('img.barcode').screenshot({ scale: 'device' });
  };

  try {
    for (const [index, code] of codes.entries()) {
      const barcodePng = await captureAt203Dpi(code, dataUrls[index]!);
      expect(decodeCode128FromPng(barcodePng), `203 dpi decode failed for ${code}`).toBe(code);
    }
    const canaryPng = await captureAt203Dpi(negativeCanary, dataUrls[codes.length]!);
    expect(
      () => decodeCode128FromPng(canaryPng),
      'known unsafe 20-character Code 128 unexpectedly decoded at 203 dpi',
    ).toThrow();
  } finally {
    await preview.close();
    await printContext.close();
  }
});

// TC-NEW-STAB-IN-FE-03 — модалка «Добавить в короб»: фото/название/артикул/размер, hover, qty только в выбранный короб.
test('STAB-IN-FE-03 box add modal product row and target box qty', async ({ page }) => {
  const e2eApi = process.env.E2E_API_ORIGIN ?? 'http://127.0.0.1:18000';
  const seed = await seedFfSellerInbound(page, `stab-in-fe03-${Date.now()}`);
  const auth = { Authorization: `Bearer ${seed.token}`, 'Content-Type': 'application/json' };

  await page.request.patch(
    `${e2eApi}/integrations/wildberries/sellers/${seed.sellerId}/tokens`,
    {
      headers: auth,
      data: JSON.stringify({
        content_api_token: 'e2e-content',
        supplies_api_token: 'e2e-supplies',
      }),
    },
  );
  const jobRes = await page.request.post(`${e2eApi}/operations/background-jobs`, {
    headers: auth,
    data: JSON.stringify({ job_type: 'wildberries_cards_sync', seller_id: seed.sellerId }),
  });
  const jobId = String(((await jobRes.json()) as { id: string }).id);
  await expect
    .poll(async () => {
      const jr = await page.request.get(`${e2eApi}/operations/background-jobs/${jobId}`, {
        headers: auth,
      });
      return (await jr.json()) as { status: string };
    })
    .toMatchObject({ status: 'done' });
  await page.request.post(
    `${e2eApi}/integrations/wildberries/sellers/${seed.sellerId}/link-product`,
    {
      headers: auth,
      data: JSON.stringify({ product_id: seed.productId, nm_id: 424242 }),
    },
  );

  const rid = await apiCreateSubmittedInbound(page.request, seed, { plannedBoxes: 1, expectedQty: 4 });
  await beginInboundReceiving(page.request, { Authorization: `Bearer ${seed.token}` }, rid);

  await loginFfAdmin(page, seed.adminEmail, seed.password);
  await page.getByTestId('nav-ff-reception').click();
  await page.getByTestId('ff-inbound-queue-table').locator('tbody tr').first().click();
  await expect(page.getByTestId('ff-inbound-doc-root')).toBeVisible();

  await expandInboundPackages(page);
  for (let i = 0; i < 2; i++) {
    await Promise.all([
      waitForPostOk(page, INBOUND_API, (u) => u.endsWith('/boxes')),
      page.getByTestId('ff-inbound-add-to-box').click(),
    ]);
    await expect(page.getByTestId('ff-inbound-box-add-dialog')).toHaveCount(0);
  }
  await expect(page.getByTestId('ff-inbound-box-row')).toHaveCount(2);

  await page.getByTestId('ff-inbound-box-row').nth(1).getByRole('button', { name: 'Наполнить' }).click();
  await expect(page.getByTestId('ff-inbound-box-add-dialog')).toBeVisible();
  await expect(page.getByTestId('ff-inbound-box-add-box-label')).toContainText('Короб № 2');

  const line = page.getByTestId(`ff-inbound-box-add-line-row-${seed.productId}`);
  await expect(line).toBeVisible();
  await expect(page.getByTestId(`ff-inbound-box-add-product-${seed.productId}-photo`)).toBeVisible();
  await expect(page.getByTestId(`ff-inbound-box-add-product-${seed.productId}-sku`)).toContainText(seed.sku);
  await expect(page.getByTestId(`ff-inbound-box-add-product-${seed.productId}-name`)).toContainText(
    'Box Product',
  );
  await expect(page.getByTestId(`ff-inbound-box-add-size-${seed.productId}`)).toContainText('L');

  const photo = page.getByTestId(`ff-inbound-box-add-product-${seed.productId}-photo`);
  await photo.hover();
  await expect(page.getByTestId('product-photo-enlarged')).toBeVisible();

  const qtyInput = page.getByTestId('ff-inbound-box-add-manual-qty').first();
  await qtyInput.fill('3');
  await Promise.all([
    waitForPutOk(page, INBOUND_API, (u) => u.includes('/boxes/') && u.includes('/lines/')),
    qtyInput.blur(),
  ]);
  await page.getByTestId('ff-inbound-box-add-close').click();

  await expect(page.getByTestId('ff-inbound-box-row').nth(0)).toContainText('Пока нет товаров');
  await expect(page.getByTestId('ff-inbound-box-row').nth(1)).toContainText('3');
  await expect(page.getByText(/закройте короб/i)).toHaveCount(0);
});
