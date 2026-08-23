import { expect, test } from '@playwright/test';

import { openFulfillmentRegistration } from './auth-flow';
import { waitForGetOk, waitForPostOk } from './api-waits';

type ScreenUnderReview = {
  tcId: string;
  path: string;
  screenTestId: string;
};

const screensUnderReview: ScreenUnderReview[] = [
  { tcId: 'S-03-TC-001', path: '/app/ff/fbs', screenTestId: 'fbs-orders-screen' },
  { tcId: 'S-14-TC-001', path: '/app/ff/packaging', screenTestId: 'ff-packaging-page' },
  { tcId: 'S-15-TC-001', path: '/app/ff/packaging/pending-marking', screenTestId: 'ff-pending-marking-page' },
];

async function registerFulfillmentOperator(page: import('@playwright/test').Page): Promise<void> {
  const email = `e2e-wb-marking-stand-${Date.now()}@example.com`;

  await page.goto('/');
  await expect(page.getByTestId('login-form')).toBeVisible();
  await openFulfillmentRegistration(page);
  await page.getByTestId('register-form').getByLabel('Организация').fill('E2E WB Marking Stand');
  await page.getByTestId('register-form').getByLabel('Email администратора').fill(email);
  await page.getByTestId('register-form').getByLabel('Пароль').fill('password123');
  await Promise.all([
    waitForPostOk(page, '/api/auth/register'),
    waitForGetOk(page, '/api/auth/me'),
    page.getByTestId('register-form').getByRole('button', { name: 'Создать аккаунт' }).click(),
  ]);
  await expect(page.getByTestId('dashboard')).toBeVisible();
}

// S-03-TC-001 / S-14-TC-001 / S-15-TC-001 — local Playwright stand renders each unchanged FBS screen.
test('WB marking review stand opens the unchanged FBS screens', async ({ page }) => {
  test.setTimeout(120_000);
  await registerFulfillmentOperator(page);

  for (const screen of screensUnderReview) {
    await page.goto(screen.path);
    await expect(page).toHaveURL(new RegExp(`${screen.path}$`));
    await expect(page.getByTestId(screen.screenTestId)).toBeVisible();
  }
});
