import { expect, type Page } from '@playwright/test'

/** Open MUI seller Autocomplete and pick seller by id (Honest Sign screens). */
export async function selectHonestSignSeller(page: Page, sellerId: string): Promise<void> {
  await page.getByTestId('ff-honest-sign-seller-picker').click()
  const option = page.getByTestId(`ff-honest-sign-seller-${sellerId}`)
  await expect(option).toBeVisible()
  await option.click()
}
