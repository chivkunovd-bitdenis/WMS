import { test, expect } from '@playwright/test';

test('app loads and root is visible', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByTestId('app-root')).toBeVisible();
});

