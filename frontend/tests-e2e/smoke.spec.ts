import { test, expect } from '@playwright/test';

// TC-S15-001 — публичный экран: корень приложения и форма входа по умолчанию.
test('app loads and root is visible', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByTestId('app-root')).toBeVisible();
  await expect(page.getByTestId('login-form')).toBeVisible();
  await expect(page.getByTestId('go-to-register')).toBeVisible();
  await expect(page.getByTestId('register-form')).toHaveCount(0);
});

