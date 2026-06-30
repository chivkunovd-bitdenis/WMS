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
  await page.getByTestId('nav-ff-reception').click();
  await expect(page.getByTestId('ff-reception-page')).toBeVisible();
  await page.getByTestId('ff-inbound-queue-table').locator('tbody tr').first().click();
  // Приёмка открывается в ff-doc-dialog (App).
  await expect(page.getByTestId('ff-doc-dialog')).toBeVisible();
  await expect(page.getByTestId('ff-inbound-doc-root')).toBeVisible();
}

type InboundBoxRef = { id: string; internal_barcode: string };

export type InboundRequestJson = {
  id: string;
  status: string;
  lines: {
    id: string;
    product_id: string;
    actual_qty?: number | null;
    effective_actual_qty?: number | null;
  }[];
  boxes: {
    id: string;
    internal_barcode: string;
    box_number?: number;
    is_open?: boolean;
    label_printed_at?: string | null;
    intake_closed_at?: string | null;
  }[];
  boxes_discrepancy?: boolean;
  actual_box_count?: number | null;
  planned_box_count?: number | null;
};

/** Begin receiving on a submitted inbound (replaces legacy primary-accept). */
export async function beginInboundReceiving(
  req: APIRequestContext,
  adminHeaders: { Authorization: string },
  rid: string,
): Promise<void> {
  const base = `${INBOUND_API}/${rid}`;
  const got = await req.get(base, { headers: adminHeaders });
  if (!got.ok()) {
    throw new Error(`inbound get: ${got.status()} ${await got.text()}`);
  }
  const body = (await got.json()) as InboundRequestJson;
  if (body.status !== 'submitted') {
    return;
  }
  const lineId = body.lines[0]?.id;
  if (!lineId) {
    throw new Error('inbound has no lines');
  }
  const patch = await req.patch(`${base}/lines/${lineId}/actual`, {
    headers: { ...adminHeaders, 'Content-Type': 'application/json' },
    data: { actual_qty: 0 },
  });
  if (!patch.ok()) {
    throw new Error(`begin receiving: ${patch.status()} ${await patch.text()}`);
  }
}

/** Create N on-demand inbound boxes (optionally close each after creation). */
export async function createInboundBoxes(
  req: APIRequestContext,
  adminHeaders: { Authorization: string },
  rid: string,
  boxCount: number,
  opts?: { closeEach?: boolean },
): Promise<InboundBoxRef[]> {
  const base = `${INBOUND_API}/${rid}`;
  const boxes: InboundBoxRef[] = [];
  const closeEach = opts?.closeEach ?? false;
  for (let i = 0; i < boxCount; i += 1) {
    const boxRes = await req.post(`${base}/boxes`, { headers: adminHeaders });
    if (!boxRes.ok()) {
      throw new Error(`create box: ${boxRes.status()} ${await boxRes.text()}`);
    }
    const box = (await boxRes.json()) as {
      id: string;
      internal_barcode: string;
      is_open?: boolean;
    };
    if (closeEach && box.is_open !== false) {
      const close = await req.post(`${base}/boxes/${box.id}/close`, { headers: adminHeaders });
      if (!close.ok()) {
        throw new Error(`close box: ${close.status()} ${await close.text()}`);
      }
    }
    boxes.push({ id: box.id, internal_barcode: box.internal_barcode });
  }
  return boxes;
}

/** Replaces removed POST .../primary-accept for e2e/API seeding. */
export async function beginInboundReceivingWithBoxes(
  req: APIRequestContext,
  adminHeaders: { Authorization: string },
  rid: string,
  opts?: { boxCount?: number; closeEach?: boolean },
): Promise<{ boxes: InboundBoxRef[]; body: InboundRequestJson }> {
  await beginInboundReceiving(req, adminHeaders, rid);
  const count = opts?.boxCount ?? 0;
  const closeEach = opts?.closeEach ?? false;
  const boxes =
    count > 0 ? await createInboundBoxes(req, adminHeaders, rid, count, { closeEach }) : [];
  const got = await req.get(`${INBOUND_API}/${rid}`, { headers: adminHeaders });
  if (!got.ok()) {
    throw new Error(`inbound get: ${got.status()} ${await got.text()}`);
  }
  return { boxes, body: (await got.json()) as InboundRequestJson };
}

/** TC-NEW-C01 — поштучный факт через скан INB и ШК товара (sku_code или WB). */
/** Заполнить факт на экране /app/ops/inbound после начала приёмки (один короб). */
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
  let got = await page.request.get(`${INBOUND_API}/${rid}`, { headers });
  if (!got.ok()) {
    throw new Error(`inbound get: ${got.status()}`);
  }
  let body = (await got.json()) as InboundRequestJson;
  if (body.status === 'submitted') {
    await beginInboundReceiving(page.request, headers, rid);
    got = await page.request.get(`${INBOUND_API}/${rid}`, { headers });
    body = (await got.json()) as InboundRequestJson;
  }
  if (!body.boxes?.length) {
    await createInboundBoxes(page.request, headers, rid, 1);
    got = await page.request.get(`${INBOUND_API}/${rid}`, { headers });
    body = (await got.json()) as InboundRequestJson;
  }
  const inb = String(body.boxes[0]!.internal_barcode);
  const openBox = body.boxes.find((b) => b.is_open);
  if (!openBox) {
    await page.getByTestId('inbound-box-open-scan').fill(inb);
    await Promise.all([
      waitForPostOk(page, INBOUND_API, (u) => u.includes('/boxes/open')),
      page.getByTestId('inbound-box-open-submit').click(),
    ]);
  }
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
  if (!Array.isArray(boxes)) {
    throw new Error('fulfillInboundViaBoxScans expected inbound boxes array');
  }
  const rounds = Math.max(boxes.length, scanCounts.length);
  for (let i = 0; i < rounds; i += 1) {
    const count = scanCounts[i] ?? 0;
    if (count <= 0) {
      continue;
    }
    let boxId = boxes[i]?.id ?? '';
    const prefBarcode = boxes[i]?.internal_barcode;
    if (prefBarcode) {
      const open = await req.post(`${base}/boxes/open`, {
        headers: { ...adminHeaders, 'Content-Type': 'application/json' },
        data: { barcode: prefBarcode },
      });
      if (open.ok()) {
        boxId = String(((await open.json()) as { id: string }).id);
      } else {
        const created = await req.post(`${base}/boxes`, { headers: adminHeaders });
        if (!created.ok()) {
          throw new Error(`create inbound box: ${created.status()} ${await created.text()}`);
        }
        boxId = String(((await created.json()) as { id: string }).id);
      }
    } else {
      const created = await req.post(`${base}/boxes`, { headers: adminHeaders });
      if (!created.ok()) {
        throw new Error(`create inbound box: ${created.status()} ${await created.text()}`);
      }
      boxId = String(((await created.json()) as { id: string }).id);
    }
    for (let n = 0; n < count; n += 1) {
      const scan = await req.post(`${base}/boxes/${boxId}/scan`, {
        headers: { ...adminHeaders, 'Content-Type': 'application/json' },
        data: { barcode: productBarcode },
      });
      if (!scan.ok()) {
        throw new Error(`scan product into box: ${scan.status()} ${await scan.text()}`);
      }
    }
    const close = await req.post(`${base}/boxes/${boxId}/close`, {
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

/** FF modal: create box, open fill, manual qty, then close box. */
export async function ffInboundBoxAddManualQty(page: Page, quantity: number): Promise<void> {
  await Promise.all([
    waitForPostOk(page, INBOUND_API, (u) => u.endsWith('/boxes')),
    page.getByTestId('ff-inbound-add-to-box').click(),
  ]);
  await page.getByTestId('ff-inbound-box-open').last().getByRole('button', { name: 'Наполнить' }).click();
  await expect(page.getByTestId('ff-inbound-box-add-dialog')).toBeVisible();
  await page.getByTestId('ff-inbound-box-add-manual-edit').first().click();
  const qtyInput = page.getByTestId('ff-inbound-box-add-manual-qty').first();
  await qtyInput.fill(String(quantity));
  await Promise.all([
    waitForPutOk(page, INBOUND_API, (u) => u.includes('/boxes/') && u.includes('/lines/')),
    qtyInput.press('Enter'),
  ]);
  await Promise.all([
    waitForPostOk(page, INBOUND_API, (u) => u.includes('/close')),
    page.getByTestId('ff-inbound-box-add-close-box').click(),
  ]);
  await expect(page.getByTestId('ff-inbound-box-add-dialog')).toBeHidden();
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
