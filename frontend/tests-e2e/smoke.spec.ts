import { test, expect } from '@playwright/test';

test('app loads and root is visible', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByTestId('app-root')).toBeVisible();
  await expect(page.getByTestId('register-form')).toBeVisible();
  await expect(page.getByTestId('login-form')).toBeVisible();
});

