import { expect, type Page } from '@playwright/test';

import { loginAsSeller, openFulfillmentRegistration } from '../auth-flow';

export type RegressionPortal = 'ff' | 'seller';

function runSuffix(caseId: string): string {
  return `${caseId.toLowerCase()}-${Date.now()}-${Math.random().toString(16).slice(2, 8)}`;
}

async function registerFf(page: Page, caseId: string): Promise<string> {
  const suffix = runSuffix(caseId);
  const email = `${suffix}@example.com`;
  await page.goto('/');
  await openFulfillmentRegistration(page);
  await page.getByTestId('register-form').getByLabel('Организация').fill(`Regression ${caseId}`);
  await page.getByTestId('register-form').getByLabel('Email администратора').fill(email);
  await page.getByTestId('register-form').getByLabel('Пароль').fill('password123');
  await page.getByTestId('register-form').getByRole('button', { name: 'Создать аккаунт' }).click();
  await expect(page.getByTestId('app-frame')).toBeVisible();
  return email;
}

async function registerSeller(page: Page, caseId: string): Promise<void> {
  await registerFf(page, caseId);
  const token = await page.evaluate(() => localStorage.getItem('wms_token_ff'));
  expect(token).toBeTruthy();
  const suffix = runSuffix(`${caseId}-seller`);
  const email = `${suffix}@example.com`;
  const created = await page.request.post('/api/sellers/with-account', {
    headers: { Authorization: `Bearer ${token}` },
    data: {
      name: `Regression seller ${caseId}`,
      email,
      password: 'password123',
    },
  });
  expect(created.ok(), await created.text()).toBeTruthy();
  await loginAsSeller(page, email, 'password123', { firstTime: false });
}

export function resolveRegressionRoute(route: string): string {
  return route
    .replace(':poolId', process.env.REGRESS_POOL_ID ?? '00000000-0000-0000-0000-000000000001')
    .replace(':productId', process.env.REGRESS_PRODUCT_ID ?? '00000000-0000-0000-0000-000000000001')
    .replace(':requestId', process.env.REGRESS_INBOUND_ID ?? '00000000-0000-0000-0000-000000000001');
}

export async function openRegressionScreen(
  page: Page,
  portal: RegressionPortal,
  route: string,
  caseId: string,
): Promise<void> {
  if (portal === 'seller') {
    await registerSeller(page, caseId);
  } else {
    await registerFf(page, caseId);
  }
  await page.goto(resolveRegressionRoute(route));
  await expect(page.getByTestId('app-frame')).toBeVisible();
}

export async function expectShellNotBlank(page: Page): Promise<void> {
  await expect(page.getByTestId('app-frame')).toBeVisible();
  await expect(page.locator('main')).not.toHaveText('');
}

export async function installEmptyGet(page: Page, pattern: string, body: string): Promise<void> {
  await page.route(pattern, async (route) => {
    if (route.request().method() !== 'GET') {
      await route.continue();
      return;
    }
    await route.fulfill({ status: 200, contentType: 'application/json', body });
  });
}

export async function installFailedGet(
  page: Page,
  pattern: string,
  mode: '500' | 'abort',
): Promise<void> {
  await page.route(pattern, async (route) => {
    if (route.request().method() !== 'GET') {
      await route.continue();
      return;
    }
    if (mode === 'abort') {
      await new Promise((resolve) => setTimeout(resolve, 1_500));
      await route.abort('failed');
      return;
    }
    await route.fulfill({
      status: 500,
      contentType: 'application/json',
      body: JSON.stringify({ detail: 'Регрессионная проверка: API недоступен' }),
    });
  });
}
