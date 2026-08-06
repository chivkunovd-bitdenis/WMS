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
      image_url: string;
    }>
  >;
};
type Workspace = {
  supply: {
    id: string;
    wb_supply_id: string;
    delivery_type: RouteName;
    packaging_task_id: string | null;
    operator_finished_at: string | null;
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
  packing_boxes: Array<{
    id: string;
    box_number: number;
    internal_barcode: string;
    wb_trbx_id: string | null;
    items_count: number;
    orders: Array<{ id: string; wb_order_id: number; product_name: string }>;
    qr_asset: { id: string; preview_url: string | null; applied_at: string | null } | null;
  }>;
  unassigned_order_ids: string[];
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
  await expect(page.getByTestId("ff-fbs-placeholder")).toContainText(
    "Нет доступа",
  );

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
  await expect(page.getByTestId("fbs-workspace")).toContainText(
    "Основной склад фулфилмента",
  );
  await expect(page.getByTestId("fbs-workspace")).not.toContainText(
    "Operator FBS WH",
  );
  return workspace;
}

async function pickAndPack(page: Page, route: RouteName, testInfo: TestInfo) {
  const orders = seed.orders[route];
  let scannerCalls = 0;
  const watchScanner = (request: { url(): string }) => {
    if (request.url().includes("/pick/scan-")) scannerCalls += 1;
  };
  page.on("request", watchScanner);
  await page.getByRole("button", { name: "Начать работу с поставкой" }).click();
  await expect(page.getByRole("tab")).toHaveCount(4);
  await expect(page.getByRole("tab", { name: "Стикеры WB" })).toHaveCount(0);
  await expect(page.getByRole("tab", { name: "Подготовка к сдаче" })).toHaveCount(0);
  for (const [index, order] of orders.entries()) {
    const row = page.getByTestId(`fbs-manual-pick-${order.wms_order_id}`);
    await row.getByLabel(`Ячейка для заказа WB №${order.wb_order_id}`).click();
    await page.getByRole("option", { name: new RegExp(seed.location_code) }).click();
    const [pickResponse] = await Promise.all([
      page.waitForResponse(
        (item) =>
          item.url().includes("/pick/confirm-product") && item.status() === 200,
      ),
      row.getByRole("button", { name: "Снять с ячейки" }).click(),
    ]);
    const pickedWorkspace = (await pickResponse.json()) as {
      progress: { picked: number; total: number };
    };
    expect(pickedWorkspace.progress).toEqual(
      expect.objectContaining({ picked: index + 1, total: orders.length }),
    );
  }
  page.off("request", watchScanner);
  expect(scannerCalls).toBe(0);
  await shot(page, testInfo, `${route}-02-picked`);

  await page.getByRole("tab", { name: "Упаковка и маркировка" }).click();
  const compact = page.getByTestId("ff-packaging-lines-compact");
  await expect(compact).toBeVisible();
  const name = page.getByTestId("ff-packaging-compact-product-name").first();
  const box = await name.boundingBox();
  expect(box?.width ?? 0).toBeGreaterThan(180);
  expect(box?.height ?? 999).toBeLessThan(100);
  expect(
    await compact.evaluate((node) => node.scrollWidth <= node.clientWidth + 1),
  ).toBeTruthy();
  await expect(page.getByTestId("ff-packaging-complete")).toBeDisabled();
  await shot(page, testInfo, `${route}-03-packaging-layout`);
  await page.getByTestId("ff-packaging-pack-btn").click();
  await expect(page.getByTestId("ff-packaging-complete")).toBeEnabled();
  await expect(page.getByTestId("ff-packaging-ack-all-packed")).toHaveCount(0);
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

  const boxesPanel = page.getByTestId("fbs-packing-boxes");
  await boxesPanel.getByLabel("Количество коробов").fill("2");
  await Promise.all([
    page.waitForResponse((item) => item.url().endsWith("/packing-boxes") && item.request().method() === "POST" && item.status() === 201),
    page.getByTestId("fbs-boxes-create").click(),
  ]);
  const putFirst = async () => {
    await Promise.all([
      page.waitForResponse((item) => item.url().includes("/packing-boxes/") && item.url().endsWith("/orders") && item.request().method() === "PUT" && item.status() === 200),
      boxesPanel.getByRole("button", { name: "Положить в короб" }).first().click(),
    ]);
  };
  await putFirst();
  await Promise.all([
    page.waitForResponse((item) => item.url().includes("/packing-boxes/") && item.url().endsWith("/orders") && item.request().method() === "DELETE" && item.status() === 200),
    page.getByTestId("fbs-boxes-table").getByRole("button", { name: "Убрать" }).click(),
  ]);
  await putFirst();
  await boxesPanel.getByRole("combobox").first().click();
  await page.getByRole("option", { name: "Короб 2" }).click();
  await putFirst();
  await expect(boxesPanel.getByText("Все упакованные товары распределены по коробам.")).toBeVisible();
  await page
    .getByRole("button", { name: "Получить и распечатать стикеры" })
    .click();
  await confirmCurrentPreview(page);
  await shot(page, testInfo, `${route}-05-order-sticker-applied`);
}

async function finishRoute(
  page: Page,
  request: APIRequestContext,
  baseURL: string,
  token: string,
  route: RouteName,
  supply: Workspace,
) {
  await expect(page.getByRole("tab")).toHaveCount(4);
  const packedWorkspace = await fetchWorkspace(request, baseURL, token, supply.supply.id);
  expect(packedWorkspace.packing_boxes).toHaveLength(2);
  expect(packedWorkspace.unassigned_order_ids).toEqual([]);

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
  await page.getByRole("tab", { name: "Сдача в WB", exact: true }).click();
  await page.getByTestId("fbs-delivery-prepare").click();
  const deliveryDialog = page.getByRole("dialog", {
    name: "Зафиксировать состав поставки?",
  });
  await expect(deliveryDialog).toBeVisible();
  expect(deliverBody).toBeNull();
  await Promise.all([
    page.waitForResponse(
      (item) =>
        item
          .url()
          .includes(
            `/api/operations/fbs-supplies/${supply.supply.id}/deliver`,
          ) && item.status() === 200,
    ),
    deliveryDialog.getByRole("button", { name: "Зафиксировать в WB" }).click(),
  ]);
  await expect(page.getByText("Статусы WB", { exact: true })).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "Обновить статусы" }),
  ).toHaveCount(0);
  if (route === "warehouse_sc") {
    await page.getByRole("button", { name: "Печать QR поставки" }).click();
  } else {
    await page.getByRole("button", { name: "Печать всех QR коробов" }).click();
  }
  await confirmCurrentPreview(page);
  await expect(page.getByTestId("fbs-local-finish")).toBeEnabled();
  await Promise.all([
    page.waitForResponse((item) => item.url().endsWith(`/api/operations/fbs-supplies/${supply.supply.id}/finish`) && item.status() === 200),
    page.getByTestId("fbs-local-finish").click(),
  ]);
  await expect(page.getByText(/Работа с поставкой завершена/).last()).toBeVisible();

  const finalWorkspace = await fetchWorkspace(
    request,
    baseURL,
    token,
    supply.supply.id,
  );
  expect(finalWorkspace.stage).toBe("tracking");
  expect(finalWorkspace.supply.operator_finished_at).toBeTruthy();
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
  expect(emuSupply.trbxIds.length).toBe(route === "pvz" ? 2 : 0);

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
        ? emuSupply.trbxIds.map((id) => ({ id, orders: [] }))
        : [],
    deliver_calls: 1,
  });

  return {
    route,
    finalWorkspace,
    emulator: emuSupply,
    emulatorAudit: emuAudit,
    deliver: deliverBody,
  };
}

// TC-S17-023/025/026 — real browser -> WMS -> Postgres/Celery -> WB emulator, with no FBS route mocks.
test("TC-S17-023/025/026: warehouse and PVZ operator flows use the real WB emulator", async ({
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
  await expect(page.getByText("Подробнее", { exact: true })).toHaveCount(0);
  await expect(
    page.getByRole("columnheader", { name: "Селлер" }),
  ).toBeVisible();
  await expect(
    page.getByRole("columnheader", { name: "Маршрут сдачи" }),
  ).toBeVisible();
  const worklist = page.getByTestId("fbs-worklist-table");
  await expect(
    worklist.getByRole("columnheader", { name: "Ячейка и остаток" }),
  ).toHaveCount(0);
  await expect(
    worklist.getByRole("columnheader", { name: "Статус" }),
  ).toHaveCount(0);
  await expect(worklist.getByText("Маркировка:", { exact: true })).toHaveCount(0);
  const imageOrder = seed.orders.warehouse_sc[0];
  const thumbnailRoot = page.getByTestId(
    `fbs-product-photo-${imageOrder.wms_order_id}`,
  );
  const thumbnail = thumbnailRoot.locator("img");
  await expect(thumbnail).toBeVisible();
  await expect(thumbnail).toHaveAttribute("src", imageOrder.image_url);
  await expect
    .poll(() =>
      thumbnail.evaluate((node: HTMLImageElement) => ({
        width: node.naturalWidth,
        height: node.naturalHeight,
      })),
    )
    .toEqual({ width: 360, height: 480 });
  await thumbnailRoot.hover();
  const enlarged = page.getByTestId("product-photo-enlarged");
  await expect(enlarged).toBeVisible();
  await expect(enlarged).toHaveAttribute("src", imageOrder.image_url);
  await page.getByRole("heading", { name: "Заказы FBS" }).hover();
  await expect(enlarged).toHaveCount(0);
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
    );
    await page.getByTestId("fbs-workspace").getByLabel("Закрыть").click();
    await page.getByRole("tab", { name: "В доставке" }).click();
    const deliveredRow = page.getByTestId(
      `fbs-order-${seed.orders[route][0].wms_order_id}`,
    );
    await expect(deliveredRow).toHaveAttribute("role", "button");
    await expect(deliveredRow).toHaveAttribute("tabindex", "0");
    await deliveredRow.click();
    await expect(page.getByTestId("fbs-workspace")).toBeVisible();
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
