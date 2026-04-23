import { test, expect } from '@playwright/test';

import { waitForGetOk, waitForPostOk } from './api-waits';
import { openFulfillmentRegistration } from './auth-flow';

// TC-NEW-FF-001 — распределение приёмки по ячейкам (FF): частично, остаток в «Без ячейки», завершение фиксирует read-only.
test('ff inbound distribution: partial, leftover without cell, complete -> readonly', async ({ page }) => {
  const email = `e2e-ff-dist-${Date.now()}@example.com`;
  const sku = `SKU-FF-D-${Date.now()}`;
  const whCode = `wh-ffd-${Date.now()}`;

  await page.goto('/');
  await openFulfillmentRegistration(page);
  await page.getByTestId('register-form').getByLabel('Организация').fill('E2E FF Dist');
  await page.getByTestId('register-form').getByLabel('Email администратора').fill(email);
  await page.getByTestId('register-form').getByLabel('Пароль').fill('password123');
  const [regRes] = await Promise.all([
    waitForPostOk(page, '/api/auth/register'),
    waitForGetOk(page, '/api/auth/me'),
    page.getByTestId('register-form').getByRole('button', { name: 'Создать аккаунт' }).click(),
  ]);
  const token = ((await regRes.json()) as { access_token: string }).access_token;
  const h = { Authorization: `Bearer ${token}` };

  const wh = await page.request.post('/api/warehouses', {
    headers: h,
    data: { name: 'Склад', code: whCode },
  });
  expect(wh.ok()).toBeTruthy();
  const wid = ((await wh.json()) as { id: string }).id;

  const loc = await page.request.post(`/api/warehouses/${wid}/locations`, {
    headers: h,
    data: { code: 'A-01' },
  });
  expect(loc.ok()).toBeTruthy();
  const lid = ((await loc.json()) as { id: string }).id;

  const pr = await page.request.post('/api/products', {
    headers: h,
    data: { name: 'Товар', sku_code: sku, length_mm: 10, width_mm: 10, height_mm: 10 },
  });
  expect(pr.ok()).toBeTruthy();
  const pid = ((await pr.json()) as { id: string }).id;

  const base = '/api/operations/inbound-intake-requests';
  const cr = await page.request.post(base, { headers: h, data: { warehouse_id: wid } });
  expect(cr.ok()).toBeTruthy();
  const rid = ((await cr.json()) as { id: string }).id;

  const planned = new Date(Date.now() + 2 * 24 * 3600 * 1000).toISOString().slice(0, 10);
  const ppl = await page.request.patch(`${base}/${rid}`, {
    headers: { ...h, 'Content-Type': 'application/json' },
    data: { planned_delivery_date: planned },
  });
  expect(ppl.ok()).toBeTruthy();

  const ln = await page.request.post(`${base}/${rid}/lines`, {
    headers: { ...h, 'Content-Type': 'application/json' },
    data: { product_id: pid, expected_qty: 5 },
  });
  expect(ln.ok()).toBeTruthy();

  const sub = await page.request.post(`${base}/${rid}/submit`, { headers: h });
  expect(sub.ok()).toBeTruthy();
  const prim = await page.request.post(`${base}/${rid}/primary-accept`, { headers: h });
  expect(prim.ok()).toBeTruthy();

  await page.goto('/app/ff/dashboard');
  await expect(page.getByTestId('ff-dashboard-inbound-block')).toBeVisible();

  await page.getByTestId('ff-dash-inbound-row').filter({ hasText: planned }).first().click();
  await expect(page.getByTestId('ff-doc-dialog')).toBeVisible();
  await expect(page.getByTestId('ff-inbound-doc-root')).toBeVisible();
  await expect(page.getByTestId('ff-inbound-status-chip')).toContainText('Принято на складе');

  await expect(page.getByTestId('ff-inbound-admin-distribution')).toBeVisible();
  await page.getByTestId('ff-inbound-distribute-open').click();

  await page.getByTestId('ff-inbound-distribution-add-row').click();
  const row = page.getByTestId('ff-inbound-distribution-row').first();
  await row.getByTestId('ff-inbound-distribution-product').click();
  await page.getByRole('option', { name: new RegExp(sku) }).click();
  await row.getByTestId('ff-inbound-distribution-qty').fill('2');
  await row.getByTestId('ff-inbound-distribution-location').click();
  await page.getByRole('option', { name: 'A-01' }).click();

  const [saveRes] = await Promise.all([
    page.waitForResponse((r) => r.request().method() === 'PUT' && r.url().includes('/distribution-lines') && r.status() === 200),
    page.getByTestId('ff-inbound-distribution-save').click(),
  ]);
  expect(saveRes.ok()).toBeTruthy();
  await expect(page.getByTestId('ff-inbound-distribution-no-cell')).toContainText('3');

  const [completeRes] = await Promise.all([
    waitForPostOk(page, '/api/operations/inbound-intake-requests', (u) => u.includes('/distribution-complete')),
    page.getByTestId('ff-inbound-distribution-complete').click(),
  ]);
  expect(completeRes.ok()).toBeTruthy();

  await expect(page.getByTestId('ff-inbound-distribution-add-row')).toHaveCount(0);
  await expect(page.getByTestId('ff-inbound-distribution-no-cell')).toContainText('3');
});

