import { test, expect } from '@playwright/test';

import {
  waitForGetOk,
  waitForInboundReceiveOk,
  waitForLocationsListGet,
  waitForPatchOk,
  waitForPostOk,
} from './api-waits';

/**
 * Полный путь пользователя с нуля: регистрация → справочники → приёмка.
 * Сценарий A: ячейка назначается после submit (PATCH), затем «Провести весь остаток».
 * Сценарий B: ячейка при создании строки → частичный приём → проведение остатка → два движения в журнале.
 */
test.describe('Full WMS user journey', () => {
  test('inbound: assign cell after submit, then post all remaining', async ({ page }) => {
    const slug = `ff-full-a-${Date.now()}`;
    const email = `e2e-full-a-${Date.now()}@example.com`;
    const sku = `SKU-FA-${Date.now()}`;
    const whCode = `wh-fa-${Date.now()}`;

    await page.goto('/');
    await page.getByTestId('register-form').getByLabel('Организация').fill('E2E Full A');
    await page.getByTestId('register-slug').fill(slug);
    await page.getByTestId('register-form').getByLabel('Email админа').fill(email);
    await page.getByTestId('register-form').getByLabel('Пароль').fill('password123');
    await Promise.all([
      waitForPostOk(page, '/api/auth/register'),
      waitForGetOk(page, '/api/auth/me'),
      page.getByTestId('register-form').getByRole('button', { name: 'Создать аккаунт' }).click(),
    ]);

    await expect(page.getByTestId('catalog-section')).toBeVisible();
    await expect(page.getByTestId('operations-section')).toBeVisible();

    await page.getByTestId('warehouse-name').fill('Склад A');
    await page.getByTestId('warehouse-code').fill(whCode);
    await Promise.all([
      waitForPostOk(page, '/api/warehouses', (u) => !u.includes('/locations')),
      waitForGetOk(page, '/api/warehouses'),
      page.getByTestId('warehouse-submit').click(),
    ]);

    await page.getByTestId('warehouse-list').getByTestId('warehouse-item').first().click();

    await page.getByTestId('location-code').fill('BIN-A1');
    await Promise.all([
      waitForPostOk(page, '/api/warehouses', (u) => u.includes('/locations')),
      waitForLocationsListGet(page),
      page.getByTestId('location-submit').click(),
    ]);

    await page.getByTestId('product-name').fill('Товар A');
    await page.getByTestId('product-sku').fill(sku);
    await page.getByTestId('product-length-mm').fill('10');
    await page.getByTestId('product-width-mm').fill('10');
    await page.getByTestId('product-height-mm').fill('10');
    await Promise.all([
      waitForPostOk(page, '/api/products'),
      waitForGetOk(page, '/api/products'),
      page.getByTestId('product-submit').click(),
    ]);

    await Promise.all([
      waitForPostOk(
        page,
        '/api/operations/inbound-intake-requests',
        (u) => !u.includes('/lines') && !u.includes('/submit'),
      ),
      page.getByTestId('inbound-create-submit').click(),
    ]);
    await expect(page.getByTestId('inbound-detail-status')).toContainText('draft');

    await page
      .getByTestId('inbound-line-product')
      .selectOption({ label: `${sku} — Товар A` });
    await page.getByTestId('inbound-line-qty').fill('5');
    // Ячейку не задаём — «позже»
    const [lineRes] = await Promise.all([
      waitForPostOk(page, '/api/operations/inbound-intake-requests', (u) => u.includes('/lines')),
      page.getByTestId('inbound-line-submit').click(),
    ]);
    expect(lineRes.ok()).toBeTruthy();
    await expect(page.getByTestId('inbound-detail-line')).toContainText('принято 0 из 5');

    await Promise.all([
      waitForPostOk(page, '/api/operations/inbound-intake-requests', (u) => u.includes('/submit')),
      page.getByTestId('inbound-submit-request').click(),
    ]);
    await expect(page.getByTestId('inbound-detail-status')).toContainText('submitted');

    await page.getByTestId('inbound-line-storage-select').selectOption({ label: 'BIN-A1' });
    const [patchRes] = await Promise.all([
      waitForPatchOk(page, '/api/operations/inbound-intake-requests', (u) =>
        u.includes('/lines/') && !u.includes('/receive'),
      ),
      page.getByTestId('inbound-line-storage-save').click(),
    ]);
    expect(patchRes.ok()).toBeTruthy();
    await expect(page.getByTestId('inbound-detail-line')).toContainText('ячейка: BIN-A1');

    const [postRes] = await Promise.all([
      waitForPostOk(page, '/api/operations/inbound-intake-requests', (u) => u.includes('/post')),
      page.getByTestId('inbound-post-submit').click(),
    ]);
    expect(postRes.ok()).toBeTruthy();
    await expect(page.getByTestId('inbound-detail-status')).toContainText('posted');
    await expect(
      page.getByTestId('inbound-movements-list').getByTestId('inbound-movement-row').first(),
    ).toContainText('+5');

    const invRow = page
      .getByTestId('inventory-balance-list')
      .getByTestId('inventory-balance-row')
      .filter({ hasText: sku });
    await expect(invRow.first()).toContainText('5');
  });

  test('inbound: cell on line create, partial receive, then post remainder', async ({ page }) => {
    const slug = `ff-full-b-${Date.now()}`;
    const email = `e2e-full-b-${Date.now()}@example.com`;
    const sku = `SKU-FB-${Date.now()}`;
    const whCode = `wh-fb-${Date.now()}`;

    await page.goto('/');
    await page.getByTestId('register-form').getByLabel('Организация').fill('E2E Full B');
    await page.getByTestId('register-slug').fill(slug);
    await page.getByTestId('register-form').getByLabel('Email админа').fill(email);
    await page.getByTestId('register-form').getByLabel('Пароль').fill('password123');
    await Promise.all([
      waitForPostOk(page, '/api/auth/register'),
      waitForGetOk(page, '/api/auth/me'),
      page.getByTestId('register-form').getByRole('button', { name: 'Создать аккаунт' }).click(),
    ]);

    await page.getByTestId('warehouse-name').fill('Склад B');
    await page.getByTestId('warehouse-code').fill(whCode);
    await Promise.all([
      waitForPostOk(page, '/api/warehouses', (u) => !u.includes('/locations')),
      waitForGetOk(page, '/api/warehouses'),
      page.getByTestId('warehouse-submit').click(),
    ]);
    await page.getByTestId('warehouse-list').getByTestId('warehouse-item').first().click();

    await page.getByTestId('location-code').fill('BIN-B1');
    await Promise.all([
      waitForPostOk(page, '/api/warehouses', (u) => u.includes('/locations')),
      waitForLocationsListGet(page),
      page.getByTestId('location-submit').click(),
    ]);

    await page.getByTestId('product-name').fill('Товар B');
    await page.getByTestId('product-sku').fill(sku);
    await page.getByTestId('product-length-mm').fill('20');
    await page.getByTestId('product-width-mm').fill('20');
    await page.getByTestId('product-height-mm').fill('20');
    await Promise.all([
      waitForPostOk(page, '/api/products'),
      waitForGetOk(page, '/api/products'),
      page.getByTestId('product-submit').click(),
    ]);

    await Promise.all([
      waitForPostOk(
        page,
        '/api/operations/inbound-intake-requests',
        (u) => !u.includes('/lines') && !u.includes('/submit'),
      ),
      page.getByTestId('inbound-create-submit').click(),
    ]);

    await page
      .getByTestId('inbound-line-product')
      .selectOption({ label: `${sku} — Товар B` });
    await page.getByTestId('inbound-line-qty').fill('8');
    await page.getByTestId('inbound-line-location').selectOption({ label: 'BIN-B1' });
    await Promise.all([
      waitForPostOk(page, '/api/operations/inbound-intake-requests', (u) => u.includes('/lines')),
      page.getByTestId('inbound-line-submit').click(),
    ]);

    await Promise.all([
      waitForPostOk(page, '/api/operations/inbound-intake-requests', (u) => u.includes('/submit')),
      page.getByTestId('inbound-submit-request').click(),
    ]);
    await expect(page.getByTestId('inbound-detail-status')).toContainText('submitted');

    await page.getByTestId('inbound-line-receive-qty').fill('3');
    const [recv1] = await Promise.all([
      waitForInboundReceiveOk(page),
      page.getByTestId('inbound-line-receive-submit').click(),
    ]);
    expect(recv1.ok()).toBeTruthy();
    await expect(page.getByTestId('inbound-detail-status')).toContainText('submitted');
    await expect(page.getByTestId('inbound-detail-line')).toContainText('принято 3 из 8');
    await expect(
      page.getByTestId('inbound-movements-list').getByTestId('inbound-movement-row').filter({ hasText: '+3' }),
    ).toHaveCount(1);

    const [postRes] = await Promise.all([
      waitForPostOk(page, '/api/operations/inbound-intake-requests', (u) => u.includes('/post')),
      page.getByTestId('inbound-post-submit').click(),
    ]);
    expect(postRes.ok()).toBeTruthy();
    await expect(page.getByTestId('inbound-detail-status')).toContainText('posted');
    await expect(page.getByTestId('inbound-detail-line')).toContainText('принято 8 из 8');

    const movements = page.getByTestId('inbound-movements-list').getByTestId('inbound-movement-row');
    await expect(movements.filter({ hasText: '+3' })).toHaveCount(1);
    await expect(movements.filter({ hasText: '+5' })).toHaveCount(1);

    const invRow = page
      .getByTestId('inventory-balance-list')
      .getByTestId('inventory-balance-row')
      .filter({ hasText: sku });
    await expect(invRow.first()).toContainText('8');
  });
});
