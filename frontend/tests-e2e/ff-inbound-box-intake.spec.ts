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
    await page.getByTestId('ff-inbound-box-open').first().getByRole('button', { name: 'Наполнить' }).click();
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

  await apiCreateSubmittedInbound(page.request, seed, { plannedBoxes: 0, expectedQty: 4 });

  await loginFfAdmin(page, seed.adminEmail, seed.password);
  await page.getByTestId('nav-ff-reception').click();
  await page.getByTestId('ff-inbound-queue-table').locator('tbody tr').first().click();
  await expect(page.getByTestId('ff-inbound-doc-root')).toBeVisible();

  for (let i = 0; i < 2; i++) {
    await Promise.all([
      waitForPostOk(page, INBOUND_API, (u) => u.endsWith('/boxes')),
      page.getByTestId('ff-inbound-add-to-box').click(),
    ]);
    await expect(page.getByTestId('ff-inbound-box-add-dialog')).toHaveCount(0);
  }
  await expect(page.getByTestId('ff-inbound-box-open')).toHaveCount(2);

  await page.getByTestId('ff-inbound-box-open').nth(1).getByRole('button', { name: 'Наполнить' }).click();
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

  await page.getByTestId('ff-inbound-box-add-manual-edit').first().click();
  const qtyInput = page.getByTestId('ff-inbound-box-add-manual-qty').first();
  await qtyInput.fill('3');
  await Promise.all([
    waitForPutOk(page, INBOUND_API, (u) => u.includes('/boxes/') && u.includes('/lines/')),
    qtyInput.press('Enter'),
  ]);
  await expect(page.getByTestId('ff-inbound-box-add-qty')).toHaveText('3');
  await page.getByTestId('ff-inbound-box-add-close').click();

  await expect(page.getByTestId('ff-inbound-box-open').nth(0)).toContainText('Пока нет товаров');
  await expect(page.getByTestId('ff-inbound-box-open').nth(1)).toContainText('3');
  await expect(page.getByText(/закройте короб/i)).toHaveCount(0);
});
