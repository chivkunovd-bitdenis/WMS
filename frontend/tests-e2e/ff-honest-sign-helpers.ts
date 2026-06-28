import { expect, type Page } from '@playwright/test'

/** Open MUI seller Autocomplete and pick seller by id (Honest Sign screens). */
export async function selectMarkingSeller(
  page: Page,
  testIdPrefix: string,
  sellerId: string,
): Promise<void> {
  const picker = page.getByTestId(`${testIdPrefix}-seller-picker`)
  await expect(picker).toBeVisible({ timeout: 30_000 })
  await picker.click()
  const option = page.getByTestId(`${testIdPrefix}-seller-${sellerId}`)
  await expect(option).toBeVisible()
  await option.click()
}

export async function selectHonestSignSeller(page: Page, sellerId: string): Promise<void> {
  await selectMarkingSeller(page, 'ff-honest-sign', sellerId)
}
