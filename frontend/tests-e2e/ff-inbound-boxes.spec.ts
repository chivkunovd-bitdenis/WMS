// TC-NEW-B01 — план/факт коробов (селлер + ФФ). TC-NEW-B02 — внутренние ШК и печать этикеток.
import { test, expect } from '@playwright/test';

import {
  waitForGetOk,
  waitForInboundBoxLabelPrintedOk,
  waitForPatchOk,
  waitForPostOk,
} from './api-waits';
import { loginAsSeller } from './auth-flow';
import {
  INBOUND_API,
  apiCreateSubmittedInbound,
  createSellerInboundDraftViaUi,
  loginFfAdmin,
  loginSellerPortal,
  openFfInboundDoc,
  seedFfSellerInbound,
  expectSellerPortalReady,
  sellerPath,
  sellerPortalEntry,
  submitSellerInbound,
} from './inbound-boxes-helpers';

test.describe.configure({ timeout: 120_000 });

test.describe('US-B-01 seller inbound draft — fields and actions', () => {
  test('planned date, planned boxes PATCH, picker, line qty, save draft, submit guard', async ({
    page,
  }) => {
    const seed = await seedFfSellerInbound(page);
    await loginSellerPortal(page, seed.sellerEmail, seed.password);

    await page.getByTestId('nav-seller-documents').click();
    await Promise.all([
      waitForPostOk(page, INBOUND_API, (u) => !u.includes('/lines') && !u.includes('/submit')),
      page.getByTestId('seller-create-inbound').click(),
    ]);
    await page.waitForURL(`**${sellerPath('/inbound/new')}`);
    await expect(page.getByTestId('seller-inbound-draft-form')).toBeVisible({ timeout: 20_000 });
    await expect(page.getByTestId('seller-inbound-status-chip')).toContainText('Черновик');

    const submitBtn = page.getByTestId('seller-inbound-submit-warehouse');
    await expect(submitBtn).toBeDisabled();

    const plannedBoxes = page.getByTestId('seller-inbound-planned-boxes');
    await plannedBoxes.fill('0');
    await plannedBoxes.blur();
    await expect(page.getByTestId('seller-inbound-draft-error')).toContainText('коробов');

    await plannedBoxes.fill('6');
    await Promise.all([
      waitForPatchOk(page, INBOUND_API, (u) => !u.includes('/lines')),
      plannedBoxes.blur(),
    ]);
    await expect(plannedBoxes).toHaveValue('6');

    const plannedDate = page.getByTestId('seller-inbound-planned-date');
    const tomorrow = new Date(Date.now() + 86400000).toISOString().slice(0, 10);
    await plannedDate.fill(tomorrow);
    await Promise.all([
      waitForPatchOk(page, INBOUND_API, (u) => !u.includes('/lines')),
      plannedDate.blur(),
    ]);

    await page.getByTestId('seller-inbound-add-products').click();
    await expect(page.getByTestId('seller-inbound-picker')).toBeVisible();
    await page.getByTestId('seller-inbound-picker-search').fill(seed.sku);
    await expect(page.getByTestId('seller-inbound-picker-row').first()).toBeVisible();

    await page.getByTestId('seller-inbound-picker-cancel').click();
    await expect(page.getByTestId('seller-inbound-picker')).toBeHidden();

    await page.getByTestId('seller-inbound-add-products').click();
    await page.getByTestId('seller-inbound-picker-qty').first().fill('7');
    await Promise.all([
      waitForPostOk(page, INBOUND_API, (u) => u.includes('/lines')),
      page.getByTestId('seller-inbound-picker-apply').click(),
    ]);
    await expect(page.getByTestId('seller-inbound-line-row')).toHaveCount(1);
    await expect(submitBtn).toBeEnabled();

    const lineQty = page.getByTestId('seller-inbound-line-qty').first();
    await lineQty.fill('9');
    await Promise.all([
      waitForPatchOk(page, INBOUND_API, (u) => u.includes('/expected')),
      lineQty.blur(),
    ]);

    await page.getByTestId('seller-inbound-save-draft').click();
    await expect(page.getByTestId('seller-documents-table')).toBeVisible();

    await page.getByTestId('seller-documents-row').first().click();
    await expect(page.getByTestId('seller-inbound-draft-form')).toBeVisible();
    await expect(plannedBoxes).toHaveValue('6');
    await expect(page.getByTestId('seller-inbound-line-qty').first()).toHaveValue('9');
  });
});

test.describe('US-B-01 FF primary accept by boxes', () => {
  test('plan match: no discrepancy warning; plan mismatch: warning + badge after accept', async ({
    page,
  }) => {
    const seed = await seedFfSellerInbound(page);
    await createSellerInboundDraftViaUi(page, seed, { plannedBoxes: '4', lineQty: '2' });
    await submitSellerInbound(page);

    await loginFfAdmin(page, seed.adminEmail, seed.password);
    await openFfInboundDoc(page, seed);

    await expect(page.getByTestId('ff-inbound-admin-submitted')).toBeVisible();
    await expect(page.getByTestId('ff-inbound-planned-boxes')).toContainText('4');
    await expect(page.getByTestId('ff-inbound-status-chip')).toContainText('Передано');

    const actualInput = page.getByTestId('ff-inbound-actual-box-count');
    await actualInput.fill('4');
    await expect(page.getByTestId('ff-inbound-boxes-discrepancy')).toBeHidden();

    await Promise.all([
      waitForPostOk(page, INBOUND_API, (u) => u.includes('/primary-accept')),
      page.getByTestId('ff-inbound-primary-accept').click(),
    ]);

    await expect(page.getByTestId('ff-inbound-admin-submitted')).toBeHidden();
    await expect(page.getByTestId('ff-inbound-status-chip')).toContainText('Принято');
    await expect(page.getByTestId('ff-inbound-boxes-discrepancy-badge')).toBeHidden();
    await expect(page.getByTestId('ff-inbound-boxes-panel')).toBeVisible();
    await expect(page.getByTestId('ff-inbound-box-row')).toHaveCount(4);

    await page.getByTestId('ff-inbound-close').click();
    await expect(page.getByTestId('ff-doc-dialog')).toBeHidden();

    const row = page.getByTestId('ff-docs-row').filter({ hasText: 'Поставка' }).first();
    await row.click();
    await expect(page.getByTestId('ff-inbound-boxes-panel')).toBeVisible();
    await expect(page.getByTestId('ff-inbound-box-row')).toHaveCount(4);
  });
});

test.describe('US-B-02 inbound box barcodes and print actions', () => {
  test('discrepancy path, INB barcodes, print one and print all call mark-label-printed', async ({
    page,
  }) => {
    await page.addInitScript(() => {
      window.print = () => {};
    });

    const seed = await seedFfSellerInbound(page);
    await createSellerInboundDraftViaUi(page, seed, { plannedBoxes: '4', lineQty: '1' });
    await submitSellerInbound(page);
    await openFfInboundDoc(page, seed);

    const actualInput = page.getByTestId('ff-inbound-actual-box-count');
    await actualInput.fill('3');
    await expect(page.getByTestId('ff-inbound-boxes-discrepancy')).toBeVisible();

    await Promise.all([
      waitForPostOk(page, INBOUND_API, (u) => u.includes('/primary-accept')),
      page.getByTestId('ff-inbound-primary-accept').click(),
    ]);

    await expect(page.getByTestId('ff-inbound-boxes-discrepancy-badge')).toBeVisible();
    await expect(page.getByTestId('ff-inbound-boxes-panel')).toBeVisible();

    const rows = page.getByTestId('ff-inbound-box-row');
    await expect(rows).toHaveCount(3);

    const barcodes = await page.getByTestId('ff-inbound-box-barcode').allTextContents();
    expect(barcodes).toHaveLength(3);
    for (const code of barcodes) {
      expect(code).toMatch(/^INB-[A-F0-9]{12}$/);
    }
    expect(new Set(barcodes).size).toBe(3);

    const row0 = rows.nth(0);
    await expect(row0.getByText('Не печатали')).toBeVisible();
    await Promise.all([
      waitForInboundBoxLabelPrintedOk(page),
      row0.getByTestId('ff-inbound-box-print').click(),
    ]);
    await expect(row0.getByText('Напечатано')).toBeVisible();

    // «Печать всех» — по одному POST на короб (уже напечатанный короб 1 тоже отмечается снова).
    const markPrinted = page.waitForResponse(
      (r) =>
        r.request().method() === 'POST' &&
        r.url().includes('/mark-label-printed') &&
        r.status() >= 200 &&
        r.status() < 300,
      { times: 3 },
    );
    await Promise.all([markPrinted, page.getByTestId('ff-inbound-boxes-print-all').click()]);
    for (let i = 0; i < 3; i += 1) {
      await expect(rows.nth(i).getByText('Напечатано')).toBeVisible();
    }
  });
});

test.describe('US-B-01/B-02 API contracts (regression)', () => {
  test('primary-accept returns boxes; mark-label-printed sets timestamp', async ({ page }) => {
    const seed = await seedFfSellerInbound(page);
    const rid = await apiCreateSubmittedInbound(page.request, seed, {
      plannedBoxes: 2,
      expectedQty: 5,
    });
    const h = { Authorization: `Bearer ${seed.token}` };

    const prim = await page.request.post(`${INBOUND_API}/${rid}/primary-accept`, {
      headers: { ...h, 'Content-Type': 'application/json' },
      data: { actual_box_count: 2 },
    });
    expect(prim.ok()).toBeTruthy();
    const body = (await prim.json()) as {
      boxes: { id: string; box_number: number; internal_barcode: string; label_printed_at: string | null }[];
      boxes_discrepancy: boolean;
    };
    expect(body.boxes).toHaveLength(2);
    expect(body.boxes_discrepancy).toBe(false);

    const boxId = body.boxes[0]!.id;
    const mark = await page.request.post(
      `${INBOUND_API}/${rid}/boxes/${boxId}/mark-label-printed`,
      { headers: h },
    );
    expect(mark.ok()).toBeTruthy();
    const marked = (await mark.json()) as { label_printed_at: string | null };
    expect(marked.label_printed_at).not.toBeNull();
  });
});

test.describe('US-B-01 seller first-time login path', () => {
  test('seller account with password can submit inbound with planned boxes', async ({ page }) => {
    const seed = await seedFfSellerInbound(page);

    const altEmail = `alt-${seed.sellerEmail}`;
    await page.request.post('/api/auth/seller-accounts', {
      headers: { Authorization: `Bearer ${seed.token}` },
      data: { seller_id: seed.sellerId, email: altEmail },
    });

    await page.getByTestId('logout').click();
    await page.goto(sellerPortalEntry());
    await page.getByTestId('login-form').waitFor({ state: 'visible' });
    await loginAsSeller(page, altEmail, seed.password, { firstTime: true });
    await expectSellerPortalReady(page);

    await page.getByTestId('nav-seller-documents').click();
    await page.getByTestId('seller-create-inbound').click();
    await page.waitForURL(`**${sellerPath('/inbound/new')}`);
    await waitForPostOk(page, INBOUND_API, (u) => !u.includes('/lines') && !u.includes('/submit'));

    await page.getByTestId('seller-inbound-planned-boxes').fill('2');
    await page.getByTestId('seller-inbound-planned-boxes').blur();
    await page.getByTestId('seller-inbound-add-products').click();
    await page.getByTestId('seller-inbound-picker-search').fill(seed.sku);
    await page.getByTestId('seller-inbound-picker-qty').first().fill('1');
    await page.getByTestId('seller-inbound-picker-apply').click();
    await Promise.all([
      waitForPostOk(page, INBOUND_API, (u) => u.includes('/submit')),
      page.getByTestId('seller-inbound-submit-warehouse').click(),
    ]);
    await expect(page.getByTestId('seller-documents-row')).toHaveCount(1);
  });
});
