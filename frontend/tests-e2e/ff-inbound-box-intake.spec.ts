import { test, expect } from '@playwright/test';

import { waitForPatchOk, waitForPostOk, waitForPutOk } from './api-waits';
import {
  INBOUND_API,
  apiCreateSubmittedInbound,
  beginInboundReceiving,
  beginInboundReceivingWithBoxes,
  ffInboundBoxAddManualQty,
  loginFfAdmin,
  openFfInboundDoc,
  seedFfSellerInbound,
} from './inbound-boxes-helpers';

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

    await ffInboundBoxAddManualQty(page, 3);
    await ffInboundBoxAddManualQty(page, 2);

    await expect(page.getByTestId('ff-inbound-line-actual-display').first()).toHaveText('5');
    await expect(page.getByTestId('ff-inbound-line-row-match')).toBeVisible();

    const [verifyRes] = await Promise.all([
      waitForPostOk(page, INBOUND_API, (u) => u.includes('/complete-receiving')),
      page.getByTestId('ff-inbound-verify-complete').click(),
    ]);
    expect(verifyRes.ok()).toBeTruthy();
    await expect(page.getByTestId('ff-inbound-status-chip')).toContainText('В сортировке');
  });

  test('TC-NEW-C01 verify with open box saves qty and auto-closes', async ({ page }) => {
    const seed = await seedFfSellerInbound(page);
    const rid = await apiCreateSubmittedInbound(page.request, seed, {
      plannedBoxes: 1,
      expectedQty: 4,
    });
    const h = { Authorization: `Bearer ${seed.token}` };
    await beginInboundReceiving(page.request, h, rid);

    await loginFfAdmin(page, seed.adminEmail, seed.password);
    await openFfInboundDoc(page, seed, { skipLogin: true });

    await page.getByTestId('ff-inbound-add-to-box').click();
    await expect(page.getByTestId('ff-inbound-box-add-dialog')).toBeVisible();
    await page.getByTestId('ff-inbound-box-add-manual-edit').first().click();
    const qtyInput = page.getByTestId('ff-inbound-box-add-manual-qty').first();
    await qtyInput.fill('4');
    await Promise.all([
      waitForPutOk(page, INBOUND_API, (u) => u.includes('/boxes/') && u.includes('/lines/')),
      qtyInput.press('Enter'),
    ]);

    await Promise.all([
      waitForPostOk(page, INBOUND_API, (u) => u.includes('/close')),
      page.getByTestId('ff-inbound-box-add-close-box').click(),
    ]);
    await expect(page.getByTestId('ff-inbound-box-add-dialog')).toBeHidden();

    const [verifyRes] = await Promise.all([
      waitForPostOk(page, INBOUND_API, (u) => u.includes('/complete-receiving')),
      page.getByTestId('ff-inbound-verify-complete').click(),
    ]);
    expect(verifyRes.ok()).toBeTruthy();
    await expect(page.getByTestId('ff-inbound-status-chip')).toContainText('В сортировке');
    await expect(page.getByTestId('ff-inbound-box-add-dialog')).toBeHidden();
  });

  test('TC-NEW-C01-N2 set line qty without open box shows error', async ({ page }) => {
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
    expect(put.status()).toBe(409);
    expect(((await put.json()) as { detail: string }).detail).toBe('box_closed');
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

    const [verifyRes] = await Promise.all([
      waitForPostOk(page, INBOUND_API, (u) => u.includes('/complete-receiving')),
      page.getByTestId('ff-inbound-verify-complete').click(),
    ]);
    expect(verifyRes.ok()).toBeTruthy();
    await expect(page.getByTestId('ff-inbound-status-chip')).toContainText('В сортировке');
  });
});
