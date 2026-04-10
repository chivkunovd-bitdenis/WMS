import { test, expect } from '@playwright/test';

test('register then see dashboard', async ({ page }) => {
  const slug = `ff-e2e-${Date.now()}`;
  const email = `e2e-${Date.now()}@example.com`;

  await page.goto('/');
  await expect(page.getByTestId('app-root')).toBeVisible();

  await page.getByTestId('register-form').getByLabel('Организация').fill('E2E FF');
  await page.getByTestId('register-slug').fill(slug);
  await page.getByTestId('register-form').getByLabel('Email админа').fill(email);
  await page.getByTestId('register-form').getByLabel('Пароль').fill('password123');
  await page.getByTestId('register-form').getByRole('button', { name: 'Создать аккаунт' }).click();

  await expect(page.getByTestId('dashboard')).toBeVisible();
  await expect(page.getByTestId('user-email')).toHaveText(email);
  await expect(page.getByTestId('org-name')).toHaveText('E2E FF');
});
