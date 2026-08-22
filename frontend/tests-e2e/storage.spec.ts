import { test, expect } from '@playwright/test'

test('S-11-TC-001 administrator opens storage for previous month', async ({ page }) => {
  await page.goto('/app/ff/inventory')
  await expect(page.getByTestId('ff-storage-page')).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Хранение' })).toBeVisible()
  await expect(page.getByTestId('storage-month')).toHaveValue('2026-07')
})

test('S-11-TC-005 operator can enter missing dimensions and unblock fixation', async ({ page }) => {
  await page.goto('/app/ff/inventory')
  await page.getByRole('button', { name: 'Внести обмер' }).click()
  await page.getByRole('button', { name: 'Сохранить' }).click()
  await expect(page.getByText('Рассчитано')).toBeVisible()
})
