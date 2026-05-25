import { expect, type APIRequestContext, type Page } from '@playwright/test';

import { waitForGetOk, waitForPatchOk, waitForPostOk, waitForPutOk } from './api-waits';
import { loginAsSeller, openFulfillmentRegistration } from './auth-flow';

export const INBOUND_API = '/api/operations/inbound-intake-requests';

/** `/seller` on unified Vite app; `` on dedicated seller portal (docker :15174). */
export const SELLER_PATH_PREFIX = process.env.E2E_SELLER_PATH_PREFIX ?? '/seller';

export function sellerPath(subpath: string): string {
  const sub = subpath.startsWith('/') ? subpath : `/${subpath}`;
  if (!SELLER_PATH_PREFIX) {
    return sub;
  }
  return `${SELLER_PATH_PREFIX}${sub}`;
}

/** Vite seller entry (avoid FF App redirect to docker :15174). */
export function sellerPortalEntry(): string {
  return SELLER_PATH_PREFIX ? `${SELLER_PATH_PREFIX}/` : '/';
}

export async function expectSellerPortalReady(page: Page): Promise<void> {
  await expect(page.getByTestId('nav-seller-documents')).toBeVisible({ timeout: 20_000 });
}

export type InboundBoxesSeed = {
  suffix: string;
  adminEmail: string;
  sellerEmail: string;
  password: string;
  sku: string;
  token: string;
  sellerId: string;
  warehouseId: string;
  productId: string;
};

/** FF admin + seller account + warehouse + product (seller-owned). */
export async function seedFfSellerInbound(
  page: Page,
  suffix = String(Date.now()),
): Promise<InboundBoxesSeed> {
  const adminEmail = `ff-box-adm-${suffix}@example.com`;
  const sellerEmail = `seller-box-${suffix}@example.com`;
  const password = 'password123';
  const sku = `sku-box-${suffix}`;

  await page.goto('/');
  await openFulfillmentRegistration(page);
  await page.getByTestId('register-form').getByLabel('Организация').fill('FF Box Co');
  await page.getByTestId('register-form').getByLabel('Email администратора').fill(adminEmail);
  await page.getByTestId('register-form').getByLabel('Пароль').fill(password);
  const [regRes] = await Promise.all([
    waitForPostOk(page, '/api/auth/register'),
    waitForGetOk(page, '/api/auth/me'),
    page.getByTestId('register-form').getByRole('button', { name: 'Создать аккаунт' }).click(),
  ]);
  const token = ((await regRes.json()) as { access_token: string }).access_token;
  const h = { Authorization: `Bearer ${token}` };

  const sellerRes = await page.request.post('/api/sellers', {
    headers: h,
    data: { name: `Box Seller ${suffix}` },
  });
  if (!sellerRes.ok()) {
    throw new Error(`seller create: ${sellerRes.status()}`);
  }
  const sellerId = String(((await sellerRes.json()) as { id: string }).id);

  await page.request.post('/api/auth/seller-accounts', {
    headers: h,
    data: { seller_id: sellerId, email: sellerEmail, password },
  });

  const whRes = await page.request.post('/api/warehouses', {
    headers: h,
    data: { name: 'WH', code: `wh-${suffix}` },
  });
  if (!whRes.ok()) {
    throw new Error(`warehouse create: ${whRes.status()}`);
  }
  const warehouseId = String(((await whRes.json()) as { id: string }).id);

  const prRes = await page.request.post('/api/products', {
    headers: h,
    data: {
      name: 'Box Product',
      sku_code: sku,
      length_mm: 100,
      width_mm: 100,
      height_mm: 100,
      seller_id: sellerId,
    },
  });
  if (!prRes.ok()) {
    throw new Error(`product create: ${prRes.status()}`);
  }
  const productId = String(((await prRes.json()) as { id: string }).id);

  return {
    suffix,
    adminEmail,
    sellerEmail,
    password,
    sku,
    token,
    sellerId,
    warehouseId,
    productId,
  };
}

export async function loginFfAdmin(
  page: Page,
  email: string,
  password: string,
): Promise<void> {
  await page.goto('/');
  const loginForm = page.getByTestId('login-form');
  if (!(await loginForm.isVisible().catch(() => false))) {
    await expect(page.getByTestId('logout')).toBeVisible({ timeout: 10_000 });
    return;
  }
  await loginForm.getByLabel('Email').fill(email);
  await loginForm.getByLabel('Пароль').fill(password);
  await Promise.all([
    waitForPostOk(page, '/api/auth/login'),
    loginForm.getByRole('button', { name: 'Войти' }).click(),
  ]);
}

export async function loginSellerPortal(
  page: Page,
  email: string,
  password: string,
): Promise<void> {
  await page.goto(sellerPortalEntry());
  const logout = page.getByTestId('logout');
  if (await logout.isVisible().catch(() => false)) {
    await logout.click();
    await page.getByTestId('login-form').waitFor({ state: 'visible' });
  }
  await loginAsSeller(page, email, password, { firstTime: false });
  await expectSellerPortalReady(page);
}

export async function createSellerInboundDraftViaUi(
  page: Page,
  seed: InboundBoxesSeed,
  opts: { plannedBoxes: string; lineQty: string },
): Promise<string> {
  await loginSellerPortal(page, seed.sellerEmail, seed.password);
  await page.getByTestId('nav-seller-documents').click();
  await Promise.all([
    waitForPostOk(page, INBOUND_API, (u) => !u.includes('/lines') && !u.includes('/submit')),
    page.getByTestId('seller-create-inbound').click(),
  ]);
  await page.waitForURL(`**${sellerPath('/inbound/new')}`);
  await expect(page.getByTestId('seller-inbound-draft-form')).toBeVisible({ timeout: 20_000 });

  const planned = page.getByTestId('seller-inbound-planned-boxes');
  await planned.fill(opts.plannedBoxes);
  await Promise.all([
    waitForPatchOk(page, INBOUND_API, (u) => !u.includes('/lines')),
    planned.blur(),
  ]);

  await page.getByTestId('seller-inbound-add-products').click();
  await expect(page.getByTestId('seller-inbound-picker')).toBeVisible();
  await page.getByTestId('seller-inbound-picker-search').fill(seed.sku);
  await page.getByTestId('seller-inbound-picker-qty').first().fill(opts.lineQty);
  await Promise.all([
    waitForPostOk(page, INBOUND_API, (u) => u.includes('/lines')),
    page.getByTestId('seller-inbound-picker-apply').click(),
  ]);
  await expect(page.getByTestId('seller-inbound-line-row')).toHaveCount(1);

  const listRes = await page.request.get(INBOUND_API, {
    headers: { Authorization: `Bearer ${await sellerAccessToken(page, seed)}` },
  });
  const rows = (await listRes.json()) as { id: string }[];
  if (!listRes.ok() || rows.length === 0) {
    throw new Error('inbound list empty after draft create');
  }
  return rows[0]!.id;
}

async function sellerAccessToken(page: Page, seed: InboundBoxesSeed): Promise<string> {
  const login = await page.request.post('/api/auth/login', {
    data: { email: seed.sellerEmail, password: seed.password },
  });
  if (!login.ok()) {
    throw new Error(`seller login: ${login.status()}`);
  }
  return String(((await login.json()) as { access_token: string }).access_token);
}

export async function submitSellerInbound(page: Page): Promise<void> {
  await Promise.all([
    waitForPostOk(page, INBOUND_API, (u) => u.includes('/submit')),
    page.getByTestId('seller-inbound-submit-warehouse').click(),
  ]);
  await expect(page.getByTestId('seller-documents-table')).toBeVisible();
}

export async function openFfInboundDoc(
  page: Page,
  seed: InboundBoxesSeed,
  opts?: { skipLogin?: boolean },
): Promise<void> {
  if (!opts?.skipLogin) {
    await loginFfAdmin(page, seed.adminEmail, seed.password);
  }
  await page.getByTestId('nav-ff-supplies-shipments').click();
  await expect(page.getByTestId('ff-supplies-shipments-page')).toBeVisible();
  await page.getByTestId('ff-docs-filter-inbound').click();
  const row = page.getByTestId('ff-docs-row').filter({ hasText: 'Поставка' }).first();
  await row.click();
  // Поставка открывается в общем ff-doc-dialog (App), не во вложенном supplies-dialog.
  await expect(page.getByTestId('ff-doc-dialog')).toBeVisible();
  await expect(page.getByTestId('ff-inbound-doc-root')).toBeVisible();
}

type InboundBoxRef = { id: string; internal_barcode: string };

/** TC-NEW-C01 — поштучный факт через скан INB и ШК товара (sku_code или WB). */
/** Заполнить факт на экране /app/ops/inbound после primary-accept (один короб). */
export async function v2InboundBoxIntakeUi(
  page: Page,
  headers: { Authorization: string },
  sku: string,
  totalQty: number,
): Promise<void> {
  const list = await page.request.get(INBOUND_API, { headers });
  if (!list.ok()) {
    throw new Error(`inbound list: ${list.status()}`);
  }
  const rid = String(((await list.json()) as { id: string }[])[0]!.id);
  const got = await page.request.get(`${INBOUND_API}/${rid}`, { headers });
  if (!got.ok()) {
    throw new Error(`inbound get: ${got.status()}`);
  }
  const inb = String(
    ((await got.json()) as { boxes: { internal_barcode: string }[] }).boxes[0]!
      .internal_barcode,
  );
  await page.getByTestId('inbound-box-open-scan').fill(inb);
  await Promise.all([
    waitForPostOk(page, INBOUND_API, (u) => u.includes('/boxes/open')),
    page.getByTestId('inbound-box-open-submit').click(),
  ]);
  for (let n = 0; n < totalQty; n++) {
    await page.getByTestId('inbound-product-scan').fill(sku);
    await Promise.all([
      waitForPostOk(page, INBOUND_API, (u) => u.includes('/boxes/') && u.includes('/scan')),
      page.getByTestId('inbound-product-scan-submit').click(),
    ]);
  }
  await Promise.all([
    waitForPostOk(page, INBOUND_API, (u) => u.includes('/close')),
    page.getByTestId('inbound-box-close').click(),
  ]);
}

export async function fulfillInboundViaBoxScans(
  req: APIRequestContext,
  adminHeaders: { Authorization: string },
  rid: string,
  boxes: InboundBoxRef[],
  productBarcode: string,
  scanCounts: number[],
): Promise<void> {
  const base = `${INBOUND_API}/${rid}`;
  for (let i = 0; i < boxes.length; i++) {
    const box = boxes[i]!;
    const count = scanCounts[i] ?? 0;
    const open = await req.post(`${base}/boxes/open`, {
      headers: { ...adminHeaders, 'Content-Type': 'application/json' },
      data: { barcode: box.internal_barcode },
    });
    if (!open.ok()) {
      throw new Error(`open inbound box: ${open.status()} ${await open.text()}`);
    }
    for (let n = 0; n < count; n++) {
      const scan = await req.post(`${base}/boxes/${box.id}/scan`, {
        headers: { ...adminHeaders, 'Content-Type': 'application/json' },
        data: { barcode: productBarcode },
      });
      if (!scan.ok()) {
        throw new Error(`scan product into box: ${scan.status()} ${await scan.text()}`);
      }
    }
    const close = await req.post(`${base}/boxes/${box.id}/close`, {
      headers: adminHeaders,
    });
    if (!close.ok()) {
      throw new Error(`close inbound box: ${close.status()} ${await close.text()}`);
    }
  }
}

export async function apiCreateSubmittedInbound(
  req: APIRequestContext,
  seed: InboundBoxesSeed,
  opts: { plannedBoxes: number; expectedQty: number },
): Promise<string> {
  const h = { Authorization: `Bearer ${seed.token}` };
  const sh = await sellerToken(req, seed);
  const cr = await req.post(INBOUND_API, {
    headers: sh,
    data: { warehouse_id: seed.warehouseId },
  });
  if (!cr.ok()) {
    throw new Error(`create inbound: ${cr.status()}`);
  }
  const rid = String(((await cr.json()) as { id: string }).id);
  await req.patch(`${INBOUND_API}/${rid}`, {
    headers: { ...sh, 'Content-Type': 'application/json' },
    data: { planned_box_count: opts.plannedBoxes },
  });
  await req.post(`${INBOUND_API}/${rid}/lines`, {
    headers: { ...sh, 'Content-Type': 'application/json' },
    data: { product_id: seed.productId, expected_qty: opts.expectedQty },
  });
  const sub = await req.post(`${INBOUND_API}/${rid}/submit`, { headers: sh });
  if (!sub.ok()) {
    throw new Error(`submit: ${sub.status()}`);
  }
  return rid;
}

/** Set quantity for the first line in the active open box (blur saves via PUT). */
export async function fillFfInboundBoxLineQty(page: Page, quantity: number): Promise<void> {
  const input = page.getByTestId('ff-inbound-box-line-qty').first();
  await input.fill(String(quantity));
  await Promise.all([
    waitForPutOk(page, INBOUND_API, (u) => u.includes('/boxes/') && u.includes('/lines/')),
    input.blur(),
  ]);
}

async function sellerToken(
  req: APIRequestContext,
  seed: InboundBoxesSeed,
): Promise<{ Authorization: string }> {
  const login = await req.post('/api/auth/login', {
    data: { email: seed.sellerEmail, password: seed.password },
  });
  if (!login.ok()) {
    throw new Error(`seller login: ${login.status()}`);
  }
  const tok = String(((await login.json()) as { access_token: string }).access_token);
  return { Authorization: `Bearer ${tok}` };
}
