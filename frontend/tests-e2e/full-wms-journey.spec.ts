import { test, expect } from '@playwright/test';

import {
  waitForGetOk,
  waitForInboundReceiveOk,
  waitForPatchOk,
  waitForPostOk,
} from './api-waits';
import { openFulfillmentRegistration } from './auth-flow';

/**
 * Полный путь пользователя с нуля: регистрация → справочники → приёмка.
 * Сценарий A: ячейка назначается после submit (PATCH), затем «Провести весь остаток».
 * Сценарий B: ячейка при создании строки → частичный приём → проведение остатка → два движения в журнале.
 *
 * TC-S06-004, TC-S06-007 — submit и проведение приёмки; TC-S03-001–S05 — справочники перед операцией.
 */
test.describe('Full WMS user journey', () => {
  test('inbound: assign cell after submit, then post all remaining', async ({ page }) => {
    const email = `e2e-full-a-${Date.now()}@example.com`;
    const sku = `SKU-FA-${Date.now()}`;
    const whCode = `wh-fa-${Date.now()}`;

    await page.goto('/');
    await openFulfillmentRegistration(page);
    await page.getByTestId('register-form').getByLabel('Организация').fill('E2E Full A');
    await page.getByTestId('register-form').getByLabel('Email администратора').fill(email);
    await page.getByTestId('register-form').getByLabel('Пароль').fill('password123');
    const [regRes] = await Promise.all([
      waitForPostOk(page, '/api/auth/register'),
      waitForGetOk(page, '/api/auth/me'),
      page.getByTestId('register-form').getByRole('button', { name: 'Создать аккаунт' }).click(),
    ]);
    const regJson = (await regRes.json()) as { access_token: string };
    const token = regJson.access_token;
    const h = { Authorization: `Bearer ${token}` };

    const wh = await page.request.post('/api/warehouses', {
      headers: h,
      data: { name: 'Склад A', code: whCode },
    });
    expect(wh.ok()).toBeTruthy();
    const wid = String(((await wh.json()) as { id: string }).id);
    const loc = await page.request.post(`/api/warehouses/${wid}/locations`, {
      headers: h,
      data: { code: 'BIN-A1' },
    });
    expect(loc.ok()).toBeTruthy();
    const pr = await page.request.post('/api/products', {
      headers: h,
      data: { name: 'Товар A', sku_code: sku, length_mm: 10, width_mm: 10, height_mm: 10 },
    });
    expect(pr.ok()).toBeTruthy();

    await page.goto('/app/ops/inbound');
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
    await expect(page.getByTestId('inbound-detail-line')).toContainText('принято 0');

    await Promise.all([
      waitForPostOk(page, '/api/operations/inbound-intake-requests', (u) => u.includes('/submit')),
      page.getByTestId('inbound-submit-request').click(),
    ]);
    await expect(page.getByTestId('inbound-detail-status')).toContainText('submitted');

    await Promise.all([
      waitForPostOk(page, '/api/operations/inbound-intake-requests', (u) => u.includes('/primary-accept')),
      page.getByTestId('inbound-primary-accept').click(),
    ]);
    await expect(page.getByTestId('inbound-detail-status')).toContainText('primary_accepted');

    await page.getByTestId('inbound-line-actual-qty').fill('5');
    await Promise.all([
      waitForPatchOk(page, '/api/operations/inbound-intake-requests', (u) => u.includes('/actual')),
      page.getByTestId('inbound-line-actual-save').click(),
    ]);
    await Promise.all([
      waitForPostOk(page, '/api/operations/inbound-intake-requests', (u) => u.includes('/verify')),
      page.getByTestId('inbound-verify-complete').click(),
    ]);
    await expect(page.getByTestId('inbound-detail-status')).toContainText('verified');

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
    const email = `e2e-full-b-${Date.now()}@example.com`;
    const sku = `SKU-FB-${Date.now()}`;
    const whCode = `wh-fb-${Date.now()}`;

    await page.goto('/');
    await openFulfillmentRegistration(page);
    await page.getByTestId('register-form').getByLabel('Организация').fill('E2E Full B');
    await page.getByTestId('register-form').getByLabel('Email администратора').fill(email);
    await page.getByTestId('register-form').getByLabel('Пароль').fill('password123');
    const [regRes] = await Promise.all([
      waitForPostOk(page, '/api/auth/register'),
      waitForGetOk(page, '/api/auth/me'),
      page.getByTestId('register-form').getByRole('button', { name: 'Создать аккаунт' }).click(),
    ]);
    const regJson = (await regRes.json()) as { access_token: string };
    const token = regJson.access_token;
    const h = { Authorization: `Bearer ${token}` };

    const wh = await page.request.post('/api/warehouses', {
      headers: h,
      data: { name: 'Склад B', code: whCode },
    });
    expect(wh.ok()).toBeTruthy();
    const wid = String(((await wh.json()) as { id: string }).id);
    const loc = await page.request.post(`/api/warehouses/${wid}/locations`, {
      headers: h,
      data: { code: 'BIN-B1' },
    });
    expect(loc.ok()).toBeTruthy();
    const pr = await page.request.post('/api/products', {
      headers: h,
      data: { name: 'Товар B', sku_code: sku, length_mm: 20, width_mm: 20, height_mm: 20 },
    });
    expect(pr.ok()).toBeTruthy();

    await page.goto('/app/ops/inbound');
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

    await Promise.all([
      waitForPostOk(page, '/api/operations/inbound-intake-requests', (u) => u.includes('/primary-accept')),
      page.getByTestId('inbound-primary-accept').click(),
    ]);
    await expect(page.getByTestId('inbound-detail-status')).toContainText('primary_accepted');

    await page.getByTestId('inbound-line-actual-qty').fill('8');
    await Promise.all([
      page.waitForResponse(
        (r) =>
          r.request().method() === 'PATCH' &&
          r.url().includes('/api/operations/inbound-intake-requests') &&
          r.url().includes('/actual') &&
          r.status() === 200,
      ),
      page.getByTestId('inbound-line-actual-save').click(),
    ]);
    await Promise.all([
      waitForPostOk(page, '/api/operations/inbound-intake-requests', (u) => u.includes('/verify')),
      page.getByTestId('inbound-verify-complete').click(),
    ]);
    await expect(page.getByTestId('inbound-detail-status')).toContainText('verified');

    await page.getByTestId('inbound-line-receive-qty').fill('3');
    const [recv1] = await Promise.all([
      waitForInboundReceiveOk(page),
      page.getByTestId('inbound-line-receive-submit').click(),
    ]);
    expect(recv1.ok()).toBeTruthy();
    await expect(page.getByTestId('inbound-detail-status')).toContainText('verified');
    await expect(page.getByTestId('inbound-detail-line')).toContainText('принято 3');
    await expect(
      page.getByTestId('inbound-movements-list').getByTestId('inbound-movement-row').filter({ hasText: '+3' }),
    ).toHaveCount(1);

    const [postRes] = await Promise.all([
      waitForPostOk(page, '/api/operations/inbound-intake-requests', (u) => u.includes('/post')),
      page.getByTestId('inbound-post-submit').click(),
    ]);
    expect(postRes.ok()).toBeTruthy();
    await expect(page.getByTestId('inbound-detail-status')).toContainText('posted');
    await expect(page.getByTestId('inbound-detail-line')).toContainText('принято 8');

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
