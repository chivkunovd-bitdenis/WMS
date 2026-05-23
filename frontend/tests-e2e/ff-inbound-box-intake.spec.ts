import { test, expect } from '@playwright/test';

import { waitForPostOk } from './api-waits';
import {
  INBOUND_API,
  apiCreateSubmittedInbound,
  loginFfAdmin,
  openFfInboundDoc,
  seedFfSellerInbound,
} from './inbound-boxes-helpers';

// TC-NEW-C01 — поштучная приёмка: скан INB → скан товара → закрыть короб → verify.
test.describe('FF inbound box piece intake', () => {
  test('TC-NEW-C01 scan two boxes then complete verification', async ({ page }) => {
    const seed = await seedFfSellerInbound(page);
    const rid = await apiCreateSubmittedInbound(page.request, seed, {
      plannedBoxes: 2,
      expectedQty: 5,
    });

    await loginFfAdmin(page, seed.adminEmail, seed.password);
    await openFfInboundDoc(page, seed, { skipLogin: true });

    await Promise.all([
      waitForPostOk(page, INBOUND_API, (u) => u.includes('/primary-accept')),
      page.getByTestId('ff-inbound-primary-accept').click(),
    ]);

    const inb1 = await page.getByTestId('ff-inbound-box-barcode').nth(0).innerText();
    const inb2 = await page.getByTestId('ff-inbound-box-barcode').nth(1).innerText();

    await page.getByTestId('ff-inbound-box-open-scan').fill(inb1);
    await Promise.all([
      waitForPostOk(page, INBOUND_API, (u) => u.includes('/boxes/open')),
      page.getByTestId('ff-inbound-box-open-submit').click(),
    ]);
    await expect(page.getByTestId('ff-inbound-active-box')).toBeVisible();

    for (let i = 0; i < 3; i++) {
      await page.getByTestId('ff-inbound-product-scan').fill(seed.sku);
      await Promise.all([
        waitForPostOk(page, INBOUND_API, (u) => u.includes('/boxes/') && u.includes('/scan')),
        page.getByTestId('ff-inbound-product-scan-submit').click(),
      ]);
    }
    await Promise.all([
      waitForPostOk(page, INBOUND_API, (u) => u.includes('/close')),
      page.getByTestId('ff-inbound-box-close').click(),
    ]);

    await page.getByTestId('ff-inbound-box-open-scan').fill(inb2);
    await Promise.all([
      waitForPostOk(page, INBOUND_API, (u) => u.includes('/boxes/open')),
      page.getByTestId('ff-inbound-box-open-submit').click(),
    ]);
    for (let i = 0; i < 2; i++) {
      await page.getByTestId('ff-inbound-product-scan').fill(seed.sku);
      await Promise.all([
        waitForPostOk(page, INBOUND_API, (u) => u.includes('/boxes/') && u.includes('/scan')),
        page.getByTestId('ff-inbound-product-scan-submit').click(),
      ]);
    }
    await Promise.all([
      waitForPostOk(page, INBOUND_API, (u) => u.includes('/close')),
      page.getByTestId('ff-inbound-box-close').click(),
    ]);

    await expect(page.getByTestId('ff-inbound-line-actual').first()).toHaveValue('5');

    const [verifyRes] = await Promise.all([
      waitForPostOk(page, INBOUND_API, (u) => u.includes('/verify')),
      page.getByTestId('ff-inbound-verify-complete').click(),
    ]);
    expect(verifyRes.ok()).toBeTruthy();
    await expect(page.getByTestId('ff-inbound-status-chip')).toContainText('Проверено');
  });

  test('TC-NEW-C01-N2 product scan without open box shows error', async ({ page }) => {
    const seed = await seedFfSellerInbound(page);
    const rid = await apiCreateSubmittedInbound(page.request, seed, {
      plannedBoxes: 1,
      expectedQty: 2,
    });
    const h = { Authorization: `Bearer ${seed.token}` };
    const prim = await page.request.post(`${INBOUND_API}/${rid}/primary-accept`, {
      headers: { ...h, 'Content-Type': 'application/json' },
      data: { actual_box_count: 1 },
    });
    const boxId = String(((await prim.json()) as { boxes: { id: string }[] }).boxes[0]!.id);
    const scan = await page.request.post(`${INBOUND_API}/${rid}/boxes/${boxId}/scan`, {
      headers: { ...h, 'Content-Type': 'application/json' },
      data: { barcode: seed.sku },
    });
    expect(scan.status()).toBe(409);
    expect(((await scan.json()) as { detail: string }).detail).toBe('no_open_box');
  });
});
