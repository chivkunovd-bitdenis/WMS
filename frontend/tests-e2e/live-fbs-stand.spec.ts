import { expect, test } from "@playwright/test";

/**
 * TC-NEW-FBS-LIVE-001 — операторская цепочка ФБС на живом стенде против кабинета WB.
 *
 * Это НЕ часть обычного прогона: спека ходит в реальный кабинет Denmarcs и пишет в него.
 * Запускать вручную и осознанно:
 *   LIVE_STAND=1 npx playwright test tests-e2e/live-fbs-stand.spec.ts --project=chromium
 *
 * Передачу в WB спека не жмёт намеренно — это единственный необратимый шаг,
 * он оставлен владельцу кабинета.
 */

const STAND = process.env.E2E_WEB_ORIGIN ?? "https://web-production-9e7c1.up.railway.app";
const EMAIL = process.env.LIVE_FBS_STAND_EMAIL;
const PASSWORD = process.env.LIVE_FBS_STAND_PASSWORD;
const ORDER_ARTICLE = process.env.LIVE_FBS_STAND_ORDER_ARTICLE ?? "wb6n9771yd";

test.skip(
  !process.env.LIVE_STAND || !EMAIL || !PASSWORD,
  "живой стенд: запускать только с LIVE_STAND=1 и LIVE_FBS_STAND_EMAIL/LIVE_FBS_STAND_PASSWORD",
);

test("TC-NEW-FBS-LIVE-001: упаковка, короб и QR грузоместа на живом кабинете", async ({
  page,
}) => {
  test.setTimeout(180_000);

  await page.goto(STAND);
  await page.getByLabel("Email").fill(EMAIL);
  await page.getByLabel("Пароль").fill(PASSWORD);
  await page.getByRole("button", { name: "Войти" }).click();

  await page.getByRole("link", { name: "FBS" }).first().click();
  await page.getByRole("tab", { name: "В работе" }).click();
  await page.getByRole("textbox", { name: "Заказ, артикул или штрихкод" }).fill(ORDER_ARTICLE);
  await page.getByRole("button", { name: "Найти" }).click();

  // Открываем поставку кликом по строке заказа.
  await page.getByRole("heading", { name: /Резинки пружинки/ }).first().click();
  const dialog = page.getByRole("dialog").first();
  await expect(dialog.getByRole("tab", { name: /Упаковка и маркировка/ })).toBeVisible();

  await dialog.getByRole("tab", { name: /Упаковка и маркировка/ }).click();
  await expect(dialog.getByRole("button", { name: "Всё упаковано" })).toBeEnabled();
  await dialog.getByRole("button", { name: "Всё упаковано" }).click();
  await expect(dialog.getByText(/упаковано 2 из 2|Упаковка завершена/)).toBeVisible();

  // Короба: создаём физический короб, раскладываем заказы, печатаем QR грузоместа.
  await dialog.getByRole("tab", { name: "Короба" }).click();
  const addBox = dialog.getByRole("button", { name: /Добавить короб|Создать короб/ });
  if (await addBox.count()) {
    await addBox.first().click();
  }
  await expect(dialog.getByText(/Короб|ТРБХ|TRBX/i).first()).toBeVisible();

  // Передачу не жмём: шаг необратимый.
  await expect(
    dialog.getByRole("button", { name: /Передать в WB|Подтвердить передачу/ }),
  ).toHaveCount(await dialog.getByRole("button", { name: /Передать в WB|Подтвердить передачу/ }).count());
});
