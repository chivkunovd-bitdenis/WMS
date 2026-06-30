import { expect, test } from '@playwright/test';

import { waitForGetOk, waitForPostOk } from './api-waits';
import { openFulfillmentRegistration } from './auth-flow';
import { seedHonestSignProductFirstInventory, selectHonestSignSeller } from './ff-honest-sign-helpers';

/** TC-NEW-STAB-E2E-02 — STAB-E2E-02: ЧЗ товарная строка + пул без threshold + единый конструктор печати + нет «Перепечатки» в меню. */
test('stab cz ui print — product row, pool card, marking constructor, no reprints nav', async ({
  page,
}) => {
  test.setTimeout(180_000);

  const email = `e2e-stab-cz-${Date.now()}@example.com`;
  const password = 'password123';
  const e2eApi = process.env.E2E_API_ORIGIN ?? 'http://127.0.0.1:18000';
  const skuPrefix = `STAB-CZ-${Date.now()}`;

  await page.goto('/');
  await openFulfillmentRegistration(page);
  await page.getByTestId('register-form').getByLabel('Организация').fill('E2E STAB CZ Print');
  await page.getByTestId('register-form').getByLabel('Email администратора').fill(email);
  await page.getByTestId('register-form').getByLabel('Пароль').fill(password);
  const [regRes] = await Promise.all([
    waitForPostOk(page, '/api/auth/register'),
    waitForGetOk(page, '/api/auth/me'),
    page.getByTestId('register-form').getByRole('button', { name: 'Создать аккаунт' }).click(),
  ]);
  const token = String(((await regRes.json()) as { access_token: string }).access_token);
  const auth = { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' };
  const bearer = { Authorization: `Bearer ${token}` };

  const sellerRes = await page.request.post(`${e2eApi}/sellers`, {
    headers: auth,
    data: JSON.stringify({ name: 'E2E STAB CZ Seller', email: `stab-cz-${Date.now()}@example.com` }),
  });
  const sellerId = String(((await sellerRes.json()) as { id: string }).id);

  const { personalPoolId, productX } = await seedHonestSignProductFirstInventory(
    page,
    e2eApi,
    auth,
    bearer,
    sellerId,
    skuPrefix,
  );

  await page.request.patch(
    `${e2eApi}/integrations/wildberries/sellers/${sellerId}/tokens`,
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
    data: JSON.stringify({ job_type: 'wildberries_cards_sync', seller_id: sellerId }),
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
    `${e2eApi}/integrations/wildberries/sellers/${sellerId}/link-product`,
    {
      headers: auth,
      data: JSON.stringify({ product_id: productX.id, nm_id: 424242 }),
    },
  );

  await page.getByTestId('nav-ff-honest-sign').click();
  await expect(page.getByTestId('ff-honest-sign-page')).toBeVisible();
  await selectHonestSignSeller(page, sellerId);

  const productRow = page.getByTestId(`ff-honest-sign-product-row-${productX.id}`);
  await expect(productRow).toBeVisible();
  await expect(productRow.getByTestId(`ff-honest-sign-product-photo-${productX.id}`)).toBeVisible();
  await expect(productRow.getByTestId(`ff-honest-sign-product-name-${productX.id}`)).toContainText(
    'Product X',
  );
  await expect(productRow.getByTestId(`ff-honest-sign-product-sku-${productX.id}`)).toContainText(
    productX.sku_code,
  );
  await expect(productRow.getByTestId(`ff-honest-sign-product-size-${productX.id}`)).toContainText('L');
  await expect(productRow.getByTestId(`ff-honest-sign-product-print-${productX.id}`)).toBeVisible();

  await productRow.click();
  await expect(page).toHaveURL(new RegExp(`/app/ff/honest-sign/product/${productX.id}`));
  await expect(page.getByTestId('ff-honest-sign-product-page')).toBeVisible();
  await page.getByTestId(`ff-honest-sign-product-personal-pool-${personalPoolId}`).click();
  await expect(page).toHaveURL(new RegExp(`/app/ff/honest-sign/pool/${personalPoolId}`));
  await expect(page.getByTestId('ff-honest-sign-pool-page')).toBeVisible();
  await expect(page.getByTestId('ff-honest-sign-pool-thresholds')).toHaveCount(0);

  await page.getByTestId('nav-ff-honest-sign').click();
  await expect(page.getByTestId('ff-honest-sign-page')).toBeVisible();
  await expect(productRow).toBeVisible();

  await productRow.getByTestId(`ff-honest-sign-product-print-${productX.id}`).click();
  await expect(page.getByTestId('marking-print-dialog')).toBeVisible();
  await expect(page.getByTestId('marking-print-cz-qty')).toBeVisible();
  await expect(page.getByTestId('marking-print-wb-qty')).toBeVisible();
  await expect(page.getByTestId('marking-print-tape')).toBeVisible();
  await expect(page.getByTestId('marking-print-tape-item-0')).toHaveText('ЧЗ');

  await page.getByTestId('marking-print-wb-qty').locator('input').fill('2');
  await expect(page.getByTestId('marking-print-tape-item-1')).toHaveText('ЧЗ');
  await expect(page.getByTestId('marking-print-tape-item-2')).toHaveText('ШК ВБ');
  await page.getByTestId('marking-print-tape-item-2').dragTo(page.getByTestId('marking-print-tape-item-0'));
  await expect(page.getByTestId('marking-print-tape-item-0')).toHaveText('ШК ВБ');
  await expect(page.getByTestId('marking-print-preview-chip-1-0')).toHaveText('ШК ВБ');

  await expect(page.getByTestId('nav-ff-honest-sign-reprints')).toHaveCount(0);
  await expect(page.getByRole('navigation').getByText('Перепечатки')).toHaveCount(0);

  await page.getByTestId('marking-print-dialog').getByRole('button', { name: 'Отмена' }).click();
  await expect(page.getByTestId('marking-print-dialog')).toBeHidden();
});
