import { expect, test } from '@playwright/test';

import {
  expectShellNotBlank,
  installEmptyGet,
  installFailedGet,
  openRegressionScreen,
  resolveRegressionRoute,
} from './helpers';

const screen = {
  "id": "S-15",
  "slug": "pending-marking",
  "name": "Ожидают маркировки",
  "portal": "ff",
  "route": "/app/ff/packaging/pending-marking",
  "heading": "Осталось промаркировать",
  "action": "Выйти",
  "primary": "0 строк",
  "api": "**/api/operations/packaging-tasks/pending-marking*",
  "empty": "Все требуемые КМ напечатаны"
} as const;
const safeRoute = "/app/ff/dashboard";

test.describe('S-15 — Ожидают маркировки', () => {
  test('TC-S15-P01 opens the live screen and shows its heading', async ({ page }) => {
    await openRegressionScreen(page, screen.portal, screen.route, 'TC-S15-P01');
    await expect(page.getByRole('heading', { name: screen.heading, exact: false }).first()).toBeVisible();
  });

  test('TC-S15-P02 exposes the significant operator element', async ({ page }) => {
    await openRegressionScreen(page, screen.portal, screen.route, 'TC-S15-P02');
    await expect(page.getByText(screen.primary, { exact: false }).first()).toBeVisible();
  });

  test('TC-S15-N01 renders a human empty state', async ({ page }) => {
    await installEmptyGet(page, screen.api, '[]');
    await openRegressionScreen(page, screen.portal, screen.route, 'TC-S15-N01');
    await expectShellNotBlank(page);
    await expect(page.getByText(screen.empty, { exact: false }).first()).toBeVisible();
  });

  test('TC-S15-N02 does not expose the screen without authentication', async ({ page }) => {
    await page.goto(resolveRegressionRoute(screen.route));
    await expect(page.getByTestId('login-form')).toBeVisible();
    await expect(page.getByRole('heading', { name: screen.heading, exact: false })).toHaveCount(0);
  });

  test('TC-S15-R01 ignores a fast double action or stays idempotent', async ({ page }) => {
    let writes = 0;
    page.on('request', (request) => {
      if (['POST', 'PUT', 'PATCH', 'DELETE'].includes(request.method())) writes += 1;
    });
    await openRegressionScreen(page, screen.portal, screen.route, 'TC-S15-R01');
    writes = 0;
    const action = page.getByRole('button', { name: screen.action, exact: false }).first();
    await expect(action).toBeVisible();
    await Promise.allSettled([action.click({ timeout: 3_000 }), action.click({ timeout: 3_000 })]);
    expect(writes).toBeLessThanOrEqual(1);
  });

  test('TC-S15-R02 survives leaving while the list response is delayed', async ({ page }) => {
    await page.route(screen.api, async (route) => {
      if (route.request().method() === 'GET') await new Promise((resolve) => setTimeout(resolve, 2_000));
      await route.continue();
    });
    await openRegressionScreen(page, screen.portal, screen.route, 'TC-S15-R02');
    await page.goto(safeRoute);
    await expectShellNotBlank(page);
  });

  test('TC-S15-F01 keeps the shell and explains a 500 response', async ({ page }) => {
    await installFailedGet(page, screen.api, '500');
    await openRegressionScreen(page, screen.portal, screen.route, 'TC-S15-F01');
    await expectShellNotBlank(page);
    await expect(page.locator('main')).toContainText(/не удалось|ошиб|повтор|недоступ|не найден/i);
  });

  test('TC-S15-F02 keeps the screen stable after a delayed abort', async ({ page }) => {
    await installFailedGet(page, screen.api, 'abort');
    await openRegressionScreen(page, screen.portal, screen.route, 'TC-S15-F02');
    await expectShellNotBlank(page);
    await expect(page.getByRole('heading', { name: screen.heading, exact: false }).first()).toBeVisible();
  });
});
