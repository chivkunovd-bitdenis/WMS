import fs from "node:fs";

import {
  expect,
  test,
  type APIRequestContext,
  type Page,
  type TestInfo,
} from "@playwright/test";

type RouteName = "warehouse_sc" | "pvz";
type Seed = {
  emulator_admin_token: string;
  seller_key: string;
  seller_id: string;
  seller_token: string;
  location_code: string;
  login: { email: string; password: string };
  role_logins: Record<
    "operator" | "operator_no_packaging" | "seller",
    { email: string; password: string }
  >;
  orders: Record<
    RouteName,
    Array<{
      wb_order_id: number;
      wms_order_id: string;
      barcode: string;
      chrt_id: number;
      created_at_wb: string;
    }>
  >;
};
type Workspace = {
  supply: {
    id: string;
    wb_supply_id: string;
    packaging_task_id: string | null;
    barcode_asset: {
      id: string;
      preview_url: string | null;
      applied_at: string | null;
    } | null;
  };
  stage: string;
  orders: Array<{ id: string; wb_order_id: number; status: string }>;
  cargo_places: Array<{
    id: string;
    wb_trbx_id: string;
    qr_asset: {
      id: string;
      preview_url: string | null;
      applied_at: string | null;
    } | null;
  }>;
};

const seedPath = process.env.FBS_E2E_SEED_FILE;
if (!seedPath) throw new Error("FBS_E2E_SEED_FILE is required");
const seed = JSON.parse(fs.readFileSync(seedPath, "utf8")) as Seed;
const emulatorUrl =
  process.env.FBS_E2E_EMULATOR_URL ?? "http://127.0.0.1:28081";

async function shot(page: Page, testInfo: TestInfo, name: string) {
  const path = testInfo.outputPath(`${name}.png`);
  await page.screenshot({ path, fullPage: false });
  await testInfo.attach(name, { path, contentType: "image/png" });
}

async function login(
  page: Page,
  credentials: { email: string; password: string } = seed.login,
  entry = "/",
): Promise<string> {
  await page.goto(entry);
  await expect(page.getByTestId("login-form")).toBeVisible();
  await page
    .getByTestId("login-form")
    .getByLabel("Email")
    .fill(credentials.email);
  await page
    .getByTestId("login-form")
    .getByLabel("Пароль")
    .fill(credentials.password);
  const [response] = await Promise.all([
    page.waitForResponse(
      (item) => item.url().includes("/api/auth/login") && item.status() === 200,
    ),
    page
      .getByTestId("login-form")
      .getByRole("button", { name: "Войти" })
      .click(),
  ]);
  const body = (await response.json()) as { access_token: string };
  if (entry.startsWith("/seller")) {
    await expect(page.getByTestId("nav-seller-documents")).toBeVisible();
  } else {
    await expect(page.getByTestId("dashboard")).toBeVisible();
  }
  return body.access_token;
}

test("TC-FBS-U2U-001/002/036: seller and staff role boundaries are enforced in the real app", async ({
  page,
  request,
  baseURL,
}) => {
  if (!baseURL) throw new Error("Playwright baseURL is required");

  const operatorToken = await login(page, seed.role_logins.operator);
  await expect(page.getByTestId("nav-ff-fbs")).toBeVisible();
  await page.getByTestId("nav-ff-fbs").click();
  await expect(page.getByTestId("fbs-orders-screen")).toBeVisible();
  await expect(page.getByTestId("fbs-nav-stock-sync")).toHaveCount(0);
  const operatorWorklist = await request.get(
    `${baseURL}/api/operations/fbs-orders/worklist`,
    { headers: { Authorization: `Bearer ${operatorToken}` } },
  );
  expect(operatorWorklist.status()).toBe(200);
  const operatorAdminRoute = await request.get(
    `${baseURL}/api/operations/fbs-sellers/${seed.seller_id}/warehouses`,
    { headers: { Authorization: `Bearer ${operatorToken}` } },
  );
  expect(operatorAdminRoute.status()).toBe(403);

  await page.getByTestId("logout").click();
  await login(page, seed.role_logins.operator_no_packaging);
  await expect(page.getByTestId("nav-ff-fbs")).toHaveCount(0);
  await page.goto("/app/ff/fbs");
  await expect(page.getByTestId("ff-fbs-placeholder")).toContainText("Нет доступа");

  await page.getByTestId("logout").click();
  const sellerToken = await login(page, seed.role_logins.seller, "/seller/");
  await expect(page.getByTestId("nav-ff-fbs")).toHaveCount(0);
  const sellerWorklist = await request.get(
    `${baseURL}/api/operations/fbs-orders/worklist`,
    { headers: { Authorization: `Bearer ${sellerToken}` } },
  );
  expect(sellerWorklist.status()).toBe(403);
});

async function fetchWorkspace(
  request: APIRequestContext,
  baseURL: string,
  token: string,
  supplyId: string,
) {
  const response = await request.get(
    `${baseURL}/api/operations/fbs-supplies/${supplyId}/workspace`,
    {
      headers: { Authorization: `Bearer ${token}` },
    },
  );
  expect(response.ok(), await response.text()).toBeTruthy();
  return (await response.json()) as Workspace;
}

async function confirmCurrentPreview(page: Page) {
  const dialog = page.getByRole("dialog", { name: "Проверка перед печатью" });
  await expect(dialog).toBeVisible();
  const image = dialog.getByRole("img").first();
  await expect(image).toBeVisible();
  await expect
    .poll(() =>
      image.evaluate((node: HTMLImageElement) => ({
        width: node.naturalWidth,
        height: node.naturalHeight,
      })),
    )
    .toEqual(
      expect.objectContaining({
        width: expect.any(Number),
        height: expect.any(Number),
      }),
    );
  const size = await image.evaluate((node: HTMLImageElement) => ({
    width: node.naturalWidth,
    height: node.naturalHeight,
  }));
  expect(size.width).toBeGreaterThan(0);
  expect(size.height).toBeGreaterThan(0);
  const confirmButtons = dialog.getByRole("button", {
    name: "Подтвердить нанесение",
  });
  while ((await confirmButtons.count()) > 0) {
    const before = await confirmButtons.count();
    await confirmButtons.first().click();
    await expect(confirmButtons).toHaveCount(before - 1);
  }
  await dialog.getByRole("button", { name: "Закрыть" }).click();
  await expect(dialog).toBeHidden();
}

async function createSupply(page: Page, route: RouteName): Promise<Workspace> {
  const orders = seed.orders[route];
  expect(new Set(orders.map((order) => order.created_at_wb)).size).toBe(2);
  for (const order of orders) {
    const row = page.getByTestId(`fbs-order-${order.wms_order_id}`);
    await expect(row).toContainText(order.barcode);
    await row.getByRole("checkbox").click();
  }
  await page.getByRole("button", { name: "Сформировать поставку" }).click();
  if (route === "pvz") await page.getByLabel("Пункт выдачи").check();
  await expect(page.getByText("Можно создать поставку")).toBeVisible();
  const [response] = await Promise.all([
    page.waitForResponse(
      (item) =>
        item.url().includes("/api/operations/fbs-supplies/from-orders") &&
        item.status() === 201,
    ),
    page.getByTestId("fbs-create-submit").click(),
  ]);
  const workspace = (await response.json()) as Workspace;
  await expect(page.getByTestId("fbs-workspace")).toBeVisible();
  return workspace;
}

async function pickAndPack(page: Page, route: RouteName, testInfo: TestInfo) {
  const orders = seed.orders[route];
  await page.getByRole("button", { name: "Начать работу с поставкой" }).click();
  await page.getByLabel("Штрихкод ячейки").fill(seed.location_code);
  await page.getByRole("button", { name: "Подтвердить ячейку" }).click();
  await expect(
    page.getByText(new RegExp(`Ячейка ${seed.location_code} подтверждена`)),
  ).toBeVisible();
  for (const [index, order] of orders.entries()) {
    await page.getByLabel("Штрихкод товара").fill(order.barcode);
    const [pickResponse] = await Promise.all([
      page.waitForResponse(
        (item) =>
          item.url().includes("/pick/scan-product") && item.status() === 200,
      ),
      page.getByRole("button", { name: "Подобрать товар" }).click(),
    ]);
    const pickedWorkspace = (await pickResponse.json()) as {
      progress: { picked: number; total: number };
    };
    expect(pickedWorkspace.progress).toEqual(
      expect.objectContaining({ picked: index + 1, total: orders.length }),
    );
  }
  await shot(page, testInfo, `${route}-02-picked`);

  await page.getByRole("tab", { name: "Упаковка" }).click();
  await expect(page.getByTestId("ff-packaging-line").first()).toBeVisible();
  await expect(page.getByTestId("ff-packaging-pack-btn")).toBeEnabled();
  await expect(page.getByTestId("ff-packaging-complete")).toBeDisabled();
  await shot(page, testInfo, `${route}-03-packaging-layout`);
  await page.getByTestId("ff-packaging-pack-btn").click();
  const packagingAcknowledgement = page.getByTestId("ff-packaging-ack-all-packed");
  await expect(packagingAcknowledgement).toBeVisible();
  await expect(packagingAcknowledgement).toBeEnabled();
  await packagingAcknowledgement.check();
  await expect(page.getByTestId("ff-packaging-complete")).toBeEnabled();
  const [completeResponse] = await Promise.all([
    page.waitForResponse(
      (item) =>
        item.url().includes("/operations/packaging-tasks/") &&
        item.url().endsWith("/complete") &&
        item.status() === 200,
    ),
    page.getByTestId("ff-packaging-complete").click(),
  ]);
  const completedTask = (await completeResponse.json()) as { status: string };
  expect(completedTask.status).toBe("done");

  await page.getByRole("tab", { name: "Печать и маркировка" }).click();
  await page.getByRole("button", { name: "Получить все стикеры" }).click();
  await confirmCurrentPreview(page);
  await shot(page, testInfo, `${route}-04-order-sticker-applied`);
}

async function finishRoute(
  page: Page,
  request: APIRequestContext,
  baseURL: string,
  token: string,
  route: RouteName,
  supply: Workspace,
  testInfo: TestInfo,
) {
  await page.getByRole("tab", { name: "Упаковка в короба" }).click();
  let boxCreateCalls = 0;
  let boxAssignCalls = 0;
  let legacyCargoCalls = 0;
  const boxesApi = `/api/operations/fbs-supplies/${supply.supply.id}/boxes`;
  page.on("request", (item) => {
    const url = item.url();
    if (url.includes("/cargo-places")) legacyCargoCalls += 1;
    if (item.method() === "POST" && url.endsWith(boxesApi)) boxCreateCalls += 1;
    if (
      item.method() === "POST" &&
      url.includes(`${boxesApi}/`) &&
      url.endsWith("/orders")
    ) {
      boxAssignCalls += 1;
    }
  });

  const boxes = page.getByTestId("fbs-boxes");
  await expect(boxes).toBeVisible();
  await expect(page.getByText(/Грузомест/)).toHaveCount(0);
  await Promise.all([
    page.waitForResponse(
      (item) => item.url().endsWith(boxesApi) && item.request().method() === "POST" && item.status() === 201,
    ),
    page.getByRole("button", { name: "Добавить короб" }).click(),
  ]);
  await expect.poll(() => boxCreateCalls).toBe(1);
  await expect(boxes.getByText("Короб 1", { exact: true })).toBeVisible();

  await boxes.getByRole("button", { name: "Добавить товар" }).click();
  const addProducts = page.getByRole("dialog", { name: /Добавить товары в короб 1/ });
  await expect(addProducts).toBeVisible();
  const packedOrders = addProducts.getByRole("checkbox");
  await expect(packedOrders).toHaveCount(supply.orders.length);
  for (let index = 0; index < supply.orders.length; index += 1) {
    await packedOrders.nth(index).check();
  }
  await Promise.all([
    page.waitForResponse(
      (item) =>
        item.url().includes(`${boxesApi}/`) &&
        item.url().endsWith("/orders") &&
        item.request().method() === "POST" &&
        item.status() === 200,
    ),
    addProducts
      .getByRole("button", { name: `Добавить ${supply.orders.length} товара` })
      .click(),
  ]);
  await expect(addProducts).toBeHidden();
  await expect.poll(() => boxAssignCalls).toBe(1);
  await expect(boxes.getByText(/Заказ WB №/)).toHaveCount(supply.orders.length);
  await expect.poll(() => legacyCargoCalls).toBe(0);
  await shot(page, testInfo, `${route}-05-boxes`);

  let deliverBody: {
    idempotency_key: string;
    confirmed_preflight_version: string;
  } | null = null;
  page.on("request", (item) => {
    if (
      item
        .url()
        .includes(`/api/operations/fbs-supplies/${supply.supply.id}/deliver`)
    ) {
      deliverBody = item.postDataJSON() as typeof deliverBody;
    }
  });
  await page.getByRole("tab", { name: "QR поставки" }).click();
  await page.getByRole("button", { name: "Проверить готовность" }).click();
  await page
    .getByRole("button", { name: "Подтвердить передачу WB" })
    .click();
  const deliveryDialog = page.getByRole("dialog", {
    name: "Подтвердить передачу в WB?",
  });
  await expect(deliveryDialog).toBeVisible();
  expect(deliverBody).toBeNull();
  await Promise.all([
    page.waitForResponse(
      (item) =>
        item.url().includes(`/api/operations/fbs-supplies/${supply.supply.id}/deliver`) &&
        item.status() === 200,
    ),
    deliveryDialog.getByRole("button", { name: "Передать в WB" }).click(),
  ]);
  await expect(
    page.getByText("WB подтвердил передачу поставки в доставку."),
  ).toBeVisible();
  await shot(page, testInfo, `${route}-06-delivered`);

  const finalWorkspace = await fetchWorkspace(
    request,
    baseURL,
    token,
    supply.supply.id,
  );
  expect(finalWorkspace.stage).toBe("tracking");
  expect(finalWorkspace.supply.packaging_task_id).toBeTruthy();
  expect(deliverBody?.confirmed_preflight_version).toBeTruthy();
  expect(deliverBody?.idempotency_key).toBeTruthy();

  const repeated = await request.post(
    `${baseURL}/api/operations/fbs-supplies/${supply.supply.id}/deliver`,
    {
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      data: deliverBody,
    },
  );
  expect(repeated.ok(), await repeated.text()).toBeTruthy();

  if (route === "warehouse_sc") {
    const qrRetry = await request.post(
      `${baseURL}/api/operations/fbs-supplies/${supply.supply.id}/retry-supply-qr`,
      { headers: { Authorization: `Bearer ${token}` } },
    );
    expect(qrRetry.ok(), await qrRetry.text()).toBeTruthy();
    const retryWorkspace = (await qrRetry.json()) as Workspace;
    expect(retryWorkspace.supply.barcode_asset).toEqual(
      expect.objectContaining({
        id: finalWorkspace.supply.barcode_asset?.id,
        preview_url: expect.any(String),
      }),
    );
  }

  const emu = await request.get(
    `${emulatorUrl}/api/v3/supplies/${supply.supply.wb_supply_id}`,
    {
      headers: { Authorization: seed.seller_token },
    },
  );
  expect(emu.ok(), await emu.text()).toBeTruthy();
  const emuSupply = (await emu.json()) as {
    done: boolean;
    orders: number[];
    trbxIds: string[];
  };
  expect(emuSupply.done).toBeTruthy();
  expect(emuSupply.orders).toEqual(
    seed.orders[route].map((order) => order.wb_order_id),
  );
  expect(emuSupply.trbxIds.length).toBe(route === "pvz" ? 1 : 0);

  const adminStateResponse = await request.get(
    `${emulatorUrl}/__admin/state?seller=${seed.seller_key}`,
    { headers: { "X-Admin-Token": seed.emulator_admin_token } },
  );
  expect(adminStateResponse.ok(), await adminStateResponse.text()).toBeTruthy();
  const adminState = (await adminStateResponse.json()) as {
    supplies: Array<{
      id: string;
      seller: string;
      done: boolean;
      orders: number[];
      trbx: Array<{ id: string; orders: number[] }>;
      deliver_calls: number;
    }>;
  };
  const emuAudit = adminState.supplies.find(
    (item) => item.id === supply.supply.wb_supply_id,
  );
  expect(emuAudit).toEqual({
    id: supply.supply.wb_supply_id,
    seller: seed.seller_key,
    done: true,
    orders: seed.orders[route].map((order) => order.wb_order_id),
    trbx:
      route === "pvz"
        ? [
            {
              id: emuSupply.trbxIds[0],
              // Canonical PVZ flow keeps order membership at supply level;
              // physical cargo places are intentionally not order-bound.
              orders: [],
            },
          ]
        : [],
    deliver_calls: 1,
  });

  await expect(
    page.getByRole("button", { name: "Печать QR поставки" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Печать QR поставки" }).click();
  await confirmCurrentPreview(page);
  await shot(page, testInfo, `${route}-07-supply-qr`);

  return {
    route,
    finalWorkspace,
    emulator: emuSupply,
    emulatorAudit: emuAudit,
    deliver: deliverBody,
  };
}

// TC-FBS-U2U-007/012/023/024/026/029 — real browser -> WMS -> Postgres/Celery -> WB emulator, with no FBS route mocks.
test("TC-FBS-U2U-007/012/023/024/026/029: warehouse and PVZ operator flows use the real WB emulator", async ({
  page,
  request,
  baseURL,
}, testInfo) => {
  if (!baseURL) throw new Error("Playwright baseURL is required");
  const network: Array<{ method: string; url: string; status: number }> = [];
  page.on("response", (response) => {
    if (response.url().includes("/api/operations/fbs")) {
      network.push({
        method: response.request().method(),
        url: response.url(),
        status: response.status(),
      });
    }
  });

  const token = await login(page);
  await page.getByTestId("nav-ff-fbs").click();
  await expect(page.getByTestId("fbs-orders-screen")).toBeVisible();
  await shot(page, testInfo, "00-real-worklist");

  const evidence: Record<string, unknown> = {
    seed: { ...seed, login: { email: seed.login.email } },
  };
  for (const route of ["warehouse_sc", "pvz"] as const) {
    const supply = await createSupply(page, route);
    await shot(page, testInfo, `${route}-01-composition`);
    await pickAndPack(page, route, testInfo);
    evidence[route] = await finishRoute(
      page,
      request,
      baseURL,
      token,
      route,
      supply,
      testInfo,
    );
    await page.getByTestId("fbs-workspace").getByLabel("Закрыть").click();
    await page.getByRole("tab", { name: "Новые" }).click();
    await page.getByLabel("Заказ, артикул или штрихкод").fill("");
    await page.getByRole("button", { name: "Найти" }).click();
  }

  expect(network.length).toBeGreaterThan(20);
  await testInfo.attach("fbs-fullstack-evidence.json", {
    body: JSON.stringify({ ...evidence, network }, null, 2),
    contentType: "application/json",
  });
});
