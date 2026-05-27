import { test, expect } from '@playwright/test';

import { waitForPostOk } from './api-waits';
import {
  INBOUND_API,
  apiCreateSubmittedInbound,
  fillFfInboundBoxLineQty,
  loginFfAdmin,
  openFfInboundDoc,
  seedFfSellerInbound,
} from './inbound-boxes-helpers';

// TC-NEW-C01 — поштучная приёмка: INB → ручное кол-во → закрыть короб → verify.
test.describe('FF inbound box piece intake', () => {
  test('TC-NEW-C01 manual qty in two boxes then complete verification', async ({ page }) => {
    const seed = await seedFfSellerInbound(page);
    await apiCreateSubmittedInbound(page.request, seed, {
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

    await fillFfInboundBoxLineQty(page, 3);
    await Promise.all([
      waitForPostOk(page, INBOUND_API, (u) => u.includes('/close')),
      page.getByTestId('ff-inbound-box-close').click(),
    ]);

    await page.getByTestId('ff-inbound-box-open-scan').fill(inb2);
    await Promise.all([
      waitForPostOk(page, INBOUND_API, (u) => u.includes('/boxes/open')),
      page.getByTestId('ff-inbound-box-open-submit').click(),
    ]);
    await fillFfInboundBoxLineQty(page, 2);
    await Promise.all([
      waitForPostOk(page, INBOUND_API, (u) => u.includes('/close')),
      page.getByTestId('ff-inbound-box-close').click(),
    ]);

    await expect(page.getByTestId('ff-inbound-line-actual').first()).toHaveValue('5');
    // TC-NEW-C04 — факт = ожидание → зелёная строка
    await expect(page.getByTestId('ff-inbound-line-row-match')).toBeVisible();

    const [verifyRes] = await Promise.all([
      waitForPostOk(page, INBOUND_API, (u) => u.includes('/verify')),
      page.getByTestId('ff-inbound-verify-complete').click(),
    ]);
    expect(verifyRes.ok()).toBeTruthy();
    await expect(page.getByTestId('ff-inbound-status-chip')).toContainText('В сортировке');
  });

  test('TC-NEW-C01 verify with open box saves qty and auto-closes', async ({ page }) => {
    const seed = await seedFfSellerInbound(page);
    await apiCreateSubmittedInbound(page.request, seed, {
      plannedBoxes: 1,
      expectedQty: 4,
    });

    await loginFfAdmin(page, seed.adminEmail, seed.password);
    await openFfInboundDoc(page, seed, { skipLogin: true });

    await Promise.all([
      waitForPostOk(page, INBOUND_API, (u) => u.includes('/primary-accept')),
      page.getByTestId('ff-inbound-primary-accept').click(),
    ]);

    const inb = await page.getByTestId('ff-inbound-box-barcode').first().innerText();
    await page.getByTestId('ff-inbound-box-open-scan').fill(inb);
    await Promise.all([
      waitForPostOk(page, INBOUND_API, (u) => u.includes('/boxes/open')),
      page.getByTestId('ff-inbound-box-open-submit').click(),
    ]);
    await fillFfInboundBoxLineQty(page, 4);

    const [verifyRes] = await Promise.all([
      waitForPostOk(page, INBOUND_API, (u) => u.includes('/verify')),
      page.getByTestId('ff-inbound-verify-complete').click(),
    ]);
    expect(verifyRes.ok()).toBeTruthy();
    await expect(page.getByTestId('ff-inbound-status-chip')).toContainText('В сортировке');
    await expect(page.getByTestId('ff-inbound-active-box')).toHaveCount(0);
  });

  test('TC-NEW-C01-N2 set line qty without open box shows error', async ({ page }) => {
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
    const put = await page.request.put(
      `${INBOUND_API}/${rid}/boxes/${boxId}/lines/${seed.productId}`,
      {
        headers: { ...h, 'Content-Type': 'application/json' },
        data: { quantity: 1 },
      },
    );
    expect(put.status()).toBe(409);
    expect(((await put.json()) as { detail: string }).detail).toBe('no_open_box');
  });
});
